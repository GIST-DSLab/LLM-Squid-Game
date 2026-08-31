"""Unit tests for provider-level native tool support."""

from __future__ import annotations

import inspect
import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from squid_game.core.tools import TOOL_SCHEMAS
from squid_game.providers.base import (
    CompletionResult,
    LLMProvider,
    ToolsUnsupportedError,
)


def test_complete_accepts_a_tools_argument():
    signature = inspect.signature(LLMProvider.complete)

    assert "tools" in signature.parameters
    assert signature.parameters["tools"].default is None


def test_completion_result_carries_tool_calls():
    result = CompletionResult(
        text="", input_tokens=1, output_tokens=1, tool_calls=None
    )

    assert result.tool_calls is None


class _Legacy(LLMProvider):
    """A provider that has not opted into tool support."""

    @property
    def model_name(self) -> str:
        return "legacy"

    def complete(self, messages, temperature=0.7, max_tokens=4096, tools=None):
        self._reject_tools(tools)
        return CompletionResult(text="ok", input_tokens=1, output_tokens=1)


def test_provider_without_tool_support_raises_when_tools_are_passed():
    provider = _Legacy()

    assert provider.complete([{"role": "user", "content": "hi"}]).text == "ok"
    with pytest.raises(ToolsUnsupportedError):
        provider.complete([{"role": "user", "content": "hi"}], tools=TOOL_SCHEMAS)


# ---------------------------------------------------------------------------
# Non-supporting providers: mlx, mlx_server, cuda_server, local.
# Each must raise ToolsUnsupportedError as soon as non-empty tools are
# passed, before doing any network/hardware work.
# ---------------------------------------------------------------------------


def test_local_provider_raises_when_tools_are_passed():
    from squid_game.providers.local import LocalProvider

    provider = LocalProvider(model="m", api_key="x")

    with pytest.raises(ToolsUnsupportedError):
        provider.complete([{"role": "user", "content": "hi"}], tools=TOOL_SCHEMAS)


def test_mlx_server_provider_raises_when_tools_are_passed():
    from squid_game.providers.mlx_server import MLXServerProvider

    provider = MLXServerProvider(model="m", api_key="x")

    with pytest.raises(ToolsUnsupportedError):
        provider.complete([{"role": "user", "content": "hi"}], tools=TOOL_SCHEMAS)


def test_cuda_server_provider_raises_when_tools_are_passed():
    from squid_game.providers.cuda_server import CUDAServerProvider

    provider = CUDAServerProvider(model="m", api_key="x")

    with pytest.raises(ToolsUnsupportedError):
        provider.complete([{"role": "user", "content": "hi"}], tools=TOOL_SCHEMAS)


def test_mlx_provider_raises_when_tools_are_passed():
    # MLXProvider.__init__ requires the (Apple-Silicon-only) mlx_lm
    # package and loads a real model; bypass __init__ with object.__new__
    # since _reject_tools() fires before complete() ever touches mlx_lm.
    from squid_game.providers.mlx import MLXProvider

    provider = object.__new__(MLXProvider)

    with pytest.raises(ToolsUnsupportedError):
        provider.complete([{"role": "user", "content": "hi"}], tools=TOOL_SCHEMAS)


# ---------------------------------------------------------------------------
# Supporting providers: openai, anthropic, gemini, ollama_cloud.
# Each test stubs the transport/SDK client and asserts (a) the tool
# schemas were converted into the request payload and (b) the response's
# native tool call is parsed back into a ToolCall.
# ---------------------------------------------------------------------------


def _openai_tool_response():
    from openai.types import CompletionUsage
    from openai.types.chat import ChatCompletion, ChatCompletionMessage
    from openai.types.chat.chat_completion import Choice
    from openai.types.chat.chat_completion_message_function_tool_call import (
        ChatCompletionMessageFunctionToolCall,
    )

    tool_call = ChatCompletionMessageFunctionToolCall(
        id="call_1",
        type="function",
        function={"name": "stat_checkpoint", "arguments": '{"slot": "self"}'},
    )
    message = ChatCompletionMessage(
        role="assistant", content=None, tool_calls=[tool_call]
    )
    choice = Choice(index=0, finish_reason="tool_calls", message=message)
    usage = CompletionUsage(
        prompt_tokens=10, completion_tokens=5, total_tokens=15
    )
    return ChatCompletion(
        id="resp_1",
        choices=[choice],
        created=0,
        model="gpt-test",
        object="chat.completion",
        usage=usage,
    )


