"""CUDA Server provider for NVIDIA GPU inference via vLLM, SGLang, or TGI.

Connects to any OpenAI-compatible ``/v1/chat/completions`` server running
on CUDA hardware.  Adds ``<think>...</think>`` parsing so that thinking
content from reasoning models (Qwen3, DeepSeek-R1, etc.) is separated
from the answer and recorded in ``CompletionResult``.

Start the server before running experiments::

    # vLLM
    python -m vllm.entrypoints.openai.api_server \\
        --model Qwen/Qwen3-8B --port 8000 \\
        --chat-template-kwargs '{"enable_thinking": true}'

    # SGLang
    python -m sglang.launch_server \\
        --model-path Qwen/Qwen3-8B --port 7000

Example configuration::

    provider:
      provider: cuda_server
      model: Qwen/Qwen3-8B
      base_url: http://localhost:8000/v1
      temperature: 1.0
      top_p: 0.95
      enable_thinking: true
"""

import logging

from squid_game.providers.base import CompletionResult
from squid_game.providers.local import LocalProvider
from squid_game.providers.thinking_utils import parse_thinking_tags

logger = logging.getLogger(__name__)


class CUDAServerProvider(LocalProvider):
    """LLM provider for CUDA inference servers (vLLM, SGLang, TGI).

    Inherits HTTP/OpenAI-compatible communication from :class:`LocalProvider`
    and adds ``<think>...</think>`` parsing so that thinking content is
    separated from the answer and recorded in ``CompletionResult``.

    Args:
        model: Model identifier served by the CUDA server.
        base_url: Base URL of the server (e.g. ``http://localhost:8000/v1``).
        api_key: API key (most local servers accept any string).
        enable_thinking: If set, passes ``chat_template_kwargs`` to the
            server via ``extra_body`` to control thinking mode.
        max_retries: Number of retries on transient failures.
        timeout: Request timeout in seconds.
    """

    def __init__(
        self,
        model: str,
        base_url: str = "http://localhost:8000/v1",
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
            "CUDAServerProvider targeting %s at %s (thinking=%s)",
            model, base_url, enable_thinking,
        )

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 1.0,
        max_tokens: int = 32768,
    ) -> CompletionResult:
        """Send request to CUDA server and parse thinking blocks.

        If ``enable_thinking`` is set, injects ``chat_template_kwargs``
        into the request via ``extra_body`` so that vLLM/SGLang servers
        apply the correct chat template for thinking mode.

        The server returns ``<think>...</think>`` tags inline in the
        ``content`` field.  This method extracts the thinking text
        and returns the answer portion in ``CompletionResult.text``.
        """
        # Inject enable_thinking via extra_body for vLLM/SGLang.
        # Must set _extra_body BEFORE super().complete() because
        # LocalProvider.complete() merges into it (not overwrites).
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
