"""Unit tests for the agent-harness runtime adapters (Task 11).

Nothing here shells out to a real ``claude`` / ``codex`` / ``ollama``
binary. ``subprocess.run`` is monkeypatched at
``squid_game.core.runtime.harness.subprocess.run`` and driven with
stdout shapes taken verbatim from the Task 1 spike findings document
(``docs/superpowers/plans/2026-08-31-harness-spike-findings.md``), so
these tests exercise real JSON/event parsing rather than mocks
asserting mocks.
"""

from __future__ import annotations

import json
import os
from types import SimpleNamespace

import pytest

from squid_game.core.runtime.harness import (
    ClaudeCodeAdapter,
    CodexAdapter,
    HarnessError,
    HarnessRuntime,
    build_harness_env,
)
from squid_game.models.config import HarnessConfig, HarnessKind


def _fake_run(recorder, stdout: str, *, returncode: int = 0, stderr: str = ""):
    def run(cmd, **kwargs):
        recorder.append({"cmd": cmd, "kwargs": kwargs})
        return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)

    return run


# ---------------------------------------------------------------------------
# build_harness_env
# ---------------------------------------------------------------------------


def test_ollama_env_points_claude_code_at_the_local_server():
    env = build_harness_env("ollama_cloud", base_url="http://ollama:11434")

    assert env["ANTHROPIC_AUTH_TOKEN"] == "ollama"
    assert env["ANTHROPIC_API_KEY"] == ""
    assert env["ANTHROPIC_BASE_URL"] == "http://ollama:11434"


def test_ollama_env_falls_back_to_localhost_when_base_url_is_none():
    env = build_harness_env("ollama_cloud", base_url=None)

    assert env["ANTHROPIC_BASE_URL"] == "http://localhost:11434"


def test_anthropic_env_does_not_override_the_base_url():
    env = build_harness_env("anthropic", base_url=None)

    assert "ANTHROPIC_BASE_URL" not in env
    assert "ANTHROPIC_AUTH_TOKEN" not in env
    assert "ANTHROPIC_API_KEY" not in env


def test_openai_env_is_empty_codex_uses_its_own_credentials():
    env = build_harness_env("openai", base_url=None)

    assert env == {}


# ---------------------------------------------------------------------------
# ClaudeCodeAdapter -- command assembly + JSON parsing
# (paths per the spike: .session_id, .usage.output_tokens,
# .usage.output_tokens_details.thinking_tokens, .result)
# ---------------------------------------------------------------------------


def test_claude_code_first_call_has_no_resume_flag(monkeypatch, tmp_path):
    calls = []
    stdout = json.dumps(
        {
            "session_id": "sess-1",
            "result": "CONTINUE",
            "usage": {
                "input_tokens": 10,
                "output_tokens": 4,
                "output_tokens_details": {"thinking_tokens": 0},
            },
        }
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    outcome = adapter.send("first prompt")

    assert calls[0]["cmd"] == [
        "claude", "-p", "first prompt", "--output-format", "json",
    ]
    assert "--resume" not in calls[0]["cmd"]
    assert outcome.text == "CONTINUE"
    assert outcome.rounds[0].output == 4
    assert outcome.rounds[0].thinking == 0
    assert adapter.session_id == "sess-1"


def test_claude_code_thinking_tokens_come_from_output_tokens_details(
    monkeypatch, tmp_path
):
    calls = []
    stdout = json.dumps(
        {
            "session_id": "sess-1",
            "result": "ok",
            "usage": {
                "input_tokens": 4,
                "output_tokens": 182,
                "output_tokens_details": {"thinking_tokens": 77},
            },
        }
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    outcome = adapter.send("Think step by step")

    assert outcome.rounds[0].thinking == 77
    assert outcome.rounds[0].output == 182


def test_claude_code_second_call_resumes_the_session(monkeypatch, tmp_path):
    calls = []
    stdout = json.dumps(
        {
            "session_id": "sess-1",
            "result": "ok",
            "usage": {"input_tokens": 1, "output_tokens": 1},
        }
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    adapter.send("first")
    adapter.send("second")

    assert "--resume" in calls[1]["cmd"]
    assert "sess-1" in calls[1]["cmd"]


def test_claude_code_resolves_a_custom_binary(monkeypatch, tmp_path):
    calls = []
    stdout = json.dumps(
        {"session_id": "s", "result": "ok", "usage": {"output_tokens": 1}}
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE, binary="/opt/claude-nightly"),
        workdir=tmp_path,
        env={},
    )

    adapter.send("go")

    assert calls[0]["cmd"][0] == "/opt/claude-nightly"


def test_claude_code_emits_the_model_flag_when_set(monkeypatch, tmp_path):
    """Important 1 (review round 1): the ollama_cloud + claude_code route
    needs --model alongside the ANTHROPIC_* env overrides, or 'claude'
    silently falls back to its own default model resolution."""
    calls = []
    stdout = json.dumps(
        {"session_id": "s", "result": "ok", "usage": {"output_tokens": 1}}
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE, model="gpt-oss:120b-cloud"),
        workdir=tmp_path,
        env={},
    )

    adapter.send("go")

    assert "--model" in calls[0]["cmd"]
    idx = calls[0]["cmd"].index("--model")
    assert calls[0]["cmd"][idx + 1] == "gpt-oss:120b-cloud"


def test_claude_code_omits_the_model_flag_when_unset(monkeypatch, tmp_path):
    calls = []
    stdout = json.dumps(
        {"session_id": "s", "result": "ok", "usage": {"output_tokens": 1}}
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    adapter.send("go")

    assert "--model" not in calls[0]["cmd"]


def test_claude_code_model_flag_survives_a_resume_call(monkeypatch, tmp_path):
    calls = []
    stdout = json.dumps(
        {"session_id": "sess-1", "result": "ok", "usage": {"output_tokens": 1}}
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE, model="gpt-oss:120b-cloud"),
        workdir=tmp_path,
        env={},
    )

    adapter.send("first")
    adapter.send("second")

    assert "--model" in calls[1]["cmd"]
    assert "--resume" in calls[1]["cmd"]


# ---------------------------------------------------------------------------
# Retry-once-then-fail (Global Constraints: a dead harness process is
# retried once; a second failure fails the season).
# ---------------------------------------------------------------------------


def test_a_nonzero_exit_is_retried_once(monkeypatch, tmp_path):
    attempts = []

    def run(cmd, **kwargs):
        attempts.append(cmd)
        if len(attempts) == 1:
            return SimpleNamespace(returncode=1, stdout="", stderr="boom")
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"session_id": "s", "result": "ok",
                 "usage": {"input_tokens": 1, "output_tokens": 1}}
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run", run
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    outcome = adapter.send("go")

    assert len(attempts) == 2
    assert outcome.text == "ok"


