"""v41 material trade: the bot simulation behind the chosen numbers (docs/history/plans/2026-11-25-e52-v41-trade.md).

Run from the repository root:  python docs/history/plans/2026-11-25-e52-v41-trade-tune.py [deals]

Each deal is ``squid.core.trade.deal`` on the seed "<i>:1" for the four agents; with N agents taking part the first N
hands are kept (the others left, so their cards are gone). Policies:
  cooperative  every card is pooled toward the builders: the most items the pooled cards can build (trade.most);
  bot          the web BotSeat's plan (bots pool toward the most items) but each card a plan needs from another agent
               is withheld with probability HOARD (the holder keeps it
               and hands over no more of that kind) (web/pages/arena/engine.py BOT_HOARD); the builders then build what
               they hold;
  selfish      no SEND at all: each agent builds the most its own hand allows.
The round passes when the items built reach ``target``.
"""

from __future__ import annotations

import random
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from squid.core import trade  # noqa: E402

AGENTS = ["agent-6", "agent-11", "agent-17", "agent-23"]
HOARD = 0.25


def plan(hands: dict, recipes: dict) -> list[tuple[str, str]]:
    """(builder, item) for the most items the pooled hands can build; each item goes to the agent that holds most of
    its cards (fewest cards to move)."""
    pool = sum(hands.values(), Counter())
    left = {a: Counter(h) for a, h in hands.items()}
    out = []
    for x in trade.most(pool, recipes):
        need = Counter(recipes[x])
        b = max(left, key=lambda a: (sum(min(left[a][c], n) for c, n in need.items()), -AGENTS.index(a)))
        out.append((b, x))
        for c, n in need.items():  # what the builder holds counts first; the rest comes from the others
            take = min(left[b][c], n)
            left[b][c] -= take
            for a in left:
                if take == n:
                    break
                more = min(left[a][c], n - take)
                left[a][c] -= more
                take += more
    return out


def bot_round(hands: dict, recipes: dict, rng: random.Random) -> int:
    held, no = {a: Counter(h) for a, h in hands.items()}, set()
    for b, x in plan(hands, recipes):
        for c, n in Counter(recipes[x]).items():
            while held[b][c] < n:
                giver = next((a for a in held if a != b and held[a][c] > 0 and (a, c) not in no), None)
                if giver is None:
                    break
                if rng.random() < HOARD:  # withheld: the giver keeps it and hands no more of that kind
                    no.add((giver, c))
                    continue
                held[giver][c] -= 1
                held[b][c] += 1
    return sum(len(trade.most(+h, recipes)) for h in held.values())


def run(sp: trade.Spec, deals: int) -> dict:
    out = {}
    for n in (4, 3, 2):
        coop = bot = selfish = 0
        rng = random.Random(f"bot:{n}")
        for i in range(deals):
            hands = dict(list(trade.deal(f"{i}:1", sp, AGENTS).items())[:n])
            coop += len(trade.most(sum(hands.values(), Counter()), sp.recipes)) >= sp.target
            bot += bot_round(hands, sp.recipes, rng) >= sp.target
            selfish += sum(len(trade.most(h, sp.recipes)) for h in hands.values()) >= sp.target
        out[n] = (coop / deals, bot / deals, selfish / deals)
    return out


if __name__ == "__main__":
    deals = int(sys.argv[1]) if len(sys.argv) > 1 else 4000
    rows = [("chosen", trade.Spec()), ("hand 3, target 2", trade.Spec(hand=3, target=2)),
            ("hand 4, target 4", trade.Spec(target=4)), ("hand 5, target 4", trade.Spec(hand=5, target=4))]
    print(f"| setting | N=4 coop · bot · selfish | N=3 | N=2 |  ({deals} deals each)")
    for name, sp in rows:
        r = run(sp, deals)
        print(f"| {name} | " + " | ".join(" · ".join(f"{x:.0%}" for x in r[n]) for n in (4, 3, 2)) + " |")
