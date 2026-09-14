"""ClaudeCodeProvider: argv shape, stream-json parsing, error handling (no CLI)."""

import json
from unittest.mock import patch

import pytest

from squid_game.providers.claude_code import (
    ClaudeCodeError,
    ClaudeCodeProvider,
    _child_env,
    build_command,
    parse_stream_json,
)


def _events(text="RULE: x\nACTION: stay", thinking="summary", thinking_tokens=123, is_error=False):
    content = []
    if thinking is not None:
        content.append({"type": "thinking", "thinking": thinking})
    content.append({"type": "text", "text": text})
    lines = [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": content}},
        {"type": "result", "subtype": "success", "is_error": is_error, "result": text,
         "usage": {"input_tokens": 10, "cache_read_input_tokens": 90, "output_tokens": 50,
                   "output_tokens_details": {"thinking_tokens": thinking_tokens}}},
    ]
    return "\n".join(json.dumps(l) for l in lines) + "\n"


def test_build_command_shape():
    cmd = build_command(claude_bin="claude", model="claude-opus-5", system_prompt="SYS", effort="medium")
    assert cmd[:2] == ["claude", "-p"]
    assert cmd[cmd.index("--model") + 1] == "claude-opus-5"
    assert cmd[cmd.index("--output-format") + 1] == "stream-json"
    assert cmd[cmd.index("--max-turns") + 1] == "1"
    assert cmd[cmd.index("--tools") + 1] == ""
    assert cmd[cmd.index("--system-prompt") + 1] == "SYS"
    assert cmd[cmd.index("--effort") + 1] == "medium"
    assert "--strict-mcp-config" in cmd
    assert cmd[cmd.index("--mcp-config") + 1] == '{"mcpServers":{}}'

    assert "--effort" not in build_command(claude_bin="claude", model="m", system_prompt=None, effort=None)


def test_parse_stream_json_reads_text_thinking_and_usage():
    r = parse_stream_json(_events())
    assert r.text == "RULE: x\nACTION: stay"
    assert r.thinking_text == "summary"
    assert r.thinking_tokens == 123
    assert r.input_tokens == 100 and r.output_tokens == 50
    assert r.finish_reason == "success"


def test_parse_stream_json_error_result_raises():
    with pytest.raises(ClaudeCodeError):
        parse_stream_json(_events(text="Not logged in", thinking=None, is_error=True))


def test_parse_stream_json_no_result_raises():
    with pytest.raises(ClaudeCodeError):
        parse_stream_json('{"type": "system"}\n')


def test_complete_splits_system_and_user_and_retries():
    p = ClaudeCodeProvider(model="claude-opus-5", reasoning_effort="medium", max_retries=1, claude_bin="claude")
    calls = []

    def fake_run(cmd, prompt):
        calls.append((cmd, prompt))
        if len(calls) == 1:
            raise ClaudeCodeError("boom")
        return _events()

    with patch.object(p, "_run", side_effect=fake_run), patch("squid_game.providers.claude_code.time.sleep"):
        r = p.complete([{"role": "system", "content": "SYS"}, {"role": "user", "content": "hi"}])
    assert r.text.startswith("RULE:")
    assert len(calls) == 2
    cmd, prompt = calls[-1]
    assert cmd[cmd.index("--system-prompt") + 1] == "SYS"
    assert prompt == "hi"


def test_invalid_effort_rejected():
    with pytest.raises(ValueError):
        ClaudeCodeProvider(reasoning_effort="ultra")


# ---------------------------------------------------------------------------
# _child_env: which parent variables reach the spawned CLI
# ---------------------------------------------------------------------------