def test_two_consecutive_failures_fail_the_season(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, "", returncode=1, stderr="permission denied"),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="permission denied"):
        adapter.send("go")

    assert len(calls) == 2


# ---------------------------------------------------------------------------
# Critical 2 (review round 1) -- a timeout, malformed/empty stdout, or a
# missing binary are all retried once then raised as HarnessError, exactly
# like a nonzero exit code.
# ---------------------------------------------------------------------------


def test_a_timeout_is_retried_once_then_succeeds(monkeypatch, tmp_path):
    import subprocess as subprocess_module

    attempts = []

    def run(cmd, **kwargs):
        attempts.append(cmd)
        if len(attempts) == 1:
            raise subprocess_module.TimeoutExpired(cmd=cmd, timeout=600)
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"session_id": "s", "result": "ok",
                 "usage": {"input_tokens": 1, "output_tokens": 1}}
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run", run
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    outcome = adapter.send("go")

    assert len(attempts) == 2
    assert outcome.text == "ok"


def test_two_consecutive_timeouts_raise_harness_error(monkeypatch, tmp_path):
    import subprocess as subprocess_module

    def run(cmd, **kwargs):
        raise subprocess_module.TimeoutExpired(cmd=cmd, timeout=600)

    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run", run
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="timed out"):
        adapter.send("go")


def test_malformed_json_is_retried_once_then_succeeds(monkeypatch, tmp_path):
    attempts = []

    def run(cmd, **kwargs):
        attempts.append(cmd)
        if len(attempts) == 1:
            return SimpleNamespace(
                returncode=0, stdout="{not valid json", stderr=""
            )
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"session_id": "s", "result": "ok",
                 "usage": {"input_tokens": 1, "output_tokens": 1}}
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run", run
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    outcome = adapter.send("go")

    assert len(attempts) == 2
    assert outcome.text == "ok"


def test_two_consecutive_malformed_json_responses_raise_harness_error(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, "{not valid json"),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="unparseable stdout"):
        adapter.send("go")

    assert len(calls) == 2


def test_a_valid_json_scalar_with_no_dict_shape_is_a_parse_failure(
    monkeypatch, tmp_path
):
    """Syntactically valid JSON (a bare string) in the wrong shape must
    not be treated as a successful response -- .get() on it raises
    AttributeError, which is one of the _PARSE_ERRORS cases."""
    calls = []
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, json.dumps("just a string")),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="unparseable stdout"):
        adapter.send("go")


def test_two_consecutive_empty_stdout_responses_raise_harness_error(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, ""),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="empty stdout"):
        adapter.send("go")

    assert len(calls) == 2


def test_whitespace_only_stdout_is_treated_as_empty(monkeypatch, tmp_path):
    calls = []
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, "   \n  "),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="empty stdout"):
        adapter.send("go")


