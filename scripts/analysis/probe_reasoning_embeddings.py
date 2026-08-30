"""CLI for the reasoning-trace SentenceBERT linear probe.

The embedding pipeline, the label definitions, the session-grouped CV
probe fit, the permutation-null test, and the report renderer live in
``squid_game.analysis.semantic.embeddings`` -- this script only parses
arguments, loads the turn-level frame, builds the embedding bank once,
loops over the requested (model-grouping, label, channel) cells, and
writes the JSON / Markdown report to disk.

Usage
-----
    uv run python -m scripts.analysis.probe_reasoning_embeddings \
        --label forfeit --label threat \
        --channel task \
        --out outputs/reasoning_probe
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from scripts.analysis._cli import add_aggregate_root_argument
from squid_game.analysis.semantic.dataset import load_all
from squid_game.analysis.semantic.embeddings import (
    DEFAULT_SBERT,
    LABELS,
    build_embedding_bank,
    render_report,
    run_cell,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    add_aggregate_root_argument(parser)
    parser.add_argument("--out", type=Path, default=Path("outputs/reasoning_probe"))
    parser.add_argument(
        "--label", action="append", choices=sorted(LABELS), dest="labels"
    )
    parser.add_argument(
        "--channel", action="append", choices=["task", "probe", "forfeit"],
        dest="channels",
    )
    parser.add_argument(
        "--mask", action="append", choices=["threat", "pull", "decision"],
        dest="mask_sets", default=None,
    )
    parser.add_argument("--model", action="append", dest="models")
    parser.add_argument("--sbert-model", default=DEFAULT_SBERT)
    parser.add_argument("--words-per-chunk", type=int, default=180)
    parser.add_argument("--batch-size", type=int, default=128)
    parser.add_argument("--n-splits", type=int, default=5)
    parser.add_argument("--n-permutations", type=int, default=100)
    parser.add_argument("--min-positive", type=int, default=20)
    parser.add_argument("--exemplars", type=int, default=5)
    parser.add_argument("--seed", type=int, default=1234)
    parser.add_argument(
        "--per-model", action="store_true",
        help="Additionally fit one probe per model, not just pooled.",
    )
    args = parser.parse_args()
    args.labels = args.labels or ["forfeit", "threat"]
    args.channels = args.channels or ["task"]
    mask_sets = args.mask_sets if args.mask_sets is not None else ["threat", "pull"]

    frame = load_all(args.root, include_text=True, models=args.models)
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

    (args.out / "probe_results.json").write_text(
        json.dumps([r for r in results if r], indent=2, default=str)
    )
    report = render_report(results)
    (args.out / "probe_report.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
