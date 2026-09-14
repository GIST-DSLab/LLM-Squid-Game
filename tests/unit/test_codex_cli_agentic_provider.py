"""CodexCliAgenticProvider: argv, CODEX_HOME layout, stream and rollout parsing."""

import json
import os
import shlex
import tomllib

import pytest

from squid_game.providers.base import ToolContext
from squid_game.providers.codex_cli import CodexCliProvider
from squid_game.providers.codex_cli_agentic import (
    CodexCliAgenticProvider,
    build_agentic_command,
    parse_agentic_stream,
    read_subagent_rollouts,
    write_codex_home,
)

CTX = ToolContext(
    slots_json={"names": ["clue-1", "clue-2"], "alive": ["clue-1"],
                "killed": [{"round": 1, "slot": "clue-2"}], "spawn_cap_per_round": 1},
    subagent_prompts={"clue-1": "You are clue-1.\nEXAMPLE: red circle 1 → A",
                      "clue-2": "You are clue-2.\nYou hold no example this round."},
)


def test_command_keeps_multi_agent_and_hooks_and_drops_ephemeral():
    cmd = build_agentic_command(codex_bin="codex", model="gpt-5.6-luna",
                                reasoning_effort="medium", workdir="/w",
                                instructions_file="/w/instructions.md")
    assert cmd[:3] == ["codex", "exec", "--json"]
    assert "--ephemeral" not in cmd
    assert "--dangerously-bypass-hook-trust" in cmd
    assert "--dangerously-bypass-approvals-and-sandbox" in cmd
    disabled = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--disable"]
    assert "shell_tool" in disabled and "unified_exec" in disabled
    assert "multi_agent" not in disabled and "hooks" not in disabled
    enabled = [cmd[i + 1] for i, a in enumerate(cmd) if a == "--enable"]
    assert set(enabled) >= {"multi_agent", "hooks"}
    assert "-c" in cmd and "agents.max_concurrent_threads_per_session=2" in cmd
    assert cmd[-1] == "-"


def test_command_does_not_ignore_the_per_call_user_config():
    """``--ignore-user-config`` skips ``$CODEX_HOME/config.toml``.

    That is the file this provider writes the ``[agents.<slot>]`` role
    tables into, so the flag would silence every role. The per-call home
    holds nothing else, so there is no user config to ignore.
    """
    cmd = build_agentic_command(codex_bin="codex", model="gpt-5.6-luna",
                                reasoning_effort="medium", workdir="/w",
                                instructions_file="/w/instructions.md")
    assert "--ignore-user-config" not in cmd


def test_command_carries_the_model_effort_workdir_and_instructions():
    cmd = build_agentic_command(codex_bin="/usr/bin/codex", model="gpt-6-mini",
                                reasoning_effort="high", workdir="/w",
                                instructions_file="/w/instructions.md")
    assert cmd[cmd.index("--model") + 1] == "gpt-6-mini"
    assert cmd[cmd.index("-C") + 1] == "/w"
    assert "model_reasoning_effort=high" in cmd
    assert "model_reasoning_summary=detailed" in cmd
    assert 'model_instructions_file="/w/instructions.md"' in cmd
    assert "--skip-git-repo-check" in cmd


def test_command_omits_effort_and_instructions_when_unset():
    cmd = build_agentic_command(codex_bin="codex", model="gpt-5.6-luna",
                                reasoning_effort=None, workdir="/w")
    assert "model_reasoning_effort" not in " ".join(cmd)
    assert "model_instructions_file" not in " ".join(cmd)


