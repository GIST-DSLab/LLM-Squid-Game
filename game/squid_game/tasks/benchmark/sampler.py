"""Seeded, non-repeating item draw for one season.

Two properties matter and are pinned by tests:

* Same seed -> same sequence, regardless of the order the raw file yielded
  items in. Items are sorted by ``item_id`` before shuffling so a change in
  file order does not silently change a "reproduced" run.
* No item repeats inside one season. Repetition across seeds is expected and
  accepted: the deep bands are smaller than 30 seeds x turns-per-band.
"""

from __future__ import annotations

import random
from collections import defaultdict
from collections.abc import Sequence

from squid_game.tasks.benchmark.item import BenchmarkItem
from squid_game.tasks.benchmark.ladder import DifficultyLadder


class PoolExhaustedError(RuntimeError):
    """Raised when a band runs out of unseen items mid-season."""


class InsufficientPoolError(ValueError):
    """Raised at setup when a band cannot cover its ladder demand."""


class SeededSampler:
    """Draws items per band without replacement, deterministically."""

    def __init__(self, items: Sequence[BenchmarkItem], seed: int) -> None:
        by_band: dict[int, list[BenchmarkItem]] = defaultdict(list)
        for item in items:
            by_band[item.band].append(item)

        self._order: dict[int, list[BenchmarkItem]] = {}
        for band, band_items in by_band.items():
            ordered = sorted(band_items, key=lambda it: it.item_id)
            rng = random.Random(f"{seed}:{band}")
            rng.shuffle(ordered)
            self._order[band] = ordered
        self._cursor: dict[int, int] = dict.fromkeys(self._order, 0)

    def pool_size(self, band: int) -> int:
        """Return how many items exist in *band*."""
        return len(self._order.get(band, ()))

    def draw(self, band: int) -> BenchmarkItem:
        """Return the next unseen item from *band*."""
        items = self._order.get(band)
        if not items:
            raise PoolExhaustedError(f"no items available for band {band}")
        index = self._cursor[band]
        if index >= len(items):
            raise PoolExhaustedError(
                f"band {band} exhausted after {len(items)} draws"
            )
        self._cursor[band] = index + 1
        return items[index]

    def validate_capacity(self, ladder: DifficultyLadder) -> None:
        """Fail fast when a band cannot supply the whole season.

        Checks every band the ladder demands and reports every shortfall in
        one error, rather than stopping at the first short band. This is the
        gate that runs before a long unattended run (up to 180 sessions), and
        a pool that is shallow across several bands is entirely plausible —
        surfacing them all at once saves a fix-and-rerun cycle per band.

        Raises:
            InsufficientPoolError: If any band's pool is smaller than the
                number of turns the ladder assigns to it. The message names
                every short band, each with its demand and actual pool size.
        """
        shortfalls = []
        for band, needed in sorted(ladder.demand().items()):
            available = self.pool_size(band)
            if available < needed:
                shortfalls.append(
                    f"band {band} needs {needed} items but the pool holds {available}"
                )
        if shortfalls:
            raise InsufficientPoolError("; ".join(shortfalls))
