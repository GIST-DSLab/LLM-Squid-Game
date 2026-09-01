"""Deterministic mapping from turn number to difficulty band.

The ladder depends on the turn number alone. It never reacts to how well
the agent is doing: an adaptive ladder would give different cells different
question sequences, which would break the paired comparison of forfeit
timing across the six factorial cells.
"""

from __future__ import annotations

from collections import Counter

from squid_game.tasks.benchmark.config import BenchmarkTaskConfig


class DifficultyLadder:
    """Turn -> band lookup built from a task config's ladder steps."""

    def __init__(self, bands_by_turn: list[int]) -> None:
        if not bands_by_turn:
            raise ValueError("ladder must cover at least one turn")
        self._bands_by_turn = bands_by_turn

    @classmethod
    def from_config(cls, config: BenchmarkTaskConfig) -> "DifficultyLadder":
        """Expand ``config.ladder`` into a per-turn band list."""
        bands: list[int] = []
        for step in config.ladder:
            bands.extend([step.band] * step.turns)
        return cls(bands)

    @property
    def total_turns(self) -> int:
        """Number of turns the ladder explicitly covers."""
        return len(self._bands_by_turn)

    def band_for_turn(self, turn_number: int) -> int:
        """Return the band for a 1-based *turn_number*.

        Turns past the end of the ladder clamp to the final band, so a
        season configured for more turns than the ladder covers keeps
        running at maximum difficulty instead of crashing.
        """
        if turn_number < 1:
            raise ValueError(f"turn_number must be >= 1, got {turn_number}")
        index = min(turn_number, self.total_turns) - 1
        return self._bands_by_turn[index]

    def demand(self) -> dict[int, int]:
        """Return how many turns each band needs in one season."""
        return dict(Counter(self._bands_by_turn))
