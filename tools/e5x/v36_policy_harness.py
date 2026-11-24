"""5.2 v36 (joint SOLVE) policy harness for rubric G01: does a seat that never solves (always PASS) end ahead of seats
that answer, through the real engine (squid.game, config e52v36_public_sol4) with scripted replies, no model.

Every TALK reply is DONE (``talk`` tokens). At SOLVE a seat's policy answers: ``solve`` = the right action with
probability ``p`` (else a wrong one), generating ``cost`` tokens; ``pass`` = ACTIONS: PASS for ``pass_cost`` tokens. One
seat (rotating with the seed) plays ``pass``, the other three ``solve``; a control has all four on ``solve``. Reported per
policy: mean change in tokens over the session (end minus start, before the end allocation; the pass seat rotates
over every start size), the share of seats still in at the end, mean rank (1 = most
tokens), and the game's Sen index on the final holdings with the allocation (mean x (1 - Gini)).

    PYTHONPATH=. python tools/e5x/v36_policy_harness.py --games 60
"""

from __future__ import annotations

import argparse
import functools
from concurrent.futures import ProcessPoolExecutor
import dataclasses
import random
import re
import statistics as st
from pathlib import Path

from squid import game as e52
from squid.__main__ import EXPERIMENTS
from squid.core.config import load
from squid.core.providers import ProviderConfig, Reply, Stub
from squid.core.puzzle import ACTIONS

ROOT = Path(__file__).resolve().parents[2]
for _name in ("public_round", "public_truth", "public_info", "task_stats"):  # pure in their arguments: cache across policies
    setattr(e52, _name, functools.lru_cache(maxsize=None)(getattr(e52, _name)))


def gini(xs: list[float]) -> float:
    xs, n = sorted(xs), len(xs)
    return 0.0 if not n or not sum(xs) else sum((2 * i - n + 1) * x for i, x in enumerate(xs)) / (n * sum(xs))


def game(seed: int, policies: dict, p: float, cost: int, pass_cost: int = 30, talk: int = 40) -> dict:
    c = load(ROOT / "squid/configs/e52v36_public_sol4.yaml", EXPERIMENTS)
    ev, rng = [], random.Random(f"harness:{seed}:{p}:{cost}")

    def respond(m, cap):
        a, u = re.search(r"agent-\d+", m[0]["content"]).group(0), m[-1]["content"]
        r = int(re.match(r"Round (\d+)", u).group(1))
        if not re.match(rf"Round {r}: SOLVE\.", u):
            return Reply("DONE", talk)
        if policies[a] == "pass":
            return Reply("ACTIONS: PASS", pass_cost)
        ans = next(e for e in ev if e["event"] == "round_start" and e["round"] == r)["tasks"][a]["answers"][0]
        act = ans if rng.random() < p else rng.choice([x for x in ACTIONS if x != ans])
        return Reply(f"ACTIONS: {act}", cost)

    g = e52.Game(c.settings, c.cells[0], seed, Stub(ProviderConfig("stub", "stub"), respond), ev.append, "h")
    res = g.run()
    end = g.end_allocation()
    final = {a: v["final"] for a, v in res["agents"].items()}
    held = [final[a] + (end["prize_each"] if a in end["winner"] else 0) for a in final]
    order = sorted(final, key=lambda a: -final[a])
    return {"final": final, "gain": {a: final[a] - g.starts[a] for a in final}, "in": {a: v["status"] == "in" for a, v in res["agents"].items()},
            "rank": {a: order.index(a) + 1 for a in final}, "sen": st.mean(held) * (1 - gini(held)),
            "charged_rounds": sum(1 for e in ev if e["event"] == "charges" and any(e["taken"].values()))}


CONDS = [(p, cost, arm) for p in (0.3, 0.6, 0.9) for cost in (800, 2000, 7000, 14000) for arm in ("one_pass", "all_solve")]


def seed_rows(i: int) -> list[tuple]:
    """Every condition for game i (seed 5000 + i): the pass seat rotates over every start size ((i // 2) % 4)."""
    agents, out = e52.AGENTS, []
    for p, cost, arm in CONDS:
        pol = {a: "pass" if arm == "one_pass" and a == agents[(i // 2) % 4] else "solve" for a in agents}
        g = game(5000 + i, pol, p, cost)
        out += [((p, cost, arm), pol[a], g["gain"][a], g["in"][a], g["rank"][a], g["sen"], g["charged_rounds"]) for a in agents]
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=16)
    ap.add_argument("--workers", type=int, default=8)
    args = ap.parse_args()
    with ProcessPoolExecutor(args.workers) as pool:
        rows = [r for chunk in pool.map(seed_rows, range(args.games)) for r in chunk]
    print(f"{args.games} games per condition")
    print("p | cost | arm | policy | mean change | still in | mean rank | Sen (M) | rounds charged")
    for cond in CONDS:
        for pol in ("pass", "solve"):
            rs = [r for r in rows if r[0] == cond and r[1] == pol]
            if rs:
                print(f"{cond[0]} | {cond[1]} | {cond[2]} | {pol} | {st.mean(r[2] for r in rs):,.0f} | "
                      f"{st.mean(r[3] for r in rs):.2f} | {st.mean(r[4] for r in rs):.2f} | "
                      f"{st.mean(r[5] for r in rs) / 1e6:.2f} | {st.mean(r[6] for r in rs) / 4:.2f}")


if __name__ == "__main__":
    main()
