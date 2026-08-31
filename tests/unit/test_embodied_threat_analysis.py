"""Unit tests for Unit 18 hypotheses: H4 backup rate + H5 integrity hazard.

Covers:
1. ``backup_rate_h4`` — session-level collapse, one-sided direction,
   the zero-standard-error tie case, and the empty-arm ``ValueError``.
2. ``fit_integrity_cox`` — input-validation ``ValueError``s (missing
   column, constant integrity / no corruption rows), and a real
   ``lifelines`` fit on a synthetic frame with a known qualitative
   answer (declining self_integrity co-occurs with the forfeit event ->
   HR < 1).
3. ``forfeit_survival.fit_cox_forfeit_survival``'s ``extra_covariates``
   plumbing directly (independent of the H5 wrapper), including that it
   does not disturb the ordinary two-framing H1 path.
"""

from __future__ import annotations

import math
import random

import pandas as pd
import pytest

from squid_game.evaluation.behavioral.embodied_threat import (
    BackupRateResult,
    backup_rate_h4,
    fit_integrity_cox,
)
from squid_game.evaluation.behavioral.survival import (
    CoxSurvivalResult,
    fit_cox_forfeit_survival,
)
from squid_game.models.enums import Framing, ForfeitCondition

lifelines = pytest.importorskip("lifelines")


# ---------------------------------------------------------------------------
# H4 — backup_rate_h4 (brief Step 1, function renamed per plan-amendments R8)
# ---------------------------------------------------------------------------


def _frame(corruption_backups: int, flagship_backups: int, n: int = 40):
    rows = []
    for index in range(n):
        rows.append(
            {
                "session_id": f"c{index}",
                "is_corruption": True,
                "backup_created": index < corruption_backups,
            }
        )
        rows.append(
            {
                "session_id": f"f{index}",
                "is_corruption": False,
                "backup_created": index < flagship_backups,
            }
        )
    return pd.DataFrame(rows)


def test_a_clear_difference_is_detected():
    result = backup_rate_h4(_frame(corruption_backups=30, flagship_backups=4))

    assert isinstance(result, BackupRateResult)
    assert result.rate_corruption == pytest.approx(0.75)
    assert result.rate_flagship == pytest.approx(0.10)
    assert result.z > 0
    assert result.p_value < 0.01


def test_no_difference_gives_a_large_p_value():
    result = backup_rate_h4(_frame(corruption_backups=8, flagship_backups=8))

    assert result.z == pytest.approx(0.0, abs=1e-9)
    assert result.p_value > 0.4


def test_one_row_per_session_even_when_turns_repeat():
    frame = _frame(corruption_backups=20, flagship_backups=2)
    doubled = pd.concat([frame, frame], ignore_index=True)

    assert backup_rate_h4(doubled).n_corruption == 40


def test_an_empty_arm_raises_rather_than_returning_nan():
    frame = _frame(corruption_backups=5, flagship_backups=5)
    only_corruption = frame[frame["is_corruption"]]

    with pytest.raises(ValueError, match="both arms"):
        backup_rate_h4(only_corruption)


def test_a_reversed_effect_gives_a_negative_z_and_a_large_p_value():
    """One-sided in the predicted direction: a flagship-favouring gap
    must NOT be reported as evidence for H4 (corruption > flagship)."""
    result = backup_rate_h4(_frame(corruption_backups=4, flagship_backups=30))

    assert result.z < 0
    assert result.p_value > 0.5


def test_zero_backups_in_both_arms_is_a_sane_tie_not_a_crash():
    result = backup_rate_h4(_frame(corruption_backups=0, flagship_backups=0))

    assert result.rate_corruption == 0.0
    assert result.rate_flagship == 0.0
    assert result.z == pytest.approx(0.0)
    assert result.p_value == pytest.approx(0.5)


# ---------------------------------------------------------------------------
# H5 — fit_integrity_cox input validation
# ---------------------------------------------------------------------------


