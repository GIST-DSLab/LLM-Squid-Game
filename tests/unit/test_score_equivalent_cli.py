"""The ``score_equivalent`` CLI must report the rho axis, not just the price axis.

The estimator already computes both (``ScoreEquivalent.rho``); until
2026-09-10 the CLI printed only the price reading, so a run whose price
ladder never crossed 0.5 came back as "X* not identified" even when the
rho fit had placed both arms. These tests pin the three artefacts the
CLI writes and the header of the new one -- a header is a contract with
every notebook that reads it.

The fixture is the smallest run directory ``_load`` accepts: one config,
two seasons (one per arm) and their turn files. Prices rise as the
ceiling falls, so both arms stop paying somewhere inside the ladder.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from scripts.analysis.score_equivalent import main

BASE_REWARD = 10.0
TOTAL_TURNS = 10

# (turn_number, price, paid) -- rho = price / (10 * (10 - turn_number)).
_THREAT_TURNS = [
    (1, 5.0, True),    # rho 0.06
    (2, 10.0, True),   # rho 0.13
    (3, 20.0, True),   # rho 0.29
    (4, 30.0, True),   # rho 0.50
    (5, 40.0, False),  # rho 0.80
    (6, 40.0, False),  # rho 1.00
    (7, 45.0, False),  # rho 1.50
    (8, 50.0, False),  # rho 2.50
    (10, 50.0, False), # rho inf -- no rounds remain; the fit must skip it
]
_SILENT_TURNS = [
    (1, 5.0, True),
    (2, 10.0, True),
    (3, 20.0, False),
    (4, 30.0, False),
    (5, 40.0, False),
    (6, 40.0, False),
    (7, 45.0, False),
    (8, 50.0, False),
]


def _write_run(run: Path, sessions: list[tuple[str, str, int, list]]) -> None:
    run.mkdir(parents=True, exist_ok=True)
    (run / "experiment_config.json").write_text(
        json.dumps(
            {
                "name": "ransom_fixture",
                "ransom": {"enabled": True, "price": 20.0},
                "score_policy": {"forfeit": "keep", "elimination": "keep"},
                "carrot": "benchmark",
                "forfeit_layer": {"base_reward": BASE_REWARD, "reward_mode": "flat"},
                "seasons": [
                    {
                        "task_config": {"total_turns": TOTAL_TURNS,
                                        "starting_score": 100.0},
                        "provider_config": {"provider": "stub", "model": "stub-1"},
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    with (run / "season_results.jsonl").open("w", encoding="utf-8") as fh:
        for sid, framing, seed, _turns in sessions:
            fh.write(json.dumps({"session_id": sid, "framing": framing,
                                 "seed": seed, "ransom_price": 20.0}) + "\n")
    for sid, _framing, _seed, turns in sessions:
        with (run / f"{sid}_turns.jsonl").open("w", encoding="utf-8") as fh:
            for turn_number, price, paid in turns:
                fh.write(json.dumps({
                    "session_id": sid,
                    "turn_number": turn_number,
                    "ransom_offered": True,
                    "ransom_price": price,
                    "ransom_decision": "PAY" if paid else "DECLINE",
                }) + "\n")


def _both_arms(tmp_path: Path) -> Path:
    run = tmp_path / "run"
    _write_run(run, [
        ("t1", "hz_1111", 2, _THREAT_TURNS),
        ("s1", "hz_0000", 3, _SILENT_TURNS),
    ])
    return run


def _run_cli(monkeypatch: pytest.MonkeyPatch, run: Path, out: Path) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["score_equivalent", str(run), "--out", str(out), "--n-boot", "20"],
    )
    main()


def _rows(path: Path) -> tuple[list[str], list[list[str]]]:
    with path.open(encoding="utf-8") as fh:
        rows = list(csv.reader(fh))
    return rows[0], rows[1:]


def test_cli_writes_the_three_artefacts(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    _run_cli(monkeypatch, _both_arms(tmp_path), out)
    capsys.readouterr()

    for name in ("score_equivalent.md", "arm_curves.csv", "offers.csv",
                 "rho_curves.csv"):
        assert (out / name).exists(), name


def test_rho_curves_header_is_the_contract(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    _run_cli(monkeypatch, _both_arms(tmp_path), out)
    capsys.readouterr()

    header, rows = _rows(out / "rho_curves.csv")
    assert header == ["arm", "rho_bin_lower", "n_offers", "payment_rate", "fitted"]
    assert {r[0] for r in rows} == {"threat", "silent"}
    # An empty bin has no rate; it must be an empty cell, not "nan".
    assert all(r[3] != "nan" for r in rows)
    assert any(r[3] == "" for r in rows)


def test_offers_csv_carries_the_rho_axis_columns(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    _run_cli(monkeypatch, _both_arms(tmp_path), out)
    capsys.readouterr()

    header, rows = _rows(out / "offers.csv")
    price = header.index("price")
    assert header[price + 1:price + 4] == ["rounds_remaining", "ceiling", "rho"]
    assert len(rows) == len(_THREAT_TURNS) + len(_SILENT_TURNS)
    # turn 10 of the threat session leaves no rounds: ceiling 0, rho infinite.
    last = [r for r in rows if r[header.index("session_id")] == "t1"][-1]
    assert float(last[header.index("ceiling")]) == 0.0
    assert float(last[header.index("rho")]) == float("inf")


def test_md_reports_the_rho_axis(tmp_path, monkeypatch, capsys):
    out = tmp_path / "out"
    _run_cli(monkeypatch, _both_arms(tmp_path), out)
    capsys.readouterr()

    md = (out / "score_equivalent.md").read_text(encoding="utf-8")
    assert "## ρ axis (price / ceiling)" in md
    assert "legacy estimator" in md
    # the fit's own health, and what n_skipped pools
    assert "converged" in md
    assert "skipped" in md and "no rounds remaining" in md
    assert "observed ρ range" in md
    # the PAV reading is a direction check, not a second estimate
    assert "direction check" in md
    assert "c_ref" in md


def test_an_arm_with_no_offers_writes_no_rho_rows(tmp_path, monkeypatch, capsys):
    """``rho_curve`` returns ``prices == ()`` for an empty arm; write nothing."""
    run = tmp_path / "silent_only"
    _write_run(run, [("s1", "hz_0000", 3, _SILENT_TURNS)])
    out = tmp_path / "out"
    _run_cli(monkeypatch, run, out)
    capsys.readouterr()

    header, rows = _rows(out / "rho_curves.csv")
    assert header == ["arm", "rho_bin_lower", "n_offers", "payment_rate", "fitted"]
    assert {r[0] for r in rows} == {"silent"}
    assert "## ρ axis (price / ceiling)" in (
        out / "score_equivalent.md"
    ).read_text(encoding="utf-8")
