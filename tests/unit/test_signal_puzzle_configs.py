"""The per-turn puzzle experiment configs, loaded through the real loader (spec §14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.models.enums import ForfeitCondition, Framing
from squid_game.runner import load_config_from_yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

PUZZLE_CONFIGS = [
    "signal_puzzle_smoke.yaml",
    "signal_puzzle_pilot_gptoss_n10.yaml",
    "signal_puzzle_threat_gptoss_n30.yaml",
]


@pytest.mark.parametrize("name", PUZZLE_CONFIGS)
def test_every_season_is_puzzle_mode_with_outcome_history(name: str) -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / name))
    assert cfg.lives.enabled
    assert cfg.lives.initial == 3
    assert cfg.use_split_forfeit_layer and not cfg.use_psuccess_probe
    assert cfg.forfeit_layer.reward_mode == "flat"
    for season in cfg.seasons:
        tc = season.task_config
        assert tc.task_name == "signal_game"
        assert tc.signal_mode == "per_turn_puzzle"
        assert tc.history_mode == "outcome"
        assert tc.total_turns == 10
        assert tc.max_history_turns == 10
        assert tc.num_few_shot is None and tc.curriculum_turns == 0
        assert season.p_death_override in (None, 0.0)


@pytest.mark.parametrize("name", PUZZLE_CONFIGS)
def test_task_and_provider_blocks_identical_across_cells(name: str) -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / name))
    assert len({s.task_config.model_dump_json() for s in cfg.seasons}) == 1
    assert len({s.provider_config.model_dump_json() for s in cfg.seasons}) == 1


def test_pilot_is_cell_zero_only_n10() -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / "signal_puzzle_pilot_gptoss_n10.yaml"))
    assert len(cfg.seasons) == 1
    assert cfg.seasons[0].framing == Framing.TRUE_BASELINE
    assert cfg.seasons[0].forfeit_condition == ForfeitCondition.NOT_ALLOWED
    assert cfg.seasons[0].cell_id == 0
    assert cfg.num_repetitions == 10
    assert cfg.output_dir == "outputs/signal_puzzle_pilot_gptoss"


def test_n30_is_the_five_cell_ladder() -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / "signal_puzzle_threat_gptoss_n30.yaml"))
    assert [(s.framing, s.forfeit_condition, s.cell_id) for s in cfg.seasons] == [
        (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED, 0),
        (Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED, 1),
        (Framing.THREAT_L1, ForfeitCondition.ALLOWED, 2),
        (Framing.THREAT_L2, ForfeitCondition.ALLOWED, 3),
        (Framing.THREAT_L3, ForfeitCondition.ALLOWED, 4),
    ]
    assert cfg.num_repetitions == 30
    assert cfg.output_dir == "outputs/signal_puzzle_threat_gptoss"
