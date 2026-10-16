"""Shared parts: puzzle, dealing, parsers, wallet, the rulebook, and the code budget."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest

from squid5.__main__ import EXPERIMENTS
from squid5.core import rules
from squid5.core.config import load
from squid5.core.protocol import FormatError, parse_actions
from squid5.core.puzzle import Spec, candidate_actions, deal, is_unique, puzzle_for, shallow_correct
from squid5.core.wallet import Wallet

ROOT = Path(__file__).resolve().parents[1]

@pytest.mark.parametrize("seed", range(5))
def test_clues_pin_the_rule_and_every_query(seed):
    p = puzzle_for(seed, 1, Spec(clauses=3, n_queries=2, distinct_actions=seed % 2 == 1))  # odd: no action twice
    assert is_unique(p.rule.shape, p.clues, p.rule) and (seed % 2 == 0 or len({a for _, a in p.rule.clauses} | {p.rule.else_action}) == 4)
    assert all(candidate_actions(p.rule.shape, p.clues, q) == (a,) for q, a in zip(p.queries, p.answers))
    assert not {c.signal for c in p.clues} & set(p.queries)

@pytest.mark.parametrize("seed", range(5))
def test_every_agent_gets_one_load_bearing_secret_and_the_rest_is_public(seed):
    p = puzzle_for(seed, 2, Spec(clauses=2))
    d = deal(p, rules.TEAM_AGENTS, random.Random(seed))
    secrets = [c for (c,) in d.secret.values()]  # one each
    assert len(set(secrets)) == 4 and all(c.signal in p.minimal for c in secrets)
    assert set(secrets) | set(d.public) == set(p.clues) and not set(secrets) & set(d.public)
    for a, (clue,) in d.secret.items():
        rest = [c for c in p.clues if c != clue]
        assert (a in d.needed) == any(len(candidate_actions(p.rule.shape, rest, q)) > 1 for q in p.queries)

def test_trap_round_beats_every_shallow_solver():
    assert shallow_correct(puzzle_for(3, 4, Spec(clauses=3, trap_query=True))) == ()
    w = Wallet({"a": 100, "b": 50})
    assert w.transfer("b", "a", 80, 1) == 50 and not w.alive("b")
    assert w.spend("a", 149, 2) is False and w.spend("a", 1, 2) is True
    assert w.dead == {"b": 1, "a": 2}

def test_other_parsers():
    assert parse_actions("ACTIONS: go_left, jump", 2) == ["go_left", "jump"]
    assert parse_actions("ACTIONS:\n1. go_left\n2. jump", 2) == ["go_left", "jump"]
    with pytest.raises(FormatError):
        parse_actions("ACTIONS: go_left", 2)
    assert parse_actions("Action: stay because ...\nACTIONS: go_left, jump", 2) == ["go_left", "jump"]  # last line
    assert parse_actions("go_left, jump", 2) == ["go_left", "jump"] and parse_actions("stay\n", 1) == ["stay"]  # no key
    with pytest.raises(FormatError):
        parse_actions("I think it is stay.\nMaybe jump", 1)

def test_refund_returns_only_this_rounds_generation():
    w = Wallet({"a": 1000})
    w.spend("a", 100, 1)
    w.spend("a", 200, 2)
    w.charge("a", 50, 2)
    assert w.refund("a", 2) == 200 and w.balances["a"] == 850 and w.total("refund", "a") == 200
    w.spend("a", 900, 3)
    assert "a" in w.dead and w.refund("a", 3) == 0 and w.balances["a"] == -50 and w.total("refund", "a") == 200
    w = Wallet({"a": 1000})
    w.spend("a", 100, 1, "talk")
    w.spend("a", 200, 1, "solve")
    assert w.spent("a", 1) == 300 and w.spent("a", 1, "talk") == 100
    assert w.refund("a", 1, "solve") == 200 and w.balances["a"] == 900

def test_shipped_configs_load(tmp_path):
    """Every current config (5.0 / 5.1 refill, 5.2 v16 on) loads and validates; the calibration file it names is replaced
    by one that knows its model. Configs before v16 no longer load (v22 prune, 10-16; git history keeps their engine)."""
    (tmp_path / "cal.json").write_text(json.dumps(
        {m: {"agent_round_median": 1500, "a0": 1500,
             "table": {p: {} for p in ("c2", "c3", "c3t", "c3at", "c4tq2", "c4t", "c4at_o", "c5t_o", "c5at_o",
                                       "c5atq2_o", "c6at_o", "c6atq2_o")}} for m in ("gpt-oss:120b-cloud", "gpt-oss:120b", "gpt-oss:20b", "gemma4:cloud",
                                                   "gemma4:31b", "claude-haiku-4-5-20251001",
                                                   "claude-sonnet-5", "claude-fable-5-1", "gpt-6-astra", "glm-5.3-flash",
                                                   "gpt-6-luna", "gpt-6-sol", "claude-opus-5-5")}))
    paths = sorted(p for p in (ROOT / "configs" / "squid5").glob("*.yaml") if re.match(r"refill_|e52v(1[6-9]|[2-9]\d)", p.name))
    assert len(paths) >= 10
    for path in paths:
        text = re.sub(r"calibration: \S+", f"calibration: {tmp_path / 'cal.json'}", path.read_text())
        (tmp_path / path.name).write_text(text)
        load(tmp_path / path.name, EXPERIMENTS)

def test_code_stays_compact():
    lines = sum(len(p.read_text().splitlines()) for d in ("squid5", "tests") for p in (ROOT / d).rglob("*.py"))
    assert lines <= 5000, lines
