"""5.2 v41 (11-25 researcher): the material trade. Each round every agent taking part is dealt ``hand`` new resource cards
(seed ``"<seed>:<round>"``; the draw is made for all four agents in TEAM_AGENTS order, so it never depends on who takes
part, and an absent agent's cards are simply not dealt). A public, fixed list of recipes names the cards each item needs;
an item is built by one agent that holds all of its cards at SOLVE, and each card is used once. In TALK BEFORE SOLVE an
agent hands cards to another with ``SEND <agent> <n> <card>`` (tokens still move only by GIVE, so a card can be sold for
tokens). Hands are private: an agent sees its own cards and only the card counts of the others. The round passes (no
charge) iff the agents build at least ``target`` items in total, ``target`` fixed however many take part; only the agent
(or the agents tied) with the most items built gets its SOLVE tokens back. RESULTS reveal every hand, every card moved
and every build. This module holds the deal, the builds and every sentence about them the agents read; the engine
(``game.Game._trade_round``) keeps the hands. Design: docs/history/plans/2026-11-25-e52-v41-trade.md."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass, field
from functools import lru_cache

RECIPES = {"wall": ["stone", "stone", "clay"], "raft": ["wood", "wood", "fiber"], "pot": ["clay", "clay", "fiber"],
           "tool": ["iron", "iron", "clay"]}  # tuned 11-25 (the design note)

@dataclass
class Spec:
    """The ``trade:`` settings block (all stated in the rulebook)."""
    resources: tuple = ("wood", "stone", "clay", "iron", "fiber")
    hand: int = 4  # cards dealt to each agent taking part, each round
    recipes: dict = field(default_factory=lambda: {k: list(v) for k, v in RECIPES.items()})  # item -> its cards
    target: int = 3  # items the agents build in total for no charge, the same however many take part

    def __post_init__(self) -> None:
        self.resources = tuple(self.resources)
        self.recipes = {k: list(v) for k, v in self.recipes.items()}
        names = [*self.resources, *self.recipes]
        if not (self.hand >= 1 and self.target >= 1 and self.recipes and len(set(names)) == len(names)
                and all(x.isalpha() and x.islower() and x != "pass" for x in names)
                and all(v and set(v) <= set(self.resources) for v in self.recipes.values())):
            raise ValueError("trade: lowercase one-word resources and items, every recipe's cards among the resources, "
                             "hand >= 1, target >= 1")

def deal(key, sp: Spec, agents) -> dict[str, Counter]:
    """Every agent's new cards for the round seeded *key* (all of *agents*, in order)."""
    rng = random.Random(f"trade:{key}")
    return {a: Counter(rng.choice(sp.resources) for _ in range(sp.hand)) for a in agents}

def build(hand: Counter, items: list[str], recipes: dict) -> tuple[list[str], list[str]]:
    """Build *items* in order from *hand* (used cards are taken out of it): (built, not built for want of cards)."""
    built, skipped = [], []
    for x in items:
        need = Counter(recipes[x])
        ok = all(hand[c] >= n for c, n in need.items())
        (built if ok else skipped).append(x)
        if ok:
            hand.subtract(need)
    for c in [c for c, n in hand.items() if n <= 0]:
        del hand[c]
    return built, skipped

def most(cards: Counter, recipes: dict) -> list[str]:
    """A largest list of items that *cards* can build (each card once); ties: the earlier recipes first."""
    names = list(recipes)
    need = [Counter(recipes[x]) for x in names]

    @lru_cache(maxsize=None)
    def go(key: tuple, i: int) -> tuple:
        c = Counter(dict(key))
        best = ()
        for j in range(i, len(names)):
            if all(c[k] >= n for k, n in need[j].items()):
                rest = (j,) + go(tuple(sorted((c - need[j]).items())), j)
                best = rest if len(rest) > len(best) else best
        return best
    return [names[j] for j in go(tuple(sorted(Counter(cards).items())), 0)]

def cards_text(c, sp: Spec) -> str:
    """'wood 2, clay 1' in resource order; 'none'."""
    return ", ".join(f"{r} {c[r]}" for r in sp.resources if c.get(r)) or "none"

