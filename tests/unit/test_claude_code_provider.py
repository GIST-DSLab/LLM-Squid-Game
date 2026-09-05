"""ClaudeCodeProvider: argv shape, stream-json parsing, error handling (no CLI)."""

import json
from unittest.mock import patch

import pytest

from squid_game.providers.claude_code import (
    ClaudeCodeError,
    ClaudeCodeProvider,
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
