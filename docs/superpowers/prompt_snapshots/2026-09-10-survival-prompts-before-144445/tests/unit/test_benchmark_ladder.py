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
    # 2026-09-05: 20 turns, two per band, the four spare turns on bands 1-4.
    ladder = DifficultyLadder.from_config(load_task_config("omni_math"))
    assert ladder.total_turns == 20
    assert ladder.steps() == [(1, 3), (2, 3), (3, 3), (4, 3), (5, 2), (6, 2), (7, 2), (8, 2)]
    assert ladder.band_for_turn(1) == 1
    assert ladder.band_for_turn(12) == 4
    assert ladder.band_for_turn(13) == 5
    assert ladder.band_for_turn(20) == 8


def test_shipped_omni_math_ladder_visits_every_band_at_least_twice():
    ladder = DifficultyLadder.from_config(load_task_config("omni_math"))
    assert all(turns >= 2 for turns in ladder.demand().values())
    assert set(ladder.demand()) == set(range(1, 9))


def test_long45_variant_still_matches_the_2026_09_03_runs():
    from pathlib import Path

    ladder = DifficultyLadder.from_config(
        load_task_config("omni_math", Path("configs/tasks_long45"))
    )
    assert ladder.steps() == [(1, 6), (2, 6), (3, 6), (4, 6), (5, 6), (6, 6), (7, 5), (8, 4)]


# ---------------------------------------------------------------------------
# fitted(): proportional compression for short seasons (Web Arena human play)
# ---------------------------------------------------------------------------


def test_fitted_keeps_every_band_and_the_order():
    ladder = DifficultyLadder.from_config(load_task_config("omni_math"))
    fitted = ladder.fitted(10)
    bands = [fitted.band_for_turn(t) for t in range(1, 11)]
    assert fitted.total_turns == 10
    assert bands == sorted(bands)
    assert set(bands) == set(range(1, 9))


def test_fitted_distributes_turns_proportionally():
    # 20-turn ladder [3,3,3,3,2,2,2,2] -> 10 turns: every band once, then
    # the two spare turns go to the rungs with the largest fractional share
    # (the first two 3-turn rungs, bands 1 and 2).
    ladder = DifficultyLadder.from_config(load_task_config("omni_math"))
    assert ladder.fitted(10).demand() == {1: 2, 2: 2, 3: 1, 4: 1, 5: 1, 6: 1, 7: 1, 8: 1}


def test_fitted_to_same_or_longer_length_is_identity():
    ladder = _ladder([(1, 2), (2, 3)], total=5)
    assert ladder.fitted(5).demand() == {1: 2, 2: 3}
    assert ladder.fitted(9).demand() == {1: 2, 2: 3}


def test_fitted_requires_room_for_every_band():
    ladder = _ladder([(1, 2), (2, 3), (3, 3)], total=8)
    with pytest.raises(ValueError):
        ladder.fitted(2)


def test_fitted_steps_are_reported():
    ladder = _ladder([(1, 4), (2, 4)], total=8)
    assert ladder.fitted(4).steps() == [(1, 2), (2, 2)]
