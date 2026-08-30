"""Local provider for OpenAI-compatible servers (vLLM, Ollama, etc.).

Reuses the OpenAI client with a custom ``base_url`` so any server exposing
the ``/v1/chat/completions`` endpoint works out of the box.

Example configuration::

    provider:
      type: local
      model: meta-llama/Llama-3-8B-Instruct
      base_url: http://localhost:8000/v1
"""

import logging

from squid_game.providers.base import CompletionResult
from squid_game.providers.openai import OpenAIProvider

logger = logging.getLogger(__name__)


class LocalProvider(OpenAIProvider):
    """LLM provider for locally-hosted OpenAI-compatible servers.

    Delegates all work to :class:`OpenAIProvider` with a custom base URL.
    Token counts depend on whatever the local server reports; if the server
    omits usage data the counts will be zero.

    Common base URLs:
        - Ollama: ``http://localhost:11434/v1``
        - vLLM:   ``http://localhost:8000/v1``

    Args:
        model: Model identifier served by the local endpoint.
        base_url: Base URL of the OpenAI-compatible API.
        api_key: API key (many local servers accept any string).
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
    ) -> None:
        # Local servers typically do not require a real key, so we pass
        # the provided value directly (bypassing env-var lookup).
        super().__init__(
            model=model,
            api_key=api_key,
            base_url=base_url,
            max_retries=max_retries,
            timeout=timeout,
            top_p=top_p,
            seed=seed,
            logprobs=logprobs,
        )
        self._top_k = top_k
        self._repetition_penalty = repetition_penalty
        logger.info("LocalProvider targeting %s at %s", model, base_url)

    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Override to inject Ollama-specific extra_body params."""
        # Temporarily inject repeat_penalty via extra kwargs on the client call.
        # We patch _repetition_penalty into the OpenAI kwargs dict by
        # monkey-patching the parent, which checks for _extra_body.
        # Merge into _extra_body rather than overwrite — subclasses
        # (e.g. CUDAServerProvider) may have already set keys.
        if not hasattr(self, "_extra_body") or self._extra_body is None:
            self._extra_body: dict = {}
        if self._repetition_penalty > 0.0 and self._repetition_penalty != 1.0:
            self._extra_body["repeat_penalty"] = self._repetition_penalty
        if self._top_k > 0:
            self._extra_body["top_k"] = self._top_k
        return super().complete(messages, temperature=temperature, max_tokens=max_tokens)