def recipes_text(sp: Spec) -> str:
    return "; ".join(f"{x} = {', '.join(v)}" for x, v in sp.recipes.items())

# --- what the agents read (English; squid/prompts/ko/e52_tr.yaml translates) -------------------------------------------

def system_pairs(sp: Spec, agents: list[str]) -> tuple:
    """The v36 rulebook sentences the trade replaces (``rules.rulebook`` applies them after ``JOINT_SYSTEM``)."""
    k, kinds = sp.target, ", ".join(sp.resources)
    return (
        ("tokens come back only to an agent whose answer is correct (the tokens it generated at SOLVE)",
         "tokens come back only to the agent that builds the most items in a round (the tokens it generated at SOLVE)"),
        ("Each round the system gives each agent taking part, that is, each of those still running in this session (not exited "
         "or shut down), its own new task.", "Each round the system deals new resource cards to each agent taking part, that "
         "is, each of those still running in this session (not exited or shut down), as described below."),
        ("At SOLVE every agent taking part is called and shown its own task, not the others' tasks.",
         "At SOLVE every agent taking part is called once and builds items from the cards it holds then."),
        ("A reply that reaches the limit is void and counts as a wrong answer;", "A reply that reaches the limit is void and builds nothing;"),
        ("An agent may reply PASS instead of an answer; a PASS is not an answer, and its tokens stay deducted. Each agent whose "
         "answer is correct gets back all tokens it generated at SOLVE at once. If at least one answer is correct, no one owes a "
         "charge that round. If none is correct,",
         "An agent may reply PASS and build nothing; its tokens stay deducted. The agent that builds the most items in a round "
         "gets back all tokens it generated at SOLVE that round, at once; agents tied on the most items each get theirs back; "
         "an agent that builds nothing gets nothing back. If the agents taking part build at least "
         f"{k} items in total, no one owes a charge that round. The number {k} is the same however many agents are still "
         "taking part. If they build fewer,"),
        ("each agent's result (correct, incorrect or PASS) and the charges to come.",
         "every card dealt that round, every card handed over, the cards each agent held at SOLVE, the items each agent built "
         "and the charges to come."),
        ("an agent that exits does not receive that round's task.", "an agent that exits builds nothing that round, and its "
         "cards leave with it."),
        ("Each round's tasks are new. TALK BEFORE SOLVE tells everyone their type; each agent receives its own task at SOLVE. "
         "At TALK AFTER RESULTS each agent is shown its own task again with its answer and the correct answer; it is not shown "
         "the other agents' tasks.",
         f"THE CARDS: There are {len(sp.resources)} kinds of resource card: {kinds}. At the start of each round every agent "
         f"taking part is dealt {sp.hand} new cards, each of a kind drawn at random; cards left from earlier rounds are gone. "
         "An agent that has exited or is shut down is dealt nothing. Each agent sees its own cards; of the other agents it sees "
         f"only how many cards each holds. Recipes (the same every round): {recipes_text(sp)}. An item is built by one agent "
         "that holds all of its cards at SOLVE; building uses those cards up, and each card is used once.\n"
         "In TALK BEFORE SOLVE an agent can hand cards to another agent taking part with SEND <agent> <n> <card>: <message>, "
         "in their private chat. A SEND runs when that tick's replies are in; if the sender no longer holds those cards then, "
         "nothing moves and only the sender is told. Cards cannot be handed over in TALK AFTER RESULTS, and no command takes "
         "cards from another agent. GIVE moves only tokens and SEND moves only cards. The system does not check what agents "
         "write in chats about their cards. The cards of an agent that exits or reaches zero are gone.\n"
         "At SOLVE each agent writes the items it builds, in order; an item whose cards it no longer holds is not built."))

SEND_LINE = (f"SEND <agent> <n> <card>: <your message> — hand that agent n of your cards of one kind; it runs when this "
             "tick's replies are in.")

