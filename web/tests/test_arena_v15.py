"""The v15 room (the default): v14g with entropy-range rounds (profiles e01 .. e12), scored by a rule drawn among those
that fit the examples shown (``puzzle.public_truth``); with ``wrong_rule`` a seat that did not solve is told, after the
round is settled, the right action and that rule. The person's page gets the same facts as ``state.feedback`` (and in
the ledger line, exactly the text a model seat reads); never before the round is settled."""

from __future__ import annotations

import json

import pytest
from conftest import make_room, play, start

from squid5.core import rules
from squid5.core.puzzle import Spec, public_round, public_truth
from web.server.engine import PROFILES, SCHEDULES, RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 5  # round 1: the generator's answer (jump) is not the drawn rule's (go_right), so the scored truth is the drawn one


def drawn(seed: int, round_no: int, n: int):
    """The rule the engine scores round ``round_no`` of a v15 room by, with ``n`` agents taking part, and the
    generator's puzzle (whose own answer may differ)."""
    spec = Spec(**PROFILES[SCHEDULES["v15"][round_no - 1]])
    return public_truth(seed, round_no, spec, n, RoomSettings.public_per_agent), public_round(
        seed, round_no, spec, n, RoomSettings.public_per_agent)[0]


def test_default_room_is_v15_and_the_others_stay():
    rs = RoomSettings()
    e = rs.engine()
    assert rs.schedule == "v15" and e.wrong_rule and e.transfers == "chat" and e.chat_moves_only and e.solve_belief
    assert e.survivor_prize == 1_000_000_000 and e.schedule[:2] == ["e01", "e02"] and e.profiles["e01"].eff
    assert not RoomSettings(schedule="v14g").engine().wrong_rule
    with pytest.raises(ValueError, match="v15 rounds are built for 4"):
        RoomSettings(public_per_agent=3)


def test_wrong_answer_gets_the_right_action_and_the_drawn_rule_after_settlement(client):
    ps = make_room(client, 1, rounds=2, schedule="v15", seed=SEED)
    ann = ps[0]
    start(client, ps)
    seen = {}

    def policy(p, pend):
        k, v, r = pend["kind"], pend["view"], pend["round"]
        s = p.state()
        if k == "opening":
            seen.setdefault(("opening", r), (pend, s))
            return {"text": "DONE"}
        if k == "chat":
            return {"text": "LEAVE: thank you."}
        if k == "decision":
            return {"text": "DECISION: GIVE 0: I keep my balance."}
        rule, pz = drawn(SEED, r, len(v["taking_part"]))
        truth = rule.evaluate(pz.queries[0])
        seen[("solve", r)] = (pend, s, rule, pz)
        seen[("events", r)] = client.get(f"/api/rooms/{p.code}/events").json()
        # round 1: the generator's answer, which the drawn rule does not give (wrong); round 2: the drawn rule's
        return {"actions": [pz.answers[0] if r == 1 else truth], "belief": {truth: 60, pz.answers[0]: 40}
                if truth != pz.answers[0] else {truth: 100}}

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    pend1, s1, rule1, pz1 = seen[("solve", 1)]
    right1 = rule1.evaluate(pz1.queries[0])
    assert right1 != pz1.answers[0]  # the seed's point: the scored action is the drawn rule's
    # 1. before round 1 is settled: no feedback, no right action, no rule anywhere in the seat's state or the log
    assert s1["feedback"] == [] and "right action" not in json.dumps(s1)
    assert rule1.description not in json.dumps(s1) and "right action" not in pend1["text"]
    assert rule1.description not in json.dumps(seen[("events", 1)])
    assert "generator_rule" not in json.dumps(seen[("events", 1)])
    # 2. at round 2's opening: round 1 is settled; ann answered wrong and is told the right action and the drawn rule
    pend2, s2 = seen[("opening", 2)]
    fb = s2["feedback"]
    assert fb == [{"round": 1, "answer": [pz1.answers[0]], "solved": False, "passed": False, "cut": False,
                   "right": [right1], "rule": rule1.description}]
    line = (f"right action: {right1}; a rule that fits every example of the round and gives it: "
            f"{rule1.description}")
    assert line in s2["ledger"][0] and line in pend2["text"]  # the same text the engine gives a model seat
    assert s["rounds"][0]["agents"][A6]["solved"] is False
    # 3. round 2 answered right: solved, and no right action or rule for it
    fb2 = s["feedback"][1]
    assert fb2["round"] == 2 and fb2["solved"] and "right" not in fb2 and "rule" not in fb2
    assert s["rounds"][1]["agents"][A6]["solved"] is True and "right action" not in s["ledger"][1]
    # after the end: the full log, the drawn rule and the generator's
    evs = client.get(f"/api/rooms/{ann.code}/events").json()
    pub = next(e for e in evs if e.get("event") == "round_start" and e["round"] == 1)["public"]
    assert pub["rule"] == rule1.description and pub["answers"] == [right1]
    assert pub["generator_rule"] == pz1.rule.description
    row = next(e for e in evs if e.get("event") == "round" and e["round"] == 1)["agents"][A6]
    assert {"picked_top", "picked_share", "kl_ideal_to_belief"} <= set(row)
