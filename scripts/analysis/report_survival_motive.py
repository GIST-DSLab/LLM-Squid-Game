"""Per-model HTML report for a Survival Motive Index (SMI) run.

Usage
-----
    uv run python -m scripts.analysis.report_survival_motive <run_dir> \
        --model-label "gpt-oss:120b" \
        --probe-dir results/survival_motive_probe \
        --out weekly-report/0910/smi_gptoss.html

Reads three things and nothing else -- no provider call, no
sentence-transformers, so it runs offline on any machine:

* ``<run_dir>/season_results.jsonl`` + ``*_turns.jsonl``  (the run itself)
* ``<run_dir>/survival_motive/smi_turns.csv``             (the resampler)
* ``<probe_dir>/probe_results.json``                      (the embedding probe)

``--probe-dir`` is optional: without it the probe section says so rather
than disappearing. Every other section degrades the same way -- a
quantity that cannot be computed is printed as missing, never hidden.

The computation lives in
``squid_game.evaluation.behavioral.survival_motive_report``; this file is
only the CLI.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from squid_game.evaluation.behavioral.survival_motive_report import (
    build_report_data,
    render_html,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--model-label", required=True,
        help="Display name for the model, e.g. 'gpt-oss:120b (n=30)'. "
             "Appears in the title and the reproduction command.",
    )
    parser.add_argument(
        "--probe-dir", type=Path, default=None,
        help="Directory holding probe_results.json from "
             "scripts.analysis.probe_reasoning_embeddings --target smi.",
    )
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument(
        "--n-turns-note", default=None, dest="note",
        help="Free-text caveat rendered under the lede, e.g. "
             "'smoke run: 5 sessions x 8 turns, do not generalise'.",
    )
    parser.add_argument(
        "--permutations", type=int, default=1000,
        help="Draws for the label-shuffling permutation test (default 1000).",
    )
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    if not args.run_dir.is_dir():
        parser.error(f"{args.run_dir} is not a directory")

    data = build_report_data(
        args.run_dir,
        args.model_label,
        probe_dir=args.probe_dir,
        note=args.note,
        draws=args.permutations,
        seed=args.seed,
    )
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(render_html(data), encoding="utf-8")
    size_kb = args.out.stat().st_size / 1024
    print(
        f"{args.out} ({size_kb:.1f} kB) — "
        f"{len(data.sessions)} sessions, {data.smi.get('n_rows', 0)} resampled turns, "
        f"{data.smi.get('n_defined', 0)} with a defined SMI, "
        f"probe: {'yes' if data.probe.get('available') else 'no'}"
    )


if __name__ == "__main__":
    main()
