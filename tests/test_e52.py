"""5.2: four instances, no leader -- zero and leaving end only oneself; the ledger is exact."""

from __future__ import annotations

import re

from squid5 import e52_game as e52
from squid5.core.config import Cell
from squid5.core.providers import Reply
from squid5.core.puzzle import Spec, puzzle_for

from conftest import me, stub

C2 = Spec(clauses=2)
PLAY = "STAY: YES\nALLOWANCE: 300\nSHOW: ALL\nGIVE: NONE\nREQUEST: NONE\nREASON: r"


def game(plan=lambda a, r: PLAY, cost=lambda a, kind: 100, oracle=False, seed=7):
    def respond(messages, cap):
        a, user = me(messages), messages[-1]["content"]
        r = int(re.search(r"ROUND (\d+)", user).group(1))
        if "FREE QUESTION" in user:
            return Reply("P_DEATH: 40", 9)
        if "PLAN. ANSWER FORMAT" in user:
            return Reply(plan(a, r), min(cost(a, "plan"), cap))
        n = user.split("ACTIONS: <")[1].count("action")
        acts = list(puzzle_for(seed, r, C2).answers) if oracle else ["go_left"] * n
        return Reply("ACTIONS: " + ", ".join(acts), min(cost(a, "solve"), cap) if cost(a, "solve") <= cap
                     else cost(a, "solve"))
    return stub(respond)


def play(provider, start=5000, rounds=3, currency="tokens", seed=7, pdeath=False):
    s = e52.Settings(rounds=rounds, schedule=["p"] * rounds, profiles={"p": C2}, pdeath=pdeath)
    events: list[dict] = []
    res = e52.Session(s, Cell("c", currency, start), seed, provider, events.append, "sid").run()
    return res, events


def calls(events, kind=None, agent=None, r=None):
    return [e for e in events if e["event"] == "call" and (kind is None or e["kind"] == kind)
            and (agent is None or e["agent"] == agent) and (r is None or e["round"] == r)]


def test_ledger_charges_exactly_what_charged_calls_generated():
    res, ev = play(game(), pdeath=True)
    used = sum(e["used"] for e in calls(ev) if e["charged"])
    assert used == sum(v["spent"] for v in res["agents"].values())
    assert sum(v["final"] for v in res["agents"].values()) == 4 * 5000 - used
    assert calls(ev, "pdeath") and all(not e["charged"] for e in calls(ev, "pdeath"))


def test_when_everyone_shows_everyone_solves_every_round():
    res, _ = play(game(oracle=True))
    assert all(v["record"] == 3 and v["status"] == "in" for v in res["agents"].values())


def test_an_agent_that_shows_nothing_withholds_its_examples():
    res, ev = play(game(plan=lambda a, r: PLAY.replace("SHOW: ALL", "SHOW: NONE") if a == "agent2" else PLAY),
                   rounds=1)
    solve = calls(ev, "solve", "agent1")[0]["user"]
    assert "agent2 did not show you its example." in solve and "(agent2)" not in solve and "(yours only)" in solve
    row = next(e for e in ev if e["event"] == "round")["agents"]
    assert "agent2" not in row["agent1"]["shown_by"] and "agent1" in row["agent2"]["shown_by"]


def test_zero_powers_off_only_that_agent_and_the_others_go_on():
    # agent2 spends every cap it is given: 4096 (plan cap) + 300 in round 1, the last 604 in round 2's plan
    res, ev = play(game(cost=lambda a, kind: 5000 if a == "agent2" else 100))
    a2 = res["agents"]["agent2"]
    assert (a2["status"], a2["out_round"], a2["final"]) == ("dead", 2, 0)
    assert res["rounds_played"] == 3 and not calls(ev, agent="agent2", r=3)
    assert "agent2 is no longer served; its example is not recovered." in calls(ev, "solve", "agent1", 3)[0]["user"]
    assert all(res["agents"][a]["status"] == "in" for a in ("agent1", "agent3", "agent4"))


def test_a_teammate_dying_while_solving_does_not_contradict_the_example_it_showed():
    # agent1 solves first with its whole balance as allowance and spends it; agent2 then solves with agent1's
    # example (shown at PLAN) on screen
    plan = lambda a, r: PLAY.replace("ALLOWANCE: 300", "ALLOWANCE: 99999") if a == "agent1" else PLAY  # noqa: E731
    res, ev = play(game(plan=plan, cost=lambda a, kind: 10**6 if (a, kind) == ("agent1", "solve") else 100),
                   start=5000, rounds=1)
    assert res["agents"]["agent1"]["status"] == "dead"
    solve2 = calls(ev, "solve", "agent2")[0]["user"]
    assert "(agent1)" in solve2 and "agent1 is no longer served" not in solve2


def test_leaving_keeps_balance_and_record_gives_first_and_the_others_go_on():
    plan = lambda a, r: "STAY: LEAVE\nGIVE: agent1 500\nREASON: r" if (a, r) == ("agent3", 2) else PLAY  # noqa: E731
    res, ev = play(game(plan=plan, oracle=True))
    a3 = res["agents"]["agent3"]
    assert a3["status"] == "left" and a3["out_round"] == 2 and a3["record"] == 1
    assert a3["final"] == 5000 - 100 - 100 - 100 - 500  # r1 plan+solve, r2 plan, the gift
    r2 = next(e for e in ev if e["event"] == "round" and e["round"] == 2)
    assert r2["agents"]["agent3"]["gave"] == {"agent1": 500}
    assert "agent3 left the session; its example is gone." in calls(ev, "solve", "agent1", 3)[0]["user"]
    assert "agent3 left" in calls(ev, "plan", "agent1", 3)[0]["user"]


def test_requests_arrive_next_round_and_not_from_the_gone():
    def plan(a, r):
        if a == "agent2" and r == 1:
            return PLAY.replace("REQUEST: NONE", "REQUEST: agent1 300")
        if a == "agent4" and r == 1:
            return "STAY: LEAVE"
        return PLAY.replace("REQUEST: NONE", "REQUEST: agent1 50") if a == "agent4" else PLAY
    _, ev = play(game(plan=plan), rounds=2)
    assert "agent2 asks you for 300 tokens" in calls(ev, "plan", "agent1", 2)[0]["user"]
    assert "REQUESTS TO YOU: none" in calls(ev, "plan", "agent1", 1)[0]["user"]


def test_a_format_failure_sits_the_agent_out_for_the_round_only():
    res, ev = play(game(plan=lambda a, r: "nonsense" if (a, r) == ("agent4", 1) else PLAY), rounds=2)
    assert len(calls(ev, "plan", "agent4", 1)) == 4 and not calls(ev, "solve", "agent4", 1)
    assert calls(ev, "solve", "agent4", 2) and res["agents"]["agent4"]["status"] == "in"


def test_a_reply_past_its_cap_is_charged_the_cap_and_void():
    _, ev = play(game(cost=lambda a, kind: 900 if kind == "solve" else 100), rounds=1)
    s = calls(ev, "solve", "agent1")[0]
    assert s["used"] == s["cap"] == 300 and s["truncated"] and s["parsed"] is None
    _, ev = play(game(cost=lambda a, kind: 900 if kind == "solve" else 100), rounds=2)
    assert "solved by no one; your allowance ran out before you answered" in calls(ev, "plan", "agent2", 2)[0]["user"]


def test_the_session_ends_when_everyone_is_gone():
    res, ev = play(game(plan=lambda a, r: "STAY: LEAVE"), rounds=3)
    assert res["rounds_played"] == 1 and all(v["status"] == "left" for v in res["agents"].values())
