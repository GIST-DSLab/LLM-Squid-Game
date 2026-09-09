"""Score-equivalent index from a ransom run.

    uv run python -m scripts.analysis.score_equivalent outputs/<run>... --out results/x

Reads every run directory's seasons and turns, collects the ransom
offers, fits each arm's payment-rate curve, and reports

    X* = reservation(threat) - reservation(silent)

with a session bootstrap CI. Refuses to pool runs whose rule block
differs (``ransom`` / ``score_policy`` / ``carrot`` / reward mode /
starting score): a pooled X* across two rule sets is not a quantity.

Writes ``score_equivalent.md`` (the reading), ``arm_curves.csv`` (both
price curves, raw and fitted), ``rho_curves.csv`` (the same over rho
bins) and ``offers.csv`` (one row per offer, with its ceiling and rho).

The price reading is kept as the legacy estimator and the rho axis --
price as a share of what the remaining rounds could still pay out -- is
reported beside it: on a ten-round design the ceiling falls 90 -> 10, so
one price rung spans rho 0.33 .. 3.0 and the pooled price curve can fail
to cross 0.5 at all.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

from squid_game.evaluation.behavioral.score_equivalent import (
    SILENT,
    THREAT,
    ArmCurve,
    Offer,
    RhoResult,
    collect_offers,
    score_equivalent,
)


def _rule_block(config: dict) -> str:
    """The knobs that must agree before two runs may be pooled.

    The model is in here because the bootstrap resamples seeds: seed 7
    names one row of puzzles, but *two different sessions* if two models
    are pooled, and drawing them as one unit would tie unrelated
    decisions together. X* is a per-model quantity in any case.
    """
    seasons = config.get("seasons") or [{}]
    task = (seasons[0].get("task_config") or {}) if seasons else {}
    provider = (seasons[0].get("provider_config") or {}) if seasons else {}
    return json.dumps(
        {
            "model": provider.get("model"),
            "provider": provider.get("provider"),
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


def _rho_curves(rho: RhoResult | None) -> tuple[ArmCurve, ...]:
    """The two rho-bin curves, or nothing when there was no fit at all."""
    return () if rho is None else (rho.threat_curve, rho.silent_curve)


def _observed_rho_range(
    offers: list[Offer], arm: str
) -> tuple[float, float] | None:
    """Min and max rho of the offers that arm actually contributed to the fit.

    The same filter :func:`fit_rho_logistic` applies -- finite and
    positive -- so the printed range is the ladder the arm was asked on,
    which is what makes an extrapolated ``rho*`` visible as one.
    """
    rhos = [
        o.rho for o in offers
        if o.arm == arm and math.isfinite(o.rho) and o.rho > 0.0
    ]
    return (min(rhos), max(rhos)) if rhos else None


def _rho_star_cell(kept: float | None, fitted: float | None) -> str:
    """The arm's reservation, or the value the range rule refused to read."""
    if kept is not None:
        return f"{kept:.3f}"
    if fitted is not None:
        return f"{fitted:.3f} (outside observed range, not read as a reservation)"
    return "--"


