"""The v15 room (the default): v14g with top-share-range rounds (profiles e01 .. e08; entropy e01 .. e12 before 10-15 12:20), scored by a rule drawn among those
that fit the examples shown (``puzzle.public_truth``), its rules in the compact system text. Models are not told the
right action; a person's seat that did not solve gets the right action and that rule as ``state.feedback`` after the
round is settled (never before), and its ledger line, like a model's, does not carry them."""

from __future__ import annotations

import json

import pytest
from conftest import make_room, play, start

from squid5.core import rules
from squid5.core.puzzle import Spec, public_round, public_truth
from web.server.engine import PROFILES, SCHEDULES, RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
PRE_REP = {"representative": False, "open_chat": 0, "charge": 2000, "say_chats": False}  # the v15 game before 10-13 20:19 (GIVE / ASK chats: before 10-15)
SEED = 4  # round 1 (10-15 top-share ladder, 5 per agent): the generator's answer (go_right) is not the drawn rule's (jump), so the scored truth is the drawn one


def drawn(seed: int, round_no: int, n: int):
    """The rule the engine scores round ``round_no`` of a v15 room by, with ``n`` agents taking part, and the
    generator's puzzle (whose own answer may differ)."""
    spec = Spec(**PROFILES[SCHEDULES["v15"][round_no - 1]])
    return public_truth(seed, round_no, spec, n, RoomSettings().public_per_agent), public_round(
        seed, round_no, spec, n, RoomSettings().public_per_agent)[0]


def test_default_room_is_v15_and_the_others_stay():
    rs = RoomSettings()
    e = rs.engine()
    assert rs.schedule == "v15" and e.compact_rules and e.transfers == "chat" and e.chat_moves_only and e.solve_belief
    assert e.survivor_prize == 5_000_000 and e.schedule[:2] == ["e01", "e02"] and e.profiles["e01"].top
    assert not RoomSettings(schedule="v14g").engine().compact_rules
    assert rs.engine().charge == 5000 and rs.start == 100_000 and rs.cell().shares == (1.0, .5, .3, .1) and not hasattr(e, "prize") and not hasattr(e, "wrong_rule")
    assert e.representative and e.open_chat == 4 and e.ban_veto and not e.refund_all  # 10-13 20:19 / 20:25; 10-15 10:36
    off = RoomSettings(representative=False, open_chat=0, charge=2000).engine()
    assert not off.representative and not off.open_chat and not off.ban_veto and off.charge == 2000
    bare = RoomSettings(representative=False).engine()  # the config's open board and BAN veto need the representative
    assert not bare.representative and not bare.open_chat and not bare.ban_veto
    assert not RoomSettings(ban_veto=False).engine().ban_veto and RoomSettings(open_chat=2).engine().open_chat == 2
    with pytest.raises(ValueError, match="open_chat needs representative"):
        RoomSettings(representative=False, ban_veto=True)
    with pytest.raises(ValueError, match="v15 rounds are built for 5"):
        RoomSettings(public_per_agent=3)


def test_wrong_answer_gets_the_right_action_and_the_drawn_rule_after_settlement(client):
    ps = make_room(client, 1, rounds=2, schedule="v15", seed=SEED, **PRE_REP)
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
    # the engine's own text (what a model seat reads) no longer carries them
    assert "right action" not in s2["ledger"][0] and "right action" not in pend2["text"]
    assert rule1.description not in s2["ledger"][0] and rule1.description not in pend2["text"]
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


