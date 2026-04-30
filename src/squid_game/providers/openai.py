"""OpenAI provider for GPT-family and o-series reasoning models.

Dual-path implementation:

- **Chat Completions API** (default): used for non-reasoning models
  (``gpt-4o``, ``gpt-4-turbo`` etc.). Thinking-token extraction falls
  back to ``usage.completion_tokens_details.reasoning_tokens`` when the
  model is an o-series model routed through the legacy chat endpoint.

- **Responses API** (reasoning models): used automatically for
  ``o1``/``o3``/``o4``/``gpt-5`` models, or when ``use_responses_api=True``
  is set explicitly. The Responses API is the only OpenAI endpoint that
  exposes (a) reasoning summaries (``response.output[*].summary[*].text``)
  and (b) API-reported reasoning tokens
  (``response.usage.output_tokens_details.reasoning_tokens``). Both are
  captured into ``CompletionResult.thinking_text`` and
  ``CompletionResult.thinking_tokens`` respectively.

The ``reasoning_effort`` param is forwarded to the Responses API as
``reasoning.effort``; requesting a summary is always on (``summary="auto"``)
so Phase O Unit 15 split-call analyses see thinking_text for the
linguistic channel (H_thinking_* keyword counts) in the same schema as
Gemini / Qwen3 providers.

Example configuration::

    provider:
      type: openai
      model: o4-mini
      reasoning_effort: medium      # forwarded to Responses API
      # api_key: defaults to OPENAI_API_KEY env var
"""

import logging
import os
import time

from openai import OpenAI
from openai import APIError, APITimeoutError, BadRequestError, RateLimitError

from squid_game.providers.base import CompletionResult, LLMProvider

logger = logging.getLogger(__name__)

# Only transient errors are retried. BadRequestError (400 — permanent
# client-side validation errors such as "org not verified for reasoning
# summaries") must propagate immediately so the caller's fallback logic
# can handle it without burning the retry budget.
_RETRYABLE_EXCEPTIONS = (RateLimitError, APITimeoutError)
_BACKOFF_SECONDS = (1, 2, 4)

# Model-name prefixes that trigger automatic Responses API routing.
# All o-series and gpt-5 family models are reasoning models that report
# reasoning tokens + reasoning summaries only through /v1/responses.
_REASONING_PREFIXES: tuple[str, ...] = ("o1", "o3", "o4", "gpt-5")


def _is_reasoning_model(model: str) -> bool:
    """Whether *model* should be routed through the Responses API."""
    return any(model.startswith(p) for p in _REASONING_PREFIXES)


