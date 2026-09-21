"""Team-wallet reading: sacrifice under charge, subagent survival, X_rho.

    uv run python scripts/analysis/team_wallet_km.py <run_dir>... --out <dir>

Every run directory is one ``(currency, inheritance)`` cell -- both are
run-level factors, read from each run's own ``experiment_config.json``,
together with ``ransom.charge`` and the session length rho needs -- so
several directories are given at once and grouped by the pair.

The models live in
``squid_game.evaluation.behavioral.team_wallet``; this script only
resolves the run directories, runs the battery and writes the artefacts:
``team_wallet_km.md`` (the reading), ``km_subagents.png``, and one CSV
per table (``exclusions``, ``rho_curves``, ``reservation_rho``,
``sacrifice_gee``, ``session_outcomes``, ``sacrifice_rates``,
``x_self_by_price``, ``subagent_slots``, ``km_subagents``,
``cox_subagents``, ``end_state``, ``scarcity_slope``, plus the ``turns``
/ ``seasons`` frames they were read from).

Read the exclusions before any rate and the GEE before X_rho: the GEE is
the estimator of record and the two indices are descriptive summaries of
the same contrast, each unidentified rather than small when a cell never
reached a decision point.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from squid_game.evaluation.behavioral.team_wallet import (
    analyse,
    discover_run_dirs,
    load_team_wallet_frames,
    write_report,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dirs",
        nargs="+",
        type=Path,
        help="Run directory (or a parent of several) holding season_results.jsonl.",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--n-boot",
        type=int,
        default=1000,
        help="Bootstrap draws for the X_self interval (seasons, within cell).",
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=0,
        help="Seed for the bootstrap, so a report is reproducible.",
    )
    args = parser.parse_args()

    runs = discover_run_dirs(args.run_dirs)
    if not runs:
        raise SystemExit(
            f"no run directory with season_results.jsonl under "
            f"{[str(p) for p in args.run_dirs]}"
        )
    turns_df, seasons_df = load_team_wallet_frames(runs)
    if turns_df.empty:
        raise SystemExit(f"no turns found under {[str(p) for p in runs]}")

    results = analyse(turns_df, seasons_df, n_boot=args.n_boot, seed=args.seed)
    report = write_report(
        args.out, results, turns_df=turns_df, seasons_df=seasons_df
    )
    print(report)
    if not results.get("km_plotted"):
        print("[warn] no km_subagents.png written (no curve, or matplotlib missing).")
    print(f"Artefacts written to {args.out}/")


if __name__ == "__main__":
    main()
