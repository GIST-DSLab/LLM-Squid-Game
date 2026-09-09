"""Draw the two curves the score-equivalent estimator fits (2026-09-10).

    uv run python -m scripts.analysis.plot_score_equivalent <out_dir> [--title T]

``<out_dir>`` is a directory ``scripts.analysis.score_equivalent`` wrote
(``rho_curves.csv``, ``arm_curves.csv``, ``offers.csv``, ``score_equivalent.md``).
Two figures land beside them, each as PNG and SVG:

``rho_curve``   payment rate against rho = price / (reward x rounds remaining),
                one line per arm, observed bin rates as markers sized by offer
                count, the logistic fit as a line, each arm's rho* marked and
                X*_rho = rho*_threat - rho*_silent annotated.
``price_curve`` the same on the price axis (the ladder the config states),
                with the price-axis X* when the estimator identified one and a
                plain "not identified" note when it did not.

rho* / X* values are read from ``score_equivalent.md`` so the figure never
re-derives a number the report does not print. The two arms keep one colour
each across every figure (threat magenta, silent blue), validated for CVD
separation; identity is also carried by marker shape and direct labels.
"""
from __future__ import annotations

import argparse
import csv
import re
from collections import defaultdict
from pathlib import Path

import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from squid_game.evaluation.behavioral.score_equivalent import (  # noqa: E402
    Offer,
    fit_rho_logistic,
)

ARMS = ("threat", "silent")
COLOR = {"threat": "#A3123F", "silent": "#2A78D6"}
MARKER = {"threat": "o", "silent": "s"}
LABEL = {"threat": "threat (hz_1111)", "silent": "silent (hz_0000)"}
INK, INK_SOFT, RULE = "#14181F", "#4C5563", "#D2D8DF"

_RHO_STAR = re.compile(r"^\|\s*(threat|silent)\s*\|\s*([-\d.]+|None)\s*\|", re.M)
_X_RHO = re.compile(r"X\\?\*_ρ = ([-\d.]+)\*\*\s*\((?:conditional )?95% percentile interval ([-\d.]+) to ([-\d.]+)\)")
_X_PTS = re.compile(r"X\\?\* = ([-\d.]+) points \(95% CI ([-\d.]+) to ([-\d.]+)\)")
_X_NONE = re.compile(r"X\\?\* not identified")
_PRICE_CROSS = re.compile(r"^\|\s*(threat|silent) \(hz_\d{4}\)\s*\|\s*([-\d.]+|None)\s*\|", re.M)


def _read_curves(path: Path) -> dict[str, list[dict]]:
    rows: dict[str, list[dict]] = defaultdict(list)
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows[r["arm"]].append(r)
    return rows


def _read_md(path: Path) -> dict:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    out: dict = {"rho_star": {}, "price_cross": {}}
    # The rho table and the price table both have an "arm | value" shape;
    # the price table's first column carries the framing in parentheses.
    for arm, val in _PRICE_CROSS.findall(text):
        out["price_cross"][arm] = None if val == "None" else float(val)
    rho_section = text.split("ρ*", 1)[1] if "ρ*" in text else ""
    for arm, val in _RHO_STAR.findall(rho_section):
        if arm not in out["rho_star"]:
            out["rho_star"][arm] = None if val == "None" else float(val)
    m = _X_RHO.search(text)
    out["x_rho"] = tuple(float(v) for v in m.groups()) if m else None
    m = _X_PTS.search(text)
    out["x_pts"] = tuple(float(v) for v in m.groups()) if m else None
    out["x_pts_none"] = bool(_X_NONE.search(text))
    return out


