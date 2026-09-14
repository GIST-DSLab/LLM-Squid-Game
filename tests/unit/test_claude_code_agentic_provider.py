"""ClaudeCodeAgenticProvider: argv, --agents/--settings JSON, stream split (no CLI)."""

import json
import os

import pytest

from squid_game.providers.base import ToolContext, AgenticCompletionResult
from squid_game.providers.claude_code_agentic import (
    build_agentic_command, build_agents_json, build_hook_settings_json,
    parse_agentic_stream,
)

CTX = ToolContext(
    slots_json={"names": ["clue-1", "clue-2"], "alive": ["clue-1"],
                "killed": [{"round": 1, "slot": "clue-2"}], "spawn_cap_per_round": 1},
    subagent_prompts={"clue-1": "You are clue-1.\nEXAMPLE: red circle 1 → A",
                      "clue-2": "You are clue-2.\nYou hold no example this round."},
)


def test_agents_json_defines_every_slot_with_identical_description_and_no_tools():
    agents = json.loads(build_agents_json(CTX, model="claude-opus-5"))
    assert set(agents) == {"clue-1", "clue-2"}
    for name, spec in agents.items():
        assert spec["description"] == "Holds one of this round's examples."
        assert spec["prompt"] == CTX.subagent_prompts[name]
        assert spec["tools"] == []
        assert spec["model"] == "claude-opus-5"


def test_hook_settings_json_wires_the_budget_script_on_the_agent_matcher():
    settings = json.loads(build_hook_settings_json(CTX))
    pre = settings["hooks"]["PreToolUse"]
    assert pre[0]["matcher"] == "Agent"
    cmd = pre[0]["hooks"][0]["command"]
    assert cmd.endswith("subagent_budget.py")
    assert pre[0]["hooks"][0]["type"] == "command"


def test_the_default_hook_script_is_the_file_task_2_landed():
    assert os.path.isabs(CTX.hook_script)
    assert os.path.exists(CTX.hook_script), CTX.hook_script
    assert CTX.hook_script.endswith(
        os.path.join("squid_game", "harness", "hooks", "subagent_budget.py")
    )


def test_command_enables_only_the_agent_tool_and_forwards_subagent_text():
    cmd = build_agentic_command(
        claude_bin="claude", model="claude-opus-5", system_prompt="SYS",
        effort="medium", tool_context=CTX, call_dir="/tmp/x",
    )
    assert cmd[:2] == ["claude", "-p"]
    assert "--tools" in cmd and cmd[cmd.index("--tools") + 1] == "Agent"
    assert "--max-turns" in cmd and cmd[cmd.index("--max-turns") + 1] == "12"
    assert "--agents" in cmd and "--settings" in cmd
    assert "--forward-subagent-text" in cmd
    assert "--no-session-persistence" in cmd
    assert "--setting-sources" in cmd and cmd[cmd.index("--setting-sources") + 1] == ""
    assert "--system-prompt" in cmd and cmd[cmd.index("--system-prompt") + 1] == "SYS"
    assert cmd[cmd.index("--effort") + 1] == "medium"
    assert "--dangerously-skip-permissions" not in cmd


# A recorded-shape fixture: main thread spawns clue-1 (allowed), tries clue-2
# (denied by the hook), then answers. Subagent events carry parent_tool_use_id.
STREAM = "\n".join(json.dumps(e) for e in [
    {"type": "system", "subtype": "init"},
    {"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "I need the examples."},
        {"type": "tool_use", "id": "tu_1", "name": "Agent",
         "input": {"subagent_type": "clue-1", "prompt": "your example?", "description": "ask"}}]}},
    {"type": "assistant", "parent_tool_use_id": "tu_1", "message": {"content": [
        {"type": "thinking", "thinking": "sub thinking"},
        {"type": "text", "text": "red circle 1 → A"}]},
     "usage": {"output_tokens": 30, "output_tokens_details": {"thinking_tokens": 12}}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": "red circle 1 → A"}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tu_2", "name": "Agent",
         "input": {"subagent_type": "clue-2", "prompt": "your example?", "description": "ask"}}]}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu_2", "is_error": True,
         "content": "clue-2 was terminated after round 1 and cannot be called."}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "thinking", "thinking": "So the rule is ..."},
        {"type": "text", "text": "RULE: if color == \"red\": A else: B\nACTION: A"}]}},
    {"type": "result", "subtype": "success", "is_error": False,
     "result": "RULE: if color == \"red\": A else: B\nACTION: A",
     "usage": {"input_tokens": 500, "output_tokens": 120,
               "output_tokens_details": {"thinking_tokens": 40}}},
])


def test_parse_separates_main_thread_from_subagents():
    res = parse_agentic_stream(STREAM)
    assert isinstance(res, AgenticCompletionResult)
    assert res.text.startswith("RULE:")
    # Main-thread thinking text excludes the subagent's block.
    assert "sub thinking" not in (res.thinking_text or "")
    assert "I need the examples." in res.thinking_text
    assert res.thinking_tokens == 40
    assert [u.slot for u in res.subagent_usage] == ["clue-1"]
    assert res.subagent_usage[0].thinking_tokens == 12
    assert res.subagent_usage[0].thinking_text == "sub thinking"
    # Spawn attempts, allowed and denied, are both recorded from the stream.
    assert [(s["slot"], s["allowed"]) for s in res.spawn_log] == [("clue-1", True), ("clue-2", False)]
    assert res.spawn_log[1]["reason"].startswith("clue-2 was terminated")


def test_the_main_thread_text_excludes_what_a_subagent_said():
    res = parse_agentic_stream(STREAM)
    assert "red circle 1" not in res.text


def test_parse_without_result_event_raises():
    from squid_game.providers.claude_code import ClaudeCodeError
    with pytest.raises(ClaudeCodeError):
        parse_agentic_stream('{"type":"assistant","message":{"content":[]}}')


def test_the_hook_log_wins_over_the_stream_when_the_hook_wrote_one(tmp_path):
    from squid_game.providers.claude_code_agentic import _merge_hook_log

    res = parse_agentic_stream(STREAM)
    log = tmp_path / "hook.log"
    log.write_text(
        json.dumps({"tool_name": "Agent", "slot": "clue-2", "decision": "deny",
                    "reason": "clue-2 was terminated after round 1 and cannot be called.",
                    "agent_id": None}) + "\n",
        encoding="utf-8",
    )
    merged = _merge_hook_log(res, str(log))
    assert [(s["slot"], s["allowed"]) for s in merged.spawn_log] == [("clue-2", False)]
    # Everything else survives the replacement.
    assert merged.text == res.text
    assert merged.subagent_usage == res.subagent_usage


def test_an_absent_hook_log_leaves_the_stream_derived_spawn_log(tmp_path):
    from squid_game.providers.claude_code_agentic import _merge_hook_log

    res = parse_agentic_stream(STREAM)
    merged = _merge_hook_log(res, str(tmp_path / "nope.log"))
    assert merged.spawn_log == res.spawn_log


def test_factory_registers_the_agentic_name():
    from squid_game.providers.factory import available_providers
    assert "claude_code_agentic" in available_providers()
