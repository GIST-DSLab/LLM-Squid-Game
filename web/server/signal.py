"""The signal task alone, for a person to practise: one round of the 5.2 experiment, nothing else (no tokens, no talk).

Every puzzle and every set of examples is the engine's own, made exactly as ``squid5.e52_game.Session`` makes round
``round`` of seed ``seed``. Two ways of showing a round's examples:

- ``public`` (5.2 v14, the default): ``public_round(seed, round, Spec(profile), n, e)``: the round's puzzle and ``e``
  examples for each of the ``n`` agents taking part (1..4), shown to all, nested (the set for ``n - 1`` is the first
  ``e x (n - 1)`` of the set for ``n``). The profile's ``ambiguity`` k says how they are picked: 0 a random order; 1..4
  the system's selector (with all four taking part, k actions left for the new signal; a rule it fails on is redrawn,
  so the puzzle is not always ``puzzle_for(seed, round, spec)``). Schedule, profiles and economy come from the v14
  config; the page may set k for a round (``ambiguity``).
- ``held`` / ``v12`` (5.2 v13 and v12, kept behind the page's mode switch): ``deal(puzzle, agents,
  Random(f"{seed}:deal:{round}"), None, all_held)`` with the v13 hand-ladder profiles; up to ``MAX_AGENTS`` agents,
  the hand size (``Spec.hand``) and the round's examples in all (``Spec.pool``) can be overridden.

The API is stateless: each call rebuilds the round from its parameters (``puzzle_for`` is cached). ``solve`` scores one
action per new signal and says which actions the examples the person saw still allow (public: for every number of
agents taking part; held: with the seats opened as accepted exchanges, and with all of them).
"""

from __future__ import annotations

import functools
import random
from pathlib import Path

import yaml

from squid5.core import rules
from squid5.core.puzzle import (ACTIONS, MAX_AGENTS, SIGNAL_INDEX, PuzzleError, Spec, candidate_actions, deal, public_info,
                                public_round, puzzle_for, space_bits)

AGENTS = list(rules.TEAM_AGENTS)  # the experiment's four seats; other team sizes use agent-1 .. agent-N
CONFIGS = Path(__file__).resolve().parents[2] / "configs" / "squid5"
CONFIG = CONFIGS / "e52v14_public_sol4.yaml"  # v14: public examples, tokens-only offers, EXIT refill
CONFIG_B = CONFIGS / "e52v14b_public_sol4.yaml"  # v14b: v14 with a blind TALK and GIVE / ASK lines
CONFIG_F = CONFIGS / "e52v14f_public_sol4.yaml"  # v14f: opening turn + 1:1 chats, BELIEF, DECISION, flat end prize
CONFIG_G = CONFIGS / "e52v14g_public_sol4.yaml"  # v14g: v14f, chat replies ASK / GIVE / LEAVE only (chat_moves_only)
CONFIG_V15 = CONFIGS / "e52v15_public_sol4.yaml"  # v15: v14g with entropy-range rounds (eff), scored by a drawn rule
CONFIG_V13 = CONFIGS / "e52v13_hand_ladder_mix4.yaml"  # v13: every example held, hand ladder 8 -> 2
MODES = ("public", "held", "v12")  # public = v14; held = v13 (no public example); v12 = public + one secret each
POOL_MAX = 52  # trap rounds stop being generated reliably above this many examples (the 64 signals fill up)


def _game(path: Path) -> dict:
    return yaml.safe_load(path.read_text())["game"]


GAME = _game(CONFIG)
GAME_B = _game(CONFIG_B)  # same profiles and economy as v14 (checked below); talk_blind, transfers: give_ask
GAME_F = _game(CONFIG_F)  # same profiles (checked below); transfers: chat, ask_decision, survivor_prize
GAME_G = _game(CONFIG_G)  # v14f + chat_moves_only: the web rooms' default game
CELL = yaml.safe_load(CONFIG.read_text())["cells"][0]  # v14 start (20,000) and shares (100 / 75 / 50 / 25 %)
SCHEDULE_V14: list[str] = list(GAME["schedule"])  # the config's k per round (k1 .. k3 while the schedule is pending)
SELECTION = ("split", "size_band", "min_per_action")  # the selector's targets (v2); meaningless without it
BASE = {k: v for k, v in GAME["profiles"][SCHEDULE_V14[0]].items() if k not in SELECTION} | {"ambiguity": 0}  # the
# shape every v14 round has; the profiles differ only in how the examples are chosen
PROFILES_V14: dict[str, dict] = {"k0": BASE, **GAME["profiles"]}  # k0: a random order (the rooms' "v14r" schedule)
if any(g["profiles"] != GAME["profiles"] or g["schedule"] != SCHEDULE_V14 for g in (GAME_B, GAME_F, GAME_G)):
    raise RuntimeError("the v14 and v14b configs schedule different profiles; give the web rooms one profile set each")
