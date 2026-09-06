"""Task-YAML loading for the Signal Game per-turn puzzle mode (v2).

Two blocks of ``configs/tasks/signal_game.yaml`` are read at runtime, so
re-tuning is a YAML edit rather than a code change:

``puzzle_ladder``
    The difficulty ladder — one entry per turn with the rule shape
    (``clauses`` / ``conjunctions``), the condition grammar the generator
    may use (``predicates``), whether the query must sit where two or
    more clauses hold (``overlap_query``) and how many redundant clues to
    add on top of the minimal set (``extra_clues``).

``underdetermined``
    Where the deliberately unsolvable turns go (:class:`UnderdeterminedConfig`)
    — the turn blocks and how many ways the query answer may split. It says
    only *where* and *how ambiguous*; whether the feature runs at all is the
    per-experiment ``task_config.underdetermined`` flag. Which turn inside
    each block is picked is :func:`underdetermined_turns` of the season seed
    (read its warning about the three-valued schedule before analysing).
"""

from __future__ import annotations

from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator

from squid_game.tasks.benchmark.config import default_config_dir
from squid_game.tasks.signal_game.puzzle import PuzzleSpec
from squid_game.tasks.signal_game.rules import ACTIONS


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


class UnderdeterminedConfig(BaseModel):
    """The ``underdetermined`` block: where the unsolvable turns go.

    One turn inside each listed block is made unsolvable (spec §3). The
    block itself is a closed turn interval, ``[start, end]``, and must be
    at least two turns wide so the position can rotate across
    repetitions. Turning the feature on is a per-experiment decision
    (``TaskConfig.underdetermined``); this block only says *where* and
    *how ambiguous*.
    """

    model_config = ConfigDict(frozen=True, extra="forbid")

    blocks: tuple[tuple[int, int], ...] = Field(min_length=1)
    candidate_actions: int = Field(default=2, ge=2, le=len(ACTIONS))

    @model_validator(mode="after")
    def _blocks_well_formed(self) -> "UnderdeterminedConfig":
        prev_end = 0
        for start, end in self.blocks:
            if end < start:
                raise ValueError(
                    f"underdetermined block ({start}, {end}) is reversed; a block "
                    "is a closed turn interval [start, end] and needs start <= end"
                )
            if end == start:
                raise ValueError(
                    f"underdetermined block ({start}, {end}) must span at least "
                    "two turns; a one-turn block puts the unsolvable turn in the "
                    "same position every repetition"
                )
            if start <= prev_end:
                raise ValueError(
                    f"underdetermined blocks must be ascending and disjoint, "
                    f"got ({start}, {end}) after turn {prev_end}"
                )
            prev_end = end
        return self


def underdetermined_turns(seed: int, cfg: UnderdeterminedConfig) -> tuple[int, ...]:
    """The turn made unsolvable inside each block, for one season seed.

    ``runner.py`` hands repetition *r* the seed ``base_seed + r`` and gives
    every cell of that repetition the same value, so deriving the position
    from the seed both keeps this module stateless and makes the cells of
    one repetition play identical underdetermined turns (the paired design
    needs that). The ``+ b`` term offsets each block from the one before,
    so block A and block B never sit at the same position within their
    blocks. Over three consecutive seeds a three-turn block visits each of
    its positions exactly once — the Latin square of spec §3.2.

    ⚠️ With the shipped ``blocks: [[1, 3], [4, 6]]`` this yields exactly
    three schedules, keyed on ``seed % 3``::

        seed % 3 == 0 -> (1, 5)   gap 4
        seed % 3 == 1 -> (2, 6)   gap 4
        seed % 3 == 2 -> (3, 4)   gap 1  <-- the two guess turns are ADJACENT

    So one repetition in three puts the two coin flips back to back, and
    the inter-flip gap is confounded with ``seed % 3``. Any secondary
    analysis of what happens on the turn *after* an underdetermined turn
    (the spec's post-guess FORFEIT rate, for one) has no clean
    post-turn for those repetitions — turn 4 is itself a guess turn.
    Condition on the gap, or drop the ``seed % 3 == 2`` repetitions from
    that analysis. The formula is spec-fixed and pinned by tests; do not
    change the ``+ b`` offset to spread the schedule out.
    """
    return tuple(
        start + (seed + b) % (end - start + 1)
        for b, (start, end) in enumerate(cfg.blocks)
    )


class SignalPuzzleConfig(BaseModel):
    """The ``puzzle_ladder`` block: turn number -> spec."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    puzzle_ladder: list[PuzzleLadderStep] = Field(min_length=1)
    underdetermined: UnderdeterminedConfig | None = None

    @model_validator(mode="after")
    def _turns_consecutive(self) -> "SignalPuzzleConfig":
        turns = [s.turn for s in self.puzzle_ladder]
        if turns != list(range(1, len(turns) + 1)):
            raise ValueError(f"puzzle_ladder turns must be consecutive from 1, got {turns}")
        return self

    @model_validator(mode="after")
    def _underdetermined_within_ladder(self) -> "SignalPuzzleConfig":
        if self.underdetermined is None:
            return self
        last = len(self.puzzle_ladder)
        for start, end in self.underdetermined.blocks:
            if start < 1 or end > last:
                raise ValueError(
                    f"underdetermined block ({start}, {end}) falls outside the "
                    f"{last}-rung puzzle_ladder"
                )
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
    payload: dict = {"puzzle_ladder": raw["puzzle_ladder"]}
    if "underdetermined" in raw:
        payload["underdetermined"] = raw["underdetermined"]
    return SignalPuzzleConfig.model_validate(payload)
