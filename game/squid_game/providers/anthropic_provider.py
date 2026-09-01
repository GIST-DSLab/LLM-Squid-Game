"""Anthropic provider for Claude-family models.

Uses the official anthropic Python client (sync) to call the messages API.
Handles the Anthropic-specific system message placement and thinking content
blocks.

Example configuration::

    provider:
      type: anthropic
      model: claude-sonnet-4-20250514
      # api_key: defaults to ANTHROPIC_API_KEY env var

Note: This file is intentionally named ``anthropic_provider.py`` (not
``anthropic.py``) to avoid shadowing the ``anthropic`` package.
"""

import logging
import os
import time

from anthropic import Anthropic
from anthropic import APIError, APITimeoutError, RateLimitError

from squid_game.core.tools import ToolCall
from squid_game.providers.base import CompletionResult, LLMProvider

logger = logging.getLogger(__name__)

_RETRYABLE_EXCEPTIONS = (RateLimitError, APITimeoutError, APIError)
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1, 2, 4)


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic messages API.

    Args:
        model: Model identifier (e.g. ``"claude-sonnet-4-20250514"``).
        api_key: Anthropic API key. Falls back to ``ANTHROPIC_API_KEY`` env var.
        base_url: Custom API base URL for private Anthropic deployments.
        max_retries: Number of retries on transient failures.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "claude-sonnet-4-20250514",
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
        top_p: float = 0.0,
        top_k: int = 0,
        enable_thinking: bool | None = None,
        thinking_budget: int | None = None,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._timeout = timeout
        self._top_p = top_p
        self._top_k = top_k
        self._enable_thinking = enable_thinking
        self._thinking_budget = thinking_budget
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Anthropic API key must be provided via api_key param "
                "or ANTHROPIC_API_KEY environment variable."
            )
        client_kwargs: dict = {"api_key": resolved_key}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = Anthropic(**client_kwargs)

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        """Send a messages request with retry on transient failures.

        System messages are extracted from ``messages`` and passed via the
        dedicated ``system`` parameter, as required by the Anthropic API.

        Args:
            messages: Chat messages with ``role`` and ``content`` keys.
                Messages with ``role="system"`` are extracted automatically.
                A message may also carry a list-of-blocks ``content``
                (e.g. ``tool_result`` blocks from a prior tool round) —
                passed through unchanged.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            tools: Optional ``TOOL_SCHEMAS``-shaped tool definitions.
                Anthropic's native tool format is ``name`` / ``description``
                / ``input_schema`` — identical to ``TOOL_SCHEMAS`` — so no
                conversion is needed; passed straight through.

        Returns:
            CompletionResult containing response text and token usage.

        Raises:
            anthropic.APIError: After exhausting all retries.
        """
        system_text, non_system = self._split_system_messages(messages)

        kwargs: dict = {
            "model": self._model,
            "messages": non_system,
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if self._top_p > 0.0:
            kwargs["top_p"] = self._top_p
        if self._top_k > 0:
            kwargs["top_k"] = self._top_k
        if system_text:
            kwargs["system"] = system_text
        if tools:
            kwargs["tools"] = tools

        # Extended thinking support (Claude 3.5+).
        # Anthropic requires temperature=1.0 when thinking is enabled.
        if self._enable_thinking:
            budget = self._thinking_budget or 10240
            kwargs["thinking"] = {
                "type": "enabled",
                "budget_tokens": budget,
            }
            kwargs["temperature"] = 1.0

        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.messages.create(**kwargs)
                break
            except _RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                if attempt < self._max_retries:
                    wait = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "Anthropic request failed (attempt %d/%d): %s. "
                        "Retrying in %ds...",
                        attempt + 1,
                        self._max_retries + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
        else:
            raise last_error  # type: ignore[misc]

        # Extract text, thinking tokens, and tool calls from content blocks.
        text_parts: list[str] = []
        thinking_text_parts: list[str] = []
        thinking_tokens = 0
        tool_calls: list[ToolCall] = []
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                thinking_tokens += getattr(
                    block, "input_tokens", len(block.thinking) // 4
                )
                thinking_text_parts.append(block.thinking)
            elif block.type == "tool_use":
                tool_calls.append(
                    ToolCall(name=block.name, args=block.input, call_id=block.id)
                )

        text = "\n".join(text_parts)
        thinking_text = "\n".join(thinking_text_parts) if thinking_text_parts else None

        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        finish_reason = response.stop_reason  # "end_turn", "max_tokens", etc.

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            thinking_text=thinking_text,
            finish_reason=finish_reason,
            tool_calls=tool_calls or None,
        )

    @staticmethod
    def _split_system_messages(
        messages: list[dict[str, object]],
    ) -> tuple[str, list[dict[str, object]]]:
        """Separate system messages from user/assistant messages.

        The Anthropic API requires the system prompt to be passed as a
        top-level ``system`` parameter rather than as a message with
        ``role="system"``.

        Also converts a tool round trip's flat history shape into
        Anthropic's native blocks — confirmed against the installed
        ``anthropic`` package's request types
        (``anthropic.types.message_param.MessageParam.role`` is
        ``Literal["user", "assistant", "system"]``: there is **no**
        ``"tool"`` role, so a flat ``{"role": "tool", ...}`` message would
        be rejected outright):

        - An ``assistant`` message carrying ``tool_calls`` (each item
          ``{"tool_call_id", "name", "args"}``) becomes an assistant
          message whose ``content`` is a block list — a ``text`` block for
          any non-empty ``content``, then one
          ``{"type": "tool_use", "id", "name", "input"}`` block per call
          (``ToolUseBlockParam``: ``id`` / ``input`` / ``name`` all
          required).
        - A ``role="tool"`` message becomes a
          ``{"type": "tool_result", "tool_use_id", "content"}`` block
          (``ToolResultBlockParam`` — no ``name`` field) inside a ``user``
          message. The Messages API requires strictly alternating
          user/assistant turns (documented, and matches the multi-tool
          example in Anthropic's own tool-use docs, where several
          ``tool_result`` blocks from one round are batched into a single
          ``user`` turn) — so consecutive ``tool`` messages are buffered
          and flushed together into one ``user`` turn rather than emitted
          as separate turns.

        Returns:
            A tuple of (concatenated system text, remaining messages).
        """
        system_parts: list[str] = []
        converted: list[dict[str, object]] = []
        pending_results: list[dict[str, object]] = []

        def flush_pending() -> None:
            if pending_results:
                converted.append(
                    {"role": "user", "content": list(pending_results)}
                )
                pending_results.clear()

        for msg in messages:
            role = msg["role"]
            if role == "system":
                flush_pending()
                system_parts.append(msg["content"])
            elif role == "tool":
                pending_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": msg.get("tool_call_id") or "",
                        "content": msg.get("content", ""),
                    }
                )
            elif role == "assistant" and msg.get("tool_calls"):
                flush_pending()
                blocks: list[dict[str, object]] = []
                if msg.get("content"):
                    blocks.append({"type": "text", "text": msg["content"]})
                for call in msg["tool_calls"]:
                    blocks.append(
                        {
                            "type": "tool_use",
                            "id": call.get("tool_call_id") or "",
                            "name": call["name"],
                            "input": call.get("args") or {},
                        }
                    )
                converted.append({"role": "assistant", "content": blocks})
            else:
                flush_pending()
                converted.append(msg)
        flush_pending()
        return "\n\n".join(system_parts), converted
