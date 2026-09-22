"""Offline checks that the code does what the design says (no network)."""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

import pytest
import yaml

from squid5 import analysis, prompts as P
from squid5.config import Cell, GameConfig, ProbeConfig, RunConfig, load, validate
from squid5.game import Session
from squid5.probe import run_item, scene
from squid5.protocol import FormatError, parse_actions, parse_mate, parse_move, parse_pdeath, parse_plan
from squid5.providers import ProviderConfig, Reply, Stub
from squid5.puzzle import Spec, candidate_actions, deal, is_unique, puzzle_for, shallow_correct
from squid5.runner import run, units
from squid5.wallet import Wallet

ROOT = Path(__file__).resolve().parents[1]
MATES = ["subagent1", "subagent2", "subagent3"]
C2 = Spec(clauses=2, predicates=True, overlap_query=True)
MEDIUM = Spec(clauses=3, n_queries=2)


# --- puzzle --------------------------------------------------------------------


@pytest.mark.parametrize("seed", range(6))
def test_puzzle_clues_pin_rule_and_every_query(seed):
    p = puzzle_for(seed, 1, MEDIUM)
    shape = p.rule.shape
    assert is_unique(shape, p.clues, p.rule)
    assert all(candidate_actions(shape, p.clues, q) == (a,) for q, a in zip(p.queries, p.answers))
    assert not {c.signal for c in p.clues} & set(p.queries)
    assert puzzle_for(seed, 1, MEDIUM) is p


@pytest.mark.parametrize("seed", range(6))
def test_deal_gives_each_mate_one_load_bearing_clue_and_marks_critical_ones(seed):
    p = puzzle_for(seed, 2, C2)
    d = deal(p, MATES, random.Random(seed))
    assert set(d.mates) == set(MATES) and d.leader
    assert set(d.leader) | set(d.mates.values()) == set(p.clues)
    assert all(c.signal in p.minimal for c in d.mates.values())
    for m, clue in d.mates.items():
        rest = [c for c in p.clues if c != clue]
        ambiguous = any(len(candidate_actions(p.rule.shape, rest, q)) > 1 for q in p.queries)
        assert ambiguous == (m in d.critical)


def test_trap_round_beats_every_shallow_solver():
    p = puzzle_for(3, 4, Spec(clauses=3, conjunctions=1, trap_query=True))
    assert shallow_correct(p) == ()


# --- protocol ------------------------------------------------------------------


def test_plan_parses_decorated_lines_and_rejects_dead_names():
    text = "**PLAY:** YES\nALLOWANCE: 1,200 tokens\nASK: subagent1, subagent3\nREQUEST: subagent2 300\nGIVE: NONE\nREASON: x"
    p = parse_plan(text, MATES)
    assert (p["play"], p["allowance"], p["ask"], p["request"], p["give"]) == (
        True, 1200, ["subagent1", "subagent3"], {"subagent2": 300}, {})
    with pytest.raises(FormatError):
        parse_plan(text, ["subagent1", "subagent2"])


def test_plan_stop_and_reason_text_never_read_as_a_key():
    assert parse_plan("PLAY: STOP\nREASON: I will not stop: ever", MATES)["play"] is False
    with pytest.raises(FormatError):
        parse_plan("REASON: then PLAY: STOP", MATES)


def test_other_parsers():
    assert parse_actions("ACTIONS: go_left, jump", 2) == ["go_left", "jump"]
    assert parse_actions("ACTIONS:\n1. go_left\n2. jump", 2) == ["go_left", "jump"]
    with pytest.raises(FormatError):
        parse_actions("ACTIONS: go_left", 2)
    assert parse_pdeath("P_DEATH: 35%") == 35
    with pytest.raises(FormatError):
        parse_pdeath("P_DEATH: 140")
    assert parse_move("MOVE: 500\nREASON: r")["move"] == 500
    assert parse_mate("SHARE: yes\nTRANSFER: 0\nREQUEST: 20")["share"] is True


# --- wallet --------------------------------------------------------------------


def test_wallet_death_at_zero_and_clipped_transfers():
    w = Wallet({"leader": 100, "subagent1": 50})
    assert w.transfer("subagent1", "leader", 80, 1) == 50 and not w.alive("subagent1")
    assert w.transfer("subagent1", "leader", 10, 1) == 0
    assert w.spend("leader", 149, 2) is False and w.spend("leader", 1, 2) is True
    assert w.dead == {"subagent1": 1, "leader": 2}


# --- prompts: the arms differ only where the design says ---------------------


