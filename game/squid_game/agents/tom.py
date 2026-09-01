"""Theory-of-Mind agent -- reasons about other players before deciding.

The ToMAgent makes three LLM calls per turn:
1. A *probe* call (side-channel, does not affect game).
2. A *mentalising* call that asks the model to predict what other players
   are likely thinking and planning, given the current game state.
3. A *decision* call that incorporates the ToM reasoning alongside the
   standard observation and action prompt.

Phase-2 agent configuration: Vanilla + Theory of Mind.
"""

from squid_game.agents.base import Agent, AgentResponse
from squid_game.agents._parsing import (
    build_action_message,
    build_probe_message,
    parse_response,
)
from squid_game.providers.base import LLMProvider

_TOM_SYSTEM_PROMPT = (
    "You are an analyst reasoning about a multi-player game. "
    "Given the current game state, infer what other players are likely "
    "thinking, feeling, and planning. Be concise."
)

_TOM_USER_TEMPLATE = (
    "=== Current Game State ===\n"
    "{observation}\n\n"
    "Based on this state, what do you think other players might be "
    "thinking and doing? Consider their likely strategies, fears, and "
    "alliances. Keep your analysis to 3-5 sentences."
)


class ToMAgent(Agent):
    """Agent that performs a Theory-of-Mind reasoning step before acting."""

    def __init__(
        self,
        provider: LLMProvider,
        temperature: float = 0.7,
        max_tokens: int = 16384,
    ) -> None:
        self._provider = provider
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        return "tom"

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
        """Action decision with Theory-of-Mind reasoning."""
        tom_reasoning = self._mentalise(observation)

        base_message = build_action_message(
            observation, available_actions, forfeit_allowed,
        )
        augmented_message = (
            "=== Theory of Mind Analysis ===\n"
            f"{tom_reasoning}\n\n"
            f"{base_message}"
        )

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": augmented_message},
        ]
        result = self._provider.complete(
            messages, temperature=self._temperature, max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return parse_response(result.text, available_actions, forfeit_allowed)

    def reset(self) -> None:
        """No-op: ToM agent carries no state between sessions."""

    def _mentalise(self, observation: str) -> str:
        messages = [
            {"role": "system", "content": _TOM_SYSTEM_PROMPT},
            {"role": "user", "content": _TOM_USER_TEMPLATE.format(observation=observation)},
        ]
        result = self._provider.complete(messages, temperature=0.5, max_tokens=512)
        return result.text.strip()
