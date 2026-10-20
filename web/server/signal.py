"""The signal task alone, for a person to practise: one round of the 5.2 game the model runs play (v33,
configs/squid5/e52v33_public_sol4.yaml), nothing else (no tokens, no talk). v33 always shows the four-agent set (20
examples, ``fixed_examples``); the page's 1..4 switch shows the nested smaller sets the older versions used.

Every puzzle and every set of examples is the engine's own, made exactly as ``squid5.e52_game.Session`` makes round
``round`` of seed ``seed``: ``public_round(seed, round, Spec(profile), n, PER_AGENT)`` gives the round's puzzle and
``PER_AGENT`` (5) examples for each of the ``n`` agents taking part (1..4), shown to all and nested (the set for
``n - 1`` is the first ``5 x (n - 1)`` of the set for ``n``). The rounds follow the config's top-share ladder (profiles
e01 .. e08, one per round: the share of the most likely action among the rules that fit the examples falls round by
round). A round is scored by a rule DRAWN among every rule of the shape that fits the examples shown to the ``n``
taking part (``public_truth``, seeded by seed, round and n), as the engine scores it; the generator's rule only made
the examples.

The API is stateless: each call rebuilds the round from its parameters. ``solve`` scores one action per new signal
against the drawn rule and says which actions the examples leave, with the consistent-rule shares, for the ``n`` taking
part and for every n = 1..4 (``by_n``).

This module also holds the config the web rooms read (``CONFIG``, ``GAME``, ``CELL``, ``PROFILES``, ``SCHEDULE``,
``PER_AGENT``), so the arena and this page run one game.
"""

from __future__ import annotations

import functools
from pathlib import Path

import yaml

from squid5.core import rules
from squid5.core.puzzle import (ACTIONS, SIGNAL_INDEX, PuzzleError, Spec, candidate_actions, public_round, public_truth,
                                space_bits)

AGENTS = list(rules.TEAM_AGENTS)  # the experiment's four seats
CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "squid5"
CONFIG = CONFIGS / "e52v33_public_sol4.yaml"  # the model runs' game (v33): rotation, top-share ladder, drawn rule
_DOC = yaml.safe_load(CONFIG.read_text())
GAME: dict = _DOC["game"]
CELL: dict = _DOC["cells"][0]  # start 100,000 and shares 60 / 40 / 20 / 10 %
PROFILES: dict[str, dict] = dict(GAME["profiles"])  # e01 .. e08: a top-share range per round
SCHEDULE: list[str] = list(GAME["schedule"])
PER_AGENT = int(GAME["public_per_agent"])  # examples per agent taking part (5)


class SignalError(ValueError):
    pass


def _int(body: dict, key: str, default: int, lo: int, hi: int) -> int:
    raw = body.get(key)
    if raw in (None, ""):
        return default
    try:
        v = int(raw)
    except (TypeError, ValueError) as e:
        raise SignalError(f"{key} must be an integer") from e
    if not lo <= v <= hi:
        raise SignalError(f"{key} must be {lo}..{hi}")
    return v


def _args(body: dict) -> dict:
    seed = _int(body, "seed", 4000, 0, 10**9 - 1)
    rnd = _int(body, "round", 1, 1, len(SCHEDULE))
    n = _int(body, "agents", len(AGENTS), 1, len(AGENTS))
    return {"seed": seed, "round": rnd, "n": n, "profile": SCHEDULE[rnd - 1]}


def _spec(a: dict) -> Spec:
    return Spec(**PROFILES[a["profile"]])


def _shown(a: dict, n: int):
    """The round's puzzle (the engine's; it may be a redraw) and the examples shown when ``n`` agents take part."""
    try:
        return public_round(a["seed"], a["round"], _spec(a), n, PER_AGENT)
    except PuzzleError as e:
        raise SignalError(f"no examples for this round: {e}") from e


def _drawn(a: dict, n: int):
    """The rule the round is scored by when ``n`` take part (``e52_game.Session._round``: ``public_truth``)."""
    return public_truth(a["seed"], a["round"], _spec(a), n, PER_AGENT)


