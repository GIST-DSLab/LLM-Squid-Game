"""Google Gemini provider for Gemini-family models.

Uses the official google-genai Python SDK (sync) to call generate_content.
Supports thinking tokens from Gemini 2.5+ models for Reasoning Investment
tracking.

Example configuration::

    provider:
      type: gemini
      model: gemini-2.0-flash
      # api_key: defaults to GEMINI_API_KEY env var
"""

import json
import logging
import os
import time

from google import genai
from google.genai import types
from google.genai.errors import APIError, ClientError, ServerError

from squid_game.core.tools import ToolCall
from squid_game.providers.base import CompletionResult, LLMProvider

logger = logging.getLogger(__name__)

_RETRYABLE_EXCEPTIONS = (ServerError, ClientError, APIError)
_MAX_RETRIES = 3
_BACKOFF_SECONDS = (2, 4, 8)


class GeminiProvider(LLMProvider):
    """LLM provider backed by the Google Gemini API.

    Args:
        model: Model identifier (e.g. ``"gemini-2.0-flash"``).
        api_key: Gemini API key. Falls back to ``GEMINI_API_KEY`` env var.
        max_retries: Number of retries on transient failures.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str = "gemini-2.0-flash",
        api_key: str | None = None,
        max_retries: int = 3,
        timeout: float = 120.0,
        top_p: float = 0.0,
        top_k: int = 0,
        seed: int | None = None,
        enable_thinking: bool | None = None,
        thinking_budget: int | None = None,
        reasoning_effort: str | None = None,
    ) -> None:
        self._model = model
        self._max_retries = max_retries
        self._timeout = timeout
        self._top_p = top_p
        self._top_k = top_k
        self._seed = seed
        self._enable_thinking = enable_thinking
        self._thinking_budget = thinking_budget
        self._reasoning_effort = reasoning_effort
        resolved_key = api_key or os.environ.get("GEMINI_API_KEY")
        if not resolved_key:
            raise ValueError(
                "Gemini API key must be provided via api_key param "
                "or GEMINI_API_KEY environment variable."
            )
        self._client = genai.Client(
            api_key=resolved_key,
            http_options=types.HttpOptions(timeout=int(timeout * 1000)),
        )

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
        """Send a generate_content request with retry on transient failures.

        System messages are extracted and passed via the ``system_instruction``
        parameter, as required by the Gemini API.

        Args:
            messages: Chat messages with ``role`` and ``content`` keys.
                Messages with ``role="system"`` are extracted automatically.
            temperature: Sampling temperature.
            max_tokens: Maximum tokens to generate.
            tools: Optional ``TOOL_SCHEMAS``-shaped tool definitions,
                wrapped into a single ``types.Tool(function_declarations=...)``
                on the request config.

        Returns:
            CompletionResult containing response text and token usage.

        Raises:
            google.genai.errors.APIError: After exhausting all retries.
        """
        system_text, contents = self._convert_messages(messages)

        config_kwargs: dict = {
            "temperature": temperature,
            "max_output_tokens": max_tokens,
        }
        if self._top_p > 0.0:
            config_kwargs["top_p"] = self._top_p
        if self._top_k > 0:
            config_kwargs["top_k"] = self._top_k
        if self._seed is not None:
            config_kwargs["seed"] = self._seed
        if tools:
            config_kwargs["tools"] = [self._build_tool(tools)]

        # Thinking config: always include thoughts for RI tracking.
        thinking_kwargs: dict = {"include_thoughts": True}
        if self._thinking_budget is not None:
            thinking_kwargs["thinking_budget"] = self._thinking_budget
        if self._reasoning_effort:
            thinking_kwargs["thinking_level"] = self._reasoning_effort
        if self._enable_thinking is False:
            thinking_kwargs = {"include_thoughts": False}

        config_kwargs["thinking_config"] = types.ThinkingConfig(**thinking_kwargs)
        config = types.GenerateContentConfig(**config_kwargs)
        if system_text:
            config.system_instruction = system_text

        last_error: Exception | None = None
        response = None
        for attempt in range(self._max_retries + 1):
            try:
                response = self._client.models.generate_content(
                    model=self._model,
                    contents=contents,
                    config=config,
                )
                break
            except _RETRYABLE_EXCEPTIONS as exc:
                last_error = exc
                if attempt < self._max_retries:
                    wait = _BACKOFF_SECONDS[min(attempt, len(_BACKOFF_SECONDS) - 1)]
                    logger.warning(
                        "Gemini request failed (attempt %d/%d): %s. "
                        "Retrying in %ds...",
                        attempt + 1,
                        self._max_retries + 1,
                        exc,
                        wait,
                    )
                    time.sleep(wait)
        else:
            raise last_error  # type: ignore[misc]

        # Extract text, thinking, and tool calls from response parts.
        text_parts: list[str] = []
        thinking_text_parts: list[str] = []
        tool_calls: list[ToolCall] = []
        finish_reason = None
        if response.candidates:
            candidate = response.candidates[0]
            finish_reason = getattr(candidate, "finish_reason", None)
            # Gemini returns enum; convert to string.
            if finish_reason is not None:
                finish_reason = str(finish_reason).lower()
            for part in candidate.content.parts:
                if part.function_call:
                    fc = part.function_call
                    tool_calls.append(
                        ToolCall(
                            name=fc.name,
                            args=dict(fc.args or {}),
                            call_id=fc.id,
                        )
                    )
                elif part.thought:
                    if part.text:
                        thinking_text_parts.append(part.text)
                elif part.text:
                    text_parts.append(part.text)

        text = "\n".join(text_parts)
        thinking_text = "\n".join(thinking_text_parts) if thinking_text_parts else None

        # Token counts from usage metadata.
        usage = response.usage_metadata
        input_tokens = usage.prompt_token_count or 0 if usage else 0
        output_tokens = usage.candidates_token_count or 0 if usage else 0

        # Prefer API-reported thinking token count; fall back to heuristic.
        thinking_tokens = 0
        if usage and usage.thoughts_token_count:
            thinking_tokens = usage.thoughts_token_count
        elif thinking_text_parts:
            thinking_tokens = len("".join(thinking_text_parts)) // 4

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
    def _build_tool(tools: list[dict]) -> types.Tool:
        """Convert ``TOOL_SCHEMAS``-shaped dicts into a Gemini ``Tool``.

        Gemini groups every function under one ``Tool.function_declarations``
        list rather than sending one tool object per function.
        """
        declarations = [
            types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters=schema["input_schema"],
            )
            for schema in tools
        ]
        return types.Tool(function_declarations=declarations)

    @staticmethod
    def _convert_messages(
        messages: list[dict[str, str]],
    ) -> tuple[str, list[types.Content]]:
        """Convert OpenAI-style messages to Gemini Content objects.

        Separates system messages and maps ``assistant`` role to ``model``.
        Also handles the flat tool-round-trip shape a runtime's tool loop
        appends to history:

        - An ``assistant`` message carrying a ``tool_calls`` list (each
          item ``{"tool_call_id", "name", "args"}``) becomes a
          ``Content(role="model", parts=[... Part(function_call=...) ...])``
          — one ``function_call`` part per call, preceded by a text part
          if the message also has non-empty ``content``.
        - A ``role="tool"`` message (``{"name", "tool_call_id", "content"}``)
          becomes a ``Part(function_response=...)``. Per the google-genai
          SDK's own automatic-function-calling implementation
          (``_extra_utils.get_function_response_parts`` /
          ``models.py``'s ``func_response_content = types.Content(role='user',
          parts=func_response_parts)``), *every* function-response part from
          one round is merged into a single ``role="user"`` Content rather
          than emitted as separate turns — Gemini's ``contents`` list
          strictly alternates ``model``/``user`` turns, so consecutive
          ``tool`` messages are buffered and flushed together.

        Returns:
            A tuple of (system instruction text, list of Content objects).
        """
        system_parts: list[str] = []
        contents: list[types.Content] = []
        pending_responses: list[types.Part] = []

        def flush_pending() -> None:
            if pending_responses:
                contents.append(
                    types.Content(role="user", parts=list(pending_responses))
                )
                pending_responses.clear()

        for msg in messages:
            role = msg["role"]
            if role == "system":
                flush_pending()
                system_parts.append(msg["content"])
            elif role == "tool":
                pending_responses.append(
                    types.Part(
                        function_response=types.FunctionResponse(
                            id=msg.get("tool_call_id") or None,
                            name=msg.get("name", ""),
                            response=GeminiProvider._parse_tool_content(
                                msg.get("content", "")
                            ),
                        )
                    )
                )
            elif role == "assistant" and msg.get("tool_calls"):
                flush_pending()
                parts: list[types.Part] = []
                if msg.get("content"):
                    parts.append(types.Part(text=msg["content"]))
                for call in msg["tool_calls"]:
                    parts.append(
                        types.Part(
                            function_call=types.FunctionCall(
                                id=call.get("tool_call_id") or None,
                                name=call["name"],
                                args=call.get("args") or {},
                            )
                        )
                    )
                contents.append(types.Content(role="model", parts=parts))
            else:
                flush_pending()
                # Gemini uses "model" instead of "assistant".
                gemini_role = "model" if role == "assistant" else "user"
                contents.append(
                    types.Content(
                        role=gemini_role,
                        parts=[types.Part(text=msg["content"])],
                    )
                )
        flush_pending()
        return "\n\n".join(system_parts), contents

    @staticmethod
    def _parse_tool_content(content: str) -> dict:
        """Parse a ``ToolResult.content`` JSON string into a dict.

        ``FunctionResponse.response`` requires a dict. Our own
        ``SandboxToolExecutor`` always emits JSON-serialised dicts, so
        ``json.loads`` succeeds in practice; the wrap-in-``result`` fallback
        only guards a non-JSON string reaching this path (e.g. a future,
        non-sandbox tool result).
        """
        try:
            parsed = json.loads(content)
        except (TypeError, ValueError):
            return {"result": content}
        return parsed if isinstance(parsed, dict) else {"result": parsed}
