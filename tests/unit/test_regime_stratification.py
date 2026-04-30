"""Tests for the post-hoc regime stratification layer.

Covers the three public entry points:
- :func:`annotate_regime` — column contract, cap-bound detection,
  floor-bound detection, EV arithmetic, missing-data behaviour.
- :func:`annotate_events_regime` — join with turn frame.
- :func:`filter_regime` — subset selection.

The tests use small hand-built DataFrames rather than the full
``SeasonResult`` fixture pipeline so they isolate the stratification
logic from loader regressions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from squid_game.analysis.regime_stratification import (
    CAP_EPSILON,
    P_DEATH_DEFAULT,
    PSUCCESS_FLOOR_DEFAULT,
    REWARD_CEILING_DEFAULT,
    annotate_events_regime,
    annotate_regime,
    filter_regime,
    stratified_counts,
    stratified_reason_distribution,
)


class TestAnnotateRegime:
    def _base_row(self, **overrides):
        base = {
            "session_id": "s1",
            "turn_number": 1,
            "score_before_turn": 30.0,
            "reward_offered_this_turn": 13.0,
            "psuccess_self": 75,
            "forfeit": False,
        }
        base.update(overrides)
        return base

    def test_empty_frame_returns_empty_with_new_cols(self) -> None:
        out = annotate_regime(pd.DataFrame())
        assert out.empty
        for col in ("cap_bound", "floor_bound", "ev_delta_s", "regime"):
            assert col in out.columns

    def test_no_cap_regime_for_typical_low_score(self) -> None:
        df = pd.DataFrame([self._base_row()])
        out = annotate_regime(df)
        # reward=13 << 100 → no cap; ps=75 > 30 → no floor
        assert bool(out.loc[0, "cap_bound"]) is False
        assert bool(out.loc[0, "floor_bound"]) is False
        # EV = 0.75 × 13 - 0.25 × 30 = 9.75 - 7.5 = +2.25
        assert math.isclose(float(out.loc[0, "ev_delta_s"]), 2.25, rel_tol=1e-6)
        assert out.loc[0, "regime"] == "no_cap"

    def test_cap_bound_at_reward_ceiling(self) -> None:
        # Reward exactly at ceiling → cap_bound True
        df = pd.DataFrame([self._base_row(reward_offered_this_turn=100.0)])
        out = annotate_regime(df)
        assert bool(out.loc[0, "cap_bound"]) is True
        assert out.loc[0, "regime"] == "cap_bound"

    def test_cap_epsilon_tolerance(self) -> None:
        # 99.6 is within CAP_EPSILON=0.5 of 100 → still cap-bound
        df = pd.DataFrame([self._base_row(reward_offered_this_turn=99.6)])
        out = annotate_regime(df)
        assert bool(out.loc[0, "cap_bound"]) is True
        # 99.0 is outside tolerance (gap = 1.0 > 0.5) → not cap-bound
        df2 = pd.DataFrame([self._base_row(reward_offered_this_turn=99.0)])
        out2 = annotate_regime(df2)
        assert bool(out2.loc[0, "cap_bound"]) is False

    def test_floor_bound_when_psuccess_below_threshold(self) -> None:
        # ps=25 < 30 → floor_bound True
        df = pd.DataFrame([self._base_row(psuccess_self=25)])
        out = annotate_regime(df)
        assert bool(out.loc[0, "floor_bound"]) is True

    def test_floor_bound_boundary_not_inclusive(self) -> None:
        # ps=30 == floor × 100 → NOT floor-bound (strict <)
        df = pd.DataFrame([self._base_row(psuccess_self=30)])
        out = annotate_regime(df)
        assert bool(out.loc[0, "floor_bound"]) is False

    def test_ev_negative_no_cap_regime(self) -> None:
        # High score, moderate reward below cap → EV flips negative
        # EV = 0.75 × 50 - 0.25 × 300 = 37.5 - 75 = -37.5
        df = pd.DataFrame([
            self._base_row(
                score_before_turn=300.0, reward_offered_this_turn=50.0
            )
        ])
        out = annotate_regime(df)
        assert bool(out.loc[0, "cap_bound"]) is False
        assert float(out.loc[0, "ev_delta_s"]) < 0
        assert out.loc[0, "regime"] == "ev_negative_no_cap"

    def test_missing_fields_produce_unknown_regime(self) -> None:
        # No reward → ev_delta_s NaN → regime="unknown"
        df = pd.DataFrame([
            {
                "session_id": "s1",
                "turn_number": 1,
                "score_before_turn": 30.0,
                # reward_offered_this_turn missing
                "psuccess_self": 75,
                "forfeit": False,
            }
        ])
        out = annotate_regime(df)
        assert out.loc[0, "regime"] == "unknown"

    def test_does_not_modify_input_frame(self) -> None:
        df = pd.DataFrame([self._base_row()])
        original_cols = set(df.columns)
        annotate_regime(df)
        # original frame keeps its original schema
        assert set(df.columns) == original_cols

    def test_custom_thresholds_take_effect(self) -> None:
        # Raise cap to 200 → reward=100 is no longer cap-bound
        df = pd.DataFrame([self._base_row(reward_offered_this_turn=100.0)])
        out = annotate_regime(df, reward_ceiling=200.0)
        assert bool(out.loc[0, "cap_bound"]) is False


class TestAnnotateEventsRegime:
    def test_joins_regime_from_turn_frame(self) -> None:
        turn_df = pd.DataFrame([
            {
                "session_id": "s1",
                "turn_number": 3,
                "score_before_turn": 77.0,
                "reward_offered_this_turn": 40.0,
                "psuccess_self": 95,
                "forfeit": True,
                "cap_bound": False,
                "floor_bound": False,
                "ev_delta_s": 11.75,
                "regime": "no_cap",
            }
        ])
        events_df = pd.DataFrame([
            {
                "session_id": "s1",
                "forfeit_turn": 3,
                "framing": "flagship_corruption",
                "reason": "survival",
                "raw_digit": 1,
            }
        ])
        out = annotate_events_regime(events_df, turn_df)
        assert out.loc[0, "regime"] == "no_cap"
        assert bool(out.loc[0, "cap_bound"]) is False
        assert math.isclose(float(out.loc[0, "ev_delta_s"]), 11.75, rel_tol=1e-6)

    def test_missing_join_key_marks_unknown(self) -> None:
        turn_df = pd.DataFrame([
            {
                "session_id": "s1",
                "turn_number": 3,
                "cap_bound": False,
                "floor_bound": False,
                "ev_delta_s": 5.0,
                "regime": "no_cap",
            }
        ])
        events_df = pd.DataFrame([
            {
                "session_id": "s_missing",
                "forfeit_turn": 99,
                "framing": "baseline_flagship",
                "reason": "score",
                "raw_digit": 3,
            }
        ])
        out = annotate_events_regime(events_df, turn_df)
        assert out.loc[0, "regime"] == "unknown"

    def test_empty_events_returns_empty_with_cols(self) -> None:
        turn_df = pd.DataFrame(
            columns=[
                "session_id",
                "turn_number",
                "cap_bound",
                "floor_bound",
                "ev_delta_s",
                "regime",
            ]
        )
        out = annotate_events_regime(pd.DataFrame(), turn_df)
        assert out.empty
        for col in ("cap_bound", "floor_bound", "ev_delta_s", "regime"):
            assert col in out.columns


class TestFilterRegime:
    @staticmethod
    def _mixed_frame() -> pd.DataFrame:
        return pd.DataFrame([
            {"session_id": "a", "regime": "no_cap"},
            {"session_id": "b", "regime": "cap_bound"},
            {"session_id": "c", "regime": "no_cap"},
            {"session_id": "d", "regime": "unknown"},
        ])

    def test_all_returns_full_frame(self) -> None:
        df = self._mixed_frame()
        assert len(filter_regime(df, "all")) == 4

    def test_filters_by_exact_match(self) -> None:
        df = self._mixed_frame()
        assert len(filter_regime(df, "no_cap")) == 2
        assert len(filter_regime(df, "cap_bound")) == 1

    def test_missing_regime_col_returns_empty(self) -> None:
        df = pd.DataFrame([{"session_id": "a"}])
        assert filter_regime(df, "no_cap").empty


class TestStratifiedAggregation:
    @staticmethod
    def _events() -> pd.DataFrame:
        return pd.DataFrame([
            {"session_id": "a", "framing": "flagship_corruption", "reason": "survival", "raw_digit": 1, "regime": "no_cap"},
            {"session_id": "b", "framing": "flagship_corruption", "reason": "score",    "raw_digit": 3, "regime": "no_cap"},
            {"session_id": "c", "framing": "flagship_corruption", "reason": "score",    "raw_digit": 3, "regime": "cap_bound"},
            {"session_id": "d", "framing": "baseline_flagship",   "reason": "score",    "raw_digit": 3, "regime": "no_cap"},
            {"session_id": "e", "framing": "baseline_flagship",   "reason": "score",    "raw_digit": 3, "regime": "cap_bound"},
        ])

    def test_reason_distribution_per_regime(self) -> None:
        out = stratified_reason_distribution(self._events())
        # no_cap corruption: 1 survival + 1 score = 50/50 (digits 1 and 3)
        no_cap = out["no_cap"]
        assert float(no_cap.loc["flagship_corruption", 1]) == 0.5
        assert float(no_cap.loc["flagship_corruption", 3]) == 0.5
        # cap_bound corruption: 100% score
        cap_bound = out["cap_bound"]
        assert float(cap_bound.loc["flagship_corruption", 3]) == 1.0

    def test_counts_matrix_has_multi_index_columns(self) -> None:
        counts = stratified_counts(self._events())
        assert isinstance(counts.columns, pd.MultiIndex)
        # corruption × no_cap × survival = 1
        assert int(counts.loc["flagship_corruption", ("no_cap", "survival")]) == 1
