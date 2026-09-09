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
bins), ``offers.csv`` (one row per offer, with its ceiling and rho) and
``forced_vs_genuine.csv`` (the forced-wrong diagnostic).

That last one is a diagnostic and not a second estimate: it splits the
offers by whether the round that opened them was forced to be graded
wrong, and counts the rounds that emptied the counter without ever being
offered a price. The headline stays pooled over every offer.

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
    POOLED,
    SILENT,
    SUPPRESSION_REASONS,
    THREAT,
    ArmCurve,
    ForcedGroup,
    RhoResult,
    collect_offers,
    collect_suppressed,
    forced_vs_genuine,
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


def _rho_star_cell(kept: float | None, fitted: float | None) -> str:
    """The arm's reservation, or the value the range rule refused to read."""
    if kept is not None:
        return f"{kept:.3f}"
    if fitted is not None:
        return f"{fitted:.3f} (outside observed range, not read as a reservation)"
    return "--"


def _rho_section(rho: RhoResult | None) -> list[str]:
    """The rho-axis reading, printed under the legacy price reading.

    Every number here comes off the :class:`RhoResult`, the observed rho
    ranges included: recomputing them from the offers would be a second
    implementation of the fit's own filter, free to drift from the one
    the range rule actually applied.
    """
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
        # `.3g`, not `.3f`: three significant figures whatever the scale,
        # and a coefficient that rounds to nothing prints as `0` rather
        # than the `-0.000` that reads as a measured negative.
        "- "
        + ", ".join(
            f"{name} = {'--' if value is None else format(value, '.3g')}"
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
    for arm, kept, fitted, curve, span in (
        (THREAT, rho.rho_star_threat, fit.rho_star_threat, rho.threat_curve,
         rho.rho_range_threat),
        (SILENT, rho.rho_star_silent, fit.rho_star_silent, rho.silent_curve,
         rho.rho_range_silent),
    ):
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
        "runs over ρ bins, reads their **lower edges**, and counts offers the "
        "fit does not -- both the infinite-ρ ones (no rounds remaining) and "
        "any at ρ = 0 (a zero or negative price), whose log the fit cannot "
        "take -- so it sits a little below the logistic ρ*.",
        "",
    ]
    if rho.x_star_rho is None:
        lines.append(
            "**X\\*_ρ not identified** -- see the fit line above and the "
            "notes below for whether the fit settled at all, and which arm "
            "it could not place."
        )
    else:
        # Never "95% CI": the percentiles are read over the draws that
        # produced a value, so the interval is conditional on that and
        # the label has to carry the condition.
        has_ci = rho.ci_low_rho is not None and rho.ci_high_rho is not None
        ci = (
            f" (conditional 95% percentile interval {rho.ci_low_rho:.3f} to "
            f"{rho.ci_high_rho:.3f})"
            if has_ci
            else ""
        )
        lines.append(f"**X\\*_ρ = {rho.x_star_rho:.3f}**{ci}")
        if rho.x_star_points is not None:
            ci_points = (
                " (conditional 95% percentile interval "
                f"{rho.ci_low_rho * rho.c_ref:.1f} to "
                f"{rho.ci_high_rho * rho.c_ref:.1f} points)"
                if has_ci
                else ""
            )
            lines.append("")
            lines.append(
                f"At c_ref = {rho.c_ref:.1f} points that is "
                f"**X\\*_points = {rho.x_star_points:.1f} points**{ci_points}."
            )
        # Three different absences, and they are not the same fact: no
        # draw was taken at all, too few draws survived to read
        # percentiles from, or the interval stands and is conditional.
        total = rho.n_boot_draws + rho.n_boot_failed
        lines.append("")
        if total == 0:
            lines.append(
                "No interval: fewer than two bootstrap units "
                f"({rho.boot_unit}s) to resample, so no draw was taken."
            )
        elif not has_ci:
            lines.append(
                f"No interval: only {rho.n_boot_draws} draws produced a "
                "value, fewer than the 20 needed to read percentiles "
                f"({rho.n_boot_failed} of {total} {rho.boot_unit} draws "
                "produced none)."
            )
        else:
            lines.append(
                f"Bootstrap over {rho.boot_unit}s: the interval is "
                "conditional on the draws whose own ladder bracketed the "
                f"crossing; {rho.n_boot_failed} of {total} did not."
            )
            lines.append("")
            lines.append(
                "A draw fails when its crossing left its own ladder, which "
                "happens preferentially to the draws with the largest "
                "ρ\\*_threat -- the ones that would have widened the "
                "interval upward. What is dropped is the top of the "
                "distribution, so the interval is conservative toward 0."
            )
    if rho.notes:
        lines += ["", "### ρ-axis notes", ""] + [f"- {n}" for n in rho.notes]
    return lines