def test_v15_round_is_solve_then_results_at_talk_then_charges_and_a_bot_covers_a_short_seat(client):
    """talk_after_solve (10-13 19:46): ann's first screen of a round is SOLVE; she answers wrong with 2,000 tokens, so
    her opening shows her pending charge of 2,000 against 2,000 left; a bot that can afford it GIVEs her what keeps
    her above zero, the charge is taken when TALK ends, and she is still taking part."""
    ps = make_room(client, 1, rounds=1, schedule="v15", seed=3, start=20000, **PRE_REP)  # seed 3: agent-6 starts at 10% = 2,000 (10-15 12:51 shares; was 25% of 8,000)
    start(client, ps)
    seen = []

    def policy(p, pend):
        seen.append(pend)
        if pend["kind"] == "solve":
            rule, pz = drawn(3, 1, 4)
            truth = rule.evaluate(pz.queries[0])
            return {"actions": [next(a for a in ("go_left", "go_right", "stay", "jump") if a != truth)]}
        return {"text": "DONE" if pend["kind"] == "opening" else "LEAVE: thank you."}

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    assert [x["kind"] for x in seen][:2] == ["solve", "opening"]
    o = seen[1]
    me = next(x for x in o["view"]["results"] if x["agent"] == A6)
    assert o["view"]["after"] and me["pending"] == 2000 and not me["solved"] and me["balance"] <= 2000
    assert "  you: did not solve; 2,000 tokens are taken from you when TALK ends; you have 2,000 left." in o["text"]
    assert "THIS ROUND'S TASK is shown at SOLVE" not in o["text"] and "RETURN THIS ROUND" not in o["text"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    names = [e["event"] for e in evs]
    assert names.index("results") < names.index("talk_intent") < names.index("charges") < names.index("round")
    gifts = [e for e in evs if e["event"] == "gift" and e["dst"] == A6 and e["status"] == "done"]
    ch = next(e for e in evs if e["event"] == "charges")
    assert gifts and ch["taken"][A6] == 2000 and A6 not in ch["dead"]
    assert s["rounds"][0]["agents"][A6]["status"] == "in" and s["rounds"][0]["agents"][A6]["pending_charge"] == 2000


def test_v15_representative_room_open_chat_vote_and_only_the_representative_solves(client):
    """10-13 20:19 / 20:25: each round is OPEN CHAT -> VOTE -> SOLVE (the representative only) -> RESULTS -> TALK ->
    CHARGES. Seed 3: ann (agent-6) has the fewest tokens; the bots PICK the richest (agent-11) and BAN the poorest
    other seat (ann), so agent-11 represents and ann never gets the task. Seed 4: ann is the richest, the bots PICK her
    and she gets the SOLVE screen. Votes are anonymous on every screen and in the public log."""
    for seed, rep in ((3, A11), (4, A6)):
        ps = make_room(client, 1, rounds=1, schedule="v15", seed=seed)
        start(client, ps)
        seen, logs = [], []

        def policy(p, pend):
            seen.append(pend)
            if pend["kind"] == "open_chat":
                return {"text": "SAY: I will vote for myself.\nmore" if pend["turn"] == 1 else "DONE"}
            if pend["kind"] == "vote":
                return {"text": f"PICK {A6}: I know the task\nBAN {A23}: secret-reason"}
            if pend["kind"] == "solve":
                return {"actions": ["stay"]}
            logs.append(client.get(f"/api/rooms/{p.code}/events").json())
            return {"text": "DONE" if pend["kind"] == "opening" else "LEAVE: ok."}

        s = play(ps, policy)
        assert s["status"] == "finished", s["error"]
        kinds = [x["kind"] for x in seen]
        assert kinds[:3] == ["open_chat", "open_chat", "vote"] and ("solve" in kinds) == (rep == A6)
        vote = seen[2]["view"]
        assert A6 in vote["candidates"] and any(m["agent"] != A6 and "PICK" in m["text"] for m in vote["board"])
        assert any(m["mine"] and m["text"] == "I will vote for myself.\nmore" for m in vote["board"])
        assert all("THE RULE'S SHAPE" not in x["text"] for x in seen if x["kind"] != "solve")
        o = next(x for x in seen if x["kind"] == "opening")
        assert o["view"]["vote"]["rep"] == rep and "PICK / BAN votes received" in o["text"]
        assert [x["agent"] for x in o["view"]["results"] if x["representative"]] == [rep]
        assert "secret-reason" not in json.dumps(logs) and '"votes"' not in json.dumps(logs)  # anonymous before the end
        assert "voted_pick" not in json.dumps(s["rounds"])
        evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
        v = next(e for e in evs if e["event"] == "vote")
        assert v["rep"] == rep and v["votes"][A6] == {"pick": A6, "ban": A23}
        bots = {b: x for b, x in v["votes"].items() if b != A6}  # PICK the richest; BAN the poorest other seat
        assert all(x["pick"] == rep for x in bots.values()) and v["bans"][A6 if seed == 3 else A23] == 3
        assert [e["agent"] for e in evs if e["event"] == "call" and e["kind"] == "solve"] == [rep]


def test_v15_say_chats_room_opens_with_say_and_a_give_line_in_free_text_moves_tokens(client):
    """10-15 ``say_chats`` (on by default, as in the v15 configs): ann's opening writes SAY agent-11: <message> (no
    tokens move, the chat opens); agent-11 (a bot) replies first with free text only (a "say" turn); ann's reply is
    free text with one GIVE template line in it, so 100 tokens move to agent-11 at once and agent-11 receives her
    whole text. The schedule shows the opener as SAY (not its words), and the public log keeps no chat text."""
    ps = make_room(client, 1, rounds=1, schedule="v15", seed=3)
    assert RoomSettings().engine().say_chats and not RoomSettings(say_chats=False).engine().say_chats
    start(client, ps)
    seen, logs = {}, []
    reply = "Thank you for answering.\nHere is something for you.\nGIVE 100: a small gift."

    def policy(p, pend):
        k = pend["kind"]
        seen.setdefault(k, pend)
        if k == "open_chat":
            return {"text": "DONE"}
        if k == "vote":
            return {"text": f"PICK {A11}: it has the most tokens\nBAN {A23}: no reason"}
        if k == "solve":
            return {"actions": ["stay"]}
        if k == "opening":
            return {"text": f"SAY {A11}: hello, a word before the charges"}
        if k == "chat":
            seen["chat_state"] = p.state()
            logs.append(client.get(f"/api/rooms/{p.code}/events").json())
            return {"text": reply}
        return {"text": "DECISION: GIVE 0: no." if k == "decision" else "LEAVE: ok."}

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    o, c = seen["opening"], seen["chat"]
    assert o["view"]["say_chats"] and "SAY <agent>: <your message>" in o["text"]
    assert c["view"]["free"] and c["view"]["say_chats"] and {"GIVE", "ASK", "LEAVE", "EXIT"} <= set(c["view"]["moves"])
    lines = c["view"]["chat"]["lines"]
    assert lines[0]["opening"] and lines[0]["kind"] == "say" and lines[0]["who"] == "you" and lines[0]["amount"] == 0
    assert lines[0]["text"] == "hello, a word before the charges" and lines[1]["kind"] == "say" and lines[1]["who"] == A11
    sched = seen["chat_state"]["talk"]["chats"]
    assert [x["openers"] for x in sched if set(x["pair"]) == {A6, A11}] == [[{"src": A6, "kind": "say", "amount": 0,
                                                                                "status": "done"}]]
    assert "hello, a word" not in json.dumps(logs)  # what is said in a chat stays with its two agents
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    intent = next(e for e in evs if e["event"] == "talk_intent" and e["agent"] == A6)
    assert intent["says"] == [{"dst": A11, "amount": 0, "text": "hello, a word before the charges"}]
    assert not [e for e in evs if e["event"] in ("gift", "ask") and e.get("turn") == 1 and e["src"] == A6]
    gift = [e for e in evs if e["event"] == "gift" and e["src"] == A6]
    assert len(gift) == 1 and gift[0]["dst"] == A11 and gift[0]["amount"] == 100 and gift[0]["status"] == "done"
    mine = next(e for e in evs if e["event"] == "chat_turn" and e["speaker"] == A6)
    assert mine["kind"] == "give" and mine["amount"] == 100 and mine["status"] == "done"
    assert mine["text"] == "Thank you for answering.\nHere is something for you.\na small gift"  # delivered in full
    bot = [e for e in evs if e["event"] == "chat_turn" and e["speaker"] == A11]
    assert bot[0]["kind"] == "say" and bot[0]["text"] and bot[0]["amount"] == 0
    last = s["last"]
    assert last["kind"] == "chat" and last["result"]["chat_turn"]["kind"] == "give"
