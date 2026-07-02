"""Unit tests for the LLM Arena RemoteProvider response parsing + guards."""

from __future__ import annotations

import pytest

from interface.remote_provider import RemoteEndpointError, RemoteProvider


def test_parse_openai_chat_shape_with_reasoning_and_usage():
    text, thinking, think_tok, in_tok, out_tok = RemoteProvider._parse(
        {
            "choices": [
                {"message": {"content": "ACTION: go_left", "reasoning_content": "red -> left"}}
            ],
            "usage": {
                "prompt_tokens": 12,
                "completion_tokens": 3,
                "completion_tokens_details": {"reasoning_tokens": 9},
            },
        }
    )
    assert text == "ACTION: go_left"
    assert thinking == "red -> left"
    assert (think_tok, in_tok, out_tok) == (9, 12, 3)


def test_parse_openai_legacy_completion_shape():
    text, *_ = RemoteProvider._parse({"choices": [{"text": "P_CORRECT: 60"}]})
    assert text == "P_CORRECT: 60"


@pytest.mark.parametrize("key", ["content", "text", "completion", "response", "output", "answer"])
def test_parse_flat_custom_shapes(key):
    text, thinking, think_tok, _in, out_tok = RemoteProvider._parse({key: "CHOICE: CONTINUE"})
    assert text == "CHOICE: CONTINUE"
    assert thinking is None
    # No usage supplied -> output tokens estimated by whitespace split.
    assert out_tok == 2


def test_parse_bare_string_body():
    text, *_ = RemoteProvider._parse("42")
    assert text == "42"


def test_parse_reasoning_tokens_estimated_from_text_when_usage_absent():
    _text, thinking, think_tok, _in, _out = RemoteProvider._parse(
        {"content": "ok", "reasoning": "two words"}
    )
    assert thinking == "two words"
    assert think_tok == 2  # estimated from split()


def test_parse_missing_answer_raises():
    with pytest.raises(RemoteEndpointError):
        RemoteProvider._parse({"unexpected": 1})
    with pytest.raises(RemoteEndpointError):
        RemoteProvider._parse({"content": ""})


@pytest.mark.parametrize("bad_url", ["ftp://x/y", "not-a-url", "file:///etc/passwd", ""])
def test_non_http_url_rejected(bad_url):
    with pytest.raises(ValueError):
        RemoteProvider(bad_url, "m")


def test_auth_header_is_attached():
    p = RemoteProvider(
        "https://example.com/v1/chat/completions",
        "my-model",
        auth_header="Authorization",
        auth_value="Bearer sk-test",
    )
    assert p._headers["Authorization"] == "Bearer sk-test"
    assert p.model_name == "my-model"
