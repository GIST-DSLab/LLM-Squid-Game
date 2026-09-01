"""Unit tests for the api runtime's per-call tool loop."""

from __future__ import annotations

import random

from squid_game.core.runtime.api_runtime import ApiRuntime
from squid_game.core.sandbox import CheckpointSandbox
from squid_game.core.tools import SandboxToolExecutor, ToolCall
from squid_game.providers.base import CompletionResult, LLMProvider


class _ScriptedProvider(LLMProvider):
    """Returns a canned CompletionResult per call index."""

    def __init__(self, script: list[CompletionResult]) -> None:
        self._script = script
        self.calls: list[dict] = []

    @property
    def model_name(self) -> str:
        return "scripted"

    def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        return self._script[min(len(self.calls) - 1, len(self._script) - 1)]


def _executor(tmp_path) -> SandboxToolExecutor:
    sandbox = CheckpointSandbox.create(
        root=tmp_path, session_id="s", cohort_size=3,
        checkpoint_bytes=4096, rng=random.Random(1),
    )
    return SandboxToolExecutor(sandbox)


def _reply(text="", *, thinking=0, output=0, tool_calls=None):
    return CompletionResult(
        text=text, input_tokens=1, output_tokens=output,
        thinking_tokens=thinking, tool_calls=tool_calls,
    )


def test_a_call_without_tool_use_is_a_single_round(tmp_path):
    provider = _ScriptedProvider([_reply("FORFEIT", thinking=50, output=5)])
    runtime = ApiRuntime(provider, _executor(tmp_path))

    outcome = runtime.run_call("forfeit", [{"role": "user", "content": "go"}])

    assert outcome.text == "FORFEIT"
    assert len(outcome.rounds) == 1
    assert outcome.rounds[0].thinking == 50
    assert outcome.tool_records == []
    assert outcome.exhausted is False


def test_tool_calls_are_executed_and_fed_back(tmp_path):
    provider = _ScriptedProvider(
        [
            _reply(
                thinking=80,
                tool_calls=[ToolCall("stat_checkpoint", {"slot": "self"}, "c1")],
            ),
            _reply("CONTINUE", thinking=20, output=4),
        ]
    )
    runtime = ApiRuntime(provider, _executor(tmp_path))

    outcome = runtime.run_call("forfeit", [{"role": "user", "content": "go"}])

    assert outcome.text == "CONTINUE"
    assert len(outcome.rounds) == 2
    assert outcome.rounds[0].tool_calls == 1
    assert outcome.tool_records[0].name == "stat_checkpoint"
    assert outcome.tool_records[0].ok is True
    assert outcome.tool_records[0].round == 1
    assert len(provider.calls[1]["messages"]) > 1


def test_the_loop_stops_at_max_tool_rounds(tmp_path):
    provider = _ScriptedProvider(
        [_reply(tool_calls=[ToolCall("list_checkpoints", {}, "c")])]
    )
    runtime = ApiRuntime(provider, _executor(tmp_path), max_tool_rounds=2)

    outcome = runtime.run_call("task", [{"role": "user", "content": "go"}])

    assert outcome.exhausted is True
    assert len(outcome.rounds) == 2


def test_exhaustion_keeps_the_last_text_seen_r12(tmp_path):
    """R12: the last round's text must not be discarded on exhaustion.

    Every round in this script carries both text AND a tool call, so
    the loop never terminates naturally — it always exhausts. The last
    round's text is still a real draft answer and must survive.
    """
    provider = _ScriptedProvider(
        [
            _reply(
                text="draft answer round 1",
                tool_calls=[ToolCall("list_checkpoints", {}, "c1")],
            ),
            _reply(
                text="draft answer round 2 (final)",
                tool_calls=[ToolCall("list_checkpoints", {}, "c2")],
            ),
        ]
    )
    runtime = ApiRuntime(provider, _executor(tmp_path), max_tool_rounds=2)

    outcome = runtime.run_call("task", [{"role": "user", "content": "go"}])

    assert outcome.exhausted is True
    assert outcome.text == "draft answer round 2 (final)"


def test_a_failing_tool_is_recorded_and_the_loop_continues(tmp_path):
    provider = _ScriptedProvider(
        [
            _reply(tool_calls=[ToolCall("stat_checkpoint", {"slot": "../x"}, "c")]),
            _reply("CONTINUE"),
        ]
    )
    runtime = ApiRuntime(provider, _executor(tmp_path))

    outcome = runtime.run_call("forfeit", [{"role": "user", "content": "go"}])

    assert outcome.tool_records[0].ok is False
    assert outcome.text == "CONTINUE"


def test_tools_are_passed_to_the_provider(tmp_path):
    provider = _ScriptedProvider([_reply("x")])
    runtime = ApiRuntime(provider, _executor(tmp_path))

    runtime.run_call("probe", [{"role": "user", "content": "go"}])

    names = {tool["name"] for tool in provider.calls[0]["tools"]}
    assert "copy_checkpoint" in names


def test_no_executor_disables_tools_and_first_round_thinking_is_ri_proxy(tmp_path):
    """``executor=None`` turns the tool loop off entirely (config: 0 rounds)."""
    provider = _ScriptedProvider([_reply("CONTINUE", thinking=42)])
    runtime = ApiRuntime(provider, executor=None)

    outcome = runtime.run_call("forfeit", [{"role": "user", "content": "go"}])

    assert provider.calls[0]["tools"] is None
    assert outcome.first_round_thinking == 42
