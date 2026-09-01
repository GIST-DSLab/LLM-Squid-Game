"""Unit tests for the benchmark Y-axis manipulation checks."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from squid_game.analysis.benchmark_checks import (
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