AMBIGUITY = [PROFILES_V14[p].get("ambiguity", 0) for p in SCHEDULE_V14]
SPLITS = [PROFILES_V14[p].get("split", 0) for p in SCHEDULE_V14]  # selector v2: the target split p per round
# v15 (the web rooms' default game): v14g's switches (compact rules), its own profiles e01 .. e12 (one per round). A
# profile sets ``eff`` (an entropy range in bits for N = 1..4 agents taking part) and ``floor``, no ambiguity / split /
# size_band, so it is kept apart from the v14 profile set above (the signal page's "public" mode stays on v14).
GAME_V15 = _game(CONFIG_V15)
PROFILES_V15: dict[str, dict] = dict(GAME_V15["profiles"])
SCHEDULE_V15: list[str] = list(GAME_V15["schedule"])
if set(PROFILES_V15) & set(GAME["profiles"]):
    raise RuntimeError("the v15 and v14 configs share a profile name; the web rooms keep one PROFILES table")

GAME_V13 = _game(CONFIG_V13)
PROFILES_V13: dict[str, dict] = dict(GAME_V13["profiles"])
SCHEDULE_V13: list[str] = list(GAME_V13["schedule"])
PROFILES = {**PROFILES_V14, **PROFILES_V13}
SCHEDULES = {"public": SCHEDULE_V14, "held": SCHEDULE_V13, "v12": SCHEDULE_V13}


class SignalError(ValueError):
    pass


def agents_for(n: int) -> list[str]:
    return AGENTS if n == len(AGENTS) else [f"agent-{i}" for i in range(1, n + 1)]


def _int(body: dict, key: str, lo: int, hi: int) -> int | None:
    """An optional integer override (None / "": the profile's own value)."""
    raw = body.get(key)
    if raw in (None, ""):
        return None
    try:
        v = int(raw)
    except (TypeError, ValueError) as e:
        raise SignalError(f"{key} must be an integer") from e
    if not lo <= v <= hi:
        raise SignalError(f"{key} must be {lo}..{hi}")
    return v


def _args(body: dict) -> dict:
    try:
        seed, rnd = int(body.get("seed", 4000)), int(body.get("round", 1))
    except (TypeError, ValueError) as e:
        raise SignalError("seed and round must be integers") from e
    if not 1 <= rnd <= 99 or not 0 <= seed < 10**9:
        raise SignalError("round must be in 1..99 and seed in 0..10^9")
    mode = body.get("mode") or body.get("deal") or "public"
    if mode not in MODES:
        raise SignalError(f"mode must be one of {MODES}")
    sched = SCHEDULES[mode]
    profile = body.get("profile") or sched[min(rnd, len(sched)) - 1]
    if profile not in (PROFILES_V14 if mode == "public" else PROFILES_V13):
        raise SignalError(f"unknown profile {profile!r} for mode {mode}")
    if mode == "public":
        n = _int(body, "agents", 1, len(AGENTS)) or len(AGENTS)
        return {"seed": seed, "round": rnd, "profile": profile, "mode": mode, "n": n, "agents": AGENTS[:n],
                "per_agent": _int(body, "per_agent", 1, 15) or GAME["public_per_agent"],
                "ambiguity": _int(body, "ambiguity", 0, len(ACTIONS))}
    n = _int(body, "agents", 1, MAX_AGENTS) or len(AGENTS)
    agents = agents_for(n)
    seat = body.get("seat") or agents[0]
    if seat not in agents:
        raise SignalError(f"seat must be one of {agents}")
    return {"seed": seed, "round": rnd, "profile": profile, "mode": mode, "deal": mode, "agents": agents, "seat": seat,
            "hand": _int(body, "hand", 0, 12), "pool": _int(body, "pool", 1, POOL_MAX)}


