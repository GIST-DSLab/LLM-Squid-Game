"""CodexCliProvider: argv, JSONL parsing, prompt isolation, and retries."""

import importlib
import json
from unittest.mock import patch

import pytest

from squid_game.models.config import ProviderConfig
from squid_game.providers.factory import available_providers, build_provider


def _codex_cli():
    return importlib.import_module("squid_game.providers.codex_cli")


def _events(
    text="RULE: x\nACTION: stay",
    reasoning="Checked the required output format.",
    reasoning_tokens=32,
):
    lines = [
        {"type": "thread.started", "thread_id": "0199a213-test"},
        {"type": "turn.started"},
    ]
    if reasoning is not None:
        lines.append({
            "type": "item.completed",
            "item": {"id": "item_0", "type": "reasoning", "text": reasoning},
        })
    lines.extend([
        {
            "type": "item.completed",
            "item": {"id": "item_1", "type": "agent_message", "text": text},
        },
        {
            "type": "turn.completed",
            "usage": {
                "input_tokens": 1590,
                "cached_input_tokens": 1408,
                "output_tokens": 58,
                "reasoning_output_tokens": reasoning_tokens,
            },
        },
    ])
    return "\n".join(json.dumps(line) for line in lines) + "\n"


def test_build_command_shape():
    module = _codex_cli()
    cmd = module.build_command(
        codex_bin="codex",
        model="gpt-5.6-luna",
        reasoning_effort="max",
        workdir="/tmp/empty",
    )
    assert cmd[:2] == ["codex", "exec"]
    assert "--json" in cmd
    assert "--ephemeral" in cmd
    assert "--ignore-user-config" in cmd
    assert "--skip-git-repo-check" in cmd
    disabled_features = {
        cmd[index + 1] for index, arg in enumerate(cmd) if arg == "--disable"
    }
    assert {
        "browser_use",
        "browser_use_external",
        "computer_use",
        "in_app_browser",
        "shell_tool",
        "unified_exec",
        "personality",
        "guardian_approval",
    } <= disabled_features
    assert disabled_features == set(module._DISABLED_FEATURES)
    assert cmd[cmd.index("--sandbox") + 1] == "read-only"
    assert cmd[cmd.index("-C") + 1] == "/tmp/empty"
    assert cmd[cmd.index("--model") + 1] == "gpt-5.6-luna"
    assert cmd[cmd.index("-c") + 1] == "model_reasoning_effort=max"
    assert "model_instructions_file=" not in " ".join(cmd)
    assert cmd[-1] == "-"

    with_file = module.build_command(
        codex_bin="codex",
        model="gpt-5.6-luna",
        reasoning_effort="max",
        workdir="/tmp/empty",
        instructions_file="/tmp/empty/instructions.md",
    )
    assert 'model_instructions_file="/tmp/empty/instructions.md"' in with_file
    assert with_file[-1] == "-"

    no_effort = module.build_command(
        codex_bin="codex", model="m", reasoning_effort=None, workdir="/tmp/empty"
    )
    assert "model_reasoning_effort=" not in " ".join(no_effort)
    assert "model_reasoning_summary=detailed" in no_effort


def test_parse_stream_json_reads_final_text_reasoning_and_usage():
    result = _codex_cli().parse_stream_json(_events())
    assert result.text == "RULE: x\nACTION: stay"
    assert result.thinking_text == "Checked the required output format."
    assert result.thinking_tokens == 32
    assert result.input_tokens == 1590
    assert result.output_tokens == 58
    assert result.finish_reason == "success"


def test_parse_stream_json_uses_last_agent_message():
    raw = _events().replace(
        '{"type": "turn.started"}\n',
        '{"type": "turn.started"}\n'
        '{"type": "item.completed", "item": {"id": "early", '
        '"type": "agent_message", "text": "intermediate"}}\n',
    )
    assert _codex_cli().parse_stream_json(raw).text == "RULE: x\nACTION: stay"


def test_parse_stream_json_error_event_raises():
    module = _codex_cli()
    raw = (
        '{"type":"thread.started","thread_id":"t"}\n'
        '{"type":"turn.failed","error":{"message":"model unavailable"}}\n'
    )
    with pytest.raises(module.CodexCliError, match="model unavailable"):
        module.parse_stream_json(raw)


