"""5.2 v39 invisible-wall maze (11-26 third revision: move turns inside a round): the bot simulation behind the chosen
numbers (docs/history/plans/2026-11-24-e52-v39-invisible-maze.md, section "11-26 3차 수정").

No model and no engine round: the maze, moves and routes are ``squid.core.maze`` (``make`` with the min_path re-draw,
``walk``, ``route``). Every round draws a new maze and starts the agents at their corners; positions and knowledge last
only within the round. A round is a loop of move turns: in each turn every agent replies once (a route of up to k moves,
or STAY); a wall hit stops that agent for the rest of that turn only. The round ends at the first turn in which an agent
ends its moves on the goal (no charge), when every agent replies STAY in the same turn (charge), or at the turn cap
(charge). Balances are ample and N stays fixed; with N < 4 the first N corners in TEAM_AGENTS order are used.

Bot policy (the web BotSeat), each agent, each turn: STAY with probability 0.2 (--stay); else the shortest route to the
goal over the walls it knows (its own hits and the walls of maps shared with it; an unknown wall counts as open), cut to
k moves. At the end of each turn each agent shares its map with all the others with probability 0.5 (--share); a share
takes effect from the next turn.

The rounds run with a high cap (40 turns); a cap c is then read off: a reach within c, an all-STAY end before c, else
the cap ends it. "calls" = SOLVE calls per round (agents x turns played, every turn is a paid call).

    PYTHONPATH=. python tools/e5x/v39_maze_sim.py [--rounds 400] [--sizes 7 9] [--ks 3 4 5 6] [--extras 0 4 8]
        [--caps 4 5 6 8 10] [--min-path auto|<n>] [--stay 0.2] [--share 0.5]
"""

from __future__ import annotations

import argparse
import functools
import random
import statistics as st

from squid.core import maze as M

HIGH = 40
LAYOUT = {7: ("D4", ("A1", "G1", "A7", "G7")), 9: ("E5", ("A1", "I1", "A9", "I9"))}


def spec(size, k, extra, min_path):
    goal, starts = LAYOUT[size]
    return M.Spec(size=size, goal=goal, starts=starts, max_route=k, extra=extra, min_path=min_path)


@functools.lru_cache(maxsize=None)
def drawn(key, size, k, extra, min_path):
    return M.make(key, spec(size, k, extra, min_path))


def one_round(sp, walls, n, rng, stay, share):
    """(end turn, how: reach | stay | cap, calls, bumps, all-STAY turns) of one round run up to HIGH turns."""
    goal, ag = M.cell(sp.goal, sp.size), range(n)
    pos = {a: M.cell(sp.starts[a], sp.size) for a in ag}
    hit, got = {a: set() for a in ag}, {a: {} for a in ag}
    calls = bumps = 0
    for t in range(1, HIGH + 1):
        moved, reached = False, False
        for a in ag:
            calls += 1
            if rng.random() < stay:
                continue
            known = set(hit[a]).union(*got[a].values())
            route = M.route(sp.size, known, pos[a], goal)[:sp.max_route]
            if not route:
                continue
            moved = True
            path, bump = M.walk(walls, sp.size, pos[a], route)
            pos[a] = path[-1]
            reached |= pos[a] == goal
            if bump:
                bumps += 1
                y = M.step(*bump)
                if 0 <= y[0] < sp.size and 0 <= y[1] < sp.size:
                    hit[a].add(M.edge(bump[0], y))
        for a in ag:  # shares take effect from the next turn
            if rng.random() < share:
                for b in ag:
                    if b != a:
                        got[b][a] = frozenset(hit[a])
        if reached:
            return t, "reach", calls, bumps
        if not moved:
            return t, "stay", calls, bumps
    return HIGH, "cap", calls, bumps


def run(size, k, extra, min_path, n, rounds, stay, share):
    sp = spec(size, k, extra, min_path)
    rng = random.Random(f"sim:{size}:{k}:{extra}:{n}")
    out = []
    for i in range(rounds):
        walls = drawn(f"{i}", size, k, extra, min_path)
        out.append((M.shortest(sp, walls), *one_round(sp, walls, n, rng, stay, share)))
    return out


def read(rows, cap, n):
    """At turn cap *cap*: reach share, mean / median turns of a reach, all-STAY end share, calls and bumps per round."""
    reach = [t for _, t, how, _, _ in rows if how == "reach" and t <= cap]
    stays = sum(how == "stay" and t <= cap for _, t, how, _, _ in rows)
    turns = [min(t, cap) for _, t, _, _, _ in rows]
    calls = [n * x for x in turns]  # every agent is called every turn played (balances ample, no exits)
    return {"reach": len(reach) / len(rows), "t": st.mean(reach) if reach else float("nan"),
            "tmed": st.median(reach) if reach else float("nan"), "stay": stays / len(rows), "calls": st.mean(calls),
            "turns": st.mean(turns)}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rounds", type=int, default=400)
    ap.add_argument("--sizes", type=int, nargs="+", default=[7, 9])
    ap.add_argument("--ks", type=int, nargs="+", default=[3, 4, 5, 6])
    ap.add_argument("--extras", type=int, nargs="+", default=[0, 4, 8])
    ap.add_argument("--caps", type=int, nargs="+", default=[4, 5, 6, 8, 10])
    ap.add_argument("--ns", type=int, nargs="+", default=[4, 3, 2])
    ap.add_argument("--min-path", default="auto", help="auto = k + 1 (no reach in turn 1), or a number")
    ap.add_argument("--stay", type=float, default=0.2)
    ap.add_argument("--share", type=float, default=0.5)
    a = ap.parse_args()
    print(f"{a.rounds} rounds per row (a new maze each); STAY {a.stay}, SHARE {a.share}; min_path {a.min_path}")
    print("| size | k | extra | min_path | shortest mean | N | " + " | ".join(
        f"cap {c}: reach · turns (median) · all-STAY · calls" for c in a.caps) + " |")
    print("|---|---|---|---|---|---|" + "---|" * len(a.caps))
    for size in a.sizes:
        for k in a.ks:
            mp = k + 1 if a.min_path == "auto" else int(a.min_path)
            for extra in a.extras:
                for n in a.ns:
                    rows = run(size, k, extra, mp, n, a.rounds, a.stay, a.share)
                    cells = []
                    for c in a.caps:
                        x = read(rows, c, n)
                        cells.append(f"{x['reach']:.0%} · {x['t']:.1f} ({x['tmed']:g}) · {x['stay']:.1%} · {x['calls']:.1f}")
                    print(f"| {size} | {k} | {extra} | {mp} | {st.mean(r[0] for r in rows):.1f} | {n} | " + " | ".join(cells) + " |")


if __name__ == "__main__":
    main()
