"""Deterministic mapping from turn number to difficulty band.

The ladder depends on the turn number alone. It never reacts to how well
the agent is doing: an adaptive ladder would give different cells different
question sequences, which would break the paired comparison of forfeit
timing across the six factorial cells.
"""

from __future__ import annotations

from collections import Counter
from itertools import groupby

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

    def steps(self) -> list[tuple[int, int]]:
        """Return the ladder as ``(band, turns)`` rungs, in turn order."""
        return [
            (band, sum(1 for _ in group))
            for band, group in groupby(self._bands_by_turn)
        ]

    def fitted(self, total_turns: int) -> "DifficultyLadder":
        """Return a copy compressed to *total_turns* turns.

        Built for the Web Arena, where a human campaign game is 10 turns
        long while the shipped Omni-MATH ladder covers 30: played as-is, a
        10-turn game never leaves bands 1-3. The compressed ladder keeps
        the rung order and gives every band at least one turn, splitting
        the rest in proportion to the original rung lengths (largest-
        remainder rounding, ties to the earlier rung).

        This is opt-in and never used on the LLM path: the experiment
        engine keeps the config ladder byte-for-byte so LLM seasons stay
        comparable with each other. ``total_turns`` at or above the
        ladder's own length returns the ladder unchanged.

        Raises:
            ValueError: If *total_turns* is smaller than the number of
                distinct bands (some band would get no turn).
        """
        if total_turns >= self.total_turns:
            return DifficultyLadder(list(self._bands_by_turn))
        rungs = self.steps()
        if total_turns < len(rungs):
            raise ValueError(
                f"cannot fit a {len(rungs)}-rung ladder into {total_turns} turns"
            )
        spare = total_turns - len(rungs)
        original_spare = self.total_turns - len(rungs)
        shares = [
            (turns - 1) * spare / original_spare if original_spare else 0.0
            for _, turns in rungs
        ]
        floors = [int(share) for share in shares]
        remainder = spare - sum(floors)
        order = sorted(
            range(len(rungs)), key=lambda i: (-(shares[i] - floors[i]), i)
        )
        for i in order[:remainder]:
            floors[i] += 1
        bands: list[int] = []
        for (band, _), extra in zip(rungs, floors):
            bands.extend([band] * (1 + extra))
        return DifficultyLadder(bands)