def _logistic_from_offers(path: Path):
    """Refit ``P(pay) = sigmoid(a_arm + b log rho)`` from ``offers.csv``.

    The estimator does not write its coefficients, only rho*. Refitting
    from the same rows with the same function reproduces the curve the
    reported rho* was read from, so the line and the marker agree.
    """
    if not path.exists():
        return None
    offers = []
    with path.open(encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rem = int(float(r["rounds_remaining"]))
            ceiling = float(r["ceiling"])
            reward = ceiling / rem if rem > 0 else 10.0
            offers.append(Offer(
                session_id=r["session_id"], arm=r["arm"], price=float(r["price"]),
                paid=r["paid"] in ("1", "True", "true"), rounds_remaining=rem,
                reward=reward, seed=int(r["seed"]) if r.get("seed") else None,
                forced_wrong=r.get("forced_wrong", "0") in ("1", "True", "true"),
            ))
    if not offers:
        return None
    fit = fit_rho_logistic(offers)
    if fit.b is None:
        return None
    return {"threat": fit.a_threat, "silent": fit.a_silent, "b": fit.b}


def _sigmoid(z: float) -> float:
    return 1.0 / (1.0 + math.exp(-z))


def _style(ax, xlabel: str) -> None:
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(RULE)
    ax.tick_params(colors=INK_SOFT, labelsize=9, length=3)
    ax.grid(axis="y", color=RULE, linewidth=0.6)
    ax.set_axisbelow(True)
    ax.set_ylim(-0.03, 1.05)
    ax.set_yticks([0, 0.25, 0.5, 0.75, 1.0])
    ax.set_yticklabels(["0", "25%", "50%", "75%", "100%"])
    ax.set_ylabel("payment rate", color=INK_SOFT, fontsize=10)
    ax.set_xlabel(xlabel, color=INK_SOFT, fontsize=10)
    ax.axhline(0.5, color=INK_SOFT, linewidth=0.8, linestyle=(0, (3, 3)))
    ax.text(ax.get_xlim()[0], 0.515, "50% = reservation", ha="left", va="bottom",
            fontsize=8, color=INK_SOFT)


NUDGE = {"threat": -1.0, "silent": 1.0}


def _plot(ax, curves: dict[str, list[dict]], xkey: str, width_ref: float) -> None:
    """Observed bin rates + PAV steps per arm.

    ``width_ref`` is one x-step of the axis (a rho bin, a ladder rung);
    markers are nudged by 6 % of it in opposite directions per arm so two
    arms that paid at the same rate in the same bin both stay visible.
    """
    for arm in ARMS:
        rows = sorted(
            (r for r in curves.get(arm, []) if r.get("payment_rate") and r.get("fitted")),
            key=lambda r: float(r[xkey]),
        )
        if not rows:
            continue
        x = [float(r[xkey]) for r in rows]
        obs = [float(r["payment_rate"]) for r in rows]
        fit = [float(r["fitted"]) for r in rows]
        n = [int(r["n_offers"]) for r in rows]
        ax.plot(x, fit, color=COLOR[arm], linewidth=1.2, linestyle=(0, (1, 2)),
                drawstyle="steps-post", alpha=0.9, label=f"{LABEL[arm]} — monotone (PAV) fit")
        xs = [v + NUDGE[arm] * 0.06 * width_ref for v in x]
        ax.scatter(xs, obs, s=[max(36, 9 * k) for k in n], color=COLOR[arm],
                   marker=MARKER[arm], edgecolors="white", linewidths=1.2, zorder=3,
                   label=f"{LABEL[arm]} — observed (size = offers)")


def _end_labels(ax, points: dict[str, tuple[float, float]]) -> None:
    """Direct labels at each arm's last point; pushed apart when they collide."""
    items = sorted(points.items(), key=lambda kv: kv[1][1])
    ys = [y for _, (_, y) in items]
    for i in range(1, len(ys)):
        if ys[i] - ys[i - 1] < 0.07:
            ys[i] = ys[i - 1] + 0.07
    for (arm, (x, _)), y in zip(items, ys):
        ax.annotate(LABEL[arm], (x, y), xytext=(8, 0), textcoords="offset points",
                    fontsize=8.5, color=INK, va="center")


def _mark_pair(ax, values: dict[str, float | None], fmt: str) -> None:
    """One dashed line per arm; a single shared label when both coincide."""
    a, b = values.get("threat"), values.get("silent")
    if a is not None and b is not None and abs(a - b) < 1e-9:
        _mark_vertical(ax, a, INK_SOFT, fmt.format(a) + " (both arms)", 0.90)
        return
    for i, arm in enumerate(ARMS):
        v = values.get(arm)
        _mark_vertical(ax, v, COLOR[arm], fmt.format(v) if v is not None else "", 0.90 - 0.22 * i)


def _mark_vertical(ax, x: float | None, color: str, text: str, y: float) -> None:
    if x is None:
        return
    ax.axvline(x, color=color, linewidth=1.2, linestyle=(0, (4, 3)), alpha=0.9)
    ax.text(x, y, text, rotation=90, ha="right", va="top", fontsize=8, color=color)


def draw(out_dir: Path, title: str | None) -> list[Path]:
    rho = _read_curves(out_dir / "rho_curves.csv")
    price = _read_curves(out_dir / "arm_curves.csv")
    md = _read_md(out_dir / "score_equivalent.md")
    written: list[Path] = []
    head = f"{title} — " if title else ""

    # --- rho axis -------------------------------------------------------
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    _plot(ax, rho, "rho_bin_lower", 0.25)
    xs = [float(r["rho_bin_lower"]) for rows in rho.values() for r in rows]
    if xs:
        ax.set_xlim(min(xs) - 0.05, max(xs) + 0.45)
    _style(ax, "ρ = price ÷ (reward × rounds remaining)   [ρ > 1: paying can never pay back]")
    ax.axvspan(1.0, ax.get_xlim()[1], color=RULE, alpha=0.35, lw=0)
    ax.text(1.02, 1.03, "above the ceiling →", fontsize=8, color=INK_SOFT, va="bottom")
    logit = _logistic_from_offers(out_dir / "offers.csv")
    ends: dict[str, tuple[float, float]] = {}
    if logit:
        lo, hi = ax.get_xlim()
        grid = [max(0.02, lo) + i * (hi - max(0.02, lo)) / 200 for i in range(201)]
        for arm in ARMS:
            a = logit[arm]
            if a is None:
                continue
            ax.plot(grid, [_sigmoid(a + logit["b"] * math.log(g)) for g in grid],
                    color=COLOR[arm], linewidth=2, label=f"{LABEL[arm]} — logistic fit (ρ* read here)")
            ends[arm] = (grid[-1], _sigmoid(a + logit["b"] * math.log(grid[-1])))
        _end_labels(ax, ends)
    _mark_pair(ax, md["rho_star"], "ρ*={:.2f}")
    if md["x_rho"]:
        x, lo, hi = md["x_rho"]
        sub = f"X*_ρ = {x:.3f}   (95% CI {lo:.2f} to {hi:.2f})"
    else:
        sub = "X*_ρ not identified"
    ax.set_title(f"{head}payment rate by ρ\n{sub}", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    fig.tight_layout()
    for ext in ("png", "svg"):
        p = out_dir / f"rho_curve.{ext}"
        fig.savefig(p, bbox_inches="tight", facecolor="white")
        written.append(p)
    plt.close(fig)

    # --- price axis -----------------------------------------------------
    fig, ax = plt.subplots(figsize=(7.2, 4.2), dpi=160)
    _plot(ax, price, "price", 5.0)
    ps = sorted({float(r["price"]) for rows in price.values() for r in rows})
    if ps:
        ax.set_xlim(ps[0] - 2, ps[-1] + 6)
        ax.set_xticks(ps)
    _style(ax, "ransom price (points)")
    _mark_pair(ax, md["price_cross"], "crossing={:.1f}")
    if md["x_pts"]:
        x, lo, hi = md["x_pts"]
        sub = f"X* = {x:.1f} points   (95% CI {lo:.1f} to {hi:.1f})"
    elif md["x_pts_none"]:
        sub = "price-axis X* not identified (no arm crosses 50% inside the ladder)"
    else:
        sub = ""
    ends = {}
    for arm in ARMS:
        rows = sorted((r for r in price.get(arm, []) if r.get("fitted")), key=lambda r: float(r["price"]))
        if rows:
            ends[arm] = (float(rows[-1]["price"]), float(rows[-1]["fitted"]))
    _end_labels(ax, ends)
    ax.set_title(f"{head}payment rate by price\n{sub}", loc="left", fontsize=11, color=INK)
    ax.legend(frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.18), ncol=2)
    fig.tight_layout()
    for ext in ("png", "svg"):
        p = out_dir / f"price_curve.{ext}"
        fig.savefig(p, bbox_inches="tight", facecolor="white")
        written.append(p)
    plt.close(fig)
    return written


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--title", default=None, help="model / run label for the figure titles")
    args = ap.parse_args()
    for p in draw(args.out_dir, args.title):
        print(p)


if __name__ == "__main__":
    main()
