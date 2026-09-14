"""ClaudeCodeAgenticProvider: argv, --agents/--settings JSON, stream split (no CLI)."""

import json
import os
import shlex

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
    # shlex.split, not endswith: the path is quoted (see the spaces test below).
    assert shlex.split(cmd)[-1].endswith("subagent_budget.py")
    assert pre[0]["hooks"][0]["type"] == "command"


def test_the_hook_command_survives_a_path_with_spaces():
    """The hook path is shell-parsed by the CLI, and this repo lives under
    ".../Mobile Documents/...". Unquoted, the shell runs "python3 /Users/x/Mobile"
    and the hook never fires -- which fails OPEN: every spawn would be allowed."""
    ctx = ToolContext(
        slots_json={}, subagent_prompts={},
        hook_script="/tmp/dir with space/subagent_budget.py",
    )
    settings = json.loads(build_hook_settings_json(ctx))
    cmd = settings["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert cmd == "python3 '/tmp/dir with space/subagent_budget.py'"
    assert shlex.split(cmd) == ["python3", "/tmp/dir with space/subagent_budget.py"]


def test_the_default_hook_command_is_two_tokens_on_this_checkout():
    cmd = json.loads(build_hook_settings_json(CTX))["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    argv = shlex.split(cmd)
    assert argv == ["python3", CTX.hook_script], argv


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


SPLIT_USAGE_STREAM = "\n".join(json.dumps(e) for e in [
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "tu_1", "name": "Agent",
         "input": {"subagent_type": "clue-1", "prompt": "?", "description": "ask"}}]}},
    {"type": "assistant", "parent_tool_use_id": "tu_1", "message": {"content": [
        {"type": "thinking", "thinking": "first half"}]},
     "usage": {"output_tokens": 30, "output_tokens_details": {"thinking_tokens": 12}}},
    {"type": "assistant", "parent_tool_use_id": "tu_1", "message": {"content": [
        {"type": "thinking", "thinking": "second half"},
        {"type": "text", "text": "red circle 1 -> A"}]},
     "usage": {"output_tokens": 7, "output_tokens_details": {"thinking_tokens": 5}}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": "tu_1", "content": "red circle 1 -> A"}]}},
    {"type": "result", "subtype": "success", "is_error": False, "result": "ACTION: A",
     "usage": {"input_tokens": 10, "output_tokens": 20,
               "output_tokens_details": {"thinking_tokens": 9}}},
])


def test_a_slot_emitting_several_usage_events_is_summed_not_overwritten():
    """Per-slot thinking tokens are a measured variable: last-wins would
    under-report a slot that streamed its usage over several events."""
    res = parse_agentic_stream(SPLIT_USAGE_STREAM)
    assert [u.slot for u in res.subagent_usage] == ["clue-1"]
    usage = res.subagent_usage[0]
    assert usage.thinking_tokens == 17          # 12 + 5, not 5
    assert usage.output_tokens == 37            # 30 + 7, not 7
    assert usage.thinking_text == "first half\nsecond half"
    # The main thread keeps only its own usage.
    assert res.thinking_tokens == 9 and res.output_tokens == 20


def test_parse_without_result_event_raises():
    from squid_game.providers.claude_code import ClaudeCodeError
    with pytest.raises(ClaudeCodeError):
        parse_agentic_stream('{"type":"assistant","message":{"content":[]}}')


def test_the_hook_log_wins_over_the_stream_when_the_hook_wrote_one(tmp_path):
    # The hook log is preferred because it records EVERY PreToolUse decision;
    # the stream only shows the attempts the CLI surfaced as tool_result blocks.
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


# ---------------------------------------------------------------------------
# The recorded stream (claude-code 2.1.270, 2026-09-14)
# ---------------------------------------------------------------------------
#
# Captured by running the real CLI through build_agentic_command() with the
# two-slot round scripts/dev/agentcli_selftest.py builds: clue-1 killed at
# round 1, clue-2 alive and holding the example. Trimmed to the events the
# parser reads (the init/rate-limit/task-notification frames and a thinking
# signature blob are dropped); every field below is the CLI's own.
#
# It is here because the hand-written STREAM above was wrong in the one way
# that mattered: it puts a subagent's usage at the TOP LEVEL of the event.
# The CLI puts it at message.usage, so the provider recorded every subagent
# as zero tokens until 2026-09-14. Note also that the real subagent emits no
# thinking block at all, and that the event names its own slot in a
# top-level "subagent_type" field.
_TU_DEAD = "toolu_01KDyCesFg5KM5aAbMrwpSuX"
_TU_ALIVE = "toolu_01EyTEKeN3uSWELvwFR9t9iS"

