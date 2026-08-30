"""Ollama Cloud provider for Qwen3 / GPT-OSS / DeepSeek reasoning models.

Unlike :class:`LocalProvider` (which targets the OpenAI-compatible
``/v1/chat/completions`` endpoint and therefore strips the native
``message.thinking`` field), this provider speaks Ollama's **native**
``/api/chat`` protocol so that reasoning content is returned as a
structured ``message.thinking`` string — the shape the Phase O Unit 15
split-call analyses expect for `thinking_text_task` /
`thinking_text_forfeit`.

The endpoint, authentication, and payload schema follow the Ollama Cloud
docs (https://docs.ollama.com/cloud, https://docs.ollama.com/capabilities/thinking):

- Base URL default: ``https://ollama.com``
- Path: ``POST /api/chat``
- Auth: ``Authorization: Bearer $OLLAMA_API_KEY``
- Request body: ``{model, messages, stream=false, think, options{...}}``
- Response body: ``{message:{content, thinking}, prompt_eval_count,
  eval_count, done_reason, ...}``

Example configuration::

    provider:
      provider: ollama_cloud
      model: qwen3.5:cloud
      api_key_env: OLLAMA_API_KEY
      enable_thinking: true
      temperature: 0.7
      top_p: 0.95
      top_k: 20

The ``enable_thinking`` toggle is forwarded to Ollama as ``think``
(boolean). For ``gpt-oss`` models that require a level
(``"low"``/``"medium"``/``"high"``), pass ``reasoning_effort`` on the
provider config instead — it is forwarded verbatim to ``think``.

Token accounting mirrors :class:`MLXServerProvider`: ``output_tokens``
is kept as Ollama's ``eval_count`` (total generated tokens, which
physically includes any thinking output), and ``thinking_tokens`` is a
whitespace-split estimate of ``message.thinking`` so the Reasoning
Investment metric is comparable across providers.
"""

import logging
import os
import time

import httpx

from squid_game.providers.base import CompletionResult, LLMProvider
from squid_game.providers.thinking_utils import parse_thinking_tags

logger = logging.getLogger(__name__)

# HTTP status codes we retry on. 4xx other than 429 are permanent
# client errors (auth, malformed payload) and propagate immediately.
_RETRYABLE_STATUSES: frozenset[int] = frozenset({429, 500, 502, 503, 504})
_BACKOFF_SECONDS: tuple[int, ...] = (1, 2, 4)