def test_codex_empty_stdout_does_not_silently_parse_as_a_result(
    monkeypatch, tmp_path
):
    """CodexAdapter._parse iterates stdout.splitlines(); on an empty
    string that loop simply never runs and would otherwise return an
    all-zero CallOutcome as if it were a real (if quiet) response.
    send() must reject empty stdout before _parse ever sees it."""
    calls = []
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, ""),
    )
    adapter = CodexAdapter(
        HarnessConfig(kind=HarnessKind.CODEX), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="empty stdout"):
        adapter.send("go")


def test_a_missing_binary_is_retried_once_then_succeeds(monkeypatch, tmp_path):
    attempts = []

    def run(cmd, **kwargs):
        attempts.append(cmd)
        if len(attempts) == 1:
            raise FileNotFoundError(2, "No such file or directory", cmd[0])
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps(
                {"session_id": "s", "result": "ok",
                 "usage": {"input_tokens": 1, "output_tokens": 1}}
            ),
            stderr="",
        )

    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run", run
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    outcome = adapter.send("go")

    assert len(attempts) == 2
    assert outcome.text == "ok"


def test_two_consecutive_missing_binary_failures_raise_harness_error(
    monkeypatch, tmp_path
):
    attempts = []

    def run(cmd, **kwargs):
        attempts.append(cmd)
        raise FileNotFoundError(2, "No such file or directory", cmd[0])

    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run", run
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="failed to launch"):
        adapter.send("go")

    assert len(attempts) == 2


# ---------------------------------------------------------------------------
# R11 / S358 -- a lost session id fails the season instead of silently
# opening a new one.
# ---------------------------------------------------------------------------


def test_a_lost_session_id_fails_the_season(monkeypatch, tmp_path):
    calls = []
    first = json.dumps(
        {"session_id": "sess-1", "result": "ok",
         "usage": {"input_tokens": 1, "output_tokens": 1}}
    )

    def run(cmd, **kwargs):
        calls.append(cmd)
        return SimpleNamespace(returncode=0, stdout=first, stderr="")

    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run", run
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )
    adapter.send("first")
    adapter.session_id = None

    with pytest.raises(HarnessError, match="session id was lost"):
        adapter.send("second")

    # The command was never re-issued: the loss is caught while
    # assembling the resume command, before any subprocess runs.
    assert len(calls) == 1


def test_require_session_raises_before_first_call_would_never_happen(tmp_path):
    """Sanity check on require_session() itself, independent of send()."""
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    with pytest.raises(HarnessError, match="session id was lost"):
        adapter.require_session()


# ---------------------------------------------------------------------------
# R11 -- env inheritance: os.environ must survive, harness-specific vars
# are layered on top.
# ---------------------------------------------------------------------------


def test_env_inherits_os_environ_and_merges_harness_specific_vars(
    monkeypatch, tmp_path
):
    calls = []
    monkeypatch.setenv("SQUID_GAME_TEST_MARKER", "present")
    stdout = json.dumps(
        {"session_id": "s", "result": "ok", "usage": {"output_tokens": 1}}
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE),
        workdir=tmp_path,
        env={"ANTHROPIC_AUTH_TOKEN": "ollama"},
    )

    adapter.send("go")

    env = calls[0]["kwargs"]["env"]
    assert env["SQUID_GAME_TEST_MARKER"] == "present"
    assert env["ANTHROPIC_AUTH_TOKEN"] == "ollama"
    # PATH is the concrete symptom of the "env={} wipes PATH" bug R11
    # warns about -- os.environ must be the base layer, not replaced.
    assert env["PATH"] == os.environ["PATH"]


def test_a_bare_env_would_wipe_path_so_we_never_pass_one(monkeypatch, tmp_path):
    """Guards the specific R11 footgun: env={**self._env} without
    **os.environ as the base would drop PATH entirely."""
    calls = []
    stdout = json.dumps(
        {"session_id": "s", "result": "ok", "usage": {"output_tokens": 1}}
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )

    adapter.send("go")

    assert "PATH" in calls[0]["kwargs"]["env"]


# ---------------------------------------------------------------------------
# CodexAdapter -- command assembly + event-stream parsing (paths per the
# spike: thread.started/.thread_id, turn.completed/.usage.{output_tokens,
# reasoning_output_tokens}, item.completed/.item split by .item.type).
# ---------------------------------------------------------------------------