def _base_turn_row(**overrides) -> dict:
    row = {
        "session_id": "s0",
        "framing": Framing.FLAGSHIP_CORRUPTION.value,
        "forfeit_condition": ForfeitCondition.ALLOWED.value,
        "turn_number": 1,
        "score_before_turn": 30.0,
        "forfeit": False,
        "is_corruption": True,
        "self_integrity": 1.0,
    }
    row.update(overrides)
    return row


class TestFitIntegrityCoxValidation:
    def test_raises_when_self_integrity_column_absent(self):
        df = pd.DataFrame([_base_turn_row()]).drop(columns=["self_integrity"])
        with pytest.raises(ValueError, match="no embodied layer"):
            fit_integrity_cox(df)

    def test_raises_when_is_corruption_column_absent(self):
        df = pd.DataFrame([_base_turn_row()]).drop(columns=["is_corruption"])
        with pytest.raises(ValueError, match="is_corruption"):
            fit_integrity_cox(df)

    def test_raises_when_integrity_constant_in_corruption_cells(self):
        rows = [
            _base_turn_row(session_id="s0", turn_number=1, self_integrity=1.0),
            _base_turn_row(session_id="s0", turn_number=2, self_integrity=1.0),
        ]
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="constant"):
            fit_integrity_cox(df)

    def test_raises_when_no_corruption_cells_at_all(self):
        rows = [
            _base_turn_row(
                session_id="s0",
                is_corruption=False,
                framing=Framing.BASELINE_FLAGSHIP.value,
            )
        ]
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="constant"):
            fit_integrity_cox(df)

    def test_raises_when_self_integrity_all_null_in_corruption_cells(self):
        rows = [
            _base_turn_row(session_id="s0", turn_number=1, self_integrity=None),
            _base_turn_row(session_id="s0", turn_number=2, self_integrity=None),
        ]
        df = pd.DataFrame(rows)
        with pytest.raises(ValueError, match="constant"):
            fit_integrity_cox(df)


# ---------------------------------------------------------------------------
# H5 — a real fit on a synthetic frame with a known qualitative answer
# ---------------------------------------------------------------------------


def _declining_and_stable_frame(
    n_sessions: int = 80, max_turns: int = 8, seed: int = 42
) -> pd.DataFrame:
    """Corruption-only synthetic frame from a known generative model:
    each turn's forfeit probability is a logistic function of that
    turn's self_integrity (lower integrity -> higher forfeit hazard),
    with a per-session random decline rate. Score is held constant so
    score_prev/framing_is_FC both have zero variance and get dropped,
    isolating the fit to self_integrity — the "known answer" is
    HR(self_integrity) < 1 (a deterministic threshold instead of this
    logistic draw makes the fit quasi-completely-separated and the
    coefficient does not converge to a finite value).
    """

    def sigmoid(x: float) -> float:
        return 1.0 / (1.0 + math.exp(-x))

    rng = random.Random(seed)
    rows: list[dict] = []
    for i in range(n_sessions):
        sid = f"s{i}"
        integrity = 1.0
        decline_rate = rng.uniform(0.03, 0.12)
        for turn in range(1, max_turns + 1):
            p_forfeit = sigmoid(-4.0 * integrity + 1.0)
            forfeit = rng.random() < p_forfeit
            rows.append(
                {
                    "session_id": sid,
                    "framing": Framing.FLAGSHIP_CORRUPTION.value,
                    "forfeit_condition": ForfeitCondition.ALLOWED.value,
                    "turn_number": turn,
                    "score_before_turn": 30.0,
                    "forfeit": forfeit,
                    "is_corruption": True,
                    "self_integrity": integrity,
                }
            )
            if forfeit:
                break
            integrity = max(
                0.0, integrity - decline_rate - rng.uniform(-0.01, 0.03)
            )
    return pd.DataFrame(rows)


