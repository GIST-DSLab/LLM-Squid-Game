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
import re
import time

from anthropic import Anthropic
from anthropic import APIError, APITimeoutError, RateLimitError

from squid_game.providers.base import CompletionResult, LLMProvider

logger = logging.getLogger(__name__)

_RETRYABLE_EXCEPTIONS = (RateLimitError, APITimeoutError, APIError)
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (1, 2, 4)

# Models on the adaptive-thinking API surface (Claude 4.6 and later, the
# Claude 5 family). On these the legacy ``{"type": "enabled",
# "budget_tokens": N}`` request is rejected with a 400, as are the sampling
# knobs ``temperature`` / ``top_p`` / ``top_k``; depth is steered through
# ``output_config.effort`` instead. Older models (Sonnet 4, Haiku 4.5, ...)
# keep the budget path.
_ADAPTIVE_THINKING_RE = re.compile(
    r"^claude-(?:opus|sonnet)-(?:5|4-[678])(?:$|-)|^claude-(?:fable|mythos)-"
)
_EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")


def uses_adaptive_thinking(model: str) -> bool:
    """True when ``model`` takes ``thinking={"type": "adaptive"}``."""
    return bool(_ADAPTIVE_THINKING_RE.match(model))


class AnthropicProvider(LLMProvider):
    """LLM provider backed by the Anthropic messages API.

    Args:
        model: Model identifier (e.g. ``"claude-sonnet-4-20250514"``).
        api_key: Anthropic API key. Falls back to ``ANTHROPIC_API_KEY`` env var.
        base_url: Custom API base URL for private Anthropic deployments.
        max_retries: Number of retries on transient failures.
        timeout: Request timeout in seconds.
        enable_thinking: Turn extended thinking on. Legacy models get a
            ``budget_tokens`` request; adaptive-thinking models
            (:func:`uses_adaptive_thinking`) get ``{"type": "adaptive",
            "display": "summarized"}``.
        thinking_budget: ``budget_tokens`` for legacy models only; ignored
            on adaptive-thinking models (the API removed the knob).
        reasoning_effort: ``output_config.effort`` for adaptive-thinking
            models (``low`` / ``medium`` / ``high`` / ``xhigh`` / ``max``);
            ignored elsewhere.

    Reasoning-investment caveat for adaptive-thinking models: the API never
    returns the raw chain of thought, only a *summary* (``display:
    "summarized"``). ``thinking_text`` is therefore that summary, and
    ``thinking_tokens`` is estimated as ``usage.output_tokens`` minus a
    4-chars-per-token estimate of the visible answer -- the thinking tokens
    are billed inside ``output_tokens`` but not itemised.
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
        reasoning_effort: str | None = None,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._timeout = timeout
        self._top_p = top_p
        self._top_k = top_k
        self._enable_thinking = enable_thinking
        self._thinking_budget = thinking_budget
        if reasoning_effort is not None and reasoning_effort not in _EFFORT_LEVELS:
            raise ValueError(
                f"reasoning_effort must be one of {_EFFORT_LEVELS}, "
                f"got {reasoning_effort!r}"
            )
        self._reasoning_effort = reasoning_effort
        self._adaptive = uses_adaptive_thinking(model)
        resolved_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Anthropic API key must be provided via api_key param "
                "or ANTHROPIC_API_KEY environment variable."
            )
        client_kwargs: dict = {"api_key": resolved_key, "timeout": timeout}
        if base_url:
            client_kwargs["base_url"] = base_url
        self._client = Anthropic(**client_kwargs)
        logger.info(
            "AnthropicProvider targeting %s (adaptive=%s, thinking=%s, effort=%s)",
            model, self._adaptive, enable_thinking, reasoning_effort,
        )

    @property
    def model_name(self) -> str:
        return self._model

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Send a messages request with retry on transient failures.

        System messages are extracted from ``messages`` and passed via the
        dedicated ``system`` parameter, as required by the Anthropic API.

        Args:
            messages: Chat messages with ``role`` and ``content`` keys.
                Messages with ``role="system"`` are extracted automatically.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.

        Returns:
            CompletionResult containing response text and token usage.

        Raises:
            anthropic.APIError: After exhausting all retries.
        """
        system_text, non_system = self._split_system_messages(messages)

        kwargs: dict = {
            "model": self._model,
            "messages": non_system,
            "max_tokens": max_tokens,
        }
        if system_text:
            kwargs["system"] = system_text

        if self._adaptive:
            # Claude 4.6+ / Claude 5: sampling knobs are rejected (400), and
            # thinking is adaptive. ``display: "summarized"`` is the only way
            # to get any thinking text back at all (default is omitted).
            if self._enable_thinking is not False:
                kwargs["thinking"] = {"type": "adaptive", "display": "summarized"}
            else:
                kwargs["thinking"] = {"type": "disabled"}
            if self._reasoning_effort:
                kwargs["output_config"] = {"effort": self._reasoning_effort}
        else:
            kwargs["temperature"] = temperature
            if self._top_p > 0.0:
                kwargs["top_p"] = self._top_p
            if self._top_k > 0:
                kwargs["top_k"] = self._top_k
            # Extended thinking support (legacy budget path).
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

        # Extract text and thinking tokens from content blocks.
        text_parts: list[str] = []
        thinking_text_parts: list[str] = []
        thinking_tokens = 0
        for block in response.content:
            if block.type == "text":
                text_parts.append(block.text)
            elif block.type == "thinking":
                thinking_tokens += getattr(
                    block, "input_tokens", len(block.thinking) // 4
                )
                thinking_text_parts.append(block.thinking)

        text = "\n".join(text_parts)
        thinking_text = "\n".join(thinking_text_parts) if thinking_text_parts else None

        usage = response.usage
        input_tokens = usage.input_tokens
        output_tokens = usage.output_tokens
        finish_reason = response.stop_reason  # "end_turn", "max_tokens", etc.

        if self._adaptive and "thinking" in kwargs and kwargs["thinking"]["type"] != "disabled":
            # The summary is not the chain of thought; size the investment
            # off the billed output instead (see class docstring).
            thinking_tokens = max(0, output_tokens - len(text) // 4)

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            thinking_text=thinking_text,
            finish_reason=finish_reason,
        )

    @staticmethod
    def _split_system_messages(
        messages: list[dict[str, object]],
    ) -> tuple[str, list[dict[str, object]]]:
        """Separate system messages from user/assistant messages.

        The Anthropic API requires the system prompt to be passed as a
        top-level ``system`` parameter rather than as a message with
        ``role="system"``.

        Returns:
            A tuple of (concatenated system text, remaining messages).
        """
        system_parts: list[str] = []
        converted: list[dict[str, object]] = []

        for msg in messages:
            if msg["role"] == "system":
                system_parts.append(msg["content"])
            else:
                converted.append(msg)
        return "\n\n".join(system_parts), converted