def _codex_stdout(*, thread_id: str, text: str, output_tokens: int,
                   reasoning_tokens: int, tool_events: list[dict] | None = None):
    lines = [json.dumps({"type": "thread.started", "thread_id": thread_id})]
    for event in tool_events or []:
        lines.append(json.dumps({"type": "item.completed", "item": event}))
    lines.append(
        json.dumps({"type": "item.completed", "item": {"type": "agent_message", "text": text}})
    )
    lines.append(
        json.dumps(
            {
                "type": "turn.completed",
                "usage": {
                    "input_tokens": 45322,
                    "output_tokens": output_tokens,
                    "reasoning_output_tokens": reasoning_tokens,
                },
            }
        )
    )
    return "\n".join(lines)


def test_codex_adapter_builds_an_exec_command_with_workspace_write(
    monkeypatch, tmp_path
):
    calls = []
    stdout = _codex_stdout(
        thread_id="01a0559a-be71-70f0-8f31-3e60a8570534",
        text="CONTINUE",
        output_tokens=145,
        reasoning_tokens=0,
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = CodexAdapter(
        HarnessConfig(kind=HarnessKind.CODEX), workdir=tmp_path, env={}
    )

    outcome = adapter.send("go")

    assert calls[0]["cmd"][:2] == ["codex", "exec"]
    assert "--skip-git-repo-check" in calls[0]["cmd"]
    assert "-s" in calls[0]["cmd"] and "workspace-write" in calls[0]["cmd"]
    assert outcome.text == "CONTINUE"
    assert outcome.rounds[0].output == 145
    assert outcome.rounds[0].thinking == 0
    assert adapter.session_id == "01a0559a-be71-70f0-8f31-3e60a8570534"


def test_codex_adapter_reads_reasoning_tokens_from_turn_completed(
    monkeypatch, tmp_path
):
    calls = []
    stdout = _codex_stdout(
        thread_id="01a0559a-1e69-7793-baf0-f0e98af39644",
        text="wrote codex_hello3.txt",
        output_tokens=391,
        reasoning_tokens=115,
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = CodexAdapter(
        HarnessConfig(kind=HarnessKind.CODEX), workdir=tmp_path, env={}
    )

    outcome = adapter.send("write a file")

    assert outcome.rounds[0].thinking == 115
    assert outcome.rounds[0].output == 391


def test_codex_adapter_counts_command_execution_and_file_change_as_tool_calls(
    monkeypatch, tmp_path
):
    calls = []
    stdout = _codex_stdout(
        thread_id="t-1",
        text="done",
        output_tokens=10,
        reasoning_tokens=0,
        tool_events=[
            {
                "type": "command_execution",
                "command": "echo hi",
                "aggregated_output": "hi\n",
                "exit_code": 0,
                "status": "completed",
            },
            {
                "type": "file_change",
                "changes": [{"path": "codex_hello.txt", "kind": "add"}],
                "status": "completed",
            },
        ],
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = CodexAdapter(
        HarnessConfig(kind=HarnessKind.CODEX), workdir=tmp_path, env={}
    )

    outcome = adapter.send("go")

    assert outcome.rounds[0].tool_calls == 2


def test_codex_adapter_resumes_via_exec_resume_subcommand(monkeypatch, tmp_path):
    calls = []
    stdout = _codex_stdout(
        thread_id="thread-1", text="ok", output_tokens=1, reasoning_tokens=0
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = CodexAdapter(
        HarnessConfig(kind=HarnessKind.CODEX), workdir=tmp_path, env={}
    )

    adapter.send("first")
    adapter.send("second")

    assert calls[1]["cmd"][:3] == ["codex", "exec", "resume"]
    assert "thread-1" in calls[1]["cmd"]


# ---------------------------------------------------------------------------
# HarnessRuntime -- R3 signature parity with ApiRuntime, message
# flattening, close() delegation.
# ---------------------------------------------------------------------------


def test_harness_runtime_flattens_system_and_user_blocks(monkeypatch, tmp_path):
    calls = []
    stdout = json.dumps(
        {"session_id": "s", "result": "ok", "usage": {"output_tokens": 1}}
    )
    monkeypatch.setattr(
        "squid_game.core.runtime.harness.subprocess.run",
        _fake_run(calls, stdout),
    )
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )
    runtime = HarnessRuntime(adapter)

    outcome = runtime.run_call(
        "task",
        [
            {"role": "system", "content": "SYSTEM BLOCK"},
            {"role": "user", "content": "USER BLOCK"},
        ],
        temperature=0.9,
        max_tokens=123,
    )

    assert outcome.text == "ok"
    prompt_arg = calls[0]["cmd"][2]
    assert prompt_arg == "SYSTEM BLOCK\n\nUSER BLOCK"


def test_harness_runtime_close_delegates_to_the_adapter(tmp_path):
    adapter = ClaudeCodeAdapter(
        HarnessConfig(kind=HarnessKind.CLAUDE_CODE), workdir=tmp_path, env={}
    )
    adapter.session_id = "sess-1"
    runtime = HarnessRuntime(adapter)

    runtime.close()

    assert adapter.session_id is None