class OllamaCloudProvider(LLMProvider):
    """LLM provider backed by Ollama Cloud's native ``/api/chat`` endpoint.

    Routes every request through the native protocol (not the
    OpenAI-compatible path) so that Qwen3 / GPT-OSS / DeepSeek
    reasoning models return ``message.thinking`` as a structured field
    rather than inlining ``<think>`` tags. Falls back to
    :func:`parse_thinking_tags` when the server happens to inline tags
    (older deployments, non-cloud tags).

    Args:
        model: Ollama model tag, e.g. ``"qwen3.5:cloud"`` or
            ``"gpt-oss:120b-cloud"``. For local Ollama usage the
            existing ``LocalProvider`` is the better fit — this class
            targets the hosted cloud path.
        api_key: Ollama Cloud API key. Falls back to the
            ``OLLAMA_API_KEY`` environment variable.
        base_url: Override the cloud host. Defaults to
            ``https://ollama.com``. Any ``/api/chat`` suffix on the
            input is stripped before the request is dispatched.
        max_retries: Retry budget for transient 429/5xx and network
            errors (exponential backoff: 1s, 2s, 4s).
        timeout: Request timeout in seconds.
        top_p: Nucleus sampling parameter (``0.0`` disables).
        top_k: Top-k sampling parameter (``0`` disables).
        seed: Deterministic seed.
        repetition_penalty: Ollama ``repeat_penalty`` option
            (``0.0`` / ``1.0`` disables).
        enable_thinking: Forwarded as the Ollama ``think`` field.
            ``None`` = omit (server default), ``True`` / ``False`` =
            force on/off. For gpt-oss which expects a level string,
            use ``reasoning_effort`` instead.
        reasoning_effort: Level string (``"low"`` / ``"medium"`` /
            ``"high"``) forwarded to ``think`` for gpt-oss-family
            models. Takes precedence over ``enable_thinking`` when set.
    """

    DEFAULT_BASE_URL = "https://ollama.com"

    def __init__(
        self,
        model: str = "qwen3.5:cloud",
        api_key: str | None = None,
        base_url: str | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
        top_p: float = 0.0,
        top_k: int = 0,
        seed: int | None = None,
        repetition_penalty: float = 0.0,
        enable_thinking: bool | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._timeout = timeout
        self._top_p = top_p
        self._top_k = top_k
        self._seed = seed
        self._repetition_penalty = repetition_penalty
        self._enable_thinking = enable_thinking
        self._reasoning_effort = reasoning_effort

        resolved_key = api_key or os.environ.get("OLLAMA_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Ollama Cloud API key must be provided via api_key param "
                "or OLLAMA_API_KEY environment variable."
            )
        self._api_key = resolved_key

        # Normalise the base URL: accept either ``https://ollama.com``
        # or ``https://ollama.com/api/chat`` — we always POST to /api/chat
        # internally so duplicate suffixes would break silently.
        host = (base_url or self.DEFAULT_BASE_URL).rstrip("/")
        if host.endswith("/api/chat"):
            host = host[: -len("/api/chat")]
        self._base_url = host

        self._client = httpx.Client(
            base_url=self._base_url,
            timeout=timeout,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        logger.info(
            "OllamaCloudProvider targeting %s at %s (thinking=%s, effort=%s)",
            model, self._base_url, enable_thinking, reasoning_effort,
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
        """Send a non-streaming chat request to Ollama Cloud.

        Args:
            messages: Chat messages with ``role`` and ``content`` keys.
                Forwarded verbatim to ``/api/chat`` — Ollama accepts
                the same role set (``system`` / ``user`` / ``assistant``
                / ``tool``) we already produce.
            temperature: Sampling temperature → ``options.temperature``.
            max_tokens: Max generation tokens → ``options.num_predict``.

        Returns:
            :class:`CompletionResult` with the answer in ``text`` and the
            reasoning trace in ``thinking_text`` (``None`` if the model
            did not reason). ``thinking_tokens`` is a whitespace-split
            estimate of the thinking text, matching the convention used
            by :class:`MLXServerProvider` so Reasoning Investment values
            are comparable across backends.
        """
        options: dict[str, object] = {
            "temperature": temperature,
            "num_predict": max_tokens,
        }
        if self._top_p > 0.0:
            options["top_p"] = self._top_p
        if self._top_k > 0:
            options["top_k"] = self._top_k
        if self._seed is not None:
            options["seed"] = self._seed
        if self._repetition_penalty > 0.0 and self._repetition_penalty != 1.0:
            options["repeat_penalty"] = self._repetition_penalty

        payload: dict[str, object] = {
            "model": self._model,
            "messages": messages,
            "stream": False,
            "options": options,
        }

        # Resolve the ``think`` field. reasoning_effort wins (gpt-oss
        # needs a level string) and falls back to the boolean toggle.
        # Absent both → omit so the server default applies.
        think_value: object | None = None
        if self._reasoning_effort is not None:
            think_value = self._reasoning_effort
        elif self._enable_thinking is not None:
            think_value = self._enable_thinking
        if think_value is not None:
            payload["think"] = think_value

        response_json = self._call_with_retry(payload)

        message = response_json.get("message") or {}
        text = message.get("content") or ""
        thinking_text_raw = message.get("thinking") or None

        input_tokens = int(response_json.get("prompt_eval_count") or 0)
        output_tokens = int(response_json.get("eval_count") or 0)
        done_reason = response_json.get("done_reason") or "stop"

        # Preferred path: Ollama returned a structured ``thinking``
        # field (cloud Qwen3 with ``think=true``). Count tokens via
        # whitespace split — matches parse_thinking_tags so the RI
        # metric is comparable to MLXServerProvider / CUDAServerProvider.
        if thinking_text_raw:
            thinking_text: str | None = thinking_text_raw
            thinking_tokens = len(thinking_text_raw.split())
        else:
            # Fallback: older deployments or non-cloud tags may still
            # inline <think>...</think> tags in content. Reuse the
            # shared parser so behaviour stays consistent with other
            # server-based providers.
            text, thinking_tokens, thinking_text = parse_thinking_tags(text)

        return CompletionResult(
            text=text,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            thinking_tokens=thinking_tokens,
            thinking_text=thinking_text,
            logprobs=None,
            finish_reason=done_reason,
        )

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    def _call_with_retry(self, payload: dict) -> dict:
        """POST ``/api/chat`` with exponential-backoff retries.

        Retries on 429 / 5xx / network errors only. Auth / validation
        errors (4xx other than 429) surface immediately so the caller
        sees actionable failure rather than burning the retry budget.
        """
        last_error: Exception | None = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.post("/api/chat", json=payload)
                if response.status_code in _RETRYABLE_STATUSES:
                    snippet = response.text[:200]
                    logger.warning(
                        "Ollama Cloud %d on attempt %d/%d: %s",
                        response.status_code,
                        attempt + 1,
                        self._max_retries + 1,
                        snippet,
                    )
                    last_error = httpx.HTTPStatusError(
                        f"Ollama Cloud transient {response.status_code}: {snippet}",
                        request=response.request,
                        response=response,
                    )
                else:
                    response.raise_for_status()
                    return response.json()
            except (
                httpx.TimeoutException,
                httpx.ConnectError,
                httpx.ReadError,
                httpx.RemoteProtocolError,
            ) as exc:
                last_error = exc
                logger.warning(
                    "Ollama Cloud network error on attempt %d/%d: %s",
                    attempt + 1, self._max_retries + 1, exc,
                )
            except httpx.HTTPStatusError:
                # Non-retryable (permanent 4xx). Propagate immediately.
                raise

            if attempt < self._max_retries:
                wait = _BACKOFF_SECONDS[
                    min(attempt, len(_BACKOFF_SECONDS) - 1)
                ]
                time.sleep(wait)
        assert last_error is not None  # loop guarantees at least one
        raise last_error

    def __del__(self) -> None:
        # Best-effort cleanup; httpx clients hold a connection pool.
        client = getattr(self, "_client", None)
        if client is not None:
            try:
                client.close()
            except Exception:
                pass