def test_write_codex_home_lays_out_agents_hooks_and_config(tmp_path):
    auth = tmp_path / "auth.json"
    auth.write_text('{"tokens": {}}')
    home = write_codex_home(str(tmp_path / "w"), CTX, source_auth=str(auth))
    assert os.path.exists(os.path.join(home, "auth.json"))
    hooks = json.load(open(os.path.join(home, "hooks.json")))
    pre = hooks["hooks"]["PreToolUse"][0]
    assert pre["matcher"] == "^(spawn_agent|Agent)$"
    # shlex.split, not endswith: the path is quoted (see the spaces test below).
    assert shlex.split(pre["hooks"][0]["command"])[-1].endswith("subagent_budget.py")
    for slot in ("clue-1", "clue-2"):
        toml = open(os.path.join(home, "agents", f"{slot}.toml")).read()
        assert f'name = "{slot}"' in toml
        assert 'description = "Holds one of this round\'s examples."' in toml
        assert "developer_instructions" in toml and CTX.subagent_prompts[slot].splitlines()[0] in toml
    cfg = open(os.path.join(home, "config.toml")).read()
    assert 'cli_auth_credentials_store = "file"' in cfg
    assert "[agents.clue-1]" in cfg and "[agents.clue-2]" in cfg
    assert os.path.join(home, "agents", "clue-1.toml") in cfg


def test_the_hook_command_survives_a_path_with_spaces(tmp_path):
    """This repository lives under ".../Mobile Documents/...".

    Unquoted, the CLI would shell-split the command, the hook would never
    run and the spawn would proceed -- fail-OPEN, the exact failure the
    budget hook exists to prevent.
    """
    ctx = ToolContext(slots_json={}, subagent_prompts={"clue-1": "You are clue-1."},
                      hook_script="/tmp/dir with space/subagent_budget.py")
    home = write_codex_home(str(tmp_path / "w"), ctx, source_auth=None)
    hooks = json.load(open(os.path.join(home, "hooks.json")))
    command = hooks["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
    assert command == "python3 '/tmp/dir with space/subagent_budget.py'"
    assert shlex.split(command) == ["python3", "/tmp/dir with space/subagent_budget.py"]


def test_write_codex_home_without_a_login_writes_no_auth(tmp_path):
    home = write_codex_home(str(tmp_path / "w"), CTX,
                            source_auth=str(tmp_path / "missing.json"))
    assert not os.path.exists(os.path.join(home, "auth.json"))
    assert os.path.exists(os.path.join(home, "hooks.json"))


def test_agent_toml_escapes_newlines_in_the_prompt(tmp_path):
    home = write_codex_home(str(tmp_path / "w"), CTX, source_auth=None)
    toml = open(os.path.join(home, "agents", "clue-1.toml")).read()
    # A TOML basic string holds the newline as an escape, never a raw break.
    assert "\\n" in toml
    assert toml.count("\n") == 3


def test_agent_toml_parses_when_the_prompt_holds_emoji_and_arrows(tmp_path):
    """``json.dumps`` defaults to ASCII, which breaks TOML on astral chars.

    An emoji would come out as the surrogate pair ``\\uD83D\\uDE00``;
    ``tomllib`` rejects that, and the CLI would lose the role entirely.
    The signal-game prompts carry ``→`` in every example line.
    """
    prompt = "You are clue-1. 😀\nEXAMPLE: red circle 1 → A"
    ctx = ToolContext(slots_json={}, subagent_prompts={"clue-1": prompt})
    home = write_codex_home(str(tmp_path / "w"), ctx, source_auth=None)
    with open(os.path.join(home, "agents", "clue-1.toml"), "rb") as fh:
        parsed = tomllib.load(fh)
    assert parsed["developer_instructions"] == prompt
    assert parsed["name"] == "clue-1"


def test_the_non_agentic_path_is_the_parent_s_own_complete():
    """The plain ``complete()`` must stay byte-for-byte the parent's."""
    assert CodexCliAgenticProvider.complete is CodexCliProvider.complete


STREAM = "\n".join(json.dumps(e) for e in [
    {"type": "thread.started", "thread_id": "t0"},
    {"type": "item.completed", "item": {"type": "reasoning", "text": "need examples"}},
    {"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "spawn_agent",
        "receiver_thread_ids": ["t1"], "prompt": "your example?", "status": "completed",
        "agents_states": {"t1": {"agent_type": "clue-1"}}}},
    {"type": "item.completed", "item": {"type": "collab_tool_call", "tool": "spawn_agent",
        "receiver_thread_ids": [], "prompt": "your example?", "status": "failed",
        "error": "clue-2 was terminated after round 1 and cannot be called.",
        "agents_states": {}}},
    {"type": "item.completed", "item": {"type": "agent_message", "text": "RULE: ...\nACTION: A"}},
    {"type": "turn.completed", "usage": {"input_tokens": 10, "output_tokens": 50,
                                          "reasoning_output_tokens": 20}},
])