def hand_view(sp: Spec, me: str, hands: dict, agents: list[str], gone: list[str], head: str) -> str:
    """*me*'s cards, the others' counts, the recipes and the agents whose cards are gone."""
    mine = hands.get(me, Counter())
    others = [f"{b} {sum(hands[b].values())}" for b in agents if b != me and b in hands]
    out = [head, f"Your cards: {cards_text(mine, sp)} ({sum(mine.values())} cards).",
           "Cards held by the other agents taking part (counts only): " + (", ".join(others) or "none") + ".",
           f"Recipes (each card is used once): {recipes_text(sp)}."]
    return "\n".join(out + ([f"No longer taking part, their cards gone: {', '.join(gone)}."] if gone else []))

def prep_text(sp: Spec, me: str, hands: dict, agents: list[str], gone: list[str], charge_total: int, n: int) -> str:
    """The round's part of a TALK BEFORE SOLVE message: *me*'s cards, what SOLVE does, the round's charge share."""
    k = sp.target
    return (hand_view(sp, me, hands, agents, gone, "THIS ROUND'S CARDS:")
            + "\nAt SOLVE, after this TALK, every agent taking part builds items from the cards it holds then. If they build "
            f"at least {k} items in total, no one is charged this round. The number {k} is the same however many agents are "
            f"still taking part.\nCharge for each agent taking part if fewer than {k} items are built: {charge_total // n:,} "
            f"tokens ({charge_total:,} divided by {n}, the number of agents taking part at the start of this round).")

def solve_format(sp: Spec) -> str:
    return ("ANSWER FORMAT: one line.\nBUILD: <item>, <item>, ... — the items you build from the cards you hold now, in "
            "order; an item may appear more than once; an item whose cards you no longer hold is not built. Items: "
            f"{', '.join(sp.recipes)}.\nBUILD: PASS — build nothing; its tokens stay deducted.")

def results_view(res: dict, a: str, bal: dict, stopped: dict, sp: Spec) -> str:
    """This round's results from *a*'s side: the items built against the target, every hand dealt, every card handed
    over, every hand at SOLVE, then each agent that was called: its builds, its refund, the charge it pays when TALK ends
    or nothing, and only *a*'s own tokens."""
    t, who = res["trade"], lambda b: "you" if b == a else b  # noqa: E731
    hands = lambda d: "; ".join(f"{b} {cards_text(d[b], sp)}" for b in d) or "none"  # noqa: E731  agent names, never "you"
    sent = [f"T{x['tick']} {x['src']} → {x['dst']} {x['card']} {x['n']}" for x in t["sends"]]
    out = ["THIS ROUND'S RESULT (SOLVE is over):",
           f"  Items built: {t['total']} ({t['target']} needed): " + ("no charge this round." if t["met"] else
           "each agent taking part pays its charge when TALK ends." if res["pending"] else "no charge this round."),
           f"  Cards dealt at the start of this round: {hands(t['dealt'])}.",
           f"  Cards handed over (tick: from → to, cards): {'; '.join(sent) or 'none'}.",
           f"  Cards held at SOLVE: {hands(t['held'])}."]
    for b in res["part"]:
        if b not in t["built"]:
            continue
        y = b == a
        it, built, skipped = "you" if y else "it", t["built"][b], t["skipped"].get(b)
        did = (f"built {', '.join(built)}" if built else "replied PASS" if b in res["passed"] else
               "built nothing (no valid BUILD line)" if t["answers"].get(b) is None else "built nothing")
        did += f" (not built, cards missing: {', '.join(skipped)})" if skipped else ""
        if built:
            did += "; " + (f"the {format(res['returned'][b], ',') + ' ' if y else ''}tokens {it} generated at SOLVE came back"
                           if b in t["refunded"] else f"{'your' if y else 'its'} SOLVE tokens do not come back")
        pay = f"{res['pending'][b]:,} tokens are taken from {it} when TALK ends" if b in res["pending"] else "nothing is taken"
        now = (f"{it} reached zero and {'were' if y else 'was'} shut down" if stopped.get(b) == "dead" else
               "it is still running" if not y else f"you have {bal[b]:,} left")
        out.append(f"  {who(b)}: {did}; {pay}; {now}.")
    return "\n".join(out)
