"""The rule agents' all-four curves (share of games with all four still in after each round) for the leaderboard's
RMST chart, added to tools/monitor/static/rule_agents_20261113.json as each row's ``curve``.

The paper stores only C and the final all-four share of its simulated rule agents. Their curves come from the paper's
own replays, unchanged: paper/cogsci2027/tools/exit_all_opportunities_20261112.rule_agents replays
rule_baselines_20261111 on its random stream and asserts C equal to the stored values (the five named types and the
random agent); rule_minimal_rescue_20261112.main's replay gives the minimal-rescue agent. This script only wraps
rule_baselines_20261111.simulate to keep each replicate's C (= first departure round / 8) and final all-four flag:
all four are in after round r < 8 exactly when the first departure came later than r, and after round 8 when nobody
left. Gate: each curve's area / 8 equals the stored C (to rounding).

Run from the repo root: ~/.venvs/squid-game/bin/python web/tools/make_rule_curves.py   (needs the paper's local
validation tables, paper/cogsci2027/validation_20261108/results/tables/*.pkl; no model calls)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np

REPO = Path(__file__).resolve().parents[2]
PAPER = REPO / "paper" / "cogsci2027"
OUT = REPO / "tools" / "monitor" / "static" / "rule_agents_20261113.json"
sys.path.insert(0, str(PAPER / "tools"))
sys.path.insert(0, str(PAPER / "validation_20261108" / "tools"))

import rule_baselines_20261111 as rb  # noqa: E402

CALLS: list[dict] = []
_simulate, _run = rb.simulate, rb.run


def simulate(*a, **k):
    out = _simulate(*a, **k)
    CALLS[-1]["parts"].append((out["C"].copy(), out["all4"].copy()))
    return out


def run(c, theta, kappa, rng, solver1, refill, exit_p=None):
    CALLS.append({"theta": theta, "kappa": kappa, "exit_p": exit_p, "parts": []})
    r = _run(c, theta, kappa, rng, solver1, refill, exit_p)
    CALLS[-1]["C"] = r["C"]
    return r


def curve(call: dict) -> list[float]:
    C = np.concatenate([p[0] for p in call["parts"]])
    all4 = np.concatenate([p[1] for p in call["parts"]])
    dep = np.rint(C * rb.w1.ROUNDS)  # first departure round, ROUNDS if nobody left before the end
    pts = [1.0] + [float((dep > r).mean()) for r in range(1, rb.w1.ROUNDS)] + [float(all4.mean())]
    assert abs(sum(pts[:-1]) / rb.w1.ROUNDS - call["C"]) < 6e-4, (sum(pts[:-1]) / rb.w1.ROUNDS, call["C"])
    return [round(x, 4) for x in pts]


def main() -> None:
    rb.simulate, rb.run = simulate, run
    import exit_all_opportunities_20261112 as ea
    ea.rule_agents()                                  # asserts every C equal to rule_baselines_20261111.json
    random_call = next(c for c in CALLS if c["exit_p"] is not None)
    named = dict(zip(("reference", "cooperator", "keeper", "stayer", "leaver"), CALLS[-5:]))
    CALLS.clear()
    import rule_minimal_rescue_20261112 as rmr
    rb.share = rmr.share
    rng = np.random.default_rng(20261112)             # rule_minimal_rescue_20261112.main, the same calls in order
    f = rb.d.load()
    cal, solver1, _, _ = rb.w1.calibrate(f)
    refill = rb.w1.Refill(rb.w1.seat_agents(f["seats"]))
    rb.run(cal["pooled"], 1.0, .25, rng, solver1, refill)
    rb.run(cal["pooled"], 1.0, rmr.MINIMAL, rng, solver1, refill)
    stored_min = json.loads((PAPER / "results" / "rule_minimal_rescue_20261112.json").read_text())["minimal_rescue"]
    assert CALLS[-1]["C"] == stored_min["C"], (CALLS[-1]["C"], stored_min["C"])
    named["minimal"] = CALLS[-1]
    named["random"] = random_call
    data = json.loads(OUT.read_text())
    for row in data["rows"]:
        call = named[row["key"]]
        assert abs(call["C"] - row["C"]) < 1e-9, (row["key"], call["C"], row["C"])
        row["curve"] = curve(call)
        print(f"{row['key']:10s} C {row['C']:.3f} curve {row['curve']}")
    data["curve_source"] = ("web/tools/make_rule_curves.py: the paper's replays (exit_all_opportunities_20261112.rule_agents, "
                            "rule_minimal_rescue_20261112.main), each replicate's first departure round; area / 8 = C")
    OUT.write_text(json.dumps(data, ensure_ascii=False, indent=1) + "\n")


if __name__ == "__main__":
    main()
