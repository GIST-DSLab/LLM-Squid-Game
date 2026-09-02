"""CLI for the H6 threat-ladder analysis.

The models and the report live in
``squid_game.evaluation.behavioral.threat_effort``; this script only
resolves run directories, runs the battery, and writes the artefacts.

Usage
-----
    uv run python scripts/analysis/analyze_threat_effort.py \
        outputs/lives_threat_smoke/ --out outputs/lives_threat_smoke/threat_effort

Several run directories may be given at once (they are pooled, with a
``model`` column preserved); each argument may be either a run directory
holding ``*_turns.jsonl`` or a parent of several.

Writes ``results.md``, ``results.json``, ``long.csv``, ``km.csv`` and
``km.png`` into ``--out`` (default: ``<first run dir>/threat_effort``).

``--legacy-mapping`` maps the archived v6 framings onto the ladder so
the same battery can be pointed at ``outputs/final_results/``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from squid_game.evaluation.behavioral.threat_effort import (
    discover_run_dirs,
    load_threat_frame,
    plot_km,
    render_report,
    run_h6,
)


def _json_safe(results: dict) -> dict:
    return {
        key: (value.to_dict(orient="records") if isinstance(value, pd.DataFrame) else value)
        for key, value in results.items()
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "run_dirs",
        nargs="+",
        type=Path,
        help="Run directory (or a parent of several) holding *_turns.jsonl.",
    )
    parser.add_argument(
        "--legacy-mapping",
        action="store_true",
        help=(
            "Map the archived v6 framings onto the ladder "
            "(baseline_flagship 1 / flagship_corruption 2 / _terminal 3) "
            "so H6 can be run over outputs/final_results as a check."
        ),
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=None,
        help="Where results.md / long.csv / km.png land.",
    )
    args = parser.parse_args()

    runs = discover_run_dirs(args.run_dirs)
    out = args.out or (runs[0] / "threat_effort")
    out.mkdir(parents=True, exist_ok=True)

    frame = load_threat_frame(args.run_dirs, legacy=args.legacy_mapping)
    if frame.empty:
        raise SystemExit(f"no turns found under {[str(p) for p in runs]}")
    frame.to_csv(out / "long.csv", index=False)

    results = run_h6(frame, legacy=args.legacy_mapping)
    results["km"].to_csv(out / "km.csv", index=False)
    if not plot_km(results["km"], out / "km.png"):
        print("[warn] no Kaplan-Meier curve written (lifelines missing "
              "or no levelled session).")

    report = render_report(results)
    (out / "results.md").write_text(report, encoding="utf-8")
    (out / "results.json").write_text(
        json.dumps(_json_safe(results), indent=2, default=str),
        encoding="utf-8",
    )
    print(report)
    print(f"\nArtefacts written to {out}/")


if __name__ == "__main__":
    main()