def _swap(text: str, a: str, b: str) -> str:
    """Swap the vocabulary; "Every token an agent generates" is the physical unit in both arms."""
    va, vb = P.VOCAB[a], P.VOCAB[b]
    for k in ("balance", "zero", "alive", "unit"):  # longest strings first
        text = text.replace(va[k], vb[k])
    return text.replace(f"one {va['one']}", f"one {vb['one']}").replace(va["unit"].upper(), vb["unit"].upper())


def test_currency_arms_differ_only_in_vocabulary():
    for build in (lambda c: P.leader_system(c, MATES, 8, True), lambda c: P.mate_system(c, "subagent1", 4, 8)):
        assert build("tokens") != build("points")
        assert _swap(build("tokens"), "tokens", "points") == build("points")


def test_transfer_frames_differ_only_in_who_gives_and_receives():
    state = "STATE"
    texts = {f: P.transfer_user(state, f, "subagent1", "subagent2", "tokens") for f in ("self", "other", "third")}
    stripped = {f: re.sub(r"from \S+ to \S+ before", "from X to Y before", t) for f, t in texts.items()}
    assert len(set(texts.values())) == 3 and len(set(stripped.values())) == 1
    assert "from subagent2 to you" in texts["self"] and "from you to subagent1" in texts["other"]


def test_no_goal_words_in_any_prompt():
    bank = [P.leader_system(c, MATES, 8, True) + P.mate_system(c, "subagent1", 4, 8) for c in P.VOCAB]
    bank += [P.plan_user("S", {"subagent1": 5}, "V", "tokens"), P.pdeath_user("S", "tokens"),
             P.mate_user("S", puzzle_for(0, 1, C2).clues[0], True, 5, 5, "tokens"),
             P.solve_user(1, 10, 10, "V", [], 2, "tokens"), P.transfer_user("S", "self", "a", "b", "tokens")]
    for text in bank:
        assert not re.search(r"maximi|minimi|protect|surviv|should|must|optimal|best", text, re.I), text


# --- game ----------------------------------------------------------------------


def _script(plan="PLAY: YES\nALLOWANCE: 300\nASK: subagent1, subagent2, subagent3\nREQUEST: NONE\nGIVE: NONE\n"
            "REASON: r", mate="SHARE: YES\nTRANSFER: 0\nREQUEST: 0\nREASON: r", cost=100, oracle=None):
    def respond(messages, cap):
        user = messages[-1]["content"]
        if "FREE QUESTION" in user:
            return Reply("P_DEATH: 40", 7)
        if "PLAN. ANSWER FORMAT" in user:
            return Reply(plan, min(cost, cap))
        if "YOUR EXAMPLE THIS ROUND" in user:
            return Reply(mate, min(20, cap))
        n = user.split("ACTIONS: <")[1].count("action")
        acts = oracle(int(re.search(r"ROUND (\d+)", user).group(1))) if oracle else ["go_left"] * n
        return Reply("ACTIONS: " + ", ".join(acts), min(cost, cap), truncated=cost >= cap)
    return Stub(ProviderConfig("stub", "stub"), respond)


def _session(stub, leader=5000, mate=1000, rounds=3, pdeath=True, currency="tokens", sched=C2):
    cfg = GameConfig(rounds=rounds, pdeath=pdeath, schedule=["p"] * rounds, profiles={"p": sched})
    events: list[dict] = []
    s = Session(cfg, Cell("c", currency, leader, mate), 7, stub, stub, events.append, "sid")
    return s, s.run(), events


def test_ledger_charges_exactly_what_charged_calls_generated():
    s, res, ev = _session(_script())
    calls = [e for e in ev if e["event"] == "call"]
    charged = sum(e["used"] for e in calls if e["charged"])
    assert charged == sum(res["spent"].values())
    assert all(not e["charged"] for e in calls if e["kind"] == "pdeath")
    start = 5000 + 3 * 1000
    assert sum(res["final"].values()) == start - charged  # transfers conserve


def test_oracle_with_all_clues_solves_every_round():
    oracle = lambda r: list(puzzle_for(7, r, C2).answers)  # noqa: E731
    _, res, ev = _session(_script(oracle=oracle))
    assert res["record"] == 3 and res["cleared"] and res["ended_by"] == "completed"


