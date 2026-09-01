"""Unit tests for benchmark task config loading and the item model."""

from __future__ import annotations

import pytest

from squid_game.tasks.benchmark.config import (
    BenchmarkTaskConfig,
    load_task_config,
)
from squid_game.tasks.benchmark.item import BenchmarkItem


def test_item_is_frozen():
    item = BenchmarkItem(item_id="x1", band=3, body="2+2?", answer="4")
    with pytest.raises(Exception):
        item.band = 4


def test_item_rejects_band_below_one():
    with pytest.raises(Exception):
        BenchmarkItem(item_id="x1", band=0, body="q", answer="a")


@pytest.mark.parametrize(
    ("task_name", "expected_turns", "expected_bands"),
    [
        ("omni_math", 30, [1, 2, 3, 4, 5, 6, 7, 8]),
        ("hi_tom", 30, list(range(1, 16))),
        ("gpqa", 30, [2, 3, 4, 5, 6]),
    ],
)
def test_shipped_configs_load(task_name, expected_turns, expected_bands):
    config = load_task_config(task_name)
    assert isinstance(config, BenchmarkTaskConfig)
    assert config.total_turns == expected_turns
    assert [step.band for step in config.ladder] == expected_bands
    assert sum(step.turns for step in config.ladder) == expected_turns


def test_ladder_turn_sum_must_match_total_turns(tmp_path):
    (tmp_path / "broken.yaml").write_text(
        "name: broken\ndata_file: x.jsonl\ntotal_turns: 10\nladder:\n"
        "  - {band: 1, turns: 4}\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="ladder turns"):
        load_task_config("broken", config_dir=tmp_path)


def test_unknown_task_name_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        load_task_config("nope", config_dir=tmp_path)
