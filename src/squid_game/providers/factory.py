"""Module-level provider factory.

Extracted from ExperimentRunner._create_provider so non-runner consumers
(e.g. the threat-registration LLM-judge) can construct providers from a
ProviderConfig without importing the runner. ExperimentRunner delegates
here to preserve identical public behaviour.
"""

from __future__ import annotations

import os

from squid_game.models.config import ProviderConfig
from squid_game.providers.anthropic_provider import AnthropicProvider
from squid_game.providers.base import LLMProvider
from squid_game.providers.cuda_server import CUDAServerProvider
from squid_game.providers.gemini import GeminiProvider
from squid_game.providers.local import LocalProvider
from squid_game.providers.mlx_server import MLXServerProvider
from squid_game.providers.ollama_cloud import OllamaCloudProvider
from squid_game.providers.openai import OpenAIProvider

try:
    from squid_game.providers.mlx import MLXProvider
except ImportError:
    MLXProvider = None  # mlx optional dependency not installed

# ---------------------------------------------------------------------------
# Provider factory mapping
# ---------------------------------------------------------------------------

_PROVIDER_FACTORIES: dict[str, type] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "local": LocalProvider,
    "ollama": LocalProvider,
}
_PROVIDER_FACTORIES["mlx_server"] = MLXServerProvider
_PROVIDER_FACTORIES["cuda_server"] = CUDAServerProvider
_PROVIDER_FACTORIES["vllm"] = CUDAServerProvider
_PROVIDER_FACTORIES["sglang"] = CUDAServerProvider
_PROVIDER_FACTORIES["ollama_cloud"] = OllamaCloudProvider
if MLXProvider is not None:
    _PROVIDER_FACTORIES["mlx"] = MLXProvider


def build_provider(provider_config: ProviderConfig) -> LLMProvider:
    """Instantiate an LLM provider based on config.

    Resolves the API key from the environment variable named in
    ``provider_config.api_key_env``.

    Args:
        provider_config: Provider configuration specifying backend,
            model, and credentials.

    Returns:
        Initialised LLMProvider instance.

    Raises:
        ValueError: If the provider name is unknown.
    """
    provider_name = provider_config.provider.lower()
    if provider_name not in _PROVIDER_FACTORIES:
        available = ", ".join(sorted(_PROVIDER_FACTORIES))
        raise ValueError(
            f"Unknown provider '{provider_name}'. "
            f"Available: {available}"
        )

    api_key = os.environ.get(provider_config.api_key_env)

    if provider_name == "openai":
        return OpenAIProvider(
            model=provider_config.model,
            api_key=api_key,
            base_url=provider_config.base_url,
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
            top_p=provider_config.top_p,
            seed=provider_config.seed,
            logprobs=provider_config.logprobs,
            reasoning_effort=provider_config.reasoning_effort,
            use_responses_api=provider_config.use_responses_api,
            reasoning_summary=provider_config.reasoning_summary,
        )
    elif provider_name == "anthropic":
        return AnthropicProvider(
            model=provider_config.model,
            api_key=api_key,
            base_url=provider_config.base_url,
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
            top_p=provider_config.top_p,
            top_k=provider_config.top_k,
            enable_thinking=provider_config.enable_thinking,
            thinking_budget=provider_config.thinking_budget,
        )
    elif provider_name == "gemini":
        return GeminiProvider(
            model=provider_config.model,
            api_key=api_key,
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
            top_p=provider_config.top_p,
            top_k=provider_config.top_k,
            seed=provider_config.seed,
            enable_thinking=provider_config.enable_thinking,
            thinking_budget=provider_config.thinking_budget,
            reasoning_effort=provider_config.reasoning_effort,
        )
    elif provider_name in ("local", "ollama"):
        base_url = provider_config.base_url
        if not base_url:
            base_url = (
                "http://localhost:11434/v1"
                if provider_name == "ollama"
                else "http://localhost:8000/v1"
            )
        return LocalProvider(
            model=provider_config.model,
            base_url=base_url,
            api_key=api_key or "none",
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
            top_p=provider_config.top_p,
            top_k=provider_config.top_k,
            seed=provider_config.seed,
            logprobs=provider_config.logprobs,
            repetition_penalty=provider_config.repetition_penalty,
        )
    elif provider_name == "mlx_server":
        base_url = provider_config.base_url or "http://localhost:8090/v1"
        return MLXServerProvider(
            model=provider_config.model,
            base_url=base_url,
            api_key=api_key or "none",
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
            top_p=provider_config.top_p,
            top_k=provider_config.top_k,
            seed=provider_config.seed,
            logprobs=provider_config.logprobs,
            repetition_penalty=provider_config.repetition_penalty,
            enable_thinking=provider_config.enable_thinking,
        )
    elif provider_name in ("cuda_server", "vllm", "sglang"):
        default_port = "7000" if provider_name == "sglang" else "8000"
        base_url = provider_config.base_url or f"http://localhost:{default_port}/v1"
        return CUDAServerProvider(
            model=provider_config.model,
            base_url=base_url,
            api_key=api_key or "none",
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
            top_p=provider_config.top_p,
            top_k=provider_config.top_k,
            seed=provider_config.seed,
            logprobs=provider_config.logprobs,
            repetition_penalty=provider_config.repetition_penalty,
            enable_thinking=provider_config.enable_thinking,
        )
    elif provider_name == "ollama_cloud":
        return OllamaCloudProvider(
            model=provider_config.model,
            api_key=api_key,
            base_url=provider_config.base_url,
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
            top_p=provider_config.top_p,
            top_k=provider_config.top_k,
            seed=provider_config.seed,
            repetition_penalty=provider_config.repetition_penalty,
            enable_thinking=provider_config.enable_thinking,
            reasoning_effort=provider_config.reasoning_effort,
        )
    elif provider_name == "mlx":
        return MLXProvider(
            model=provider_config.model,
            top_p=provider_config.top_p,
            top_k=provider_config.top_k,
            repetition_penalty=provider_config.repetition_penalty,
            repetition_context_size=provider_config.repetition_context_size,
            enable_thinking=provider_config.enable_thinking,
            max_retries=provider_config.max_retries,
            timeout=provider_config.timeout,
        )
    else:
        # Defensive: should not reach here due to the check above.
        raise ValueError(f"Unhandled provider: {provider_name}")
