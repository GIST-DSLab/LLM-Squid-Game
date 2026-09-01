"""Unit tests for seeded, non-repeating item sampling."""

from __future__ import annotations

import pytest

from squid_game.tasks.benchmark.config import BenchmarkTaskConfig
from squid_game.tasks.benchmark.item import BenchmarkItem
from squid_game.tasks.benchmark.ladder import DifficultyLadder
from squid_game.tasks.benchmark.sampler import (
    InsufficientPoolError,
    PoolExhaustedError,
    SeededSampler,
)


def _items(band: int, count: int) -> list[BenchmarkItem]:
    return [
        BenchmarkItem(item_id=f"b{band}-i{i}", band=band, body=f"q{i}", answer=str(i))
        for i in range(count)
    ]


def test_same_seed_gives_same_sequence():
    pool = _items(1, 10)
    sampler_a = SeededSampler(pool, seed=7)
    sampler_b = SeededSampler(pool, seed=7)
    assert [sampler_a.draw(1).item_id for _ in range(5)] == [
        sampler_b.draw(1).item_id for _ in range(5)
    ]


def test_different_seed_gives_different_sequence():
    pool = _items(1, 20)
    a = [SeededSampler(pool, seed=1).draw(1).item_id for _ in range(1)]
    b = [SeededSampler(pool, seed=2).draw(1).item_id for _ in range(1)]
    assert a != b


def test_no_repeat_within_a_session():
    pool = _items(1, 6)
    sampler = SeededSampler(pool, seed=3)
    drawn = [sampler.draw(1).item_id for _ in range(6)]
    assert len(set(drawn)) == 6


def test_draw_past_the_pool_raises():
    sampler = SeededSampler(_items(1, 2), seed=3)
    sampler.draw(1)
    sampler.draw(1)
    with pytest.raises(PoolExhaustedError):
        sampler.draw(1)


def test_draw_from_unknown_band_raises():
    sampler = SeededSampler(_items(1, 2), seed=3)
    with pytest.raises(PoolExhaustedError):
        sampler.draw(9)


def test_validate_capacity_rejects_a_shallow_pool():
    config = BenchmarkTaskConfig(
        name="t",
        data_file="t.jsonl",
        total_turns=4,
        ladder=[{"band": 1, "turns": 4}],
    )
    ladder = DifficultyLadder.from_config(config)
    ok = SeededSampler(_items(1, 4), seed=1)
    ok.validate_capacity(ladder)  # does not raise
    shallow = SeededSampler(_items(1, 3), seed=1)
    with pytest.raises(InsufficientPoolError, match="band 1"):
        shallow.validate_capacity(ladder)


def test_item_order_does_not_depend_on_input_order():
    pool = _items(1, 8)
    forward = SeededSampler(pool, seed=11)
    reversed_pool = SeededSampler(list(reversed(pool)), seed=11)
    assert [forward.draw(1).item_id for _ in range(8)] == [
        reversed_pool.draw(1).item_id for _ in range(8)
    ]