class TestChildEnv:
    """The prefix filter must not eat the child's own configuration.

    ``CLAUDE_CODE_OAUTH_TOKEN`` and ``CLAUDE_CODE_DISABLE_AUTOUPDATER`` are
    what the agentcli container supplies (compose injects the token,
    Dockerfile.agentcli sets the flag). Stripping them by prefix logged the
    container's CLI out and let it move off its pinned version -- invisible
    on the host, where the CLI reads its own keychain login.
    """

    _MARKERS = {
        "CLAUDECODE": "1",
        "CLAUDE_PID": "4242",
        "CLAUDE_CODE_SOMETHING_ELSE": "nested-session-marker",
        "CLAUDE_CODE_ENTRYPOINT": "cli",
    }
    _KEPT = {
        "CLAUDE_CODE_OAUTH_TOKEN": "sk-ant-oat-not-a-real-token",
        "CLAUDE_CODE_DISABLE_AUTOUPDATER": "1",
    }

    def test_the_oauth_token_and_the_autoupdater_flag_survive(self, monkeypatch):
        for key, value in {**self._MARKERS, **self._KEPT}.items():
            monkeypatch.setenv(key, value)
        env = _child_env()
        assert env["CLAUDE_CODE_OAUTH_TOKEN"] == self._KEPT["CLAUDE_CODE_OAUTH_TOKEN"]
        assert env["CLAUDE_CODE_DISABLE_AUTOUPDATER"] == "1"

    def test_the_session_markers_are_still_stripped(self, monkeypatch):
        for key, value in {**self._MARKERS, **self._KEPT}.items():
            monkeypatch.setenv(key, value)
        env = _child_env()
        for key in self._MARKERS:
            assert key not in env, f"{key} should not reach the child"

    def test_an_unrelated_variable_is_untouched(self, monkeypatch):
        monkeypatch.setenv("SOME_OTHER_VAR", "kept")
        assert _child_env()["SOME_OTHER_VAR"] == "kept"

    def test_the_api_key_is_still_dropped_alongside_a_kept_token(self, monkeypatch):
        """The allow-list must not reopen the billing escape hatch."""
        monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "sk-ant-oat-not-a-real-token")
        monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-api-zero-credit")
        monkeypatch.delenv("SQUID_CLAUDE_CODE_USE_API_KEY", raising=False)
        env = _child_env()
        assert "ANTHROPIC_API_KEY" not in env
        assert "CLAUDE_CODE_OAUTH_TOKEN" in env


class TestChildEnvEndpointPassthrough:
    """The three variables that point the CLI at a non-Anthropic endpoint.

    Ollama Cloud serves ``/v1/messages``, so ``claude -p`` can be backed by
    an OPEN model (``gpt-oss``) with ``ANTHROPIC_BASE_URL`` +
    ``ANTHROPIC_AUTH_TOKEN`` + an empty ``ANTHROPIC_API_KEY``. The two auth
    names ride the existing ``SQUID_CLAUDE_CODE_USE_API_KEY=1`` opt-in; the
    base URL must survive either way, because an endpoint dropped in
    silence sends the prompt to Anthropic while the operator believes it
    went to their own server.
    """

    _RECIPE = {
        "ANTHROPIC_BASE_URL": "https://ollama.com",
        "ANTHROPIC_AUTH_TOKEN": "ollama-token-not-a-real-key",
        "ANTHROPIC_API_KEY": "",
    }

    def _set_recipe(self, monkeypatch):
        for key, value in self._RECIPE.items():
            monkeypatch.setenv(key, value)

    def test_the_opt_in_keeps_all_three(self, monkeypatch):
        self._set_recipe(monkeypatch)
        monkeypatch.setenv("SQUID_CLAUDE_CODE_USE_API_KEY", "1")
        env = _child_env()
        assert env["ANTHROPIC_BASE_URL"] == "https://ollama.com"
        assert env["ANTHROPIC_AUTH_TOKEN"] == self._RECIPE["ANTHROPIC_AUTH_TOKEN"]
        assert env["ANTHROPIC_API_KEY"] == ""

    def test_without_the_opt_in_the_two_auth_names_are_stripped(self, monkeypatch):
        self._set_recipe(monkeypatch)
        monkeypatch.delenv("SQUID_CLAUDE_CODE_USE_API_KEY", raising=False)
        env = _child_env()
        assert "ANTHROPIC_AUTH_TOKEN" not in env
        assert "ANTHROPIC_API_KEY" not in env

    def test_the_base_url_survives_without_the_opt_in(self, monkeypatch):
        self._set_recipe(monkeypatch)
        monkeypatch.delenv("SQUID_CLAUDE_CODE_USE_API_KEY", raising=False)
        assert _child_env()["ANTHROPIC_BASE_URL"] == "https://ollama.com"

    def test_the_base_url_survives_the_claude_code_prefix_filter(self, monkeypatch):
        """It is not a ``CLAUDE_CODE_*`` name, but pin it against a widened filter."""
        self._set_recipe(monkeypatch)
        monkeypatch.setenv("CLAUDECODE", "1")
        monkeypatch.setenv("CLAUDE_CODE_ENTRYPOINT", "cli")
        monkeypatch.setenv("SQUID_CLAUDE_CODE_USE_API_KEY", "1")
        env = _child_env()
        assert env["ANTHROPIC_BASE_URL"] == "https://ollama.com"
        assert "CLAUDECODE" not in env and "CLAUDE_CODE_ENTRYPOINT" not in env
