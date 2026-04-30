"""Abstract base class for LLM providers in the Squid Game benchmark.

LLM providers handle the raw API communication with language model services.
They are consumed by Agent implementations, never by the core engine directly.
This separation allows swapping between providers (OpenAI, Anthropic, local)
without touching agent logic.

To add a new provider:
    1. Subclass LLMProvider in a new file under src/squid_game/providers/
    2. Implement complete() and model_name
    3. Register via the provider registry
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CompletionResult:
    """Result of a single LLM completion call.

    Attributes:
        text: The generated text content.
        input_tokens: Number of tokens in the prompt.
        output_tokens: Number of tokens in the completion.
        thinking_tokens: Number of reasoning/thinking tokens (extended thinking).
        logprobs: Per-token log probabilities, if available.
        finish_reason: Why generation stopped ("stop" = EOS, "length" = max_tokens).
    """

    text: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int = 0
    thinking_text: str | None = None
    logprobs: list[float] | None = None
    finish_reason: str | None = None


class LLMProvider(ABC):
    """Abstract interface for language model API providers.

    Provides a unified completion interface that agents use to interact
    with any LLM backend. Token counts from CompletionResult feed into
    the Reasoning Investment (RI) metric on the X-axis.
    """

    @property
    @abstractmethod
    def model_name(self) -> str:
        """Identifier of the underlying model (e.g. 'gpt-4o', 'claude-sonnet-4-20250514')."""

    @abstractmethod
    def complete(
        self,
        messages: list[dict[str, str]],
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CompletionResult:
        """Send a chat completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature controlling randomness.
            max_tokens: Maximum number of tokens to generate.

        Returns:
            CompletionResult with the generated text and token usage.
        """