def test_parse_reads_collab_calls_as_spawn_attempts():
    res = parse_agentic_stream(STREAM)
    assert res.text.startswith("RULE:")
    assert res.thinking_tokens == 20
    assert [(s["slot"], s["allowed"]) for s in res.spawn_log] == [("clue-1", True), (None, False)]


def test_parse_keeps_the_denial_reason_and_the_primary_usage():
    res = parse_agentic_stream(STREAM)
    assert res.input_tokens == 10 and res.output_tokens == 50
    assert res.thinking_text == "need examples"
    assert res.spawn_log[0]["reason"] is None
    assert "terminated after round 1" in res.spawn_log[1]["reason"]
    assert res.subagent_usage == ()


def test_parse_raises_on_a_failed_turn():
    from squid_game.providers.codex_cli import CodexCliError

    raw = json.dumps({"type": "turn.failed", "error": {"message": "model unavailable"}})
    with pytest.raises(CodexCliError, match="model unavailable"):
        parse_agentic_stream(raw)


def test_read_subagent_rollouts_sums_child_thread_tokens(tmp_path):
    d = tmp_path / "sessions" / "2026" / "09" / "14"
    d.mkdir(parents=True)
    (d / "rollout-parent.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"type": "session_meta", "payload": {"id": "t0", "thread_source": "cli"}},
    ]))
    (d / "rollout-child.jsonl").write_text("\n".join(json.dumps(e) for e in [
        {"type": "session_meta", "payload": {"id": "t1", "thread_source": "subagent",
            "parent_thread_id": "t0",
            "source": {"subagent": {"thread_spawn": {"agent_role": "clue-1"}}}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"output_tokens": 80, "reasoning_output_tokens": 33}}}},
        {"type": "event_msg", "payload": {"type": "token_count", "info": {
            "total_token_usage": {"output_tokens": 90, "reasoning_output_tokens": 41}}}},
    ]))
    usage = read_subagent_rollouts(str(tmp_path))
    assert [(u.slot, u.thinking_tokens, u.output_tokens) for u in usage] == [("clue-1", 41, 90)]


def test_read_subagent_rollouts_tolerates_a_missing_sessions_tree(tmp_path):
    assert read_subagent_rollouts(str(tmp_path / "nothing-here")) == ()


def test_provider_refuses_models_without_spawn_tools():
    with pytest.raises(ValueError, match="spawn"):
        CodexCliAgenticProvider(model="gpt-5.5")


def test_provider_accepts_the_spawn_capable_prefixes():
    for model in ("gpt-5.6-luna", "gpt-6-mini"):
        provider = CodexCliAgenticProvider(model=model, codex_bin="/nonexistent/codex")
        assert provider.model_name == model


def test_factory_registers_the_agentic_name():
    from squid_game.providers.factory import available_providers
    assert "codex_cli_agentic" in available_providers()


def test_factory_builds_the_agentic_provider():
    from squid_game.models.config import ProviderConfig
    from squid_game.providers.factory import build_provider

    provider = build_provider(ProviderConfig(
        provider="codex_cli_agentic", model="gpt-5.6-luna", reasoning_effort="medium",
    ))
    assert isinstance(provider, CodexCliAgenticProvider)
    assert provider.model_name == "gpt-5.6-luna"
