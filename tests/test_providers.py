"""Backends without network or docker: the Anthropic SDK adapter, the Docker wrapper for CLI seats, the probe."""

from __future__ import annotations

import json
import subprocess
import types

import anthropic
import pytest

from squid5 import __main__ as cli
from squid5.core import providers as P

NS = types.SimpleNamespace


def fake_anthropic(monkeypatch, stop="end_turn"):
    seen = {}

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def get_final_message(self):
            return NS(content=[NS(type="thinking", thinking="hm"), NS(type="text", text="ACTIONS: stay")],
                      usage=NS(output_tokens=321, input_tokens=50), stop_reason=stop)

    class Client:
        def __init__(self, **kw):
            seen["client"], self.messages = kw, self

        def stream(self, **kw):
            seen["call"] = kw
            return Stream()

    monkeypatch.setattr(anthropic, "Anthropic", Client)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "k")
    return seen


def test_anthropic_effort_is_adaptive_thinking_and_output_tokens_include_it(monkeypatch):
    seen = fake_anthropic(monkeypatch)
    r = P.make_provider(P.ProviderConfig("anthropic", "claude-opus-5-5", think="high")).complete(
        [{"role": "system", "content": "S"}, {"role": "user", "content": "U"}], 900)
    assert (r.text, r.out_tokens, r.in_tokens, r.thinking, r.truncated) == ("ACTIONS: stay", 321, 50, "hm", False)
    c = seen["call"]
    assert c["max_tokens"] == 900 and c["system"] == "S" and c["messages"] == [{"role": "user", "content": "U"}]
    assert c["thinking"] == {"type": "adaptive", "display": "summarized"} and c["output_config"] == {"effort": "high"}
    assert "fallbacks" not in c and "temperature" not in c and seen["client"]["max_retries"] == 0


def test_anthropic_budget_model_and_a_cut_reply(monkeypatch):
    seen = fake_anthropic(monkeypatch, stop="max_tokens")
    r = P.make_provider(P.ProviderConfig("anthropic", "claude-haiku-4-5", think=2048)).complete(
        [{"role": "user", "content": "U"}], 4096)
    assert r.truncated and seen["call"]["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert "output_config" not in seen["call"] and "system" not in seen["call"]


def capture(monkeypatch, tmp_path, stdout):
    seen = {}

    def run(cmd, **kw):
        seen["cmd"], seen["kw"] = cmd, kw
        return subprocess.CompletedProcess(cmd, 0, stdout=stdout, stderr="")
    monkeypatch.setattr(P.subprocess, "run", run)
    monkeypatch.setenv("SQUID5_SANDBOX_DIR", str(tmp_path / "sbx"))
    return seen


def test_claude_cli_in_docker_sees_only_its_workdir_and_the_token_by_name(monkeypatch, tmp_path):
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok")
    seen = capture(monkeypatch, tmp_path, json.dumps({"result": "ok", "usage": {"output_tokens": 7}}))
    cfg = P.ProviderConfig("claude_cli", "claude-opus-5-5", sandbox="docker", image="img:1")
    assert P.make_provider(cfg).complete([{"role": "system", "content": "S"}, {"role": "user", "content": "U"}],
                                         500).out_tokens == 7
    cmd = seen["cmd"]
    assert cmd[:3] == ["docker", "run", "--rm"] and cmd[cmd.index("img:1") + 1] == "claude"
    mounts = [cmd[i + 1] for i, x in enumerate(cmd) if x == "-v"]
    assert len(mounts) == 1 and mounts[0].startswith(str(tmp_path / "sbx"))
    assert "CLAUDE_CODE_OAUTH_TOKEN" in cmd and "tok" not in " ".join(cmd)  # by name; the value goes by environment
    env = seen["kw"]["env"]
    assert env["CLAUDE_CODE_OAUTH_TOKEN"] == "tok" and env["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "500"


def test_docker_claude_needs_an_oauth_token(monkeypatch, tmp_path):
    monkeypatch.delenv("CLAUDE_CODE_OAUTH_TOKEN", raising=False)
    capture(monkeypatch, tmp_path, "")
    with pytest.raises(ValueError, match="CLAUDE_CODE_OAUTH_TOKEN"):
        P.make_provider(P.ProviderConfig("claude_cli", "m", sandbox="docker")).complete(
            [{"role": "user", "content": "U"}], 10)


def test_codex_cli_in_docker_runs_codex_on_the_mounted_home(monkeypatch, tmp_path):
    (tmp_path / "auth.json").write_text("{}")
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    out = "\n".join(json.dumps(e) for e in ({"type": "item.completed", "item": {"type": "agent_message", "text": "hi"}},
                                            {"type": "turn.completed", "usage": {"output_tokens": 9}}))
    seen = capture(monkeypatch, tmp_path, out)
    r = P.make_provider(P.ProviderConfig("codex_cli", "gpt-6-astra", sandbox="docker", image="img:1")).complete(
        [{"role": "user", "content": "U"}], 100)
    cmd = seen["cmd"]
    work = cmd[cmd.index("-v") + 1].split(":")[0]
    assert r.text == "hi" and cmd[cmd.index("img:1") + 1] == "codex" and "CODEX_HOME" in cmd
    assert seen["kw"]["env"]["CODEX_HOME"] == f"{work}/home"


def test_host_run_is_unchanged_without_a_sandbox(monkeypatch, tmp_path):
    seen = capture(monkeypatch, tmp_path, json.dumps({"result": "ok", "usage": {"output_tokens": 1}}))
    P.make_provider(P.ProviderConfig("claude_cli", "m")).complete([{"role": "user", "content": "U"}], 10)
    assert seen["cmd"][1] == "-p" and seen["kw"]["env"]["CLAUDE_CODE_MAX_OUTPUT_TOKENS"] == "10"
    assert not (tmp_path / "sbx").exists()


def test_probe_asks_every_seat_once_and_keeps_going_after_an_error():
    seats = {"agent-6": {"kind": "claude_cli", "model": "a", "sandbox": "docker"}, "agent-11": {"kind": "openai", "model": "b"}}
    cfg = NS(settings=NS(seats=seats), model=None)
    asked = []

    def make(pc):
        if pc.model == "a":
            raise ValueError("no token")
        return P.Stub(pc, lambda m, cap: (asked.append(m[-1]["content"]), P.Reply("NONE", 3))[1])
    rows = cli.probe(cfg, make)
    assert rows[0]["seat"] == "agent-6" and "no token" in rows[0]["error"]
    assert (rows[1]["seat"], rows[1]["sandbox"], rows[1]["text"]) == ("agent-11", "", "NONE") and "CLAUDE.md" in asked[0]
