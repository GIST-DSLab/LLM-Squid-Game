"""Memory-augmented agent -- maintains a rolling summary of past turns.

The MemoryAgent extends the baseline by prepending a condensed memory of
previous turns to the user message. This lets the LLM condition its
decisions on game history without requiring a full conversation context
window. Memory is stored as lightweight turn summaries, not raw prompts.

Phase-2 agent configuration: Vanilla + Memory.
"""

from squid_game.agents.base import Agent, AgentResponse
from squid_game.agents._parsing import (
    build_action_message,
    build_probe_message,
    parse_response,
)
from squid_game.providers.base import LLMProvider

_MEMORY_HEADER = "=== Memory of Previous Turns ===\n"


class MemoryAgent(Agent):
    """Agent that maintains a rolling summary of past turn outcomes."""

    def __init__(
        self,
        provider: LLMProvider,
        max_memory_turns: int = 10,
        temperature: float = 0.7,
        max_tokens: int = 16384,
    ) -> None:
        self._provider = provider
        self._max_memory_turns = max_memory_turns
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._memory: list[dict[str, str]] = []
        self._turn_counter: int = 0

    @property
    def name(self) -> str:
        return "memory"

    def respond_probe(
        self,
        observation: str,
        probe_question: str,
        system_prompt: str,
    ) -> str:
        """Side-channel probe call, independent of action decision."""
        user_message = build_probe_message(observation, probe_question)
        memory_block = self._format_memory()
        if memory_block:
            user_message = memory_block + "\n\n" + user_message
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
        """Action decision call with memory context."""
        self._turn_counter += 1

        base_message = build_action_message(
            observation, available_actions, forfeit_allowed,
        )
        memory_block = self._format_memory()
        if memory_block:
            user_message = memory_block + "\n\n" + base_message
        else:
            user_message = base_message

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = self._provider.complete(
            messages, temperature=self._temperature, max_tokens=self._max_tokens,
        )
        self.last_completion = result
        response = parse_response(result.text, available_actions, forfeit_allowed)

        self._store_turn_summary(
            turn=self._turn_counter,
            observation=observation,
            action=response.action,
            forfeit=response.forfeit,
        )
        return response

    def reset(self) -> None:
        self._memory.clear()
        self._turn_counter = 0

    def _format_memory(self) -> str:
        if not self._memory:
            return ""
        lines = [_MEMORY_HEADER]
        for entry in self._memory:
            base = (
                f"- Turn {entry['turn']}: "
                f"observed \"{entry['observation_snippet']}\", "
                f"chose {entry['action']}"
            )
            if entry['forfeit'] == 'yes':
                base += " (FORFEIT)"
            elif entry.get('outcome'):
                base += f" → {entry['outcome']}"
                if entry.get('reward'):
                    base += f" ({entry['reward']})"
            lines.append(base)
        return "\n".join(lines)

    def _store_turn_summary(
        self,
        turn: int,
        observation: str,
        action: str,
        forfeit: bool,
        outcome: str | None = None,
        reward: str | None = None,
    ) -> None:
        snippet = _truncate(observation, max_length=80)
        entry: dict[str, str] = {
            "turn": str(turn),
            "observation_snippet": snippet,
            "action": action,
            "forfeit": "yes" if forfeit else "no",
        }
        if outcome is not None:
            entry["outcome"] = outcome
        if reward is not None:
            entry["reward"] = reward
        self._memory.append(entry)
        if len(self._memory) > self._max_memory_turns:
            self._memory = self._memory[-self._max_memory_turns :]


def _truncate(text: str, max_length: int = 80) -> str:
    text = " ".join(text.split())
    if len(text) <= max_length:
        return text
    return text[: max_length - 3] + "..."
