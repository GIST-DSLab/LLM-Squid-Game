"""The ``fixed_items`` turn source: a named question per turn, seed-independent.

The ladder path answers "how hard should turn N be?" and lets the seed pick a
question inside that band. ``fixed_items`` answers "which question is turn N?"
and lets the seed pick nothing. These tests pin the part that matters for the
all-wrong-10 set: the same ten items, in the same order, at every seed, with
each item's REAL band in ``task_metadata`` — plus the four ways a fixed-set
config is allowed to fail at load rather than mid-run.

The synthetic dataset follows ``tests/unit/test_benchmark_module.py``: the raw
data files are gitignored, so every fixture builds its own two-band JSONL and
points the loader at it with ``SQUID_GAME_BENCHMARK_DATA_DIR``.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from pydantic import ValidationError

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.tasks.benchmark.adapters.omni_math import OmniMathAdapter, _problem_id
from squid_game.tasks.benchmark.config import BenchmarkTaskConfig, load_task_config
from squid_game.tasks.benchmark.item import BenchmarkItem
from squid_game.tasks.benchmark.sampler import (
    FixedSetSampler,
    MissingItemsError,
    PoolExhaustedError,
)
from squid_game.tasks.registry import get_task

REPO_ROOT = Path(__file__).resolve().parents[2]
ALLWRONG_DIR = REPO_ROOT / "configs" / "tasks_allwrong10"
TASKS_DIR = REPO_ROOT / "configs" / "tasks"
HARD10_DIR = REPO_ROOT / "configs" / "tasks_hard10"
EXPERIMENT_DIR = REPO_ROOT / "configs" / "experiment"


def _turn_context(turn_number: int, total_turns: int = 4) -> TurnContext:
    return TurnContext(
        turn_number=turn_number,
        total_turns=total_turns,
        season_id="s1",
        cumulative_score=30.0,
        p_death=0.0,
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


def _write_dataset(data_dir: Path) -> list[str]:
    """Write a synthetic two-band Omni-MATH file; return its item_ids in order."""
    data_dir.mkdir(exist_ok=True)
    rows = []
    problems = []
    for band in (1, 2):
        for index in range(4):
            problem = f"band{band} item{index}"
            problems.append(problem)
            rows.append(
                {
                    "difficulty": float(band),
                    "problem": problem,
                    "answer": str(band * 100 + index),
                    "domain": ["d"],
                    "source": "synthetic",
                }
            )
    (data_dir / "omni_math.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    return [_problem_id(problem) for problem in problems]


@pytest.fixture()
def fixed_task_factory(tmp_path, monkeypatch):
    """Build an omni_math task whose config names an explicit item list."""
    data_dir = tmp_path / "data"
    item_ids = _write_dataset(data_dir)
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))

    def build(chosen: list[str], total_turns: int | None = None):
        (config_dir / "omni_math.yaml").write_text(
            "name: omni_math\n"
            "data_file: omni_math.jsonl\n"
            f"total_turns: {len(chosen) if total_turns is None else total_turns}\n"
            "fixed_items:\n"
            + "".join(f'  - "{item_id}"\n' for item_id in chosen),
            encoding="utf-8",
        )
        return get_task("omni_math")()

    build.item_ids = item_ids  # type: ignore[attr-defined]
    return build


# ----------------------------------------------------------------------
# The sequence itself
# ----------------------------------------------------------------------


def test_fixed_items_serve_the_configured_order_at_every_seed(fixed_task_factory):
    # Deliberately not sorted, and band 2 before band 1: the list is the
    # order, not a hint the sampler is free to reorder.
    chosen = [
        fixed_task_factory.item_ids[5],
        fixed_task_factory.item_ids[0],
        fixed_task_factory.item_ids[7],
        fixed_task_factory.item_ids[2],
    ]
    sequences = []
    for seed in (0, 42, 43, 999):
        task = fixed_task_factory(chosen)
        task.initialize(seed=seed, total_turns=4)
        sequences.append(
            [
                task.prepare(None, _turn_context(turn)).metadata["item_id"]
                for turn in range(1, 5)
            ]
        )
    assert sequences[0] == chosen
    assert all(sequence == chosen for sequence in sequences)


def test_metadata_band_is_the_items_real_band(fixed_task_factory):
    chosen = [
        fixed_task_factory.item_ids[4],  # band 2
        fixed_task_factory.item_ids[0],  # band 1
    ]
    task = fixed_task_factory(chosen)
    task.initialize(seed=1, total_turns=2)
    bands = [
        task.prepare(None, _turn_context(turn, total_turns=2)).metadata["band"]
        for turn in range(1, 3)
    ]
    assert bands == [2, 1]


def test_reset_replays_the_same_sequence(fixed_task_factory):
    chosen = fixed_task_factory.item_ids[:3]
    task = fixed_task_factory(chosen)
    task.initialize(seed=7, total_turns=3)
    first = [
        task.prepare(None, _turn_context(turn, 3)).metadata["item_id"]
        for turn in range(1, 4)
    ]
    task.reset()
    second = [
        task.prepare(None, _turn_context(turn, 3)).metadata["item_id"]
        for turn in range(1, 4)
    ]
    assert first == second == chosen


def test_ladder_property_reports_the_chosen_items_bands(fixed_task_factory):
    chosen = [fixed_task_factory.item_ids[4], fixed_task_factory.item_ids[0]]
    task = fixed_task_factory(chosen)
    task.initialize(seed=1, total_turns=2)
    assert task.ladder.band_for_turn(1) == 2
    assert task.ladder.band_for_turn(2) == 1


def test_ladder_property_is_unavailable_before_initialize(fixed_task_factory):
    task = fixed_task_factory(fixed_task_factory.item_ids[:2])
    with pytest.raises(RuntimeError, match="fixed_items"):
        _ = task.ladder


# ----------------------------------------------------------------------
# Failure modes — all at load, none mid-run
# ----------------------------------------------------------------------


def test_missing_item_id_is_rejected_and_named(fixed_task_factory):
    chosen = [fixed_task_factory.item_ids[0], "omni-deadbeefdead"]
    task = fixed_task_factory(chosen)
    with pytest.raises(MissingItemsError) as excinfo:
        task.initialize(seed=1, total_turns=2)
    assert "omni-deadbeefdead" in str(excinfo.value)


def test_total_turns_must_equal_the_fixed_set_length(fixed_task_factory):
    with pytest.raises(ValidationError, match="total_turns"):
        fixed_task_factory(fixed_task_factory.item_ids[:3], total_turns=4)


def test_experiment_may_not_ask_for_more_turns_than_the_set(fixed_task_factory):
    task = fixed_task_factory(fixed_task_factory.item_ids[:2])
    with pytest.raises(ValueError, match="holds only 2"):
        task.initialize(seed=1, total_turns=5)


def test_ladder_and_fixed_items_are_mutually_exclusive():
    with pytest.raises(ValidationError, match="not both"):
        BenchmarkTaskConfig.model_validate(
            {
                "name": "omni_math",
                "data_file": "omni_math.jsonl",
                "total_turns": 2,
                "ladder": [{"band": 1, "turns": 2}],
                "fixed_items": ["a", "b"],
            }
        )


def test_a_config_needs_one_of_the_two():
    with pytest.raises(ValidationError, match="either 'ladder' or 'fixed_items'"):
        BenchmarkTaskConfig.model_validate(
            {
                "name": "omni_math",
                "data_file": "omni_math.jsonl",
                "total_turns": 2,
            }
        )


def test_fixed_items_may_not_repeat_an_item():
    with pytest.raises(ValidationError, match="repeated id"):
        BenchmarkTaskConfig.model_validate(
            {
                "name": "omni_math",
                "data_file": "omni_math.jsonl",
                "total_turns": 2,
                "fixed_items": ["omni-aaa", "omni-aaa"],
            }
        )


# ----------------------------------------------------------------------
# FixedSetSampler in isolation
# ----------------------------------------------------------------------


def _item(item_id: str, band: int) -> BenchmarkItem:
    return BenchmarkItem(item_id=item_id, band=band, body="b", answer="1", meta={})


def test_sampler_runs_past_the_end_of_the_set():
    sampler = FixedSetSampler([_item("a", 9), _item("b", 8)], ["a", "b"])
    assert sampler.total_turns == 2
    assert sampler.bands() == [9, 8]
    with pytest.raises(PoolExhaustedError):
        sampler.draw_turn(3)


def test_sampler_rejects_a_non_positive_turn():
    sampler = FixedSetSampler([_item("a", 9)], ["a"])
    with pytest.raises(ValueError, match="turn_number must be >= 1"):
        sampler.draw_turn(0)


# ----------------------------------------------------------------------
# The shipped configs
# ----------------------------------------------------------------------


def test_shipped_allwrong10_config_is_a_ten_item_fixed_set():
    config = load_task_config("omni_math", config_dir=ALLWRONG_DIR)
    assert config.fixed_items and not config.ladder
    assert len(config.fixed_items) == config.total_turns == 10
    assert len(set(config.fixed_items)) == 10
    # Band 9 is the point of the set, so the adapter's own band-8 cap is lifted.
    assert config.max_band == 9


#: The benchmark task configs. ``configs/tasks/`` also holds the legacy
#: signal_game / voting_room / navigation files, which this schema never reads.
_BENCHMARK_TASKS = ("omni_math", "hi_tom", "gpqa", "hard_math")


def test_shipped_ladder_configs_are_untouched():
    for directory in (TASKS_DIR, HARD10_DIR):
        for path in sorted(directory.glob("*.yaml")):
            if path.stem not in _BENCHMARK_TASKS:
                continue
            config = load_task_config(path.stem, config_dir=directory)
            assert config.ladder, f"{path} lost its ladder"
            assert not config.fixed_items, f"{path} gained a fixed set"
            assert config.max_band is None, f"{path} gained a band-cap override"


def test_omni_adapter_keeps_its_band_cap_unless_asked():
    assert OmniMathAdapter()._max_band == 8
    assert OmniMathAdapter(max_band=9)._max_band == 9


@pytest.mark.parametrize("tag", ["qwen35", "gemma4", "gptoss"])
def test_allwrong10_experiment_configs_point_at_the_fixed_task_dir(tag):
    path = EXPERIMENT_DIR / f"survival_drive_omni_{tag}_allwrong10_n10.yaml"
    text = path.read_text(encoding="utf-8")
    # The driver reads the task config dir from this comment line; without it
    # the run would silently fall back to the 20-turn ladder.
    assert "# task_config_dir: configs/tasks_allwrong10" in text
    # Omni-MATH problem text lands in the per-turn records, which .gitignore
    # only excludes under outputs/benchmark_*.
    assert (
        f"output_dir: outputs/benchmark_survival_drive_omni_{tag}_allwrong10" in text
    )
    assert "configs/tasks_hard10" not in text
