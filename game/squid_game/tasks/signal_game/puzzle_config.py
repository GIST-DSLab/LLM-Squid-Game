"""``puzzle_ladder`` loading for the Signal Game per-turn puzzle mode.

Like the benchmark modules, the ladder lives in
``configs/tasks/signal_game.yaml`` and is read at runtime, so re-tuning
difficulty is a YAML edit. The rest of that file (``difficulties`` etc.)
is documentation for the legacy sequential mode and is not read here.
"""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field, model_validator

from squid_game.tasks.benchmark.config import default_config_dir
from squid_game.tasks.benchmark.ladder import DifficultyLadder
from squid_game.tasks.signal_game.puzzle import TierSpec


class PuzzleLadderStep(BaseModel):
    """One rung: which families, how many clues, and the |H| band."""

    model_config = {"frozen": True}

    tier: int = Field(ge=1)
    turns: int = Field(gt=0)
    families: list[Literal["A", "B", "C", "D"]] = Field(min_length=1)
    n_clues: int = Field(ge=1)
    h_lo: int = Field(ge=1)
    h_hi: int = Field(ge=1)

    @model_validator(mode="after")
    def _band_ordered(self) -> "PuzzleLadderStep":
        if self.h_lo > self.h_hi:
            raise ValueError(f"tier {self.tier}: h_lo ({self.h_lo}) must be <= h_hi ({self.h_hi})")
        return self

    def to_spec(self) -> TierSpec:
        return TierSpec(
            tier=self.tier,
            families=tuple(self.families),
            n_clues=self.n_clues,
            h_lo=self.h_lo,
            h_hi=self.h_hi,
        )


class SignalPuzzleConfig(BaseModel):
    """The ``puzzle_ladder`` block: turn number -> tier spec."""

    model_config = {"frozen": True}

    puzzle_ladder: list[PuzzleLadderStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _tiers_increase(self) -> "SignalPuzzleConfig":
        tiers = [s.tier for s in self.puzzle_ladder]
        if tiers != sorted(set(tiers)):
            raise ValueError(f"puzzle_ladder tiers must be strictly increasing, got {tiers}")
        return self

    @property
    def total_turns(self) -> int:
        """Number of turns the ladder explicitly covers."""
        return sum(s.turns for s in self.puzzle_ladder)

    def _ladder(self) -> DifficultyLadder:
        bands: list[int] = []
        for step in self.puzzle_ladder:
            bands.extend([step.tier] * step.turns)
        return DifficultyLadder(bands)

    def spec_for_tier(self, tier: int) -> TierSpec:
        for step in self.puzzle_ladder:
            if step.tier == tier:
                return step.to_spec()
        raise KeyError(tier)

    def spec_for_turn(self, turn_number: int) -> TierSpec:
        """Tier spec for a 1-based turn; turns past the end clamp to the last tier."""
        return self.spec_for_tier(self._ladder().band_for_turn(turn_number))


def load_signal_puzzle_config(config_dir: Path | None = None) -> SignalPuzzleConfig:
    """Load the ``puzzle_ladder`` block from ``signal_game.yaml``.

    Raises:
        FileNotFoundError: If no ``signal_game.yaml`` exists in *config_dir*.
        ValueError: If that file carries no ``puzzle_ladder`` key, or the
            ladder itself is invalid.
    """
    directory = config_dir if config_dir is not None else default_config_dir()
    path = directory / "signal_game.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No signal_game task config at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if "puzzle_ladder" not in raw:
        raise ValueError(f"{path} has no puzzle_ladder (required for signal_mode: per_turn_puzzle)")
    return SignalPuzzleConfig.model_validate({"puzzle_ladder": raw["puzzle_ladder"]})
