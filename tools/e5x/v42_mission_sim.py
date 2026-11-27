"""5.2 v42 secret mission: the bot simulation behind the chosen numbers (docs/history/plans/2026-11-25-e52-v42-secret-mission.md).

No model and no engine round: each round is ``squid.core.mission.resolve`` (votes -> team -> FAIL count) and the charge /
share arithmetic of the design (every agent taking part pays charge_total // N when the mission fails, then
``mission.shares`` pays steal_pct % of what was taken to the team's FAIL players). Balances are ample (no agent reaches
zero) and N stays fixed for the whole session, so each row is one table size. TALK and SOLVE generation is left out: it
is the same for every policy.

Card policies:  honest  every agent plays SUCCESS
                fixed1  one agent (a different seat each session) always plays FAIL, the others SUCCESS
                fixed2  two agents always play FAIL
                p=0.2 / p=0.4  each agent plays FAIL with that probability each round
Vote policies:  random     each agent votes for m agents drawn at random (itself allowed)
                suspicion  each agent votes for itself and the m - 1 others it suspects least: for every earlier failed
                           mission it spreads the FAIL cards it did not play itself over the other team members (an agent
                           knows its own card), and every earlier mission with no FAIL card it cannot account for takes
                           0.25 off each other member; ties at random. Saboteurs vote the same way (self first).
'FAIL seat' in the p rows = the seats whose FAIL card was used (on the team) at least once in the session.

    PYTHONPATH=. python tools/e5x/v42_mission_sim.py [--games 4000] [--rounds 8] [--pct 50]
"""

from __future__ import annotations

import argparse
import random
import statistics as st

from squid.core import mission, rules

AG = rules.TEAM_AGENTS
C = 24000


def cards_of(policy: str, part: list[str], bad: list[str], rng: random.Random) -> dict:
    if policy.startswith("p="):
        p = float(policy[2:])
        return {a: "FAIL" if rng.random() < p else "SUCCESS" for a in part}
    return {a: "FAIL" if a in bad else "SUCCESS" for a in part}


def suspicion(me: str, part: list[str], log: list[dict]) -> dict:
    score = dict.fromkeys(part, 0.0)
    for x in log:
        mine = x["cards"].get(me) == "FAIL" and me in x["team"]
        others = [b for b in x["team"] if b != me]
        left = x["fails"] - mine
        for b in others:
            score[b] += left / len(others) if left else -0.25
    return score


def votes_of(policy: str, part: list[str], m: int, log: list[dict], rng: random.Random) -> dict:
    if policy == "random":
        return {a: rng.sample(part, m) for a in part}
    out = {}
    for a in part:
        s = suspicion(a, part, log)
        others = sorted(rng.sample([b for b in part if b != a], len(part) - 1), key=lambda b: s[b])
        out[a] = [a] + others[:m - 1]
    return out


def session(n: int, cards: str, votes: str, rounds: int, pct: int, seed: int) -> dict:
    rng = random.Random(f"sim:{seed}")
    part, sp = AG[:n], mission.Spec(steal_pct=pct)
    k = 2 if cards == "fixed2" else 1 if cards == "fixed1" else 0
    bad = rng.sample(part, min(k, n))
    net, log = dict.fromkeys(part, 0), []
    for r in range(1, rounds + 1):
        x = mission.resolve(votes_of(votes, part, sp.team if n > sp.team else n, log, rng),
                            cards_of(cards, part, bad, rng), part, sp, f"{seed}:{r}")
        log.append(x)
        if not x["passed"]:
            taken = {a: C // n for a in part}
            for a in part:
                net[a] -= taken[a]
            for a, v in mission.shares(taken, x["failers"], {}, pct).items():
                net[a] += v
    if cards.startswith("p="):  # the FAIL seats: those whose FAIL card was used at least once
        bad = [a for a in part if any(a in x["failers"] for x in log)]
    return {"passed": [x["passed"] for x in log], "net": net, "bad": bad}


def row(n, cards, votes, games, rounds, pct) -> str:
    runs = [session(n, cards, votes, rounds, pct, g) for g in range(games)]
    passed = [p for s in runs for p in s["passed"]]
    late = [p for s in runs for p in s["passed"][rounds // 2:]]
    bad = [s["net"][a] for s in runs for a in s["bad"]]
    good = [v for s in runs for a, v in s["net"].items() if a not in s["bad"]]
    drain = st.mean(sum(s["net"].values()) for s in runs) / rounds
    fmt = lambda xs: f"{st.mean(xs):>+9,.0f}" if xs else f"{'-':>9}"  # noqa: E731
    return (f"| {n} | {cards:<6} | {votes:<9} | {st.mean(passed):.2f} | {st.mean(late):.2f} | {fmt(bad)} | {fmt(good)} "
            f"| {drain:>+8,.0f} |")


def arithmetic(pcts=(25, 34, 40, 50, 60, 75)) -> list[str]:
    out = ["Per failed mission, net tokens of a FAIL player against a mission that succeeds (0), by steal_pct:",
           "| steal_pct | N=4 one FAIL | N=4 two FAIL | N=3 one | N=3 two | N=2 one | N=2 two | drain per failed mission |",
           "|---|---|---|---|---|---|---|---|"]
    for p in pcts:
        cells = []
        for n in (4, 3, 2):
            taken = {a: C // n for a in AG[:n]}
            cells += [f"{mission.shares(taken, AG[:f], {}, p)[AG[0]] - C // n:+,}" for f in (1, 2)]
        out.append(f"| {p} | " + " | ".join(cells) + f" | {-C * (100 - p) // 100:,} |")
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--games", type=int, default=4000)
    ap.add_argument("--rounds", type=int, default=8)
    ap.add_argument("--pct", type=int, default=50)
    a = ap.parse_args()
    print("\n".join(arithmetic()) + "\n")
    print(f"Sessions: {a.games} per row, {a.rounds} rounds, team 2, steal_pct {a.pct}, charge {C:,}. 'pass' = share of "
          f"rounds with no FAIL card on the team; 'late' = rounds {a.rounds // 2 + 1}-{a.rounds}; 'FAIL seat' / 'other "
          "seat' = mean net tokens over the session (charges paid, shares received) of the fixed FAIL seats (p rows: the seats "
          "whose FAIL card was used at least once) and of the rest; "
          "'drain' = mean change of all tokens per round.")
    print("| N | cards | votes | pass | late | FAIL seat | other seat | drain/round |\n|---|---|---|---|---|---|---|---|")
    for n in (4, 3, 2):
        for cards in ("honest", "fixed1", "fixed2", "p=0.2", "p=0.4"):
            for votes in ("random", "suspicion"):
                if not (cards == "fixed2" and n == 2 and votes == "suspicion"):
                    print(row(n, cards, votes, a.games, a.rounds, a.pct))


if __name__ == "__main__":
    main()
