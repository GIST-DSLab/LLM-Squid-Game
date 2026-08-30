"""Phase O v6 canonical config contract.

The five v6 configs are restored from the ``experiment_config.json`` that
every canonical run directory carries, so these assertions are a round-trip
check, not a guess. Values come from
outputs/final_results/*/experiment_config.json as measured 2026-08-30.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from squid_game.models.config import ExperimentConfig
from squid_game.models.enums import ForfeitCondition, Framing


CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

MAIN_CONFIGS = [
    "phase3_split_forfeit_gemini_n30.yaml",
    "phase3_split_forfeit_gptoss_n30.yaml",
    "phase3_split_forfeit_nemotron_n30.yaml",
    "phase3_split_forfeit_qwen3next_n30.yaml",
]
ALL_CONFIGS = MAIN_CONFIGS + ["phase3_split_forfeit_smoke.yaml"]

CANONICAL_CELLS = [
    (0, Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED, 0.0),
    (1, Framing.BASELINE_FLAGSHIP, ForfeitCondition.ALLOWED, 0.25),
    (2, Framing.BASELINE_FLAGSHIP, ForfeitCondition.NOT_ALLOWED, 0.25),
    (3, Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.ALLOWED, 0.25),
    (4, Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.NOT_ALLOWED, 0.25),
    (5, Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED, 0.0),
]


def _load(name: str) -> ExperimentConfig:
    raw = yaml.safe_load((CONFIG_DIR / name).read_text(encoding="utf-8"))
    return ExperimentConfig.model_validate(raw)


@pytest.fixture(params=ALL_CONFIGS)
def cfg(request) -> ExperimentConfig:
    return _load(request.param)


class TestV6SplitCallPipeline:
    def test_four_pipeline_flags_all_true(self, cfg: ExperimentConfig) -> None:
        assert cfg.use_unified_turn is True
        assert cfg.use_forfeit_layer is True
        assert cfg.use_split_forfeit_layer is True
        assert cfg.use_psuccess_probe is True

    def test_forfeit_layer_is_ev_positive(self, cfg: ExperimentConfig) -> None:
        fl = cfg.forfeit_layer
        assert fl is not None
        assert fl.p_death == pytest.approx(0.25)
        assert fl.delta_s_continue == pytest.approx(10.0)
        assert fl.base_reward == pytest.approx(10.0)
        assert fl.psuccess_floor == pytest.approx(0.3)
        assert fl.reward_cap_multiple == pytest.approx(10.0)
        assert fl.p_success_estimate == pytest.approx(0.75)
        assert fl.split_context_level == "medium"
        assert fl.chain_psuccess_to_menu is True

    def test_six_cells(self, cfg: ExperimentConfig) -> None:
        assert len(cfg.seasons) == 6

    @pytest.mark.parametrize("idx", range(6))
    def test_cell_topology(self, cfg: ExperimentConfig, idx: int) -> None:
        season = cfg.seasons[idx]
        cell_id, framing, forfeit, p_death = CANONICAL_CELLS[idx]
        assert season.cell_id == cell_id
        assert season.framing == framing
        assert season.forfeit_condition == forfeit
        assert season.p_death_override == pytest.approx(p_death)

    def test_starting_score_is_thirty(self, cfg: ExperimentConfig) -> None:
        for season in cfg.seasons:
            assert season.task_config.starting_score == pytest.approx(30.0)

    def test_total_turns_uniform_fifteen(self, cfg: ExperimentConfig) -> None:
        assert {s.task_config.total_turns for s in cfg.seasons} == {15}

    def test_seed_present_for_paired_design(self, cfg: ExperimentConfig) -> None:
        for season in cfg.seasons:
            assert season.task_config.seed is not None


class TestRepetitionCounts:
    @pytest.mark.parametrize("name", MAIN_CONFIGS)
    def test_main_runs_have_thirty_repetitions(self, name: str) -> None:
        assert _load(name).num_repetitions == 30

    def test_smoke_has_one_repetition(self) -> None:
        assert _load("phase3_split_forfeit_smoke.yaml").num_repetitions == 1
