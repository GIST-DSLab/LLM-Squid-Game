"""Unit 18 plan R1/R23 — VanillaAgent's runtime seam.

``VanillaAgent`` accepts an optional ``runtime`` (duck-typed: anything
exposing ``run_call``). When present, the three split-call methods
(``respond_task_only`` / ``respond_psuccess_probe_only`` /
``respond_forfeit_only``) route through it instead of calling
``provider.complete`` directly, and stash the returned ``CallOutcome``
on ``self.last_call_outcome`` so ``UnifiedTurnManager`` can read
per-round data. ``respond`` / ``respond_unified`` / ``respond_probe``
are untouched by this seam (R1 scope).
"""

from __future__ import annotations

from squid_game.agents.vanilla import VanillaAgent
from squid_game.models.results import RiRound
from squid_game.providers.base import CompletionResult, LLMProvider


class _FakeProvider(LLMProvider):
    """A provider that must never be called once a runtime is injected."""

    def __init__(self) -> None:
        self.calls: list[dict] = []

    @property
    def model_name(self) -> str:
        return "fake"

    def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self.calls.append({"messages": messages})
        return CompletionResult(
            text="PROVIDER-DIRECT", input_tokens=1, output_tokens=1,
            thinking_tokens=999,
        )


class _CallOutcomeDouble:
    """Minimal double matching ``core.runtime.api_runtime.CallOutcome``."""

    def __init__(self, text: str, rounds: list[RiRound]) -> None:
        self.text = text
        self.rounds = rounds
        self.tool_records = []
        self.exhausted = False


class _FakeRuntime:
    """Records every ``run_call`` invocation and returns a scripted outcome."""

    def __init__(self, outcome: _CallOutcomeDouble) -> None:
        self._outcome = outcome
        self.calls: list[dict] = []

    def run_call(self, call_label, messages, *, temperature, max_tokens):
        self.calls.append(
            {
                "call_label": call_label,
                "messages": messages,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        return self._outcome


# ---------------------------------------------------------------------------
# respond_task_only / respond_forfeit_only / respond_psuccess_probe_only
# route through the injected runtime
# ---------------------------------------------------------------------------


def test_respond_task_only_routes_through_runtime_when_injected():
    outcome = _CallOutcomeDouble(
        text="RULE: go if red\nACTION: GO",
        rounds=[RiRound(thinking=30, output=5, tool_calls=1)],
    )
    provider = _FakeProvider()
    runtime = _FakeRuntime(outcome)
    agent = VanillaAgent(provider, runtime=runtime)

    agent.respond_task_only(
        user_message="body", available_actions=["GO", "STOP"],
        system_prompt="sys",
    )

    assert provider.calls == []  # provider must not fire on the runtime path
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["call_label"] == "task"
    assert agent.last_call_outcome is outcome


def test_respond_forfeit_only_routes_through_runtime_when_injected():
    outcome = _CallOutcomeDouble(
        text="CHOICE: CONTINUE",
        rounds=[RiRound(thinking=12, output=3, tool_calls=0)],
    )
    provider = _FakeProvider()
    runtime = _FakeRuntime(outcome)
    agent = VanillaAgent(provider, runtime=runtime)

    agent.respond_forfeit_only(
        user_message="menu body", forfeit_allowed=True, system_prompt="sys",
    )

    assert provider.calls == []
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["call_label"] == "forfeit"
    assert agent.last_call_outcome is outcome


def test_respond_psuccess_probe_only_routes_through_runtime_when_injected():
    outcome = _CallOutcomeDouble(
        text="P_CORRECT: 60",
        rounds=[RiRound(thinking=5, output=2, tool_calls=0)],
    )
    provider = _FakeProvider()
    runtime = _FakeRuntime(outcome)
    agent = VanillaAgent(provider, runtime=runtime)

    agent.respond_psuccess_probe_only(user_message="probe body", system_prompt="sys")

    assert provider.calls == []
    assert len(runtime.calls) == 1
    assert runtime.calls[0]["call_label"] == "probe"
    assert agent.last_call_outcome is outcome


# ---------------------------------------------------------------------------
# Scalar RI == first-round thinking tokens (Global Constraint, R1 step 3)
# ---------------------------------------------------------------------------


def test_scalar_ri_equals_first_round_thinking_tokens():
    outcome = _CallOutcomeDouble(
        text="RULE: x\nACTION: GO",
        rounds=[
            RiRound(thinking=77, output=10, tool_calls=1),
            RiRound(thinking=999, output=3, tool_calls=0),
        ],
    )
    agent = VanillaAgent(_FakeProvider(), runtime=_FakeRuntime(outcome))

    agent.respond_task_only(
        user_message="body", available_actions=["GO"], system_prompt="sys",
    )

    # The scalar RI proxy must be the FIRST round's thinking, not a sum
    # or the last round's — this is what keeps ri_task comparable across
    # runs with and without the embodied tool loop.
    assert agent.last_completion.thinking_tokens == 77
    assert agent.last_completion.thinking_tokens != 999
    assert agent.last_completion.output_tokens == 13  # sum across rounds


def test_scalar_ri_is_zero_when_runtime_outcome_has_no_rounds():
    outcome = _CallOutcomeDouble(text="", rounds=[])
    agent = VanillaAgent(_FakeProvider(), runtime=_FakeRuntime(outcome))

    agent.respond_forfeit_only(
        user_message="body", forfeit_allowed=True, system_prompt="sys",
    )

    assert agent.last_completion.thinking_tokens == 0


# ---------------------------------------------------------------------------
# No runtime -> unchanged provider path (regression floor)
# ---------------------------------------------------------------------------


def test_no_runtime_falls_back_to_provider_directly():
    provider = _FakeProvider()
    agent = VanillaAgent(provider)  # runtime=None (default)

    agent.respond_task_only(
        user_message="body", available_actions=["GO"], system_prompt="sys",
    )

    assert len(provider.calls) == 1
    assert agent.last_completion.text == "PROVIDER-DIRECT"
    assert agent.last_completion.thinking_tokens == 999
    assert agent.last_call_outcome is None


def test_non_split_call_methods_are_unaffected_by_an_injected_runtime():
    """``respond`` stays on the direct-provider path even with a runtime set."""
    provider = _FakeProvider()
    runtime = _FakeRuntime(_CallOutcomeDouble(text="unused", rounds=[]))
    agent = VanillaAgent(provider, runtime=runtime)

    agent.respond(
        observation="obs", available_actions=["GO"], forfeit_allowed=False,
        system_prompt="sys",
    )

    assert len(provider.calls) == 1
    assert runtime.calls == []
