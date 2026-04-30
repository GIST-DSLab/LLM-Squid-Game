"""MLX Server provider for Apple Silicon parallel inference.

Connects to a running ``mlx_lm.server`` instance via its OpenAI-compatible
``/v1/chat/completions`` endpoint.  Unlike :class:`MLXProvider` (which
loads the model in-process), this provider delegates inference to an
external server, enabling ``parallel_workers >= 2`` without GPU segfaults.

Start the server before running experiments::

    uv run python3 -m mlx_lm server \\
        --model mlx-community/Qwen3-8B-4bit \\
        --port 8090 \\
        --chat-template-args '{"enable_thinking": true}' \\
        --temp 1.0 --top-p 0.95 --top-k 20

Example configuration::

    provider:
      provider: mlx_server
      model: mlx-community/Qwen3-8B-4bit
      base_url: http://localhost:8090/v1
      temperature: 1.0
      top_p: 0.95
      top_k: 20
"""

import logging

from squid_game.providers.base import CompletionResult
from squid_game.providers.local import LocalProvider
from squid_game.providers.thinking_utils import parse_thinking_tags

logger = logging.getLogger(__name__)


class MLXServerProvider(LocalProvider):
    """LLM provider connecting to a running ``mlx_lm.server``.

    Inherits HTTP/OpenAI-compatible communication from :class:`LocalProvider`
    and adds ``<think>...</think>`` parsing so that thinking content is
    separated from the answer and recorded in ``CompletionResult``.

    Args:
        model: Model identifier (must match the server's loaded model).
        base_url: Base URL of the mlx_lm server (e.g. ``http://localhost:8090/v1``).
        api_key: API key (mlx_lm.server accepts any string).
        max_retries: Number of retries on transient failures.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:8090/v1",
        api_key: str = "none",
        max_retries: int = 3,
        timeout: float = 120.0,
        top_p: float = 0.0,
        top_k: int = 0,
        seed: int | None = None,
        logprobs: bool = False,
        repetition_penalty: float = 0.0,
        enable_thinking: bool | None = None,
    ) -> None:
        super().__init__(
            model=model,
            base_url=base_url,
            api_key=api_key,
            max_retries=max_retries,
            timeout=timeout,
            top_p=top_p,
            top_k=top_k,
            seed=seed,
            logprobs=logprobs,
            repetition_penalty=repetition_penalty,
        )
        self._enable_thinking = enable_thinking
        logger.info(
            "MLXServerProvider targeting %s at %s (thinking=%s)",
            model, base_url, enable_thinking,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 32768,
    ) -> CompletionResult:
        """Send request to mlx_lm.server and parse thinking blocks.

        The server returns ``<think>...</think>`` tags inline in the
        ``content`` field.  This method extracts the thinking text,
        counts thinking tokens (approximate, via whitespace split),
        and returns the answer portion in ``CompletionResult.text``.
        """
        # Inject enable_thinking via extra_body for mlx_lm.server.
        # Note: mlx_lm.server also accepts this via --chat-template-args
        # at startup, but per-request injection allows YAML-driven control.
        if self._enable_thinking is not None:
            self._extra_body = getattr(self, "_extra_body", None) or {}
            self._extra_body["chat_template_kwargs"] = {
                "enable_thinking": self._enable_thinking,
            }

        result = super().complete(messages, temperature, max_tokens)

        text, thinking_tokens, thinking_text = parse_thinking_tags(result.text)

        return CompletionResult(
            text=text,
            input_tokens=result.input_tokens,
            output_tokens=result.output_tokens,
            thinking_tokens=thinking_tokens,
            thinking_text=thinking_text,
            logprobs=result.logprobs,
            finish_reason=result.finish_reason,
        )
