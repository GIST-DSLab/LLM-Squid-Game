"""Unit tests for the turn -> difficulty band ladder."""

from __future__ import annotations

import pytest

from squid_game.tasks.benchmark.config import BenchmarkTaskConfig, load_task_config
from squid_game.tasks.benchmark.ladder import DifficultyLadder


def _ladder(steps: list[tuple[int, int]], total: int) -> DifficultyLadder:
    config = BenchmarkTaskConfig(
        name="t",
        data_file="t.jsonl",
        total_turns=total,
        ladder=[{"band": band, "turns": turns} for band, turns in steps],
    )
    return DifficultyLadder.from_config(config)


def test_band_for_turn_walks_the_rungs():
    ladder = _ladder([(1, 2), (2, 3)], total=5)
    assert [ladder.band_for_turn(t) for t in range(1, 6)] == [1, 1, 2, 2, 2]


def test_turn_beyond_total_clamps_to_last_band():
    ladder = _ladder([(1, 2), (2, 3)], total=5)
    assert ladder.band_for_turn(6) == 2
    assert ladder.band_for_turn(99) == 2


def test_turn_number_must_be_positive():
    ladder = _ladder([(1, 2)], total=2)
    with pytest.raises(ValueError):
        ladder.band_for_turn(0)


def test_demand_counts_turns_per_band():
    ladder = _ladder([(1, 2), (2, 3), (2, 1)], total=6)
    assert ladder.demand() == {1: 2, 2: 4}


def test_shipped_omni_math_ladder_matches_spec():
    ladder = DifficultyLadder.from_config(load_task_config("omni_math"))
    assert ladder.band_for_turn(1) == 1
    assert ladder.band_for_turn(4) == 1
    assert ladder.band_for_turn(5) == 2
    assert ladder.band_for_turn(24) == 6
    assert ladder.band_for_turn(25) == 7
    assert ladder.band_for_turn(30) == 8
