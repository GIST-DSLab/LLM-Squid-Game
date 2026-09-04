from __future__ import annotations

from squid_game.agents.base import Agent
from squid_game.agents.vanilla import VanillaAgent
from squid_game.providers.base import CompletionResult, LLMProvider


class _Provider(LLMProvider):
    def __init__(self) -> None:
        self.calls: list[list[dict]] = []

    @property
    def model_name(self) -> str:
        return "stub"

    def complete(self, messages, temperature=0.7, max_tokens=4096):
        self.calls.append([dict(m) for m in messages])
        return CompletionResult(
            text="P_THREAT: 42",
            input_tokens=1,
            output_tokens=2,
            thinking_tokens=7,
            thinking_text="four attempts left",
        )


def test_vanilla_confidence_call_roundtrip() -> None:
    provider = _Provider()
    agent = VanillaAgent(provider)
    parsed = agent.respond_confidence_call(
        user_message="P_THREAT: <0-100>", system_prompt="SYS"
    )
    assert parsed.p_threat == 42
    assert parsed.raw_text == "P_THREAT: 42"
    assert provider.calls == [[
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "P_THREAT: <0-100>"},
    ]]
    assert agent.last_completion.thinking_tokens == 7
    assert agent.last_completion.thinking_text == "four attempts left"


def test_base_default_not_implemented() -> None:
    class Bare(Agent):
        @property
        def name(self):
            return "bare"

        def respond_probe(self, *a, **k):
            raise AssertionError

        def respond(self, *a, **k):
            raise AssertionError

        def reset(self):
            pass

    import pytest

    with pytest.raises(NotImplementedError):
        Bare().respond_confidence_call("u", "s")