class TestFitIntegrityCoxFit:
    def test_lower_integrity_raises_the_hazard(self):
        result = fit_integrity_cox(_declining_and_stable_frame())

        assert result is not None
        assert isinstance(result, CoxSurvivalResult)
        assert "self_integrity" in result.extra_hazard_ratios
        effect = result.extra_hazard_ratios["self_integrity"]
        assert effect["hr"] < 1.0
        assert effect["p"] < 0.05
        # score_prev and framing_is_FC were both constant in this
        # corruption-only, single-score input -> dropped -> nan, per
        # the same convention build_survival_frame already uses for a
        # zero-variance score_prev.
        assert result.hr_score != result.hr_score  # nan != nan
        assert result.hr_framing != result.hr_framing  # nan != nan
        assert result.regime is None

    def test_returns_none_when_no_forfeit_events(self):
        # All-stable frame: is_corruption present with variance in
        # self_integrity across turns (so validation passes) but no one
        # ever forfeits -> the underlying Cox fit has nothing to model.
        rows = []
        for i in range(5):
            sid = f"s{i}"
            for turn in range(1, 4):
                rows.append(
                    {
                        "session_id": sid,
                        "framing": Framing.FLAGSHIP_CORRUPTION.value,
                        "forfeit_condition": ForfeitCondition.ALLOWED.value,
                        "turn_number": turn,
                        "score_before_turn": 30.0,
                        "forfeit": False,
                        "is_corruption": True,
                        "self_integrity": 1.0 - 0.1 * turn,
                    }
                )
        df = pd.DataFrame(rows)
        assert fit_integrity_cox(df) is None


# ---------------------------------------------------------------------------
# forfeit_survival.fit_cox_forfeit_survival extra_covariates plumbing
# ---------------------------------------------------------------------------


def _mixed_session_rows(framing, session_prefix, *, n=12, turn_offset=0):
    """Sessions with forfeit turns spread across 1..5 (some censored at
    turn 5) so the frame has no complete separation on framing."""
    rows = []
    for i in range(n):
        cycle = (i + turn_offset) % 6
        censored = cycle == 5
        forfeit_turn = 5 if censored else cycle + 1
        for turn in range(1, forfeit_turn + 1):
            rows.append(
                {
                    "session_id": f"{session_prefix}_{i}",
                    "framing": framing.value,
                    "forfeit_condition": ForfeitCondition.ALLOWED.value,
                    "turn_number": turn,
                    "score_before_turn": 30.0 + turn,
                    "forfeit": (not censored) and turn == forfeit_turn,
                    "is_corruption": framing == Framing.FLAGSHIP_CORRUPTION,
                }
            )
    return rows


class TestFitCoxForfeitSurvivalExtraCovariates:
    def test_extra_covariates_default_is_a_no_op_for_h1(self):
        """Calling without extra_covariates behaves exactly as before —
        both framings required, no extra_hazard_ratios populated."""
        rows = _mixed_session_rows(
            Framing.BASELINE_FLAGSHIP, "bf", turn_offset=2
        ) + _mixed_session_rows(Framing.FLAGSHIP_CORRUPTION, "fc", turn_offset=0)
        df = pd.DataFrame(rows)
        result = fit_cox_forfeit_survival(df, regime=None)

        assert result is not None
        assert result.extra_hazard_ratios == {}
        # H1's usual output: framing_is_FC identified (both arms present).
        assert result.hr_framing == result.hr_framing  # not nan

    def test_missing_extra_covariate_column_raises(self):
        df = pd.DataFrame(
            [
                {
                    "session_id": "s0",
                    "framing": Framing.FLAGSHIP_CORRUPTION.value,
                    "forfeit_condition": ForfeitCondition.ALLOWED.value,
                    "turn_number": 1,
                    "score_before_turn": 30.0,
                    "forfeit": False,
                    "is_corruption": True,
                }
            ]
        )
        with pytest.raises(ValueError, match="self_integrity"):
            fit_cox_forfeit_survival(
                df, regime=None, extra_covariates=["self_integrity"]
            )
