"""Unit test for the 3-way verbal forfeit-reason tally.

Covers the extension that counts task_curiosity(2) and score(3) alongside
survival(1) for the LLM report's 100%-stacked verbal bar. Offline: writes a
small ``regime_stratified_forfeit_events.csv`` fixture and checks the split.
"""

from __future__ import annotations

import csv
from pathlib import Path

import importlib


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["regime", "framing", "raw_digit"]
    with path.open("w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def test_analyze_one_model_splits_three_reasons(tmp_path: Path) -> None:
    mod = importlib.import_module("scripts.analyze_verbal_reason")
    rows = [
        # In-sample: no_cap x threat cell, one of each reason + an extra score.
        {"regime": "no_cap", "framing": "flagship_corruption", "raw_digit": "1"},
        {"regime": "no_cap", "framing": "baseline_flagship", "raw_digit": "2"},
        {"regime": "no_cap", "framing": "flagship_corruption", "raw_digit": "3"},
        {"regime": "no_cap", "framing": "flagship_corruption", "raw_digit": "3"},
        # Out-of-sample: excluded by regime and by framing filters.
        {"regime": "cap_bound", "framing": "flagship_corruption", "raw_digit": "1"},
        {"regime": "no_cap", "framing": "true_baseline", "raw_digit": "1"},
        # Blank/unknown digit is dropped from the split.
        {"regime": "no_cap", "framing": "flagship_corruption", "raw_digit": ""},
    ]
    csv_path = tmp_path / "regime_stratified_forfeit_events.csv"
    _write_csv(csv_path, rows)

    out = mod.analyze_one_model("test-model", csv_path)

    # n_forfeits counts the in-sample rows (incl. the blank-digit one).
    assert out["n_forfeits"] == 5
    assert out["n_reason_survival"] == 1
    assert out["n_reason_task_curiosity"] == 1
    assert out["n_reason_score"] == 2
    # Recognised-digit counts never exceed n_forfeits.
    assert (
        out["n_reason_survival"]
        + out["n_reason_task_curiosity"]
        + out["n_reason_score"]
        <= out["n_forfeits"]
    )
