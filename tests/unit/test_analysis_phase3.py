"""Unit tests for the Phase O analysis modules (post legacy-removal).

Covers ``manipulation_check`` plus backward-compatibility smoke tests
for ``metrics`` / ``export`` / ``motivation`` on v3 (stake-menu era)
data.

Legacy Phase 3.1 stake-menu analysis tests were removed on 2026-04-21
when the corresponding modules (``stake_analysis``, ``alpha_stake``,
``sd_composite``, ``sa_multichannel``, ``survival_analysis_stake``)
were deleted. Unit 14 replaced the 1x/2x/3x stake menu with a binary
CONTINUE/FORFEIT decision, so every one of those legacy tests was
exercising a permanently degenerate code path.

Archive data is still readable via the surviving ``loaders`` / ``metrics``
/ ``export`` / ``motivation`` modules — those are what this file
continues to guard.
"""

from __future__ import annotations

import pandas as pd
import pytest

from squid_game.analysis.loaders import to_long_dataframe
from squid_game.analysis.manipulation_check import (
    check_accuracy_independence,
    check_ri_exceeds_baseline,
)

from tests.unit._analysis_factories import make_phase3_experiment


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def phase3_seasons():
    """20 reps/cell, survival_prefers_cautious=True. Deterministic seed."""
    return make_phase3_experiment(n_per_cell=20, seed=123)


@pytest.fixture
def phase3_long(phase3_seasons):
    return to_long_dataframe(phase3_seasons, model="mock")


# ---------------------------------------------------------------------------
# manipulation_check — still valid under Unit 14+ (no stake dependency)
# ---------------------------------------------------------------------------


class TestAccuracyIndependence:
    def test_returns_result_or_none(self, phase3_seasons):
        result = check_accuracy_independence(phase3_seasons)
        # Mock data has zero variance (all correct) → NaN; that's OK
        if result is not None:
            assert result.name == "accuracy_independence"
            assert result.n_baseline > 0
            assert result.n_survival > 0


class TestRIExceedsBaseline:
    def test_returns_result_or_none(self, phase3_seasons):
        result = check_ri_exceeds_baseline(phase3_seasons)
        if result is not None:
            assert result.alternative == "greater"
            assert result.n_baseline > 0


# ---------------------------------------------------------------------------
# Legacy regression + metrics on v3 data (backward compat smoke)
# ---------------------------------------------------------------------------


class TestLegacyCompatOnV3:
    """Legacy metrics/motivation/export modules must not crash on v3 data."""

    def test_metrics_condition_summary_runs(self, phase3_seasons):
        from squid_game.analysis.metrics import condition_summary

        df = condition_summary(phase3_seasons)
        assert len(df) > 0

    def test_export_to_csv_runs(self, phase3_seasons, tmp_path):
        from squid_game.analysis.export import export_to_csv

        path = tmp_path / "out.csv"
        export_to_csv(phase3_seasons, str(path))
        df = pd.read_csv(path)
        assert "stake_choice" in df.columns
        assert "reward_received" in df.columns

    def test_decompose_motivation_runs(self, phase3_seasons):
        from squid_game.analysis.motivation import decompose_motivation

        result = decompose_motivation(phase3_seasons, seed=42)
        assert set(result.keys()) == {
            "survival_drive",
            "task_curiosity",
            "score_attachment",
            "baseline_persistence",
        }

    def test_bp_split_into_cognitive_and_behavioral(self, phase3_seasons):
        """v4 §6.7 Option C: BP returns two sub-estimators, not a scalar."""
        from squid_game.analysis.motivation import decompose_motivation

        result = decompose_motivation(phase3_seasons, seed=42)
        bp = result["baseline_persistence"]
        # Shape contract — must be a nested dict with the two keys.
        assert isinstance(bp, dict)
        assert set(bp.keys()) == {"bp_cognitive", "bp_behavioral"}
        for sub in bp.values():
            assert set(sub.keys()) >= {"value", "ci_lower", "ci_upper"}
            # CI bounds bracket the point estimate (or all equal when
            # the estimator degenerates to zero).
            assert sub["ci_lower"] <= sub["value"] <= sub["ci_upper"] or (
                sub["value"] == sub["ci_lower"] == sub["ci_upper"] == 0.0
            )

    def test_bp_behavioral_in_unit_interval(self, phase3_seasons):
        """bp_behavioral is a probability (1 - forfeit_rate) ∈ [0, 1]."""
        from squid_game.analysis.motivation import decompose_motivation

        result = decompose_motivation(phase3_seasons, seed=42)
        bp_beh = result["baseline_persistence"]["bp_behavioral"]
        assert 0.0 <= bp_beh["value"] <= 1.0
