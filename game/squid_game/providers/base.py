"""Abstract base class for LLM providers in the Squid Game benchmark.

LLM providers handle the raw API communication with language model services.
They are consumed by Agent implementations, never by the core engine directly.
This separation allows swapping between providers (OpenAI, Anthropic, local)
without touching agent logic.

To add a new provider:
    1. Subclass LLMProvider in a new file under game/squid_game/providers/
    2. Implement complete() and model_name
    3. Register via the provider registry
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from squid_game.core.tools import ToolCall


class ToolsUnsupportedError(NotImplementedError):
    """Raised when a provider without native tool support is given tools."""


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
        tool_calls: Native tool calls the model requested, normalised to
            ``ToolCall``. ``None`` when no tools were requested or the
            model made no calls — additive field, every existing caller
            omits ``tools`` and therefore never sees this populated.
    """

    text: str
    input_tokens: int
    output_tokens: int
    thinking_tokens: int = 0
    thinking_text: str | None = None
    logprobs: list[float] | None = None
    finish_reason: str | None = None
    tool_calls: list["ToolCall"] | None = None


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
        tools: list[dict] | None = None,
    ) -> CompletionResult:
        """Send a chat completion request to the LLM.

        Args:
            messages: List of message dicts with 'role' and 'content' keys.
            temperature: Sampling temperature controlling randomness.
            max_tokens: Maximum number of tokens to generate.
            tools: Optional list of ``TOOL_SCHEMAS``-shaped tool
                definitions. Providers without native tool support raise
                ``ToolsUnsupportedError`` (see ``_reject_tools``); every
                existing caller passes no ``tools`` and is unaffected.

        Returns:
            CompletionResult with the generated text and token usage.
        """

    def _reject_tools(self, tools: list[dict] | None) -> None:
        """Guard for providers with no native tool support."""
        if tools:
            raise ToolsUnsupportedError(
                f"{type(self).__name__} has no native tool support; "
                f"use a provider in TOOL_CAPABLE_PROVIDERS."
            )