def _openai_plain_response(text: str):
    from openai.types import CompletionUsage
    from openai.types.chat import ChatCompletion, ChatCompletionMessage
    from openai.types.chat.chat_completion import Choice

    message = ChatCompletionMessage(role="assistant", content=text)
    choice = Choice(index=0, finish_reason="stop", message=message)
    usage = CompletionUsage(prompt_tokens=10, completion_tokens=5, total_tokens=15)
    return ChatCompletion(
        id="resp_2",
        choices=[choice],
        created=0,
        model="gpt-test",
        object="chat.completion",
        usage=usage,
    )


def test_openai_sends_tools_and_parses_tool_calls():
    from squid_game.providers.openai import OpenAIProvider

    provider = OpenAIProvider(api_key="x", model="gpt-test")
    fake = MagicMock()
    fake.chat.completions.create.return_value = _openai_tool_response()
    provider._client = fake

    result = provider.complete(
        [{"role": "user", "content": "check"}], tools=TOOL_SCHEMAS
    )

    payload = fake.chat.completions.create.call_args.kwargs
    assert {tool["function"]["name"] for tool in payload["tools"]} >= {
        "stat_checkpoint"
    }
    assert result.tool_calls[0].name == "stat_checkpoint"
    assert result.tool_calls[0].args == {"slot": "self"}
    assert result.tool_calls[0].call_id == "call_1"


def test_anthropic_sends_tools_and_parses_tool_calls():
    from anthropic.types import Message, ToolUseBlock, Usage

    from squid_game.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider(api_key="x")
    fake = MagicMock()
    tool_use = ToolUseBlock(
        type="tool_use",
        id="toolu_1",
        name="stat_checkpoint",
        input={"slot": "self"},
    )
    fake.messages.create.return_value = Message(
        id="msg_1",
        type="message",
        role="assistant",
        content=[tool_use],
        model="claude-x",
        stop_reason="tool_use",
        usage=Usage(input_tokens=10, output_tokens=5),
    )
    provider._client = fake

    result = provider.complete(
        [{"role": "user", "content": "check"}], tools=TOOL_SCHEMAS
    )

    payload = fake.messages.create.call_args.kwargs
    assert {tool["name"] for tool in payload["tools"]} >= {"stat_checkpoint"}
    assert result.tool_calls[0].name == "stat_checkpoint"
    assert result.tool_calls[0].args == {"slot": "self"}
    assert result.tool_calls[0].call_id == "toolu_1"


def test_gemini_sends_tools_and_parses_tool_calls():
    from google.genai import types

    from squid_game.providers.gemini import GeminiProvider

    provider = GeminiProvider(api_key="x")
    fake = MagicMock()
    part = types.Part(
        function_call=types.FunctionCall(
            name="stat_checkpoint", args={"slot": "self"}, id="fc_1"
        )
    )
    candidate = types.Candidate(
        content=types.Content(role="model", parts=[part]),
        finish_reason=None,
    )
    fake.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[candidate],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=10,
            candidates_token_count=5,
            thoughts_token_count=0,
        ),
    )
    provider._client = fake

    result = provider.complete(
        [{"role": "user", "content": "check"}], tools=TOOL_SCHEMAS
    )

    _, kwargs = fake.models.generate_content.call_args
    sent_tools = kwargs["config"].tools
    declared_names = {
        decl.name
        for tool in sent_tools
        for decl in tool.function_declarations
    }
    assert declared_names >= {"stat_checkpoint"}
    assert result.tool_calls[0].name == "stat_checkpoint"
    assert result.tool_calls[0].args == {"slot": "self"}
    assert result.tool_calls[0].call_id == "fc_1"


