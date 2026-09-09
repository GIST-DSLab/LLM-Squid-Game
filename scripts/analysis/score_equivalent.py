"""Score-equivalent index from a ransom run.

    uv run python -m scripts.analysis.score_equivalent outputs/<run>... --out results/x

Reads every run directory's seasons and turns, collects the ransom
offers, fits each arm's payment-rate curve, and reports

    X* = reservation(threat) - reservation(silent)

with a session bootstrap CI. Refuses to pool runs whose rule block
differs (``ransom`` / ``score_policy`` / ``carrot`` / reward mode /
starting score): a pooled X* across two rule sets is not a quantity.

Writes ``score_equivalent.md`` (the reading), ``arm_curves.csv`` (both
curves, raw and fitted) and ``offers.csv`` (one row per offer).
"""

from __future__ import annotations

import argparse
import csv
import json
from pathlib import Path

from squid_game.evaluation.behavioral.score_equivalent import (
    SILENT,
    THREAT,
    collect_offers,
    score_equivalent,
)


def _rule_block(config: dict) -> str:
    """The knobs that must agree before two runs may be pooled."""
    seasons = config.get("seasons") or [{}]
    task = (seasons[0].get("task_config") or {}) if seasons else {}
    return json.dumps(
        {
            "ransom": config.get("ransom"),
            "score_policy": config.get("score_policy"),
            "carrot": config.get("carrot"),
            "reward_mode": (config.get("forfeit_layer") or {}).get("reward_mode"),
            "base_reward": (config.get("forfeit_layer") or {}).get("base_reward"),
            "starting_score": task.get("starting_score"),
            "total_turns": task.get("total_turns"),
        },
        sort_keys=True,
    )


def _load(run_dir: Path) -> tuple[dict, list[dict], dict[str, list[dict]]]:
    config = json.loads((run_dir / "experiment_config.json").read_text())
    seasons = [
        json.loads(line)
        for line in (run_dir / "season_results.jsonl").read_text().splitlines()
        if line.strip()
    ]
    turns: dict[str, list[dict]] = {}
    for path in run_dir.glob("*_turns.jsonl"):
        for line in path.read_text().splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            sid = str(row.get("session_id") or row.get("season_id") or path.stem)
            turns.setdefault(sid, []).append(row)
    return config, seasons, turns


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n-boot", type=int, default=1000)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    offers, blocks = [], set()
    for run_dir in args.run_dirs:
        config, seasons, turns = _load(run_dir)
        blocks.add(_rule_block(config))
        if len(blocks) > 1:
            raise SystemExit(
                f"{run_dir}: ransom / score_policy / carrot / reward / starting "
                "score differ from an earlier run; pooling them would average "
                "two different games. Analyse them separately."
            )
        season0 = (config.get("seasons") or [{}])[0]
        offers.extend(
            collect_offers(
                seasons,
                turns,
                reward=float((config.get("forfeit_layer") or {}).get("base_reward", 10.0)),
                total_turns=int((season0.get("task_config") or {}).get("total_turns", 10)),
            )
        )
    if not offers:
        raise SystemExit("no ransom offers found; was ransom.enabled set?")

    result = score_equivalent(offers, n_boot=args.n_boot)

    with (args.out / "offers.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["session_id", "arm", "price", "paid", "rounds_remaining", "dominated"])
        for o in offers:
            w.writerow([o.session_id, o.arm, o.price, int(o.paid),
                        o.rounds_remaining, int(o.dominated)])

    with (args.out / "arm_curves.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "price", "n_offers", "payment_rate", "fitted"])
        for curve in (result.threat, result.silent):
            for price, count, rate, fit in zip(
                curve.prices, curve.counts, curve.rates, curve.fitted
            ):
                w.writerow([curve.arm, price, count, f"{rate:.4f}", f"{fit:.4f}"])

    lines = [
        "# Score-equivalent index (ransom design)",
        "",
        f"- sessions: {result.n_sessions}, offers: {result.n_offers}",
        f"- accepted offers that were score-dominated: {result.dominated_share:.2f}",
        f"- offers above the dominance line: {result.n_dominated} of {result.n_offers}",
        "",
        "| arm | reservation price |",
        "|---|---|",
        f"| threat (hz_1111) | {result.threat.reservation} |",
        f"| silent (hz_0000) | {result.silent.reservation} |",
        "",
    ]
    if result.x_star is None:
        lines.append("**X\\* not identified.**")
    else:
        ci = (
            f" (95% CI {result.ci_low:.1f} to {result.ci_high:.1f})"
            if result.ci_low is not None
            else ""
        )
        lines.append(f"**X\\* = {result.x_star:.1f} points{ci}**")
        if result.x_star_dominated is not None:
            lines.append("")
            lines.append(
                f"Restricted to the {result.n_dominated} offers above the "
                f"dominance line: **X\\* = {result.x_star_dominated:.1f} points**."
            )
    if result.notes:
        lines += ["", "## Notes", ""] + [f"- {n}" for n in result.notes]
    # The two arms need not have met the same prices -- a cell whose
    # sessions never reached a decision point contributes none -- so the
    # table is keyed on the union and a missing cell prints as a dash.
    prices = sorted(set(result.threat.prices) | set(result.silent.prices))
    lines += ["", "## Payment rate by price", "",
              "| arm | " + " | ".join(f"{p:g}" for p in prices) + " |",
              "|---|" + "---|" * len(prices)]
    for curve in (result.threat, result.silent):
        by_price = dict(zip(curve.prices, curve.rates))
        cells = [
            f"{by_price[p]:.2f}" if p in by_price else "--" for p in prices
        ]
        lines.append(f"| {curve.arm} | " + " | ".join(cells) + " |")
    (args.out / "score_equivalent.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