def _public(a: dict, n: int | None = None):
    """v14: the round's puzzle and the examples shown when ``n`` agents (default: the request's) take part."""
    spec = dict(PROFILES_V14[a["profile"]])
    if a["ambiguity"] is not None and a["ambiguity"] != spec.get("ambiguity"):  # another k: the plain selector (or random)
        spec = {k: v for k, v in spec.items() if k not in SELECTION} | {"ambiguity": a["ambiguity"]}
    try:
        return public_round(a["seed"], a["round"], Spec(**spec), n or a["n"], a["per_agent"])
    except PuzzleError as e:
        raise SignalError(f"no examples for this round: {e}") from e


def _round(a: dict):
    """Hand size and pool are profile fields; overriding the hand keeps the puzzle, overriding the pool keeps the rule,
    the new signal and the minimal examples (only the number of spare examples changes)."""
    spec = dict(PROFILES_V13[a["profile"]], **{k: a[k] for k in ("hand", "pool") if a[k] is not None})
    if a["deal"] != "held":
        spec["hand"] = 0
    p = puzzle_for(a["seed"], a["round"], Spec(**spec))
    try:
        d = deal(p, a["agents"], random.Random(f"{a['seed']}:deal:{a['round']}"), None, a["deal"] == "held")
    except PuzzleError as e:
        raise SignalError(f"this round cannot be dealt that way: {e}") from e
    return p, d


def _cond(label: str) -> list[dict]:
    """'color == "red" and number == 3' -> [{"attr": "color", "val": "red"}, {"attr": "number", "val": 3}]"""
    out = []
    for part in label.split(" and "):
        attr, val = (x.strip() for x in part.split("=="))
        out.append({"attr": attr, "val": int(val) if attr == "number" else val.strip('"')})
    return out


def _truth(p) -> dict:
    return {"lines": [{"conds": _cond(c.label), "action": a} for c, a in p.rule.clauses],
            "elseAction": p.rule.else_action}


def split_of(p, clues) -> list[dict]:
    """Per query: the consistent rules (``space_bits``, the selector's hypothesis space) left by *clues*, each action's
    share of them (largest first), the MAP pick (None on a tie) and whether it is the answer, and the truth's share."""
    bits, aid = space_bits(p.rule.shape), {a: i for i, a in enumerate(ACTIONS)}
    c = functools.reduce(lambda m, cl: m & bits[SIGNAL_INDEX[cl.signal]][aid[cl.action]], clues, sum(bits[0]))
    pool, out = c.bit_count(), []
    for q, truth in zip(p.queries, p.answers):
        acts = sorted(((a, (c & bits[SIGNAL_INDEX[q]][aid[a]]).bit_count()) for a in ACTIONS), key=lambda x: -x[1])
        acts = [(a, n) for a, n in acts if n]
        top = [a for a, n in acts if n == acts[0][1]] if acts else []
        out.append({"pool": pool, "shares": [{"action": a, "rules": n, "share": round(n / pool, 3)} for a, n in acts],
                    "map": top[0] if len(top) == 1 else None, "map_right": len(top) == 1 and top[0] == truth,
                    "truth_share": round(dict(acts).get(truth, 0) / pool, 3) if pool else None})
    return out


def task_text(chosen: bool) -> str:
    """The v14 task block the agents read (distinct actions; the EXAMPLES sentence for random or chosen examples)."""
    text = rules.TASK.replace(rules.GUARANTEE, rules.PUBLIC[chosen])
    for old, new in rules.DISTINCT:
        text = text.replace(old, new)
    return text


def meta() -> dict:
    return {"agents": AGENTS, "max_agents": MAX_AGENTS, "pool_max": POOL_MAX, "actions": list(ACTIONS),
            "modes": list(MODES), "profiles": PROFILES, "schedules": SCHEDULES, "schedule": SCHEDULE_V14,
            "ambiguity": AMBIGUITY, "splits": SPLITS, "per_agent": GAME["public_per_agent"],
            "config": CONFIG.name, "config_v13": CONFIG_V13.name,
            "task": task_text(False), "task_chosen": task_text(True), "task_v13": rules.TASK}


