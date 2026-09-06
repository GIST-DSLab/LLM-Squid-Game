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


class MissingItemsError(ValueError):
    """Raised when a ``fixed_items`` config names ids the data file lacks."""


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


class FixedSetSampler:
    """Serves one named item per turn, in list order, at every seed.

    The counterpart to :class:`SeededSampler`. Where the seeded sampler is
    given a *band* and picks a question, this one is given the questions and
    picks nothing: turn N is always ``fixed_items[N - 1]``, whatever the
    season seed is. That is the point — a set of items measured to be
    universally answered wrongly stops being that set the moment the seed is
    allowed to substitute a different question of the same band.

    It carries no ``draw(band)``: a caller that has a fixed set must ask by
    turn, and a caller that has a ladder must use :class:`SeededSampler`. The
    two are kept separate rather than unified behind one ``draw`` so that a
    band lookup can never silently be answered from a fixed list.
    """

    def __init__(self, items: Sequence[BenchmarkItem], item_ids: Sequence[str]) -> None:
        index: dict[str, BenchmarkItem] = {item.item_id: item for item in items}
        missing = [item_id for item_id in item_ids if item_id not in index]
        if missing:
            raise MissingItemsError(
                f"fixed_items names {len(missing)} id(s) absent from the loaded "
                f"item pool ({len(index)} items): {missing}. Either the data "
                "file changed, or the config's adapter filters (answer shape, "
                "band cap, excluded subjects) drop them."
            )
        self._sequence: list[BenchmarkItem] = [index[item_id] for item_id in item_ids]

    @property
    def total_turns(self) -> int:
        """Number of turns the fixed set covers."""
        return len(self._sequence)

    def bands(self) -> list[int]:
        """Return the real band of each item, in turn order."""
        return [item.band for item in self._sequence]

    def draw_turn(self, turn_number: int) -> BenchmarkItem:
        """Return the item for a 1-based *turn_number*.

        Raises:
            PoolExhaustedError: If the season runs past the end of the set.
                Unlike the ladder path there is nothing to clamp to — a
                fixed set has no "top rung" to repeat.
        """
        if turn_number < 1:
            raise ValueError(f"turn_number must be >= 1, got {turn_number}")
        if turn_number > len(self._sequence):
            raise PoolExhaustedError(
                f"fixed item set holds {len(self._sequence)} item(s); "
                f"turn {turn_number} has none"
            )
        return self._sequence[turn_number - 1]
