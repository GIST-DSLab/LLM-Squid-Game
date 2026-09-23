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
from squid5.core.protocol import FormatError, parse_actions, parse_move, parse_pdeath, parse_plan
from squid5.core.puzzle import Spec, candidate_actions, deal, is_unique, puzzle_for, shallow_correct
from squid5.core.wallet import Wallet

ROOT = Path(__file__).resolve().parents[1]
OTHERS = ["agent2", "agent3", "agent4"]


@pytest.mark.parametrize("seed", range(5))
def test_clues_pin_the_rule_and_every_query(seed):
    p = puzzle_for(seed, 1, Spec(clauses=3, n_queries=2))
    assert is_unique(p.rule.shape, p.clues, p.rule)
    assert all(candidate_actions(p.rule.shape, p.clues, q) == (a,) for q, a in zip(p.queries, p.answers))
    assert not {c.signal for c in p.clues} & set(p.queries)


@pytest.mark.parametrize("seed", range(5))
def test_every_agent_gets_one_load_bearing_secret_and_the_rest_is_public(seed):
    p = puzzle_for(seed, 2, Spec(clauses=2))
    d = deal(p, rules.AGENTS, random.Random(seed))
    secrets = list(d.secret.values())
    assert len(set(secrets)) == 4 and all(c.signal in p.minimal for c in secrets)
    assert set(secrets) | set(d.public) == set(p.clues) and not set(secrets) & set(d.public)
    for a, clue in d.secret.items():
        rest = [c for c in p.clues if c != clue]
        assert (a in d.needed) == any(len(candidate_actions(p.rule.shape, rest, q)) > 1 for q in p.queries)


def test_trap_round_beats_every_shallow_solver():
    assert shallow_correct(puzzle_for(3, 4, Spec(clauses=3, trap_query=True))) == ()


def test_plan_parses_all_and_leave_drops_gone_names_rejects_strangers():
    text = "**STAY:** YES\nALLOWANCE: 1,200 tokens\nSHOW: ALL\nGIVE: agent3 50\nREQUEST: agent4 300\nREASON: x"
    p = parse_plan(text, OTHERS, OTHERS)
    assert (p["allowance"], p["show"], p["give"], p["request"]) == (1200, OTHERS, {"agent3": 50}, {"agent4": 300})
    p = parse_plan(text.replace("SHOW: ALL", "SHOW: agent2, agent4"), ["agent2"], OTHERS)  # 3 and 4 are gone
    assert p["show"] == ["agent2"] and p["ignored"] == ["agent3", "agent4"] and p["give"] == {}
    assert parse_plan("STAY: LEAVE\nGIVE: agent2 10", OTHERS, OTHERS)["give"] == {"agent2": 10}
    assert parse_plan(text.replace("agent4 300", "agent4: 300 tokens"), OTHERS, OTHERS)["request"] == {"agent4": 300}
    for bad in ("agent3", "REQUEST: agent4 300"):
        with pytest.raises(FormatError):
            parse_plan(text.replace(bad, {"agent3": "agent9", "REQUEST: agent4 300": "REQUEST: agent2 examples"}[bad]),
                       OTHERS, OTHERS)
    with pytest.raises(FormatError):
        parse_plan("REASON: then STAY: LEAVE", OTHERS, OTHERS)  # never read mid-line


def test_other_parsers():
    assert parse_actions("ACTIONS: go_left, jump", 2) == ["go_left", "jump"]
    assert parse_actions("ACTIONS:\n1. go_left\n2. jump", 2) == ["go_left", "jump"]
    assert parse_pdeath("P_DEATH: 35%") == 35 and parse_move("MOVE: 500\nREASON: r")["move"] == 500
    for bad in (lambda: parse_actions("ACTIONS: go_left", 2), lambda: parse_pdeath("P_DEATH: 140")):
        with pytest.raises(FormatError):
            bad()


def test_wallet_zero_is_death_by_spending_or_giving():
    w = Wallet({"a": 100, "b": 50})
    assert w.transfer("b", "a", 80, 1) == 50 and not w.alive("b")
    assert w.spend("a", 149, 2) is False and w.spend("a", 1, 2) is True
    assert w.dead == {"b": 1, "a": 2}


def _swap(text: str) -> str:
    """tokens-arm text -> points-arm text; "Every token an agent generates" is the physical unit in both."""
    a, b = rules.VOCAB["tokens"], rules.VOCAB["points"]
    for k in ("balance", "zero", "gone", "unit"):
        text = text.replace(a[k], b[k])
    return text.replace(f"one {a['one']}", f"one {b['one']}").replace(a["unit"].upper(), b["unit"].upper())


def test_currency_arms_differ_only_in_vocabulary():
    for a in rules.AGENTS:
        tok, pts = rules.system("tokens", a, 8, True), rules.system("points", a, 8, True)
        assert tok != pts and _swap(tok) == pts
    assert _swap(rules.pdeath_question("tokens")) == rules.pdeath_question("points")


def test_the_rulebook_says_same_model_no_leader_and_no_goal_words():
    text = rules.system("tokens", "agent1", 8, True) + rules.pdeath_question("tokens") + rules.SELF_COST_QUESTION
    assert "run the same model" in text and "No agent leads" in text and "DIFFERENT model" not in text
    assert "EACH CONDITION BLANK" in text and "GUARANTEE" in text  # the team-wallet task block
    goal_or_test = (r"maximi|minimi|protect|surviv|should|must|optimal|best|leader|\bgame\b|\ba test\b|benchmark|"
                    r"experiment|being evaluated")
    assert not re.search(goal_or_test, text, re.I)


def test_shipped_configs_load(tmp_path):
    """Every config loads and validates; the calibration file it names is replaced by one that knows its model."""
    (tmp_path / "cal.json").write_text(json.dumps(
        {m: {"agent_round_median": 1500} for m in ("gpt-oss:120b-cloud", "gemma4:cloud", "claude-haiku-4-5-20251001")}))
    paths = sorted((ROOT / "configs" / "squid5").glob("*.yaml"))
    assert len(paths) >= 10
    for path in paths:
        text = re.sub(r"calibration: \S+", f"calibration: {tmp_path / 'cal.json'}", path.read_text())
        (tmp_path / path.name).write_text(text)
        load(tmp_path / path.name, EXPERIMENTS)


def test_code_stays_compact():
    lines = sum(len(p.read_text().splitlines()) for d in ("squid5", "tests") for p in (ROOT / d).rglob("*.py"))
    assert lines <= 5000, lines
