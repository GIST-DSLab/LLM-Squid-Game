"""CLI for the Call-1 reasoning-investment regression.

The model and its report (design, formula, fitting, contrasts, Markdown
rendering) live in ``squid_game.analysis.cognitive.ri_call1`` — this
script only loads the turn-level frame, runs the fit per model and
pooled, and writes the CSV / JSON / Markdown report to disk.

Usage
-----
    uv run python -m scripts.analyze_call1_ri \
        --root outputs/final_results --out outputs/call1_ri_analysis
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from squid_game.analysis.cognitive.ri_call1 import (
    OUTCOMES,
    fit_one,
    render_report,
)
from squid_game.analysis.semantic.dataset import load_all


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("outputs/final_results"),
        help="Directory holding the per-model run directories.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("outputs/call1_ri_analysis"),
        help="Where the report / CSV / JSON land.",
    )
    parser.add_argument("--model", action="append", dest="models")
    args = parser.parse_args()

    frame = load_all(args.root, models=args.models)
    args.out.mkdir(parents=True, exist_ok=True)
    frame.to_csv(args.out / "turn_observations.csv", index=False)

    all_results: dict[str, list[dict]] = {}
    for outcome in OUTCOMES:
        per_model = [
            fit_one(frame[frame["model"] == model], outcome, model)
            for model in sorted(frame["model"].unique())
        ]
        # Pooled fit: each model's token counts are divided by that
        # model's own mean before the log, so the pooled coefficient is
        # not dominated by whichever model happens to be the most
        # verbose (qwen3-next emits ~11x nemotron's tokens). The ratio
        # stays non-negative, which log1p requires.
        pooled = frame.copy()
        pooled[outcome] = frame.groupby("model")[outcome].transform(
            lambda s: s / (s.mean() or 1.0)
        )
        per_model.append(
            fit_one(pooled, outcome, "POOLED (within-model scaled)")
        )
        all_results[outcome] = per_model

    (args.out / "call1_ri_results.json").write_text(
        json.dumps(all_results, indent=2, default=str)
    )
    report = render_report(all_results)
    (args.out / "call1_ri_report.md").write_text(report)
    print(report)


if __name__ == "__main__":
    main()