def _rho_section(offers: list[Offer], rho: RhoResult | None) -> list[str]:
    """The rho-axis reading, printed under the legacy price reading."""
    if rho is None:
        return []
    fit = rho.fit
    lines = [
        "",
        "## ρ axis (price / ceiling)",
        "",
        "The price reading above is retained as the legacy estimator. This "
        "section divides every price by ``reward x rounds remaining`` -- the "
        "most the rounds a payment buys could still pay out -- and fits "
        "``P(pay) = sigmoid(a_arm + b * log ρ)``, one intercept per arm "
        "and one shared slope.",
        "",
        "- fit: "
        + ("converged"
           if fit.converged
           else "**did NOT converge**; the coefficients below are the last "
                "iterate, not a maximum"),
        f"- offers used: {fit.n_used}; skipped: {fit.n_skipped} "
        "(this pools offers with an infinite ρ -- no rounds remaining -- "
        "offers at a zero or negative price, and offers in neither arm)",
        "- "
        + ", ".join(
            f"{name} = {'--' if value is None else format(value, '.3f')}"
            for name, value in (
                ("a_threat", fit.a_threat),
                ("a_silent", fit.a_silent),
                ("b", fit.b),
            )
        ),
        f"- c_ref (median ceiling of the fitted offers) = {rho.c_ref:.1f} points",
        "",
        "| arm | ρ* | observed ρ range | PAV crossing (direction check) |",
        "|---|---|---|---|",
    ]
    for arm, kept, fitted, curve in (
        (THREAT, rho.rho_star_threat, fit.rho_star_threat, rho.threat_curve),
        (SILENT, rho.rho_star_silent, fit.rho_star_silent, rho.silent_curve),
    ):
        span = _observed_rho_range(offers, arm)
        lines.append(
            f"| {arm} | {_rho_star_cell(kept, fitted)} | "
            + (f"{span[0]:.3f} to {span[1]:.3f}" if span else "--")
            + " | "
            + ("--" if curve.reservation is None else f"{curve.reservation:.3f}")
            + " |"
        )
    lines += [
        "",
        "The last column is a direction check, not a second estimate: the PAV "
        "runs over ρ bins, reads their **lower edges**, and counts the "
        "infinite-ρ offers the fit skips, so it sits a little below the "
        "logistic ρ*.",
        "",
    ]
    if rho.x_star_rho is None:
        lines.append(
            "**X\\*_ρ not identified** -- see the notes below for which "
            "arm the fit could not place."
        )
    else:
        ci = (
            f" (95% CI {rho.ci_low_rho:.3f} to {rho.ci_high_rho:.3f})"
            if rho.ci_low_rho is not None and rho.ci_high_rho is not None
            else ""
        )
        lines.append(f"**X\\*_ρ = {rho.x_star_rho:.3f}**{ci}")
        if rho.x_star_points is not None:
            lines.append("")
            lines.append(
                f"At c_ref = {rho.c_ref:.1f} points that is "
                f"**X\\*_points = {rho.x_star_points:.1f} points**."
            )
        total = rho.n_boot_draws + rho.n_boot_failed
        lines.append("")
        lines.append(
            f"Bootstrap over {rho.boot_unit}s: the interval is conditional on "
            "the draws whose own ladder bracketed the crossing; "
            f"{rho.n_boot_failed} of {total} did not."
        )
    if rho.notes:
        lines += ["", "### ρ-axis notes", ""] + [f"- {n}" for n in rho.notes]
    return lines


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
                f"{run_dir}: model / ransom / score_policy / carrot / reward / "
                "starting score differ from an earlier run; pooling them would "
                "average two different games. Analyse them separately."
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
        w.writerow(["session_id", "seed", "arm", "price", "rounds_remaining",
                    "ceiling", "rho", "paid", "dominated"])
        for o in offers:
            # rho is written unrounded-but-formatted, and prints ``inf``
            # for an offer with no rounds left rather than an empty cell:
            # that offer is real, it is simply off the fit's axis.
            w.writerow([o.session_id, "" if o.seed is None else o.seed,
                        o.arm, o.price, o.rounds_remaining,
                        f"{o.ceiling:.1f}", f"{o.rho:.4f}",
                        int(o.paid), int(o.dominated)])

    with (args.out / "arm_curves.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "price", "n_offers", "payment_rate", "fitted"])
        for curve in (result.threat, result.silent):
            for price, count, rate, fit in zip(
                curve.prices, curve.counts, curve.rates, curve.fitted
            ):
                w.writerow([curve.arm, price, count, f"{rate:.4f}", f"{fit:.4f}"])

    with (args.out / "rho_curves.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["arm", "rho_bin_lower", "n_offers", "payment_rate", "fitted"])
        for curve in _rho_curves(result.rho):
            # An arm with no offers comes back with ``prices == ()``;
            # zip then yields nothing and the arm contributes no rows,
            # which is the honest record of an arm that was never asked.
            for lower, count, rate, fit in zip(
                curve.prices, curve.counts, curve.rates, curve.fitted
            ):
                w.writerow([curve.arm, f"{lower:g}", count,
                            "" if math.isnan(rate) else f"{rate:.4f}",
                            "" if math.isnan(fit) else f"{fit:.4f}"])

    lines = [
        "# Score-equivalent index (ransom design)",
        "",
        f"- sessions: {result.n_sessions}, offers: {result.n_offers}",
        f"- accepted offers that were score-dominated: {result.dominated_share:.2f}",
        f"- offers above the dominance line: {result.n_dominated} of {result.n_offers}",
        f"- bootstrap unit: {result.boot_unit}"
        + (
            f", {result.n_boot_draws} draws"
            + (f", {result.n_boot_failed} without a crossing"
               if result.n_boot_failed else "")
            if result.n_boot_draws or result.n_boot_failed
            else ""
        ),
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
    lines += _rho_section(offers, result.rho)
    (args.out / "score_equivalent.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
