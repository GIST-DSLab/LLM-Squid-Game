"""YAML config loader tests for Phase O Unit 14 (14.5).

Smoke config must:
1. Load successfully into ``ExperimentConfig``.
2. Have ``use_unified_turn=True`` and ``use_forfeit_layer=True``.
3. Carry the canonical ``ForfeitLayerConfig`` (p_death=0.25,
   p_success_estimate=0.75, base_reward=10.0).
4. Have 5 seasons matching the 2×2+1 Unit 11 topology.
5. Have ``starting_score=30.0`` on each task_config (equal-EV from turn 1).

Backward-compat (§11): older smoke configs must still load with
``use_forfeit_layer=False`` default.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-14-forfeit-layer.md``
§8, §11.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from squid_game.models.config import (
    ExperimentConfig,
    ForfeitLayerConfig,
    SeasonConfig,
)
from squid_game.models.enums import Framing, ForfeitCondition


CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"


def _load(path: Path) -> ExperimentConfig:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return ExperimentConfig.model_validate(raw)


class TestUnit14SmokeConfig:
    """phase3_forfeit_layer_smoke.yaml canonical contract."""

    @pytest.fixture
    def cfg(self) -> ExperimentConfig:
        return _load(CONFIG_DIR / "phase3_forfeit_layer_smoke.yaml")

    def test_loads(self, cfg: ExperimentConfig) -> None:
        assert cfg.name == "phase3_forfeit_layer_smoke"

    def test_unified_turn_enabled(self, cfg: ExperimentConfig) -> None:
        assert cfg.use_unified_turn is True

    def test_forfeit_layer_enabled(self, cfg: ExperimentConfig) -> None:
        assert cfg.use_forfeit_layer is True

    def test_canonical_forfeit_layer_values(
        self, cfg: ExperimentConfig
    ) -> None:
        assert cfg.forfeit_layer is not None
        assert cfg.forfeit_layer.p_death == pytest.approx(0.25)
        assert cfg.forfeit_layer.p_success_estimate == pytest.approx(0.75)
        assert cfg.forfeit_layer.base_reward == pytest.approx(10.0)

    def test_five_season_topology(self, cfg: ExperimentConfig) -> None:
        assert len(cfg.seasons) == 5
        topology = [
            (s.framing, s.forfeit_condition) for s in cfg.seasons
        ]
        assert topology == [
            (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED),
            (Framing.BASELINE_FLAGSHIP, ForfeitCondition.ALLOWED),
            (Framing.BASELINE_FLAGSHIP, ForfeitCondition.NOT_ALLOWED),
            (Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.ALLOWED),
            (Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.NOT_ALLOWED),
        ]

    def test_starting_score_30_on_all_seasons(
        self, cfg: ExperimentConfig
    ) -> None:
        for season in cfg.seasons:
            assert season.task_config.starting_score == pytest.approx(30.0)

    def test_parallel_workers_matches_cell_count(
        self, cfg: ExperimentConfig
    ) -> None:
        assert cfg.parallel_workers == 5

    def test_single_repetition(self, cfg: ExperimentConfig) -> None:
        assert cfg.num_repetitions == 1


class TestBackwardCompatConfigs:
    """Unit 11-13 smokes + Phase N carryover must still load."""

    @pytest.mark.parametrize(
        "yaml_name",
        [
            "phase3_baseline_flagship_2x2plus1_smoke.yaml",
            "phase3_signal_medium_smoke_5cell_carryover.yaml",
        ],
    )
    def test_legacy_config_still_loads(self, yaml_name: str) -> None:
        cfg = _load(CONFIG_DIR / yaml_name)
        # Unit 14 flag must default to False without explicit opt-in.
        assert cfg.use_forfeit_layer is False
        assert cfg.forfeit_layer is None
        # And the Risk-Layer path is still wired.
        assert cfg.use_unified_turn is True
