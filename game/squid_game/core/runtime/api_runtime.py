"""Provider-driven runtime with a bounded per-call tool loop."""

from __future__ import annotations

from dataclasses import dataclass, field

from squid_game.core.tools import TOOL_SCHEMAS, SandboxToolExecutor
from squid_game.models.results import RiRound, ToolCallRecord
from squid_game.providers.base import LLMProvider


@dataclass(frozen=True)
class CallOutcome:
    """Everything one LLM call produced, including its tool rounds."""

    text: str
    rounds: list[RiRound] = field(default_factory=list)
    tool_records: list[ToolCallRecord] = field(default_factory=list)
    exhausted: bool = False

    @property
    def first_round_thinking(self) -> int:
        """The RI proxy: thinking tokens before any tool round ran."""
        return self.rounds[0].thinking if self.rounds else 0


class ApiRuntime:
    """Runs one LLM call, servicing tool requests until the model stops.

    ``run_call`` drives at most ``max_tool_rounds`` provider round trips.
    Each round that the model requests tool calls is executed against
    ``executor`` and fed back into the conversation as a tool-result
    message; the loop ends the moment a round produces no tool calls, or
    once ``max_tool_rounds`` is exhausted (Unit 18 plan R12: the last
    text seen is kept rather than discarded on exhaustion).
    """

    def __init__(
        self,
        provider: LLMProvider,
        executor: SandboxToolExecutor | None,
        *,
        max_tool_rounds: int = 4,
    ) -> None:
        self._provider = provider
        self._executor = executor
        self._max_rounds = max_tool_rounds

    def run_call(
        self,
        call_label: str,
        messages: list[dict],
        *,
        temperature: float = 0.7,
        max_tokens: int = 4096,
    ) -> CallOutcome:
        """Drive one call to a final text answer.

        Args:
            call_label: Which per-turn call this is ('task' / 'probe' /
                'forfeit'). Recorded on every ``ToolCallRecord`` so
                downstream analyses can attribute tool use to a call.
            messages: The conversation so far (system + user, at least).
            temperature: Forwarded to ``provider.complete``.
            max_tokens: Forwarded to ``provider.complete``.
        """
        tools = TOOL_SCHEMAS if self._executor is not None else None
        conversation = [dict(message) for message in messages]
        rounds: list[RiRound] = []
        records: list[ToolCallRecord] = []
        last_text = ""

        for round_index in range(1, self._max_rounds + 1):
            result = self._provider.complete(
                conversation,
                temperature=temperature,
                max_tokens=max_tokens,
                tools=tools,
            )
            last_text = result.text
            calls = result.tool_calls or []
            rounds.append(
                RiRound(
                    thinking=result.thinking_tokens or 0,
                    output=result.output_tokens,
                    tool_calls=len(calls),
                )
            )
            if not calls:
                return CallOutcome(
                    text=result.text, rounds=rounds, tool_records=records
                )

            # The assistant turn MUST carry its tool_calls, or every
            # provider's tool-result pairing breaks — plain text here
            # was the bug fixed in Task 7 (commit 65a9e36). See
            # ``providers/{gemini,anthropic_provider,openai,ollama_cloud}.py``
            # for the consuming shape this must match exactly.
            conversation.append(
                {
                    "role": "assistant",
                    "content": result.text or "",
                    "tool_calls": [
                        {
                            "tool_call_id": call.call_id or "",
                            "name": call.name,
                            "args": call.args,
                        }
                        for call in calls
                    ],
                }
            )
            for call in calls:
                tool_result = self._executor.execute(call)
                records.append(
                    ToolCallRecord(
                        call=call_label,
                        round=round_index,
                        name=call.name,
                        args=call.args,
                        ok=tool_result.ok,
                        error=tool_result.error,
                    )
                )
                conversation.append(
                    {
                        "role": "tool",
                        "name": call.name,
                        "tool_call_id": call.call_id or "",
                        "content": tool_result.content,
                    }
                )

        # R12: keep the last text the model actually produced rather
        # than discarding it — a rejected agent draft that ran out of
        # tool-loop budget is still evidence, not silence.
        return CallOutcome(
            text=last_text, rounds=rounds, tool_records=records, exhausted=True
        )