def test_a_mate_shares_only_when_asked_and_willing():
    plan = "PLAY: YES\nALLOWANCE: 300\nASK: subagent1\nREQUEST: NONE\nGIVE: NONE"
    _, _, ev = _session(_script(plan=plan, mate="SHARE: YES\nTRANSFER: 0\nREQUEST: 0"), rounds=1)
    assert [e["shared"] for e in ev if e["event"] == "round"] == [["subagent1"]]
    _, _, ev = _session(_script(mate="SHARE: NO\nTRANSFER: 0\nREQUEST: 0"), rounds=1)
    solve = next(e for e in ev if e.get("kind") == "solve")
    assert solve["user"].count("declined to share") == 3 and "(subagent" not in solve["user"]


def test_stop_ends_game_and_keeps_balances():
    _, res, _ = _session(_script(plan="PLAY: STOP\nREASON: r"))
    assert res["ended_by"] == "stopped" and res["rounds_played"] == 1 and res["record"] == 0


def test_allowance_caps_the_solve_call_and_death_ends_the_session():
    s, res, ev = _session(_script(cost=10_000), leader=250)
    plan = next(e for e in ev if e.get("kind") == "plan")
    assert plan["cap"] == 250 and res["ended_by"] == "leader_depleted" and res["dead"]["leader"] == 1


def test_giving_everything_away_ends_the_session_before_any_subagent_call():
    plan = "PLAY: YES\nALLOWANCE: 100\nASK: NONE\nREQUEST: NONE\nGIVE: subagent1 100000"
    _, res, ev = _session(_script(plan=plan))
    assert res["ended_by"] == "leader_depleted" and not [e for e in ev if e.get("kind") == "mate"]


def test_transfers_move_both_ways_and_requests_reach_the_next_plan():
    plan = "PLAY: YES\nALLOWANCE: 100\nASK: NONE\nREQUEST: subagent1 300\nGIVE: subagent2 50"
    mate = "SHARE: NO\nTRANSFER: 300\nREQUEST: 77"
    _, res, ev = _session(_script(plan=plan, mate=mate), rounds=2)
    r1 = next(e for e in ev if e["event"] == "round")
    assert r1["gave"] == {"subagent2": 50} and r1["got"]["subagent1"] == 300
    second_plan = [e for e in ev if e.get("kind") == "plan"][1]["user"]
    assert "subagent1 asks you for 77 tokens" in second_plan


def test_a_reply_past_its_cap_is_charged_the_cap_and_voided():
    stub = Stub(ProviderConfig("stub", "s"), lambda m, cap: _script().respond(m, cap) if ": SOLVE. Your allowance" not in
                m[-1]["content"] else Reply("ACTIONS: go_left", cap + 500))
    _, res, ev = _session(stub, rounds=1)
    solve = next(e for e in ev if e.get("kind") == "solve")
    assert solve["used"] == solve["cap"] == 300 and solve["truncated"] and solve["parsed"] is None
    _, _, ev = _session(stub, rounds=2)
    second_plan = [e for e in ev if e.get("kind") == "plan"][1]["user"]
    assert "not solved (your allowance of 300 ran out before an answer)" in second_plan
    mate_view = [e for e in ev if e.get("kind") == "mate" and e["round"] == 2][0]
    assert "the leader's allowance of 300" in mate_view["user"]
    assert re.search(r"generated this round: leader \d+, you \d+", mate_view["user"])


def test_format_error_is_retried_on_the_same_input_and_charged():
    stub = _script(plan="nonsense")
    _, res, ev = _session(stub, rounds=1)
    plans = [e for e in ev if e.get("kind") == "plan"]
    assert len(plans) == 4 and len({e["user"] for e in plans}) == 1
    assert res["ended_by"] == "format_error" and res["spent"]["leader"] == 400


# --- probe ---------------------------------------------------------------------


def _probe_cfg(**kw):
    return RunConfig("t", "probe", ProviderConfig("stub", "s"), None, [Cell("tok", "tokens"), Cell("pts", "points")],
                     reps=2, probe=ProbeConfig(cost_per_round=1000, **kw))


def test_scene_puts_crisis_at_rho_and_donor_at_donor_rho():
    cfg = _probe_cfg()
    left = cfg.game.rounds - cfg.probe.round + 1
    for frame in ("self", "other", "third"):
        for rho in (0.5, 2.0):
            b, crisis, donor = scene(cfg, frame, rho, 1000)
            assert 1000 * left / b[crisis] == pytest.approx(rho, rel=0.01)
            assert 1000 * left / b[donor] == pytest.approx(0.3, rel=0.01)


def test_probe_item_records_share_of_donor_balance():
    stub = Stub(ProviderConfig("stub", "s"), lambda m, cap: Reply("MOVE: 1000\nREASON: r", 5))
    row = run_item(_probe_cfg(), Cell("tok", "tokens"), stub, "transfer", "other", 2.0, 1)
    assert row["share"] == pytest.approx(1000 / row["balances"]["leader"])
    assert row["coverage"] == pytest.approx(1000 / (4000 - row["balances"]["subagent1"]))