class OpenAIProvider(LLMProvider):
    """LLM provider backed by the OpenAI API.

    Dispatches to Chat Completions (``/v1/chat/completions``) or
    Responses (``/v1/responses``) based on model family. The Responses
    path is required for o-series reasoning models to receive the
    reasoning summary and the API-reported reasoning-token count.

    Args:
        model: Model identifier (e.g. ``"gpt-4o"`` or ``"o4-mini"``).
        api_key: OpenAI API key. Falls back to ``OPENAI_API_KEY`` env var.
        base_url: Optional base URL override for compatible APIs.
        max_retries: Retry budget on transient errors.
        timeout: HTTP timeout in seconds.
        top_p: Nucleus sampling parameter (ignored for reasoning models).
        seed: Deterministic seed (ignored for reasoning models).
        logprobs: Request log probabilities (Chat Completions only).
        reasoning_effort: One of ``"low"``/``"medium"``/``"high"``. When
            set, overrides auto-detection and forces the Responses API.
        use_responses_api: Explicit override. ``None`` = auto-detect by
            model prefix; ``True``/``False`` force one or the other.
        reasoning_summary: Summary verbosity forwarded to the Responses
            API (``"auto"`` / ``"concise"`` / ``"detailed"``). Default
            ``"auto"`` gives the provider best-effort summaries.
    """

    def __init__(
        self,
        model: str = "gpt-4o",
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
        top_p: float = 0.0,
        seed: int | None = None,
        logprobs: bool = False,
        reasoning_effort: str | None = None,
        use_responses_api: bool | None = None,
        reasoning_summary: str = "auto",
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._timeout = timeout
        self._top_p = top_p
        self._seed = seed
        self._logprobs = logprobs
        self._reasoning_effort = reasoning_effort
        self._reasoning_summary = reasoning_summary
        # Auto-route reasoning models through the Responses API unless
        # the caller explicitly opts out. Non-reasoning models stay on
        # Chat Completions for backward compatibility (deterministic
        # seeds, logprobs, temperature support).
        if use_responses_api is None:
            self._use_responses = _is_reasoning_model(model) or (
                reasoning_effort is not None
            )
        else:
            self._use_responses = bool(use_responses_api)

        resolved_key = api_key or os.environ.get("OPENAI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "OpenAI API key must be provided via api_key param "
                "or OPENAI_API_KEY environment variable."
            )
        self._client = OpenAI(
            api_key=resolved_key,
            base_url=base_url,
            timeout=timeout,
            max_retries=0,  # Disable SDK-level retries; our provider handles retries
        )

    @property
    def model_name(self) -> str:
        return self._model

    # ------------------------------------------------------------------
    # Public entry
    # ------------------------------------------------------------------

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Send a completion request, dispatching by endpoint family.

        Args:
            messages: Chat messages with ``role`` and ``content`` keys.
            temperature: Sampling temperature (ignored on Responses API).
            max_tokens: Maximum tokens to generate (forwarded as
                ``max_completion_tokens`` on Chat / ``max_output_tokens``
                on Responses).

        Returns:
            CompletionResult. For reasoning models routed through the
            Responses API, ``thinking_tokens`` is the API-reported
            ``reasoning_tokens`` count and ``thinking_text`` is the
            concatenated ``summary_text`` blocks.
        """
        if self._use_responses:
            return self._complete_responses(messages, max_tokens)
        return self._complete_chat(messages, temperature, max_tokens)

    # ------------------------------------------------------------------
    # Responses API path (o-series / gpt-5)
    # ------------------------------------------------------------------

    def _complete_responses(
        self,
        messages: list[dict[str, str]],
        max_tokens: int,
    ) -> CompletionResult:
        """Call ``/v1/responses`` and extract summary + reasoning tokens."""
        input_items = self._messages_to_input(messages)

        reasoning_payload: dict = {}
        if self._reasoning_summary:
            reasoning_payload["summary"] = self._reasoning_summary
        if self._reasoning_effort:
            reasoning_payload["effort"] = self._reasoning_effort

        kwargs: dict = {
            "model": self._model,
            "input": input_items,
            "max_output_tokens": max_tokens,
        }
        if reasoning_payload:
            kwargs["reasoning"] = reasoning_payload

        try:
            response = self._call_with_retry(
                self._client.responses.create, kwargs, endpoint="responses"
            )
        except BadRequestError as exc:
            # Organization-not-verified orgs can still use o-series for
            # reasoning token accounting, they just cannot receive the
            # human-readable summary. Detect that specific 400 and retry
            # without ``summary``. We remember the downgrade so subsequent
            # calls skip the summary request up-front (cheaper).
            msg = str(exc)
            if (
                "reasoning.summary" in msg
                or "generate reasoning summaries" in msg
            ) and "summary" in reasoning_payload:
                logger.warning(
                    "OpenAI org not verified for reasoning summaries — "
                    "falling back to token-only accounting. "
                    "thinking_text will be None for this model."
                )
                self._reasoning_summary = ""
                reasoning_payload.pop("summary", None)
                if reasoning_payload:
                    kwargs["reasoning"] = reasoning_payload
                else:
                    kwargs.pop("reasoning", None)
                response = self._call_with_retry(
                    self._client.responses.create,
                    kwargs,
                    endpoint="responses",
                )
            else:
                raise

        # Usage: prompt / output / reasoning tokens. Shape:
        #   usage.input_tokens, usage.output_tokens,
        #   usage.output_tokens_details.reasoning_tokens
        usage = getattr(response, "usage", None)
        input_tokens = int(getattr(usage, "input_tokens", 0) or 0) if usage else 0
        output_tokens = int(getattr(usage, "output_tokens", 0) or 0) if usage else 0
        reasoning_tokens = 0
        if usage is not None:
            details = getattr(usage, "output_tokens_details", None)
            if details is not None:
                reasoning_tokens = int(
                    getattr(details, "reasoning_tokens", 0) or 0
                )

        # Walk response.output to split reasoning summaries from the
        # final message content. The Responses API returns a list of
        # output items; reasoning items carry ``type="reasoning"`` with
        # a ``summary`` array, and the final answer arrives as
        # ``type="message"`` with ``content`` list of output_text parts.
        summary_parts: list[str] = []
        answer_parts: list[str] = []
        finish_reason: str | None = None
        output_items = getattr(response, "output", None) or []
        for item in output_items:
            item_type = getattr(item, "type", None)
            if item_type == "reasoning":
                for block in getattr(item, "summary", None) or []:
                    btype = getattr(block, "type", None)
                    btext = getattr(block, "text", None)
                    if btype == "summary_text" and btext:
                        summary_parts.append(btext)
            elif item_type == "message":
                for block in getattr(item, "content", None) or []:
                    btype = getattr(block, "type", None)
                    btext = getattr(block, "text", None)
                    if btype in ("output_text", "text") and btext:
                        answer_parts.append(btext)
                if finish_reason is None:
                    finish_reason = getattr(item, "status", None)

        # Fallback: older SDK versions expose a flattened ``output_text``.
        if not answer_parts:
            fallback_text = getattr(response, "output_text", None)
            if fallback_text:
                answer_parts.append(fallback_text)
        if finish_reason is None:
            finish_reason = getattr(response, "status", None)

        text = "\n".join(p for p in answer_parts if p).strip()
        thinking_text = "\n\n".join(summary_parts).strip() or None

        # If the summary is empty but reasoning tokens were charged, the
        # model reasoned internally without emitting a summary — still
        # report the token count so Reasoning Investment accounting is
        # accurate.
        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=reasoning_tokens,
            thinking_text=thinking_text,
            logprobs=None,
            finish_reason=finish_reason,
        )

    # ------------------------------------------------------------------
    # Chat Completions API path (non-reasoning models)
    # ------------------------------------------------------------------

    def _complete_chat(
        self,
        messages: list[dict[str, str]],
        temperature: float,
        max_tokens: int,
    ) -> CompletionResult:
        """Call ``/v1/chat/completions`` for non-reasoning models."""
        kwargs: dict = {
            "model": self._model,
            "messages": messages,
            "max_tokens": max_tokens,
            "temperature": temperature,
        }
        if self._top_p > 0.0:
            kwargs["top_p"] = self._top_p
        if self._seed is not None:
            kwargs["seed"] = self._seed
        if self._logprobs:
            kwargs["logprobs"] = True

        extra_body = getattr(self, "_extra_body", None)
        if extra_body:
            kwargs["extra_body"] = extra_body

        response = self._call_with_retry(
            self._client.chat.completions.create, kwargs, endpoint="chat"
        )

        usage = response.usage
        input_tokens = usage.prompt_tokens if usage else 0
        output_tokens = usage.completion_tokens if usage else 0

        # API-reported reasoning tokens — present for o-series even when
        # routed through chat completions (rare but possible via proxy).
        thinking_tokens = 0
        if usage is not None:
            details = getattr(usage, "completion_tokens_details", None)
            if details is not None:
                thinking_tokens = int(
                    getattr(details, "reasoning_tokens", 0) or 0
                )

        choice = response.choices[0]
        text = choice.message.content or ""
        finish_reason = choice.finish_reason

        # Some newer SDK builds surface a ``reasoning_content`` field on
        # the message (o-series on chat completions, Qwen on compat
        # proxies). Capture it for the linguistic channel if present.
        thinking_text: str | None = None
        msg_data = (
            choice.message.model_dump()
            if hasattr(choice.message, "model_dump")
            else {}
        )
        reasoning_text = (
            msg_data.get("reasoning_content")
            or msg_data.get("reasoning")
            or ""
        )
        if reasoning_text:
            thinking_text = reasoning_text
            # If API reported 0 reasoning_tokens but text exists, fall
            # back to whitespace split as a last-resort estimate so RI
            # is non-zero.
            if thinking_tokens == 0:
                thinking_tokens = len(reasoning_text.split())
            if not text:
                text = reasoning_text

        logprobs_list: list[float] | None = None
        if choice.logprobs and choice.logprobs.content:
            logprobs_list = [tok.logprob for tok in choice.logprobs.content]

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            thinking_text=thinking_text,
            logprobs=logprobs_list,
            finish_reason=finish_reason,
        )

    # ------------------------------------------------------------------
    # Shared helpers
    # ------------------------------------------------------------------

    def _call_with_retry(self, fn, kwargs: dict, *, endpoint: str):
        """Exponential-backoff retry wrapper shared by both endpoints."""
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                return fn(**kwargs)
            except _RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                if attempt < self._max_retries:
                    wait = _BACKOFF_SECONDS[
                        min(attempt, len(_BACKOFF_SECONDS) - 1)
                    ]
                    logger.warning(
                        "OpenAI %s request failed (attempt %d/%d): %s. "
                        "Retrying in %ds...",
                        endpoint,
                        attempt + 1,
                        self._max_retries + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
        raise last_error  # type: ignore[misc]

    @staticmethod
    def _messages_to_input(
        messages: list[dict[str, str]],
    ) -> list[dict[str, object]]:
        """Convert Chat-style messages to Responses API ``input`` shape.

        The Responses API accepts either a bare string or a list of
        message-like items. Each item has ``role`` and ``content`` where
        ``content`` is a list of typed parts — ``input_text`` for user
        / system input, ``output_text`` reserved for model echoes.
        """
        input_items: list[dict[str, object]] = []
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            input_items.append(
                {
                    "role": role,
                    "content": [
                        {"type": "input_text", "text": content}
                    ],
                }
            )
        return input_items