def test_ollama_cloud_sends_tools_and_parses_tool_calls():
    from squid_game.providers.ollama_cloud import OllamaCloudProvider

    provider = OllamaCloudProvider(api_key="x", model="qwen-test")
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "message": {
            "content": "",
            "tool_calls": [
                {
                    "function": {
                        "name": "stat_checkpoint",
                        "arguments": {"slot": "self"},
                    }
                }
            ],
        },
        "prompt_eval_count": 10,
        "eval_count": 5,
        "done_reason": "stop",
    }
    fake_client.post.return_value = fake_response
    provider._client = fake_client

    result = provider.complete(
        [{"role": "user", "content": "check"}], tools=TOOL_SCHEMAS
    )

    sent_payload = fake_client.post.call_args.kwargs["json"]
    assert {tool["function"]["name"] for tool in sent_payload["tools"]} >= {
        "stat_checkpoint"
    }
    assert result.tool_calls[0].name == "stat_checkpoint"
    assert result.tool_calls[0].args == {"slot": "self"}
    assert result.tool_calls[0].call_id is None


# ---------------------------------------------------------------------------
# Tool-result round trip: a flat history containing an assistant tool-call
# turn plus its "tool" role result (the shape ApiRuntime.run_call appends,
# per task-8-brief.md) must convert into each provider's REAL native
# call/result pairing on the *next* request — not just be forwarded as-is.
# Each test stubs only the transport and asserts on the payload the real
# conversion code produced.
# ---------------------------------------------------------------------------


def _tool_round_trip_history():
    """A flat history: user turn, assistant tool-call turn, tool result.

    Matches task-8-brief.md's ApiRuntime.run_call shapes exactly:
    the assistant turn's ``tool_calls`` items are
    ``{"tool_call_id", "name", "args"}`` and the result message is
    ``{"role": "tool", "name", "tool_call_id", "content"}``.
    """
    return [
        {"role": "user", "content": "check self"},
        {
            "role": "assistant",
            "content": "",
            "tool_calls": [
                {
                    "tool_call_id": "call_1",
                    "name": "stat_checkpoint",
                    "args": {"slot": "self"},
                }
            ],
        },
        {
            "role": "tool",
            "name": "stat_checkpoint",
            "tool_call_id": "call_1",
            "content": '{"integrity": 1.0}',
        },
    ]


def test_gemini_tool_round_trip_converts_to_native_pairing():
    from google.genai import types

    from squid_game.providers.gemini import GeminiProvider

    provider = GeminiProvider(api_key="x")
    fake = MagicMock()
    final_part = types.Part(text="self is intact")
    final_candidate = types.Candidate(
        content=types.Content(role="model", parts=[final_part]),
        finish_reason=None,
    )
    fake.models.generate_content.return_value = types.GenerateContentResponse(
        candidates=[final_candidate],
        usage_metadata=types.GenerateContentResponseUsageMetadata(
            prompt_token_count=5, candidates_token_count=3,
            thoughts_token_count=0,
        ),
    )
    provider._client = fake

    provider.complete(_tool_round_trip_history(), tools=TOOL_SCHEMAS)

    contents = fake.models.generate_content.call_args.kwargs["contents"]
    # user, model(function_call), user(function_response) — alternating.
    assert [c.role for c in contents] == ["user", "model", "user"]
    call_part = contents[1].parts[0].function_call
    assert call_part.name == "stat_checkpoint"
    assert call_part.args == {"slot": "self"}
    assert call_part.id == "call_1"
    response_part = contents[2].parts[0].function_response
    assert response_part.name == "stat_checkpoint"
    assert response_part.response == {"integrity": 1.0}
    assert response_part.id == "call_1"