RECORDED_EVENTS = [
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": _TU_DEAD, "name": "Agent",
         "input": {"description": "Get example from clue-1",
                   "prompt": "Please share your example for this round.",
                   "subagent_type": "clue-1", "run_in_background": False}}],
        "usage": {"input_tokens": 2, "output_tokens": 17}}},
    {"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": _TU_DEAD, "is_error": True,
         "content": "clue-1 was terminated after round 1 and cannot be called."}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": _TU_ALIVE, "name": "Agent",
         "input": {"description": "Get example from clue-2",
                   "prompt": "Please share your example for this round.",
                   "subagent_type": "clue-2", "run_in_background": False}}],
        "usage": {"input_tokens": 2, "output_tokens": 17}}},
    {"type": "user", "parent_tool_use_id": _TU_ALIVE, "subagent_type": "clue-2",
     "message": {"content": [
         {"type": "text", "text": "Please share your example for this round."}]}},
    {"type": "assistant", "parent_tool_use_id": _TU_ALIVE, "subagent_type": "clue-2",
     "message": {"content": [{"type": "text", "text": "red circle 1 → A"}],
                 "usage": {"input_tokens": 2, "cache_creation_input_tokens": 889,
                           "cache_read_input_tokens": 0, "output_tokens": 1,
                           "service_tier": "standard"}}},
    {"type": "user", "message": {"content": [
        {"tool_use_id": _TU_ALIVE, "type": "tool_result", "content": [
            {"type": "text", "text": "red circle 1 → A"},
            {"type": "text", "text": "<usage>subagent_tokens: 901\ntool_uses: 0</usage>"}]}]}},
    {"type": "assistant", "message": {"content": [
        {"type": "text", "text": "I called each clue agent once, and only clue-2 "
                                 "sent back an example.\n\n**clue-2:**\n```\n"
                                 "red circle 1 → A\n```"}],
        "usage": {"input_tokens": 32, "output_tokens": 2}}},
    {"type": "result", "subtype": "success", "is_error": False,
     "result": "I called each clue agent once, and only clue-2 sent back an example.",
     "usage": {"input_tokens": 34, "cache_creation_input_tokens": 1598,
               "cache_read_input_tokens": 3928, "output_tokens": 454,
               "output_tokens_details": {"thinking_tokens": 40}}},
]
RECORDED_STREAM = "\n".join(json.dumps(e) for e in RECORDED_EVENTS)


class TestTheRecordedStream:
    def test_the_alive_slot_usage_comes_from_message_usage(self):
        """The regression the live self-test caught: not top-level usage."""
        res = parse_agentic_stream(RECORDED_STREAM)
        assert [u.slot for u in res.subagent_usage] == ["clue-2"]
        usage = res.subagent_usage[0]
        assert usage.output_tokens == 1          # message.usage.output_tokens
        # The real subagent emits no thinking block and no
        # output_tokens_details, so there is nothing to estimate from.
        assert usage.thinking_tokens == 0
        assert usage.thinking_text is None

    def test_thinking_tokens_are_read_from_message_usage_details(self):
        events = [dict(e) for e in RECORDED_EVENTS]
        sub = json.loads(json.dumps(events[4]))
        sub["message"]["usage"]["output_tokens_details"] = {"thinking_tokens": 21}
        sub["message"]["content"] = [
            {"type": "thinking", "thinking": "which example do I hold?"},
            {"type": "text", "text": "red circle 1 → A"},
        ]
        events[4] = sub
        res = parse_agentic_stream("\n".join(json.dumps(e) for e in events))
        assert res.subagent_usage[0].thinking_tokens == 21
        assert res.subagent_usage[0].thinking_text == "which example do I hold?"

    def test_the_subagent_text_stays_out_of_the_main_thread(self):
        res = parse_agentic_stream(RECORDED_STREAM)
        assert res.text.startswith("I called each clue agent once")
        # The main thread quotes the example in its own summary, but the
        # subagent's own bare line is not appended as a separate block.
        assert not res.text.endswith("red circle 1 → A")
        assert res.thinking_tokens == 40          # the result event's own
        assert res.output_tokens == 454

    def test_the_dead_slot_denial_survives_with_its_reason(self):
        res = parse_agentic_stream(RECORDED_STREAM)
        assert [(s["slot"], s["allowed"]) for s in res.spawn_log] == [
            ("clue-1", False), ("clue-2", True)]
        assert "terminated after round 1" in res.spawn_log[0]["reason"]

    def test_the_slot_is_recovered_from_subagent_type_without_the_tool_use(self):
        """A truncated stream that lost the spawning tool_use block.

        ``parent_tool_use_id`` then maps to nothing, but the event names
        its own slot -- so the usage is still attributed rather than
        dropped on the floor.
        """
        events = [e for e in RECORDED_EVENTS
                  if not (e["type"] == "assistant"
                          and any(b.get("id") == _TU_ALIVE
                                  for b in e["message"]["content"]))]
        res = parse_agentic_stream("\n".join(json.dumps(e) for e in events))
        assert [u.slot for u in res.subagent_usage] == ["clue-2"]
        assert res.subagent_usage[0].output_tokens == 1

    def test_the_parser_does_not_subtract_the_subagent_total(self):
        """Spec §7.1 is OPEN; what is pinned here is the parser's silence.

        The result event's usage is passed through exactly as the CLI
        sent it, and the subagent's beside it, raw. Whether the CLI folds
        the child's tokens into the parent total is undecided (see
        ``parse_agentic_stream``), so this test fixes only that the
        parser invents no adjustment in either direction.
        """
        res = parse_agentic_stream(RECORDED_STREAM)
        assert res.output_tokens == RECORDED_EVENTS[-1]["usage"]["output_tokens"]
        assert res.thinking_tokens == 40
        assert sum(u.thinking_tokens for u in res.subagent_usage) == 0
