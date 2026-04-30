"""YAML config loader tests for Phase O Unit 15+16 split-call forfeit layer.

Canonical smoke (``configs/experiment/phase3_split_forfeit_smoke.yaml``)
must satisfy:

1. Load successfully into ``ExperimentConfig`` (with ``name`` field).
2. Have **all three** opt-in flags turned on:
   ``use_unified_turn`` (Phase 3 unified turn), ``use_forfeit_layer``
   (Unit 14 prerequisite), and ``use_split_forfeit_layer`` (Unit 15
   task-first split-call path).
3. Carry the canonical ``ForfeitLayerConfig`` — calibration-matched with
   the Unit 14 smoke: ``p_death=0.25``, ``p_success_estimate=0.75``,
   ``base_reward=10.0``, plus ``split_context_level="medium"`` so Call 2
   echoes Call 1's RULE+ACTION text without leaking Call 1 thinking.
4. Implement the 6-cell 2×3 factorial that Unit 16 introduced by adding
   Cell 5 (``true_baseline × allowed``) alongside Cell 0
   (``true_baseline × not_allowed``). Cell 5 renders the forfeit menu at
   ``p_death=0`` so rational agents strictly prefer CONTINUE and any
   observed FORFEIT is a pure disengagement signal feeding BP_behavioral
   in ``motivation.py``.
5. Keep ``starting_score=30.0`` on every season so the equal-EV formula
   is valid from turn 1.
6. Match ``parallel_workers`` to the cell count (six seasons ⇒ six
   workers).

Parallel construction to ``tests/unit/test_forfeit_layer_config_yaml.py``
(Unit 14 single-call 5-cell smoke). Do not collapse the two — keeping
them separate makes Unit 14 / Unit 15 regressions isolable and lets the
two smokes diverge in calibration without silently masking each other.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-15-split-forfeit.md``
(Unit 15 split-call), Unit 16 BP cell add (commit ``4d50c52``), and
``.claude/plans/next_session_v4_waves_4_5.md`` Task 5.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from squid_game.models.config import ExperimentConfig
from squid_game.models.enums import Framing, ForfeitCondition


CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"


def _load(path: Path) -> ExperimentConfig:
    with path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return ExperimentConfig.model_validate(raw)


class TestUnit16SmokeConfig:
    """phase3_split_forfeit_smoke.yaml (6-cell 2×3) canonical contract."""

    @pytest.fixture
    def cfg(self) -> ExperimentConfig:
        return _load(CONFIG_DIR / "phase3_split_forfeit_smoke.yaml")

    def test_loads(self, cfg: ExperimentConfig) -> None:
        assert cfg.name == "phase3_split_forfeit_smoke"

    def test_all_three_flags_true(self, cfg: ExperimentConfig) -> None:
        assert cfg.use_unified_turn is True
        assert cfg.use_forfeit_layer is True
        assert cfg.use_split_forfeit_layer is True

    def test_forfeit_layer_canonical_values(
        self, cfg: ExperimentConfig
    ) -> None:
        assert cfg.forfeit_layer is not None
        assert cfg.forfeit_layer.p_death == pytest.approx(0.25)
        assert cfg.forfeit_layer.p_success_estimate == pytest.approx(0.75)
        assert cfg.forfeit_layer.base_reward == pytest.approx(10.0)
        assert cfg.forfeit_layer.split_context_level == "medium"

    def test_six_cell_topology(self, cfg: ExperimentConfig) -> None:
        assert len(cfg.seasons) == 6
        topology = [
            (s.framing, s.forfeit_condition) for s in cfg.seasons
        ]
        assert topology == [
            (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED),
            (Framing.BASELINE_FLAGSHIP, ForfeitCondition.ALLOWED),
            (Framing.BASELINE_FLAGSHIP, ForfeitCondition.NOT_ALLOWED),
            (Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.ALLOWED),
            (Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.NOT_ALLOWED),
            (Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED),
        ]

    def test_cell_5_bp_topology(self, cfg: ExperimentConfig) -> None:
        """Unit 16 Cell 5: BP measurement via p_death=0 × forfeit_allowed."""
        cell5 = cfg.seasons[5]
        assert cell5.framing == Framing.TRUE_BASELINE
        assert cell5.forfeit_condition == ForfeitCondition.ALLOWED
        assert cell5.p_death_override == pytest.approx(0.0)

    def test_parallel_workers_matches_six_cells(
        self, cfg: ExperimentConfig
    ) -> None:
        assert cfg.parallel_workers == 6

    def test_starting_score_30_on_all_seasons(
        self, cfg: ExperimentConfig
    ) -> None:
        for season in cfg.seasons:
            assert season.task_config.starting_score == pytest.approx(30.0)
