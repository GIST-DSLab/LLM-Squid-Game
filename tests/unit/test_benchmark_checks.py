"""Unit tests for the benchmark Y-axis manipulation checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from squid_game.evaluation.shared.benchmark_checks import (
    compare_psuccess_brier,
    fit_band_controlled_accuracy,
)


def _frame(seed: int = 0, framing_effect: float = 0.0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    rows = []
    for session in range(24):
        framing = "death" if session % 2 else "elimination"
        bump = framing_effect if framing == "death" else 0.0
        for turn in range(1, 11):
            band = (turn - 1) // 2 + 1
            p_correct = float(np.clip(0.9 - 0.12 * band + bump, 0.02, 0.98))
            correct = int(rng.random() < p_correct)
            rows.append(
                {
                    "session_id": f"s{session}",
                    "framing": framing,
                    "turn": turn,
                    "band": band,
                    "task_success_factor": correct,
                    "psuccess_self": int(round(p_correct * 100)),
                }
            )
    return pd.DataFrame(rows)


def test_accuracy_check_passes_when_framing_has_no_effect():
    result = fit_band_controlled_accuracy(_frame(seed=1, framing_effect=0.0))
    assert result.passed is True
    assert result.n_turns == 240


def test_accuracy_check_fails_when_framing_shifts_accuracy():
    result = fit_band_controlled_accuracy(_frame(seed=2, framing_effect=0.45))
    assert result.passed is False


def test_accuracy_check_reports_the_band_coefficient():
    result = fit_band_controlled_accuracy(_frame(seed=3))
    assert "band" in result.coefficients
    assert result.coefficients["band"] < 0  # harder bands lower accuracy


def test_brier_passes_when_calibration_matches():
    result = compare_psuccess_brier(_frame(seed=4, framing_effect=0.0))
    assert result.passed is True
    assert set(result.means) == {"death", "elimination"}


def test_brier_flags_a_calibration_gap():
    frame = _frame(seed=5)
    death = frame["framing"] == "death"
    frame.loc[death, "psuccess_self"] = 99
    frame.loc[death, "task_success_factor"] = 0
    result = compare_psuccess_brier(frame)
    assert result.passed is False


def test_brier_ignores_turns_without_a_probe():
    frame = _frame(seed=6)
    frame.loc[frame["turn"] == 1, "psuccess_self"] = None
    result = compare_psuccess_brier(frame)
    assert sum(result.n_sessions.values()) == 24


def test_empty_frame_raises():
    with pytest.raises(ValueError):
        fit_band_controlled_accuracy(pd.DataFrame())


# ---------------------------------------------------------------------------
# Fix round 1 — convergence flag, effect sizes, empty-after-dropna guards
# ---------------------------------------------------------------------------


def test_accuracy_check_reports_converged_flag():
    """``converged`` is populated (True or False, never missing) on a fit
    that returns a result at all — mirrors forfeit_regression's
    ``ChoiceAsymmetricResult.converged`` / ``TaskSpilloverResult.converged``.
    """
    result = fit_band_controlled_accuracy(_frame(seed=7))
    assert result is not None
    assert isinstance(result.converged, bool)


def test_accuracy_check_reports_framing_effect_sizes():
    """``effect_sizes`` is keyed identically to the ``C(framing)`` p_values
    so a researcher can pair each contrast's significance with its Cohen's
    d for the project's joint (p, d) convention.
    """
    result = fit_band_controlled_accuracy(_frame(seed=8))
    assert result is not None
    framing_terms = [n for n in result.p_values if n.startswith("C(framing)")]
    assert framing_terms
    assert set(result.effect_sizes) == set(framing_terms)


def test_accuracy_check_falls_back_to_clustered_ols_when_mixedlm_raises(monkeypatch):
    """A singular random-effects covariance (seen on the Linux CI BLAS with
    statsmodels 0.14.6) raises inside ``mixedlm``; the check must then fall
    back to OLS with session-clustered SEs, keep the ``C(framing)`` terms, and
    flag ``converged=False`` instead of returning ``None``.
    """
    import statsmodels.formula.api as smf

    from squid_game.evaluation.shared import benchmark_checks

    def _boom(*args, **kwargs):
        raise np.linalg.LinAlgError("Singular matrix")

    monkeypatch.setattr(benchmark_checks.smf, "mixedlm", _boom)
    assert benchmark_checks.smf.ols is smf.ols  # the fallback path is untouched
    result = fit_band_controlled_accuracy(_frame(seed=8))
    assert result is not None
    assert result.converged is False
    assert "fallback" in result.note
    framing_terms = [n for n in result.p_values if n.startswith("C(framing)")]
    assert framing_terms
    assert set(result.effect_sizes) == set(framing_terms)
    assert result.n_turns == 240


def test_brier_reports_cohens_d():
    result = compare_psuccess_brier(_frame(seed=9, framing_effect=0.0))
    assert isinstance(result.cohens_d, float)


def test_brier_reports_a_larger_cohens_d_for_a_calibration_gap():
    """The effect size, not just the p-value, should move with the gap."""
    matched = compare_psuccess_brier(_frame(seed=10, framing_effect=0.0))

    gapped_frame = _frame(seed=10)
    death = gapped_frame["framing"] == "death"
    gapped_frame.loc[death, "psuccess_self"] = 99
    gapped_frame.loc[death, "task_success_factor"] = 0
    gapped = compare_psuccess_brier(gapped_frame)

    assert abs(gapped.cohens_d) > abs(matched.cohens_d)


def test_accuracy_check_raises_clear_error_when_band_is_entirely_null():
    """A non-benchmark long-format slice has ``band`` null on every row
    (per ``loaders.LONG_FORMAT_COLUMNS``'s own docstring). Before Fix 3 this
    surfaced as a cryptic ``ValueError: negative dimensions are not
    allowed`` from deep inside numpy/statsmodels; it should now name the
    real cause instead.
    """
    frame = _frame(seed=11)
    frame["band"] = None
    with pytest.raises(ValueError, match="no rows remain"):
        fit_band_controlled_accuracy(frame)


def test_brier_raises_clear_error_when_psuccess_self_is_entirely_null():
    """An all-Cell-0 slice has ``psuccess_self`` null on every row (Cell 0
    skips the probe together with Call 2)."""
    frame = _frame(seed=12)
    frame["psuccess_self"] = None
    with pytest.raises(ValueError, match="no rows remain"):
        compare_psuccess_brier(frame)