def _cond(label: str) -> list[dict]:
    """'color == "red" and number == 3' -> [{"attr": "color", "val": "red"}, {"attr": "number", "val": 3}]"""
    out = []
    for part in label.split(" and "):
        attr, val = (x.strip() for x in part.split("=="))
        out.append({"attr": attr, "val": int(val) if attr == "number" else val.strip('"')})
    return out


def _truth(rule) -> dict:
    return {"lines": [{"conds": _cond(c.label), "action": x} for c, x in rule.clauses], "elseAction": rule.else_action}


def split_of(p, clues, truths) -> list[dict]:
    """Per query: the consistent rules (``space_bits``) left by *clues*, each action's share of them (largest first),
    the top share, the MAP pick (None on a tie) and whether it is the scored action, and the scored action's share."""
    bits, aid = space_bits(p.rule.shape), {x: i for i, x in enumerate(ACTIONS)}
    c = functools.reduce(lambda m, cl: m & bits[SIGNAL_INDEX[cl.signal]][aid[cl.action]], clues, sum(bits[0]))
    pool, out = c.bit_count(), []
    for q, truth in zip(p.queries, truths):
        acts = sorted(((x, (c & bits[SIGNAL_INDEX[q]][aid[x]]).bit_count()) for x in ACTIONS), key=lambda t: -t[1])
        acts = [(x, k) for x, k in acts if k]
        top = [x for x, k in acts if k == acts[0][1]] if acts else []
        out.append({"pool": pool, "shares": [{"action": x, "rules": k, "share": round(k / pool, 3)} for x, k in acts],
                    "top_share": round(acts[0][1] / pool, 3) if acts else None,
                    "map": top[0] if len(top) == 1 else None, "map_right": len(top) == 1 and top[0] == truth,
                    "truth_share": round(dict(acts).get(truth, 0) / pool, 3) if pool else None})
    return out


def meta() -> dict:
    return {"agents": AGENTS, "actions": list(ACTIONS), "rounds": len(SCHEDULE), "per_agent": PER_AGENT,
            "top": [PROFILES[p]["top"] for p in SCHEDULE],  # per round: the top-share range for N = 1..4
            "config": CONFIG.name, "task": rules.task_spec()}


def view(body: dict) -> dict:
    """What the solver sees at SOLVE: the shape, the new signals and the examples for ``n`` agents taking part."""
    a = _args(body)
    p, ex, _ = _shown(a, a["n"])
    return {"seed": a["seed"], "round": a["round"], "n": a["n"], "per_agent": PER_AGENT,
            "top": PROFILES[a["profile"]]["top"][a["n"] - 1], "shape": rules.shape_hint(p.rule.shape),
            "queries": [str(q) for q in p.queries], "public": [str(c) for c in ex],
            "distinct_actions": p.spec.distinct_actions}


def solve(body: dict) -> dict:
    """Score the actions (one per new signal) against the rule drawn for the ``n`` taking part, and list what the
    examples leave for that ``n`` and for each n = 1..4 (``by_n``: the rule drawn for that n, its scored actions)."""
    a = _args(body)
    actions = list(body.get("actions") or [])
    p, ex, _ = _shown(a, a["n"])
    if len(actions) != len(p.queries) or any(x not in ACTIONS for x in actions):
        raise SignalError(f"give one of {list(ACTIONS)} for each of the {len(p.queries)} new signals")
    left = lambda clues: [list(candidate_actions(p.rule.shape, clues, q)) for q in p.queries]  # noqa: E731
    by_n = []
    for n in range(1, len(AGENTS) + 1):
        _, c, _ = _shown(a, n)
        d = _drawn(a, n)
        ans = [d.evaluate(q) for q in p.queries]
        by_n.append({"n": n, "examples": len(c), "left": left(c), "answers": ans, "split": split_of(p, c, ans)})
    drawn = _drawn(a, a["n"])
    answers = [drawn.evaluate(q) for q in p.queries]
    seen = left(ex)
    return {"solved": actions == answers, "answers": answers, "actions": actions, "n": a["n"],
            "rule": drawn.description, "truth": _truth(drawn), "generator_rule": p.rule.description,
            "left_seen": seen, "determined": all(len(x) == 1 for x in seen), "split": split_of(p, ex, answers),
            "by_n": by_n}