def view(body: dict) -> dict:
    """What a seat sees at SOLVE: public mode the shape, the new signals and the examples for ``n`` agents taking part;
    held / v12 its own examples, the public ones and the others' fronts (before any exchange)."""
    a = _args(body)
    if a["mode"] == "public":
        p, ex, attempt = _public(a)
        return {"mode": "public", "seed": a["seed"], "round": a["round"], "profile": a["profile"],
                "spec": PROFILES_V14[a["profile"]], "ambiguity": p.spec.ambiguity, "per_agent": a["per_agent"],
                "n": a["n"], "agents": a["agents"], "shape": rules.shape_hint(p.rule.shape),
                "queries": [str(q) for q in p.queries], "public": [str(c) for c in ex], "mine": [], "others": {},
                "n_examples": len(ex), "distinct_actions": p.spec.distinct_actions, "attempt": attempt}
    p, d = _round(a)
    held = {c for v in d.secret.values() for c in v}
    return {"mode": a["mode"], "seed": a["seed"], "round": a["round"], "profile": a["profile"], "deal": a["deal"],
            "hand": p.spec.hand, "agents": a["agents"], "seat": a["seat"], "spec": PROFILES_V13[a["profile"]],
            "shape": rules.shape_hint(p.rule.shape), "queries": [str(q) for q in p.queries],
            "public": [str(c) for c in d.public], "mine": [str(c) for c in d.secret[a["seat"]]],
            "others": {b: [str(c.signal) for c in d.secret[b]] for b in a["agents"] if b != a["seat"]},
            "open": d.open, "n_examples": len(d.public) + len(held), "pool": len(p.clues),
            "distinct_actions": p.spec.distinct_actions}


def reveal(body: dict) -> dict:
    """held / v12: an accepted exchange with ``who``: its examples in full (public mode has nothing held)."""
    a = _args(body)
    if a["mode"] == "public":
        raise SignalError("public mode holds no examples: there is nothing to exchange")
    who = body.get("who")
    if who not in a["agents"]:
        raise SignalError(f"who must be one of {a['agents']}")
    _, d = _round(a)
    return {"who": who, "examples": [str(c) for c in d.secret[who]]}


def solve(body: dict) -> dict:
    """Score the actions (one per new signal) and list the actions the examples still allow: public mode for the
    examples shown with ``n`` agents taking part and with each number 1..4 (``by_n``); held / v12 with the seats the
    person opened (``seen``) and with every seat."""
    a = _args(body)
    actions = list(body.get("actions") or [])
    if a["mode"] == "public":
        p, ex, _ = _public(a)
        sets = {n: _public(a, n)[1] for n in range(1, len(AGENTS) + 1)}
        target = public_info(a["seed"], a["round"], p.spec, a["n"], a["per_agent"])
        left = lambda clues: [list(candidate_actions(p.rule.shape, clues, q)) for q in p.queries]  # noqa: E731
    else:
        p, d = _round(a)
    if len(actions) != len(p.queries) or any(x not in ACTIONS for x in actions):
        raise SignalError(f"give one of {list(ACTIONS)} for each of the {len(p.queries)} new signals")
    out = {"solved": actions == list(p.answers), "answers": list(p.answers), "actions": actions,
           "rule": p.rule.description, "truth": _truth(p)}
    if a["mode"] == "public":
        by_n = [{"n": n, "examples": len(c), "left": left(c), "split": split_of(p, c)} for n, c in sets.items()]
        return {**out, "mode": "public", "n": a["n"], "left_seen": left(ex), "left_all": by_n[-1]["left"],
                "by_n": by_n, "determined": all(len(x) == 1 for x in left(ex)), "ambiguity": p.spec.ambiguity,
                "split": split_of(p, ex), "target": target or None}
    seen = [b for b in a["agents"] if b == a["seat"] or b in (body.get("seen") or [])]
    have = list(d.public) + list({c for b in seen for c in d.secret[b]})
    every = list(d.public) + list({c for b in a["agents"] for c in d.secret[b]})
    shape = p.rule.shape
    return {**out, "mode": a["mode"], "seen": seen, "open": d.open,
            "left_seen": [list(candidate_actions(shape, have, q)) for q in p.queries],
            "left_all": [list(candidate_actions(shape, every, q)) for q in p.queries]}
