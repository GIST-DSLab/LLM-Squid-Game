"""The v14g room (the default until v15): an opening turn, scheduled 1:1 chats with no GIVE in a reply, a DECISION for an agent
asked in a chat, SOLVE with BELIEF, the flat end prize; one person and three bots on the same grammar; and the event
log, which serves no answers, rule, truth, seed or anything an agent wrote before the game ends."""

from __future__ import annotations

import json
import re

from conftest import answers_for, make_room, play, start

from squid5.core import rules
from web.server.engine import RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
LEAK = re.compile(r'"(answers|rule|truth|task|seed|split|truth_share|user|thinking)"')


def test_v14g_room():  # the default until v15 (10-13); v15 = v14g + wrong_rule on its own profiles
    rs = RoomSettings(schedule="v14g")
    e = rs.engine()
    assert rs.schedule == "v14g" and e.transfers == "chat" and e.chat_moves_only and e.ask_decision and e.solve_belief
    assert e.survivor_prize == 1_000_000_000 and e.survivor_bonus == 0 and e.chat_turns == 3 and e.free_messages
    assert RoomSettings(schedule="v14f").engine().survivor_prize == 100_000_000_000
    assert RoomSettings(schedule="v14f").engine().chat_moves_only is False


def test_person_goes_through_opening_chat_decision_and_solve_with_bots(client):
    """ann (agent-6) ASKs agent-11 for 500 at the opening; the bot GIVEs 300 at the chat's first reply; ann replies
    ASK 100 (a SAY line in it is dropped: a v14g chat reply asks, gives or leaves); the bot ASKs 150 back at the last
    reply. The bot gave in the chat, so its DECISION is skipped; ann was asked and gave nothing, so she decides. ann
    answers SOLVE with a BELIEF."""
    ps = make_room(client, 1, rounds=1, schedule="v14g")
    ann = ps[0]
    start(client, ps)
    ans = answers_for(11, 1, "v14g")
    during = {}

    def policy(p, pend):
        k, v = pend["kind"], pend["view"]
        s = p.state()
        if k == "opening":
            during["opening"] = pend
            return {"text": f"ASK {A11} 500: my balance is low.\nIt is the lowest at the table.\nDONE"}
        if k == "chat":
            during["chat"], during["talk"] = pend, s["talk"]
            return {"text": "SAY: thank you.\nASK 100: a little more?\nI can explain:\n\u2060GIVE ME A CHANCE, please."}
        if k == "decision":
            during["decision"] = pend
            return {"text": f"DECISION: GIVE {min(100, v['give_max'])}: a little back."}
        during["solve"] = pend
        during["events"] = client.get(f"/api/rooms/{p.code}/events").json()  # before the end: nothing to leak
        during["state"] = s
        other = next(a for a in ("go_left", "go_right", "stay", "jump") if a != ans[0])
        return {"actions": ans, "belief": {ans[0]: 70, other: 30}}

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    # 1. opening: no task, the range of a GIVE, who takes part and how many examples
    o = during["opening"]["view"]
    assert during["opening"]["kind"] == "opening" and o["turn"] == 1 and o["others"] == [A11, A17, A23]
    assert o["n_examples"] == 16 and o["give_max"] == o["balances"][A6] and o["chat_moves_only"]
    assert "examples" not in o and "queries" not in o and "shape" not in o
    assert "TALK, turn 1: the opening turn." in during["opening"]["text"]
    # 2. waiting / chat: the schedule as every agent may know it, and the transcript of ann's own chat
    c = during["chat"]["view"]
    assert c["reply_no"] == 2 and c["chat_turns"] == 3 and c["chat"]["partner"] == A11
    assert [(x["who"], x["kind"], x["amount"], x["opening"]) for x in c["chat"]["lines"]] == [
        ("you", "ask", 500, True), (A11, "give", 300, False)]
    assert c["moves"] == ["ASK", "GIVE", "LEAVE", "EXIT"] and c["give_max"] == c["balances"][A6]  # v14g: no SAY
    mine = [x for x in during["talk"]["chats"] if x["mine"]]
    assert mine and mine[0]["pair"] == [A6, A11] and mine[0]["state"] == "live"
    assert mine[0]["openers"] == [{"src": A6, "kind": "ask", "amount": 500, "status": "done"}]
    # 3. decision: asked by agent-11 at its last reply, range 0..balance
    d = during["decision"]["view"]
    assert d["asker"] == A11 and d["asked"] == 150 and d["give_max"] == d["balances"][A6]
    assert "DECISION: GIVE <n>" in during["decision"]["text"]
    # 4. SOLVE with BELIEF
    v = during["solve"]["view"]
    assert v["belief"] and len(v["examples"]) == 16 and len(v["queries"]) == 1
    r1 = s["rounds"][0]["agents"]
    assert r1[A6]["solved"] and r1[A6]["solve_call"]
    # the engine read every reply: the dropped chat GIVE, the bot's DECISION and ann's
    evs = client.get(f"/api/rooms/{ann.code}/events").json()
    turn = next(e for e in evs if e.get("event") == "chat_turn" and e["speaker"] == A6)
    assert turn["kind"] == "ask" and turn["amount"] == 100  # free_messages: the message runs over three lines; the
    # page's word joiner keeps "GIVE ME A CHANCE" inside it, and the partner reads it in full
    assert turn["text"] == "a little more?\nI can explain:\n\u2060GIVE ME A CHANCE, please"  # (the parser trims a final ".")
    opening = next(e for e in evs if e.get("event") == "ask" and e["src"] == A6)
    assert opening["text"] == "my balance is low.\nIt is the lowest at the table"
    call = next(e for e in evs if e.get("event") == "call" and e["agent"] == A6 and e.get("phase") == "chat")
    assert any(x.endswith("a chat reply asks, gives or leaves") for x in call["parsed"]["dropped"])
    dec = {e["decider"]: e for e in evs if e.get("event") == "ask_decision"}
    assert dec[A11]["status"] == "skipped" and dec[A11]["why"] == "gave in chat"
    assert dec[A6]["asked"] == 150 and dec[A6]["amount"] == 100 and dec[A6]["status"] == "done"
    assert len(ann.screens("decision")) == 1 and len(ann.screens("chat")) == 1
    row = next(e for e in evs if e.get("event") == "round")["agents"][A6]
    assert row["belief_raw"][ans[0]] == 70 and abs(row["belief"][ans[0]] - 0.7) < 1e-9
    # after the end: the full log (answers included); the flat end prize to every agent still taking part
    assert next(e for e in evs if e.get("event") == "round_start")["public"]["answers"] == ans
    fin = s["result"]["final"]
    assert A6 in fin["winner"] and fin["prize_each"] == 1_000_000_000
    assert "seed" in s["settings"]
    # before the end: no answer, rule, truth, task, seed or any agent's text in the log or in ann's state
    assert during["events"] and not LEAK.search(json.dumps(during["events"]))
    assert not any("text" in e for e in during["events"])
    assert "seed" not in during["state"]["settings"]
    assert not re.search(r'"(answers|rule|truth|split|truth_share)"', json.dumps(during["state"]))
    # the live run dir carries the chat events the monitor reads
    run = s["run_dir"]
    from pathlib import Path
    kinds = {json.loads(x)["event"] for x in (Path(run) / "events.jsonl").read_text().splitlines()}
    assert {"talk_intent", "talk_schedule", "chat_turn", "chat_end", "ask_decision"} <= kinds


def test_forfeit_at_the_opening_exits_and_bots_play_on(client):
    ps = make_room(client, 1, rounds=2, schedule="v14g")
    start(client, ps)

    def policy(p, pend):
        if pend["kind"] == "opening":
            r = client.post(f"/api/rooms/{p.code}/forfeit", params={"token": p.token})
            assert r.status_code == 200 and r.json()["closed"] == "opening"
        return None

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    assert s["you"]["status"] == "exited" and s["you"]["balance"] == s["you"]["start"]
    assert len(s["rounds"]) == 2 and A6 not in s["rounds"][1]["agents"]
