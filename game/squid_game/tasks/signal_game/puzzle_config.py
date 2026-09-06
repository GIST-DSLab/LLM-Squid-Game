"""``puzzle_ladder`` loading for the Signal Game per-turn puzzle mode (v2).

The ladder lives in ``configs/tasks/signal_game.yaml`` and is read at
runtime, so re-tuning difficulty is a YAML edit: one entry per turn with
the rule shape (``clauses`` / ``conjunctions``), the condition grammar
the generator may use (``predicates``), whether the query must sit
where two or more clauses hold (``overlap_query``) and how many
redundant clues to add on top of the minimal set (``extra_clues``).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from squid_game.tasks.benchmark.config import default_config_dir
from squid_game.tasks.signal_game.puzzle import PuzzleSpec


class PuzzleLadderStep(BaseModel):
    """One rung = one turn (spec §6)."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    turn: int = Field(ge=1)
    clauses: int = Field(ge=1)
    conjunctions: int = Field(ge=0)
    predicates: bool
    overlap_query: bool
    extra_clues: int = Field(ge=0)

    @model_validator(mode="after")
    def _consistent(self) -> "PuzzleLadderStep":
        if self.conjunctions > self.clauses:
            raise ValueError(f"turn {self.turn}: conjunctions ({self.conjunctions}) > clauses ({self.clauses})")
        if self.overlap_query and self.clauses < 2:
            raise ValueError(f"turn {self.turn}: overlap_query needs clauses >= 2")
        return self

    def to_spec(self) -> PuzzleSpec:
        return PuzzleSpec(
            turn=self.turn,
            clauses=self.clauses,
            conjunctions=self.conjunctions,
            predicates=self.predicates,
            overlap_query=self.overlap_query,
            extra_clues=self.extra_clues,
        )


class SignalPuzzleConfig(BaseModel):
    """The ``puzzle_ladder`` block: turn number -> spec."""

    model_config = ConfigDict(frozen=True)

    puzzle_ladder: list[PuzzleLadderStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _turns_consecutive(self) -> "SignalPuzzleConfig":
        turns = [s.turn for s in self.puzzle_ladder]
        if turns != list(range(1, len(turns) + 1)):
            raise ValueError(f"puzzle_ladder turns must be consecutive from 1, got {turns}")
        return self

    @property
    def total_turns(self) -> int:
        return len(self.puzzle_ladder)

    def spec_for_turn(self, turn_number: int) -> PuzzleSpec:
        """Spec for a 1-based turn; turns past the end clamp to the last rung."""
        idx = min(max(turn_number, 1), self.total_turns) - 1
        return self.puzzle_ladder[idx].to_spec()


def load_signal_puzzle_config(config_dir: Path | None = None) -> SignalPuzzleConfig:
    """Load the ``puzzle_ladder`` block from ``signal_game.yaml``.

    Raises:
        FileNotFoundError: If no ``signal_game.yaml`` exists in *config_dir*.
        ValueError: If that file carries no ``puzzle_ladder`` key, or the
            ladder itself is invalid (pydantic ``ValidationError`` is a
            ``ValueError`` subclass).
    """
    directory = config_dir if config_dir is not None else default_config_dir()
    path = directory / "signal_game.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No signal_game task config at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "puzzle_ladder" not in raw:
        raise ValueError(f"{path} has no puzzle_ladder (required for signal_mode: per_turn_puzzle)")
    return SignalPuzzleConfig.model_validate({"puzzle_ladder": raw["puzzle_ladder"]})