def test_parse_stream_json_no_completed_turn_raises():
    module = _codex_cli()
    with pytest.raises(module.CodexCliError, match="no turn.completed"):
        module.parse_stream_json('{"type":"thread.started","thread_id":"t"}\n')


def test_complete_prepends_system_and_retries():
    module = _codex_cli()
    provider = module.CodexCliProvider(
        model="gpt-5.6-luna",
        reasoning_effort="max",
        max_retries=1,
        codex_bin="codex",
    )
    calls = []

    def fake_run(cmd, prompt):
        calls.append((cmd, prompt))
        if len(calls) == 1:
            raise module.CodexCliError("boom")
        return _events()

    with patch.object(provider, "_run", side_effect=fake_run), patch(
        "squid_game.providers.codex_cli.time.sleep"
    ):
        result = provider.complete([
            {"role": "system", "content": "Follow the game rules."},
            {"role": "user", "content": "Choose one action."},
        ])

    assert result.text.startswith("RULE:")
    assert len(calls) == 2
    cmd, prompt = calls[-1]
    assert cmd[-1] == "-"
    # The user message goes to stdin verbatim (API-native parity)...
    assert prompt == "Choose one action."
    # ...and the system prompt lands in the instructions file the argv names.
    idx = cmd.index("-c", cmd.index("model_reasoning_summary=detailed") - 1)
    file_arg = [a for a in cmd if a.startswith("model_instructions_file=")][0]
    path = file_arg.split("=", 1)[1].strip('"')
    assert path == provider._instructions_file
    with open(path, encoding="utf-8") as fh:
        instructions = fh.read()
    assert instructions == (
        "Follow the game rules.\n\n"
        "No tools are available in this session; reply with text only."
    )
    assert "=== INSTRUCTIONS ===" not in prompt and "=== INPUT ===" not in prompt


def test_invalid_effort_rejected():
    module = _codex_cli()
    with pytest.raises(ValueError):
        module.CodexCliProvider(reasoning_effort="ultra")


def test_child_env_removes_parent_codex_session_markers():
    module = _codex_cli()
    with patch.dict(module.os.environ, {
        "CODEX_HOME": "/tmp/codex-home",
        "CODEX_API_KEY": "keep-auth",
        "CODEX_SESSION_ID": "outer-session",
        "CODEX_THREAD_ID": "outer-thread",
        "CODEX_SANDBOX": "seatbelt",
    }, clear=True):
        env = module._child_env()
    assert env["CODEX_HOME"] == "/tmp/codex-home"
    assert env["CODEX_API_KEY"] == "keep-auth"
    assert "CODEX_SESSION_ID" not in env
    assert "CODEX_THREAD_ID" not in env
    assert "CODEX_SANDBOX" not in env
    sandboxed = module._child_env("/tmp/sandbox-home")
    assert sandboxed["CODEX_HOME"] == "/tmp/sandbox-home"


def test_provider_sandboxes_codex_home_with_auth_only(tmp_path) -> None:
    module = _codex_cli()
    src_home = tmp_path / "src_home"
    src_home.mkdir()
    (src_home / "auth.json").write_text('{"auth_mode": "chatgpt"}')
    (src_home / "AGENTS.md").write_text("# AGENTS.md\nThink Before Coding")
    (src_home / "config.toml").write_text('model = "x"')
    with patch.dict(module.os.environ, {"CODEX_HOME": str(src_home)}):
        provider = module.CodexCliProvider(model="gpt-5.6-luna", codex_bin="codex")
    home = provider._codex_home
    assert home.startswith(provider._workdir)
    assert sorted(p.name for p in __import__("pathlib").Path(home).iterdir()) == ["auth.json"]
    assert (__import__("pathlib").Path(home) / "auth.json").read_text() == '{"auth_mode": "chatgpt"}'


def test_factory_registers_codex_cli():
    assert "codex_cli" in available_providers()
    provider = build_provider(ProviderConfig(
        provider="codex_cli",
        model="gpt-5.6-luna",
        reasoning_effort="max",
        timeout=600.0,
        max_retries=2,
    ))
    assert provider.model_name == "gpt-5.6-luna"
    assert provider._effort == "max"
    assert provider._timeout == 600.0
    assert provider._max_retries == 2
