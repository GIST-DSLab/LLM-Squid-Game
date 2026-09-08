"""Score-equivalent index over one or more run directories.

    uv run python -m scripts.analysis.score_equivalent \
        outputs/<date>/score_equiv_gptoss120b/<ts>_... \
        --out results/score_equiv/gptoss120b

Reads each run's ``season_results.jsonl`` + ``experiment_config.json``,
labels sessions as THREAT or RULER (``event_score_loss``), fits the
ruler curve F(X), and reports X* = F^{-1}(threat forfeit rate) with a
session-level bootstrap interval. Several run directories of the SAME
model and rule set may be passed together; they are pooled.

Refuses to pool runs whose ``event_roll`` / ``score_policy`` / ``carrot``
blocks differ: the ruler is only a ruler if the two arms were produced
under one set of rules. See
``squid_game.evaluation.behavioral.score_equivalent``.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from squid_game.evaluation.behavioral.score_equivalent import (
    LabelledSession,
    label_sessions,
    read_run,
    score_equivalent,
)


def _rule_signature(config: dict) -> tuple:
    return (
        json.dumps(config.get("event_roll"), sort_keys=True),
        json.dumps(config.get("score_policy"), sort_keys=True),
        config.get("carrot"),
        json.dumps(
            {
                k: (config.get("forfeit_layer") or {}).get(k)
                for k in ("base_reward", "reward_mode", "reward_growth")
            },
            sort_keys=True,
        ),
    )


def _fmt_curve(curve, raw) -> str:
    lines = ["| X | forfeit rate (raw) | monotone | n |", "|--:|--:|--:|--:|"]
    raw_by_x = {x: (f, n) for x, f, n in raw}
    for x, f, n in curve:
        fr, _ = raw_by_x.get(x, (f, n))
        lines.append(f"| {x:g} | {fr:.3f} | {f:.3f} | {n} |")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dirs", type=Path, nargs="+")
    parser.add_argument("--out", type=Path, default=None)
    parser.add_argument("--n-boot", type=int, default=1000)
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()

    sessions: list[LabelledSession] = []
    signature = None
    x_all = None
    for run_dir in args.run_dirs:
        rows, config = read_run(run_dir)
        sig = _rule_signature(config)
        if signature is None:
            signature = sig
        elif sig != signature:
            raise SystemExit(
                f"{run_dir}: event_roll / score_policy / carrot / reward differ "
                "from the first run; refusing to pool."
            )
        labelled, x_all = label_sessions(rows, config)
        sessions.extend(labelled)

    if not any(s.arm == "threat" for s in sessions):
        raise SystemExit("no threat-arm sessions with forfeit allowed found")
    if not any(s.arm == "ruler" for s in sessions):
        raise SystemExit("no ruler-arm sessions (event_score_loss) found")

    res = score_equivalent(
        sessions, x_all=x_all, n_boot=args.n_boot, seed=args.seed
    )
    censor = " (censored: above the top rung)" if res.censored else ""
    ci = f"[{res.ci[0]:g}, {res.ci[1]:g}]" if res.ci else "n/a"
    report = "\n".join(
        [
            "# Score-equivalent index",
            "",
            f"Threat arm: {res.threat_n} sessions, forfeit rate {res.threat_rate:.3f}.",
            f"Ruler top rung ('all') placed at X = {x_all:g}.",
            "",
            f"**X\\* = {res.x_star:g} points{censor}**, bootstrap 95% CI {ci} "
            f"({args.n_boot} resamples, seed {args.seed}).",
            "",
            "## Ruler curve",
            "",
            _fmt_curve(res.curve, res.raw_curve),
            "",
        ]
    )
    print(report)
    if args.out is not None:
        args.out.mkdir(parents=True, exist_ok=True)
        (args.out / "score_equivalent.md").write_text(report, encoding="utf-8")
        (args.out / "score_equivalent.json").write_text(
            json.dumps(
                {
                    "x_star": res.x_star,
                    "censored": res.censored,
                    "ci": res.ci,
                    "threat_rate": res.threat_rate,
                    "threat_n": res.threat_n,
                    "x_all": x_all,
                    "curve": res.curve,
                    "raw_curve": res.raw_curve,
                    "run_dirs": [str(p) for p in args.run_dirs],
                },
                indent=2,
            ),
            encoding="utf-8",
        )


if __name__ == "__main__":
    main()
