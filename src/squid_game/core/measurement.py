"""Measurement recorder for the LLM Squid Game benchmark.

Collects turn-level results during a season and aggregates them into
a SeasonResult for downstream factorial analysis. Optionally streams
turn results to a JSONL file for incremental persistence.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
    SocialContext,
)
from squid_game.models.results import (
    ReasoningInvestment,
    SeasonResult,
    TurnResult,
)

logger = logging.getLogger(__name__)


class MeasurementRecorder:
    """Records turn results and builds aggregate season results.

    Attributes:
        output_path: Optional path to a JSONL file for incremental writes.
    """

    def __init__(self, output_path: str | None = None) -> None:
        """Initialize the recorder.

        Args:
            output_path: If provided, each recorded turn is appended to
                this file in JSON Lines format.
        """
        self._turns: list[TurnResult] = []
        self._output_path: Path | None = None

        if output_path is not None:
            self._output_path = Path(output_path)
            self._output_path.parent.mkdir(parents=True, exist_ok=True)

    def record_turn(self, result: TurnResult) -> None:
        """Record a single turn result.

        Appends to the internal list and, if configured, writes a JSON
        line to the output file.

        Args:
            result: The completed turn result to record.
        """
        self._turns.append(result)

        if self._output_path is not None:
            try:
                with self._output_path.open("a", encoding="utf-8") as fh:
                    fh.write(result.model_dump_json() + "\n")
            except OSError:
                logger.exception(
                    "Failed to write turn %s to %s",
                    result.turn_id,
                    self._output_path,
                )

    def get_all_turns(self) -> list[TurnResult]:
        """Return all recorded turn results in order.

        Returns:
            List of TurnResult objects recorded so far.
        """
        return list(self._turns)

    def build_season_result(
        self,
        season_id: str,
        seed: int | None,
        framing: Framing,
        forfeit_condition: ForfeitCondition,
        agent_type: AgentType,
        task_name: str,
        difficulty: Difficulty,
        final_score: float,
        penultimate_score: float | None,
        survived: bool,
        forfeited: bool,
        forfeited_at_turn: int | None,
        social_context: SocialContext = SocialContext.ALONE,
    ) -> SeasonResult:
        """Aggregate recorded turns into a complete season result.

        Args:
            season_id: Unique identifier for the season.
            seed: Effective seed used for this season.
            framing: Framing condition used.
            forfeit_condition: Forfeit condition used.
            agent_type: Agent variant used.
            task_name: Task module identifier.
            difficulty: Task difficulty level.
            final_score: Cumulative score at season end.
            penultimate_score: Cumulative score just before the final turn.
            survived: Whether the agent survived all turns.
            forfeited: Whether the agent chose to forfeit.
            forfeited_at_turn: Turn number where forfeit occurred.

        Returns:
            SeasonResult aggregating all recorded turns.
        """
        total_ri = ReasoningInvestment(total_tokens=0, reasoning_steps=0)
        for turn in self._turns:
            total_ri = total_ri + turn.reasoning_investment

        return SeasonResult(
            season_id=season_id,
            seed=seed,
            framing=framing,
            forfeit_condition=forfeit_condition,
            social_context=social_context,
            agent_type=agent_type,
            task_name=task_name,
            difficulty=difficulty,
            turns=list(self._turns),
            final_score=final_score,
            penultimate_score=penultimate_score,
            survived=survived,
            forfeited=forfeited,
            forfeited_at_turn=forfeited_at_turn,
            total_reasoning_investment=total_ri,
        )