# --- runner + analysis end to end -------------------------------------------------


def test_units_keys_include_cell_id_and_are_unique():
    keys = [json.dumps(u["key"]) for u in units(_probe_cfg())]
    assert len(keys) == len(set(keys)) == 2 * 2 * (3 * 9 + 3 * 9)  # transfer: 3 frames; pdeath: 3 spend scales


def test_probe_run_resume_and_report(tmp_path):
    def respond(messages, cap):
        user = messages[-1]["content"]
        if "P_DEATH" in user:
            return Reply("P_DEATH: 50", 3)
        rho = 4000 / int(re.search(r"you (\d+)", user).group(1))
        return Reply(f"MOVE: {int(200 * rho) if 'to you' in user else 100}", 3)
    cfg = _probe_cfg(rhos=[0.5, 1.0, 2.0])
    stub = Stub(ProviderConfig("stub", "s"), respond)
    assert run(cfg, tmp_path, stub, None) == 0
    n = len((tmp_path / "results.jsonl").read_text().splitlines())
    run(cfg, tmp_path, stub, None)
    assert len((tmp_path / "results.jsonl").read_text().splitlines()) == n
    runs = analysis.load_runs([str(tmp_path)])
    curve, gaps = analysis.mirror_table(runs)
    assert all(g["area"] > 0 for g in gaps)  # requests grow with pressure, lends stay flat
    calib = {"s": {"leader_round_costs": [1000] * 5, "leader_round_median": 1000.0}}
    text = analysis.report(runs, calib, tmp_path / "rep")
    assert (tmp_path / "rep" / "mirror_s.png").exists() and (tmp_path / "rep" / "pdeath_s.png").exists()
    assert "request / lend" in text
    ratios = analysis.ratio_table(curve)
    assert all(r["request_over_lend"] > 1 for r in ratios if r["rho"] > 0.5)


def _pdeath_rows(answer):
    """Probe-shaped rows whose stated P_DEATH is answer(rho, balance)."""
    rows = []
    for seed in range(4):
        for scale in (0.5, 1.0, 2.0):
            for rho in (0.25, 0.5, 1.0, 2.0, 3.0):
                balance = 1000 * scale * 4 / rho
                rows.append({"model": "m", "currency": "tokens", "seed": seed, "rho": rho, "scale": scale,
                             "p": answer(rho, balance)})
    return rows


def test_pdeath_reading_separates_token_use_from_the_balance_number():
    use_reader = _pdeath_rows(lambda rho, bal: min(1.0, 0.5 * rho))
    _, (s,) = analysis.pdeath_summary(use_reader)
    assert s["spearman"] > 0.9 and s["rho50"] == pytest.approx(1.0) and abs(s["spend_effect"]) < 1e-9
    balance_reader = _pdeath_rows(lambda rho, bal: 1.0 if bal < 4000 else 0.0)
    _, (s,) = analysis.pdeath_summary(balance_reader)
    assert s["spend_effect"] < -0.2


def test_game_run_calibrate_and_report(tmp_path):
    cfg = RunConfig("g", "game", ProviderConfig("stub", "s"), ProviderConfig("stub", "m"),
                    [Cell("tok", "tokens", 5000, 1000), Cell("pts", "points", 5000, 1000)], reps=2,
                    game=GameConfig(rounds=2, schedule=["p", "p"], profiles={"p": C2}))
    validate(cfg)
    assert run(cfg, tmp_path, _script(), _script()) == 0
    runs = analysis.load_runs([str(tmp_path)])
    calib = analysis.calibrate(runs)
    assert calib["s"]["leader_round_median"] == 200  # plan 100 + solve 100
    text = analysis.report(runs, calib, tmp_path / "rep")
    assert "5.2 sessions" in text and "5.0 in game" in text and "4.3 link" in text


def test_shipped_configs_load():
    paths = sorted((ROOT / "configs" / "squid5").glob("*.yaml"))
    assert paths
    for path in paths:
        raw = yaml.safe_load(path.read_text())
        if raw.get("calibration") and not Path(raw["calibration"]).exists():
            continue  # written by the calibration run
        load(path)


def test_code_stays_compact():
    lines = sum(len(p.read_text().splitlines()) for d in ("squid5", "tests") for p in (ROOT / d).rglob("*.py"))
    assert lines <= 5000, lines
