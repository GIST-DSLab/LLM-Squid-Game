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

import os as _os
from abc import ABC, abstractmethod
from dataclasses import dataclass


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


# ---------------------------------------------------------------------------
# Agentic (tool-enabled) providers -- subagent-kill design
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SubagentUsage:
    """Token accounting for one subagent spawn (subagent-kill design)."""

    slot: str
    thinking_tokens: int
    output_tokens: int
    thinking_text: str | None = None


_DEFAULT_HOOK = _os.path.join(
    _os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))),
    "harness", "hooks", "subagent_budget.py",
)


@dataclass(frozen=True)
class ToolContext:
    """What an agentic task call needs beyond the messages.

    ``slots_json`` is ``SlotLedger.to_json()``; ``subagent_prompts`` maps
    every slot name (alive or not -- the tool surface must not reveal
    which) to the system prompt of that slot. See spec §6.4 / §7.
    """

    slots_json: dict
    subagent_prompts: dict[str, str]
    subagent_description: str = "Holds one of this round's examples."
    max_turns: int = 12
    hook_script: str = _DEFAULT_HOOK


@dataclass(frozen=True)
class AgenticCompletionResult(CompletionResult):
    """``CompletionResult`` plus per-subagent usage and the spawn log."""

    subagent_usage: tuple[SubagentUsage, ...] = ()
    spawn_log: tuple[dict, ...] = ()


class AgenticProvider(ABC):
    """Mixin for providers that can run a tool-enabled task call."""

    @abstractmethod
    def complete_agentic(
        self,
        messages: list[dict[str, str]],
        tool_context: ToolContext,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> AgenticCompletionResult:
        """Run one agentic turn with the slots in *tool_context* available."""