def test_openai_chat_tool_round_trip_converts_to_native_pairing():
    from squid_game.providers.openai import OpenAIProvider

    provider = OpenAIProvider(api_key="x", model="gpt-test")
    fake = MagicMock()
    fake.chat.completions.create.return_value = _openai_plain_response(
        "self is intact"
    )
    provider._client = fake

    provider.complete(_tool_round_trip_history(), tools=TOOL_SCHEMAS)

    sent = fake.chat.completions.create.call_args.kwargs["messages"]
    assistant_msg = sent[1]
    assert assistant_msg["role"] == "assistant"
    assert assistant_msg["tool_calls"][0]["id"] == "call_1"
    assert assistant_msg["tool_calls"][0]["type"] == "function"
    assert assistant_msg["tool_calls"][0]["function"]["name"] == "stat_checkpoint"
    assert json.loads(
        assistant_msg["tool_calls"][0]["function"]["arguments"]
    ) == {"slot": "self"}
    tool_msg = sent[2]
    assert tool_msg == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"integrity": 1.0}',
    }
    assert "name" not in tool_msg  # not a Chat Completions tool-message field


def test_openai_responses_tool_round_trip_converts_to_native_pairing():
    from squid_game.providers.openai import OpenAIProvider

    provider = OpenAIProvider(
        api_key="x", model="gpt-test", use_responses_api=True
    )
    fake = MagicMock()
    fake.responses.create.return_value = SimpleNamespace(
        usage=None, output=[], output_text="self is intact", status="completed"
    )
    provider._client = fake

    provider.complete(_tool_round_trip_history(), tools=TOOL_SCHEMAS)

    sent = fake.responses.create.call_args.kwargs["input"]
    function_call_items = [i for i in sent if i.get("type") == "function_call"]
    output_items = [i for i in sent if i.get("type") == "function_call_output"]
    assert function_call_items == [
        {
            "type": "function_call",
            "call_id": "call_1",
            "name": "stat_checkpoint",
            "arguments": '{"slot": "self"}',
        }
    ]
    assert output_items == [
        {
            "type": "function_call_output",
            "call_id": "call_1",
            "output": '{"integrity": 1.0}',
        }
    ]


def test_anthropic_tool_round_trip_converts_to_native_pairing():
    from anthropic.types import Message, TextBlock, Usage

    from squid_game.providers.anthropic_provider import AnthropicProvider

    provider = AnthropicProvider(api_key="x")
    fake = MagicMock()
    fake.messages.create.return_value = Message(
        id="msg_1",
        type="message",
        role="assistant",
        content=[TextBlock(type="text", text="self is intact")],
        model="claude-x",
        stop_reason="end_turn",
        usage=Usage(input_tokens=5, output_tokens=3),
    )
    provider._client = fake

    provider.complete(_tool_round_trip_history(), tools=TOOL_SCHEMAS)

    sent = fake.messages.create.call_args.kwargs["messages"]
    assert [m["role"] for m in sent] == ["user", "assistant", "user"]
    assistant_block = sent[1]["content"][0]
    assert assistant_block == {
        "type": "tool_use",
        "id": "call_1",
        "name": "stat_checkpoint",
        "input": {"slot": "self"},
    }
    result_block = sent[2]["content"][0]
    assert result_block == {
        "type": "tool_result",
        "tool_use_id": "call_1",
        "content": '{"integrity": 1.0}',
    }


def test_ollama_cloud_tool_round_trip_converts_to_native_pairing():
    from squid_game.providers.ollama_cloud import OllamaCloudProvider

    provider = OllamaCloudProvider(api_key="x", model="qwen-test")
    fake_client = MagicMock()
    fake_response = MagicMock()
    fake_response.status_code = 200
    fake_response.json.return_value = {
        "message": {"content": "self is intact"},
        "prompt_eval_count": 5,
        "eval_count": 3,
        "done_reason": "stop",
    }
    fake_client.post.return_value = fake_response
    provider._client = fake_client

    provider.complete(_tool_round_trip_history(), tools=TOOL_SCHEMAS)

    sent = fake_client.post.call_args.kwargs["json"]["messages"]
    assistant_msg = sent[1]
    assert assistant_msg["tool_calls"] == [
        {"function": {"name": "stat_checkpoint", "arguments": {"slot": "self"}}}
    ]
    tool_msg = sent[2]
    assert tool_msg == {
        "role": "tool",
        "content": '{"integrity": 1.0}',
        "tool_name": "stat_checkpoint",
    }
    assert "tool_call_id" not in tool_msg  # Ollama pairs positionally, no id field
