"""CLI for the survival-motive metric probe (P2).

Feature construction, the RidgeCV fit, the permutation null, the Cox
side-table and the report renderer all live in
``squid_game.evaluation.behavioral.motive_probe`` -- this script only parses
arguments, loads the turn frames, fits one probe per model, and writes the
JSON / Markdown to disk.

Usage
-----
    # ladder runs
    uv run python scripts/analysis/probe_threat_motive.py \
        --runs outputs/lives_threat_smoke --out results/threat_probe

    # archived v6 runs, framings mapped through LEGACY_THREAT_LEVEL
    uv run python scripts/analysis/probe_threat_motive.py \
        --root outputs/final_results --legacy-mapping \
        --out results/threat_probe
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import pandas as pd

from squid_game.evaluation.behavioral.motive_probe import (
    build_session_features,
    fit_motive_probe,
    hazard_ratio_table,
    render_motive_report,
)
from squid_game.evaluation.semantic.dataset import RunSpec, load_all, load_turns


def _load(args) -> pd.DataFrame:
    frames = []
    if args.root is not None:
        frames.append(load_all(args.root, legacy=args.legacy))
    for run in args.runs or []:
        frames.append(load_turns(RunSpec.from_dir(run), legacy=args.legacy))
    if not frames:
        raise SystemExit("pass --root and/or --runs")
    return pd.concat(frames, ignore_index=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=None,
                        help="Directory holding per-model run directories.")
    parser.add_argument("--runs", type=Path, nargs="*", default=None,
                        help="Individual run directories.")
    parser.add_argument("--out", type=Path,
                        default=Path("results/threat_probe"))
    parser.add_argument("--n-permutations", type=int, default=200)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument("--legacy-mapping", action="store_true", dest="legacy")
    parser.add_argument("--no-per-model", action="store_false",
                        dest="per_model")
    parser.set_defaults(per_model=True)
    args = parser.parse_args()

    frame = _load(args)
    features = build_session_features(frame, seed=args.seed)
    if features.empty:
        raise SystemExit(
            "no session carried a threat_level -- pass --legacy-mapping for "
            "archived v6 runs"
        )

    groups: list[tuple[str, pd.DataFrame]] = [("POOLED", features)]
    if args.per_model:
        groups += [
            (m, features[features["model"] == m])
            for m in sorted(features["model"].dropna().unique())
        ]

    results: dict[str, dict] = {}
    for label, group in groups:
        probe = fit_motive_probe(
            group, seed=args.seed, n_permutations=args.n_permutations
        )
        results[label] = {
            "probe": probe.as_dict(),
            "hazard": hazard_ratio_table(group),
        }

    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "motive_results.json").write_text(
        json.dumps(results, indent=2, default=str)
    )
    for label, payload in results.items():
        if label == "POOLED":
            continue
        model_dir = args.out / label
        model_dir.mkdir(parents=True, exist_ok=True)
        (model_dir / "motive_results.json").write_text(
            json.dumps(payload, indent=2, default=str)
        )
    features.to_csv(args.out / "motive_session_features.csv", index=False)
    report = render_motive_report(results)
    (args.out / "motive_report.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
