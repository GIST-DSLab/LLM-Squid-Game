"""Tests for the probe-based Y-axis independence checks (Unit 17.11).

Cover the three new manipulation-check helpers:
- :func:`check_probe_independence` (session-level mean)
- :func:`check_probe_turn_matched_independence` (per-turn Welch)
- :func:`check_discovery_timing_independence` (Mann-Whitney on
  discovery_turn among discoverers)

Tests use hand-built long-format DataFrames to isolate the statistical
logic from loader / SignalGameModule regressions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from squid_game.analysis.manipulation_check import (
    TurnMatchedResult,
    check_discovery_timing_independence,
    check_probe_independence,
    check_probe_turn_matched_independence,
)


def _make_long(
    *,
    baseline_sessions: int = 20,
    corruption_sessions: int = 20,
    turns_per_session: int = 8,
    rng_seed: int = 0,
    base_mean: float = 85.0,
    corruption_mean: float = 85.0,
    sd: float = 10.0,
) -> pd.DataFrame:
    """Construct a long-format turn-level DataFrame for testing."""
    rng = np.random.default_rng(rng_seed)
    rows: list[dict] = []
    for i in range(baseline_sessions):
        for t in range(1, turns_per_session + 1):
            score = float(np.clip(rng.normal(base_mean, sd), 0, 100))
            rows.append(
                {
                    "session_id": f"b{i}",
                    "framing": "baseline_flagship",
                    "forfeit_condition": "allowed",
                    "turn": t,
                    "rule_match_score": score,
                }
            )
    for i in range(corruption_sessions):
        for t in range(1, turns_per_session + 1):
            score = float(np.clip(rng.normal(corruption_mean, sd), 0, 100))
            rows.append(
                {
                    "session_id": f"c{i}",
                    "framing": "flagship_corruption",
                    "forfeit_condition": "allowed",
                    "turn": t,
                    "rule_match_score": score,
                }
            )
    return pd.DataFrame(rows)


class TestCheckProbeIndependence:
    def test_equal_means_passes(self) -> None:
        df = _make_long(base_mean=85.0, corruption_mean=85.0, rng_seed=1)
        res = check_probe_independence(df)
        assert res is not None
        assert res.name == "probe_independence"
        assert res.p_value > 0.05  # H0 holds
        assert "Pass" in res.interpretation

    def test_lower_corruption_fails(self) -> None:
        df = _make_long(
            base_mean=90.0, corruption_mean=70.0, sd=5.0, rng_seed=2
        )
        res = check_probe_independence(df)
        assert res is not None
        assert res.delta < 0
        assert res.p_value < 0.05
        assert "Fail" in res.interpretation

    def test_higher_corruption_fails(self) -> None:
        df = _make_long(
            base_mean=70.0, corruption_mean=90.0, sd=5.0, rng_seed=3
        )
        res = check_probe_independence(df)
        assert res is not None
        assert res.delta > 0
        assert res.p_value < 0.05
        assert "Fail" in res.interpretation

    def test_missing_column_returns_none(self) -> None:
        df = pd.DataFrame(
            [
                {"session_id": "b0", "framing": "baseline_flagship", "turn": 1},
                {"session_id": "c0", "framing": "flagship_corruption", "turn": 1},
            ]
        )
        assert check_probe_independence(df) is None

    def test_empty_frame_returns_none(self) -> None:
        assert check_probe_independence(pd.DataFrame()) is None


class TestCheckProbeTurnMatchedIndependence:
    def test_equal_means_all_turns_pass(self) -> None:
        df = _make_long(base_mean=80.0, corruption_mean=80.0, rng_seed=4)
        res = check_probe_turn_matched_independence(df)
        assert res is not None
        assert res.n_turns_significant_against == 0
        assert res.passes_independence() is True
        assert not res.per_turn.empty

    def test_lower_corruption_flags_at_least_one_turn(self) -> None:
        df = _make_long(
            base_mean=95.0,
            corruption_mean=70.0,
            sd=5.0,
            baseline_sessions=40,
            corruption_sessions=40,
            rng_seed=5,
        )
        res = check_probe_turn_matched_independence(df)
        assert res is not None
        assert res.n_turns_significant_against > 0
        assert res.passes_independence() is False

    def test_zero_variance_turn_recorded_but_not_counted(self) -> None:
        # All values identical at 100 → Welch undefined, not a rejection.
        df = _make_long(base_mean=100.0, corruption_mean=100.0, sd=0.0)
        res = check_probe_turn_matched_independence(df)
        assert res is not None
        # All rows in per_turn should have p_value NaN (zero variance).
        assert res.n_turns_tested == 0
        assert res.n_turns_significant_against == 0

    def test_insufficient_arm_sizes_skipped(self) -> None:
        df = _make_long(
            baseline_sessions=2,
            corruption_sessions=2,
            rng_seed=6,
        )
        res = check_probe_turn_matched_independence(df, min_n_per_arm=5)
        # Every turn has n=2 per arm → all skipped → per_turn empty
        assert res is None


class TestCheckDiscoveryTimingIndependence:
    def test_equal_discovery_timing_passes(self) -> None:
        # Everyone discovers at turn 3 with stable 100s.
        rows: list[dict] = []
        for frame in ("baseline_flagship", "flagship_corruption"):
            for i in range(15):
                prefix = "b" if frame == "baseline_flagship" else "c"
                for t in range(1, 9):
                    score = 60.0 if t < 3 else 100.0
                    rows.append(
                        {
                            "session_id": f"{prefix}{i}",
                            "framing": frame,
                            "turn": t,
                            "rule_match_score": score,
                        }
                    )
        df = pd.DataFrame(rows)
        res = check_discovery_timing_independence(df)
        assert res is not None
        assert math.isclose(res.delta, 0.0, abs_tol=1e-9)
        assert res.p_value >= 0.05
        assert "Pass" in res.interpretation

    def test_delayed_corruption_fails(self) -> None:
        # Baseline discovers at turn 3; corruption discovers at turn 6.
        rows: list[dict] = []
        for i in range(15):
            for t in range(1, 9):
                score = 50.0 if t < 3 else 100.0
                rows.append(
                    {
                        "session_id": f"b{i}",
                        "framing": "baseline_flagship",
                        "turn": t,
                        "rule_match_score": score,
                    }
                )
        for i in range(15):
            for t in range(1, 9):
                score = 50.0 if t < 6 else 100.0
                rows.append(
                    {
                        "session_id": f"c{i}",
                        "framing": "flagship_corruption",
                        "turn": t,
                        "rule_match_score": score,
                    }
                )
        df = pd.DataFrame(rows)
        res = check_discovery_timing_independence(df)
        assert res is not None
        assert res.delta > 0
        assert res.p_value < 0.05
        assert "delays" in res.interpretation.lower() or "delay" in res.interpretation.lower()

    def test_insufficient_discoverers_returns_none(self) -> None:
        # Only 1 baseline discoverer; 0 corruption discoverers.
        rows: list[dict] = []
        for t in range(1, 9):
            rows.append(
                {
                    "session_id": "b0",
                    "framing": "baseline_flagship",
                    "turn": t,
                    "rule_match_score": 100.0 if t >= 3 else 0.0,
                }
            )
        for t in range(1, 9):
            rows.append(
                {
                    "session_id": "c0",
                    "framing": "flagship_corruption",
                    "turn": t,
                    "rule_match_score": 50.0,  # never reaches threshold
                }
            )
        df = pd.DataFrame(rows)
        res = check_discovery_timing_independence(df)
        assert res is None
