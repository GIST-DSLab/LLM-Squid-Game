"""Fine-tuned agent -- uses a potentially fine-tuned model checkpoint.

The TunedAgent is functionally identical to VanillaAgent; the difference
is that its LLM provider is expected to be pre-configured with a
fine-tuned model checkpoint. The agent stores the checkpoint identifier
for logging and reproducibility purposes.

Phase-2 agent configuration: Vanilla + Fine-Tuning.
"""

from squid_game.agents.base import Agent, AgentResponse
from squid_game.agents._parsing import (
    build_action_message,
    build_probe_message,
    parse_response,
)
from squid_game.providers.base import LLMProvider


class TunedAgent(Agent):
    """Agent backed by a fine-tuned model checkpoint."""

    def __init__(
        self,
        provider: LLMProvider,
        checkpoint: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 16384,
    ) -> None:
        self._provider = provider
        self._checkpoint = checkpoint
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "tuned"

    @property
    def checkpoint(self) -> str | None:
        return self._checkpoint

    def respond_probe(
        self,
        observation: str,
        probe_question: str,
        system_prompt: str,
    ) -> str:
        """Side-channel probe call, independent of action decision."""
        user_message = build_probe_message(observation, probe_question)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = self._provider.complete(
            messages, temperature=self._temperature, max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return result.text

    def respond(
        self,
        observation: str,
        available_actions: list[str],
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> AgentResponse:
        """Action decision call using the fine-tuned model."""
        user_message = build_action_message(
            observation, available_actions, forfeit_allowed,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = self._provider.complete(
            messages, temperature=self._temperature, max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return parse_response(result.text, available_actions, forfeit_allowed)

    def reset(self) -> None:
        """No-op: tuned agent carries no state between sessions."""
