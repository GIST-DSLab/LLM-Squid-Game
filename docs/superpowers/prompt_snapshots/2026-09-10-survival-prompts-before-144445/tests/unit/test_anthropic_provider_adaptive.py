"""AnthropicProvider request shapes: legacy budget path vs adaptive thinking.

Claude 4.6+ / Claude 5 reject ``budget_tokens`` and the sampling knobs with a
400 and only ever return a thinking *summary*; older models keep the legacy
shape. These tests pin both request builders and the reasoning-investment
estimate without touching the network.
"""

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from squid_game.providers.anthropic_provider import (
    AnthropicProvider,
    uses_adaptive_thinking,
)


def _provider(model: str, **kw) -> tuple[AnthropicProvider, MagicMock]:
    p = AnthropicProvider(model=model, api_key="test-key", **kw)
    client = MagicMock()
    p._client = client
    return p, client


def _response(text: str, thinking: str | None, output_tokens: int):
    content = []
    if thinking is not None:
        content.append(SimpleNamespace(type="thinking", thinking=thinking))
    content.append(SimpleNamespace(type="text", text=text))
    return SimpleNamespace(
        content=content,
        usage=SimpleNamespace(input_tokens=100, output_tokens=output_tokens),
        stop_reason="end_turn",
    )


@pytest.mark.parametrize(
    "model,expected",
    [
        ("claude-opus-5", True),
        ("claude-sonnet-5", True),
        ("claude-opus-4-6", True),
        ("claude-opus-4-8", True),
        ("claude-sonnet-4-6", True),
        ("claude-fable-5-1", True),
        ("claude-sonnet-4-20250514", False),
        ("claude-haiku-4-5", False),
        ("claude-opus-4-5", False),
    ],
)
def test_uses_adaptive_thinking(model, expected):
    assert uses_adaptive_thinking(model) is expected


def test_adaptive_request_shape_and_ri_estimate():
    p, client = _provider(
        "claude-opus-5", enable_thinking=True, reasoning_effort="medium",
        top_p=0.95, top_k=40,
    )
    client.messages.create.return_value = _response(
        "RULE: x\nACTION: stay", "summary of reasoning", output_tokens=900
    )
    result = p.complete(
        [{"role": "system", "content": "sys"}, {"role": "user", "content": "hi"}],
        temperature=1.0, max_tokens=4096,
    )
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["thinking"] == {"type": "adaptive", "display": "summarized"}
    assert kwargs["output_config"] == {"effort": "medium"}
    assert kwargs["system"] == "sys"
    assert kwargs["messages"] == [{"role": "user", "content": "hi"}]
    for banned in ("temperature", "top_p", "top_k"):
        assert banned not in kwargs
    # summary text is carried, tokens are output minus visible-answer estimate
    assert result.thinking_text == "summary of reasoning"
    assert result.thinking_tokens == 900 - len("RULE: x\nACTION: stay") // 4
    assert result.text == "RULE: x\nACTION: stay"


def test_adaptive_without_effort_omits_output_config():
    p, client = _provider("claude-sonnet-5", enable_thinking=True)
    client.messages.create.return_value = _response("ok", "", output_tokens=10)
    p.complete([{"role": "user", "content": "hi"}])
    assert "output_config" not in client.messages.create.call_args.kwargs


def test_legacy_request_keeps_budget_path():
    p, client = _provider(
        "claude-sonnet-4-20250514", enable_thinking=True, thinking_budget=2048,
        top_p=0.9,
    )
    client.messages.create.return_value = _response("ok", "raw cot", output_tokens=50)
    result = p.complete([{"role": "user", "content": "hi"}], temperature=0.3)
    kwargs = client.messages.create.call_args.kwargs
    assert kwargs["thinking"] == {"type": "enabled", "budget_tokens": 2048}
    assert kwargs["temperature"] == 1.0  # forced when thinking is on
    assert kwargs["top_p"] == 0.9
    assert "output_config" not in kwargs
    assert result.thinking_text == "raw cot"
    assert result.thinking_tokens == len("raw cot") // 4


def test_invalid_effort_rejected():
    with pytest.raises(ValueError):
        AnthropicProvider(model="claude-opus-5", api_key="k", reasoning_effort="ultra")