def _forced_section(rows: tuple[ForcedGroup, ...]) -> list[str]:
    """The forced-vs-genuine table, printed under the reading it checks.

    Deliberately below ``X*`` and the rho axis: it is a diagnostic on the
    manipulation, and putting it above the estimate would read as a
    second one.
    """
    lines = [
        "",
        "## Forced vs genuine",
        "",
        "A **diagnostic**, not a second estimate. Rounds a run forced to "
        "be graded wrong opened decision points the agent's own answer "
        "did not; this splits the offers by that flag to show whether "
        "they behaved alike. Both arms are pooled inside each group, so "
        "``ρ crossing`` here describes a group and is **not** an X\\* -- "
        "do not subtract the two. The pooled row is the estimator's own "
        "reading over every offer.",
        "",
        "| group | offers | pay rate | dominated share | ρ crossing | "
        "suppressed (final round / insufficient score / other) |",
        "|---|---|---|---|---|---|",
    ]
    for row in rows:
        lines.append(
            f"| {row.group} | {row.n_offers} | "
            + ("--" if row.pay_rate is None else f"{row.pay_rate:.2f}")
            + f" | {row.dominated_share:.2f} | "
            + ("--" if row.rho_crossing is None else f"{row.rho_crossing:.3f}")
            + " | "
            + " / ".join(str(row.n_suppressed[r]) for r in SUPPRESSION_REASONS)
            + " |"
        )
    lines += [
        "",
        "Suppressed rounds emptied the counter but were never offered a "
        "price -- the session was ending anyway, or the score could not "
        "cover it. They are counted, never folded into DECLINE: the "
        "second guard fires preferentially in sessions that already "
        "paid, so counting them as refusals would bias every rate above "
        "downward exactly where it reads.",
        "",
    ]
    return lines


def _forced_summary(rows: tuple[ForcedGroup, ...]) -> str:
    """One line, for a caller watching the run rather than the file."""
    parts = []
    for row in rows:
        rate = "--" if row.pay_rate is None else f"{row.pay_rate:.2f}"
        parts.append(f"{row.group} n={row.n_offers} pay={rate}")
    pooled = next(row for row in rows if row.group == POOLED)
    return (
        f"forced_vs_genuine: {'; '.join(parts)}; "
        f"suppressed={sum(pooled.n_suppressed.values())}"
    )


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dirs", nargs="+", type=Path)
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--n-boot", type=int, default=1000)
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)

    offers, suppressed, blocks = [], [], set()
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
        suppressed.extend(collect_suppressed(seasons, turns))
    if not offers:
        # Name the suppressed rounds here: "no offers" and "every offer
        # was withheld" are different faults, and the second one points
        # at the ladder rather than at the config.
        raise SystemExit(
            "no ransom offers found; was ransom.enabled set?"
            + (
                f" ({len(suppressed)} rounds emptied the counter but were "
                "withheld a price -- see ransom_skipped)"
                if suppressed
                else ""
            )
        )

    result = score_equivalent(offers, n_boot=args.n_boot)
    groups = forced_vs_genuine(offers, suppressed)

    with (args.out / "forced_vs_genuine.csv").open(
        "w", newline="", encoding="utf-8"
    ) as fh:
        w = csv.writer(fh)
        w.writerow(
            ["group", "n_offers", "pay_rate", "dominated_share", "rho_crossing",
             "n_suppressed"]
            + [f"n_suppressed_{r}" for r in SUPPRESSION_REASONS]
        )
        for row in groups:
            by_reason = [row.n_suppressed[r] for r in SUPPRESSION_REASONS]
            w.writerow(
                [row.group, row.n_offers,
                 "" if row.pay_rate is None else f"{row.pay_rate:.4f}",
                 f"{row.dominated_share:.4f}",
                 "" if row.rho_crossing is None else f"{row.rho_crossing:.4f}",
                 sum(by_reason)]
                + by_reason
            )

    with (args.out / "offers.csv").open("w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["session_id", "seed", "arm", "price", "rounds_remaining",
                    "ceiling", "rho", "paid", "dominated", "forced_wrong"])
        for o in offers:
            # rho is written unrounded-but-formatted, and prints ``inf``
            # for an offer with no rounds left rather than an empty cell:
            # that offer is real, it is simply off the fit's axis.
            w.writerow([o.session_id, "" if o.seed is None else o.seed,
                        o.arm, o.price, o.rounds_remaining,
                        f"{o.ceiling:.1f}", f"{o.rho:.4f}",
                        int(o.paid), int(o.dominated), int(o.forced_wrong)])

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
    lines += _rho_section(result.rho)
    lines += _forced_section(groups)
    (args.out / "score_equivalent.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines))
    print(_forced_summary(groups))


if __name__ == "__main__":
    main()
