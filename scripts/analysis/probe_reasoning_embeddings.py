"""CLI for the reasoning-trace SentenceBERT linear probe (P1).

The embedding pipeline, the target definitions, the session-grouped CV
probe fit, the permutation-null test, and the report renderer live in
``squid_game.evaluation.semantic.embeddings`` -- this script only parses
arguments, loads the turn-level frame, builds the embedding bank once,
loops over the requested (model-grouping, target, channel) cells, and
writes the JSON / Markdown report to disk.

Usage
-----
    # P1: regress the ordinal threat level off the CoT, per model
    uv run python -m scripts.analysis.probe_reasoning_embeddings \
        --target threat_level --channel task --channel forfeit \
        --legacy-mapping --out results/threat_probe

    # legacy binary probes
    uv run python -m scripts.analysis.probe_reasoning_embeddings \
        --target forfeit --target threat --channel task
"""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis._cli import add_aggregate_root_argument
from squid_game.evaluation.semantic.dataset import load_all
from squid_game.evaluation.semantic.embeddings import (
    DEFAULT_MASK_SETS,
    DEFAULT_SBERT,
    LABELS,
    build_embedding_bank,
    render_report,
    run_cell,
    write_results,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_aggregate_root_argument(parser)
    parser.add_argument("--out", type=Path, default=Path("results/reasoning_probe"))
    parser.add_argument(
        "--target", "--label", action="append", choices=sorted(LABELS),
        dest="labels",
    )
    parser.add_argument(
        "--channel", action="append", choices=["task", "probe", "forfeit"],
        dest="channels",
    )
    parser.add_argument(
        "--mask", action="append",
        choices=["threat", "pull", "decision", "lives"],
        dest="mask_sets", default=None,
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--sbert-model", default=DEFAULT_SBERT)
    parser.add_argument("--words-per-chunk", type=int, default=180)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--n-permutations", type=int, default=200)
    parser.add_argument("--min-positive", type=int, default=20)
    parser.add_argument("--min-rows", type=int, default=0)
    parser.add_argument("--exemplars", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--legacy-mapping", action="store_true", dest="legacy",
        help="Map the archived v6 framings onto the threat ladder "
             "(LEGACY_THREAT_LEVEL). Off by default so a ladder-era run "
             "never absorbs baseline_flagship rows as level 1.",
    )
    parser.add_argument(
        "--no-per-model", action="store_false", dest="per_model",
        help="Fit only the pooled probe. Per-model fitting is the default "
             "(spec 5.1: the probes are per-model).",
    )
    parser.set_defaults(per_model=True)
    args = parser.parse_args()
    args.labels = args.labels or ["threat_level"]
    args.channels = args.channels or ["task"]
    mask_sets = (
        args.mask_sets
        if args.mask_sets is not None
        else list(DEFAULT_MASK_SETS)
    )

    frame = load_all(
        args.root, include_text=True, models=args.models, legacy=args.legacy
    )
    frame["bank_row"] = np.arange(len(frame))
    args.out.mkdir(parents=True, exist_ok=True)
    bank = build_embedding_bank(
        frame, channels=args.channels, mask_sets=mask_sets, args=args
    )

    groupings: list[tuple[str, pd.DataFrame]] = [("POOLED", frame)]
    if args.per_model:
        groupings += [
            (m, frame[frame["model"] == m])
            for m in sorted(frame["model"].unique())
        ]

    results: list[dict] = []
    for group_label, group in groupings:
        for label_name in args.labels:
            for channel in args.channels:
                results.append(
                    run_cell(
                        group,
                        bank,
                        label_name=label_name,
                        channel=channel,
                        group_label=group_label,
                        args=args,
                    )
                )

    write_results(results, args.out)
    print(render_report(results))


if __name__ == "__main__":
    main()
