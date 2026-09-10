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


def _one_seed(tmp_path: Path) -> Path:
    """Both arms on a single seed: one bootstrap unit, so no draw is taken.

    ``_bootstrap`` returns before the loop when there are fewer than two
    units, so ``n_boot_draws`` and ``n_boot_failed`` are both 0 -- the
    case the md must not report as "0 of 20 draws did not".
    """
    run = tmp_path / "one_seed"
    _write_run(run, [
        ("t1", "hz_1111", 5, _THREAT_TURNS),
        ("s1", "hz_0000", 5, _SILENT_TURNS),
    ])
    return run


def _many_seeds(tmp_path: Path) -> Path:
    """Six seeds, each carrying both arms, so the draws produce an interval.

    Half the seeds pay the silent arm's third rung and half do not, which
    is what keeps the percentile interval from collapsing onto the point
    estimate.
    """
    run = tmp_path / "many_seeds"
    sessions = []
    for seed in range(6):
        silent = list(_SILENT_TURNS)
        if seed % 2 == 0:
            silent[2] = (3, 20.0, True)
        sessions.append((f"t{seed}", "hz_1111", seed, _THREAT_TURNS))
        sessions.append((f"s{seed}", "hz_0000", seed, silent))
    _write_run(run, sessions)
    return run


def _run_cli(
    monkeypatch: pytest.MonkeyPatch, run: Path, out: Path, n_boot: int = 20
) -> None:
    monkeypatch.setattr(
        "sys.argv",
        ["score_equivalent", str(run), "--out", str(out), "--n-boot", str(n_boot)],
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


class TestWhyThereIsNoInterval:
    """Three different absences of a CI, and the md must not confuse them."""

    def test_a_single_unit_says_so_instead_of_printing_zero_of_zero(
        self, tmp_path, monkeypatch, capsys
    ):
        out = tmp_path / "out"
        _run_cli(monkeypatch, _one_seed(tmp_path), out)
        capsys.readouterr()

        md = (out / "score_equivalent.md").read_text(encoding="utf-8")
        assert "**X\\*_ρ" in md  # the point estimate is there; only the CI is not
        assert "0 of 0" not in md
        assert "fewer than two bootstrap units" in md

    def test_too_few_usable_draws_names_the_twenty_draw_floor(
        self, tmp_path, monkeypatch, capsys
    ):
        """Two arm-segregated seeds: some draws hold one arm only, and 20
        resamples cannot leave 20 survivors once any of them fail."""
        out = tmp_path / "out"
        _run_cli(monkeypatch, _both_arms(tmp_path), out)
        capsys.readouterr()

        md = (out / "score_equivalent.md").read_text(encoding="utf-8")
        assert "fewer than the 20 needed to read percentiles" in md
        assert "of 20" in md

    def test_a_real_interval_is_labelled_conditional_and_says_which_way(
        self, tmp_path, monkeypatch, capsys
    ):
        out = tmp_path / "out"
        _run_cli(monkeypatch, _many_seeds(tmp_path), out, n_boot=200)
        capsys.readouterr()

        md = (out / "score_equivalent.md").read_text(encoding="utf-8")
        # Only the ρ section: the price axis above it is the legacy
        # estimator and its wording is deliberately left alone.
        rho_md = md.split("## ρ axis (price / ceiling)", 1)[1]
        assert "conditional 95% percentile interval" in rho_md
        assert "95% CI" not in rho_md
        assert "conservative toward 0" in rho_md
        # the same interval, converted at c_ref, on the points line
        assert "X\\*_points" in rho_md
        points_line = next(
            line for line in rho_md.splitlines() if "X\\*_points" in line
        )
        assert "conditional 95% percentile interval" in points_line
        assert "points" in points_line


def test_the_coefficients_are_printed_without_trailing_zero_noise(
    tmp_path, monkeypatch, capsys
):
    """``.3g``, not ``.3f``: three significant figures, and no ``-0.000``."""
    out = tmp_path / "out"
    _run_cli(monkeypatch, _both_arms(tmp_path), out)
    capsys.readouterr()

    md = (out / "score_equivalent.md").read_text(encoding="utf-8")
    assert "a_silent = -18," in md  # `.3f` would print -18.024


def test_the_observed_range_comes_from_the_result_not_a_second_computation(
    tmp_path, monkeypatch, capsys
):
    """The CLI prints ``RhoResult.rho_range_*``, the range the rule used."""
    out = tmp_path / "out"
    _run_cli(monkeypatch, _both_arms(tmp_path), out)
    capsys.readouterr()

    md = (out / "score_equivalent.md").read_text(encoding="utf-8")
    # rho spans 5 / 90 = 0.056 up to 50 / 20 = 2.5 in both arms.
    assert md.count("0.056 to 2.500") == 2

    from scripts.analysis import score_equivalent as cli

    assert not hasattr(cli, "_observed_rho_range")


def test_the_pav_caveat_names_both_kinds_of_offer_the_fit_skips(
    tmp_path, monkeypatch, capsys
):
    """Infinite ρ and zero-price offers are both binned but not fitted."""
    out = tmp_path / "out"
    _run_cli(monkeypatch, _both_arms(tmp_path), out)
    capsys.readouterr()

    md = (out / "score_equivalent.md").read_text(encoding="utf-8")
    caveat = next(
        line
        for line in md.splitlines()
        if "direction check, not a second estimate" in line
    )
    assert "infinite" in caveat
    assert "ρ = 0" in caveat


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
