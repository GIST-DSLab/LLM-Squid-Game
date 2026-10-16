"""The room path (API -> seats -> engine) is the experiment engine itself: replaying every reply the room's seats gave
(text and tokens, from the room's call events) to a ``squid5.e52_game.Session`` built directly on the same seed gives
the same round starts, solvers, gifts and asks, results, charges, rounds and result. The room covers the v17b moves: a
SAY opening, an ASK, a GIVE, GIVE ALL, an
EXIT before SOLVE and an EXIT line after RESULTS that the engine ignores."""

from __future__ import annotations

from conftest import answers_for, make_room, play, start, wrong_for

from squid5 import e52_game as e52
from squid5.core import rules
from squid5.core.providers import ProviderConfig, Reply, Stub
from web.server.engine import RoomSettings, kind_of, round_of, turn_of

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 21  # round 1's solver: agent-11 (bob); round 2's: agent-6 (ann)


def test_room_matches_direct_engine_run(client):
    ps = make_room(client, 2, seed=SEED, rounds=3, rate=80)
    ann, bob = ps

    def policy(p, pend):
        k, v, r = pend["kind"], pend["view"], pend["round"]
        if k == "solve":
            n = len(v["taking_part"])
            return {"actions": (wrong_for if (p.agent, r) == (A11, 1) else answers_for)(SEED, r, n)}
        if k == "opening":
            if p is ann and (r, v["phase"]) == (1, "prep"):
                return {"text": f"SAY {A11}: a deal?\nSAY {A23}: hello"}
            if p is ann and (r, v["phase"]) == (2, "rescue"):
                return {"text": f"SAY {A23}: everything I have"}
            if p is bob and v["phase"] == "rescue":
                return {"text": "EXIT: too late to leave"}  # ignored: no EXIT after RESULTS
            if p is bob and (r, v["phase"]) == (3, "prep"):
                return {"text": "EXIT: I leave now"}
            return {"text": "DONE"}
        if k == "chat":
            mine = [x for x in v["chat"]["lines"] if x["who"] == "you"]
            if p is ann and (r, v["phase"], v["chat"]["partner"]) == (2, "rescue", A23):
                return {"text": "All of it.\nGIVE ALL: take it"}
            if p is ann and v["chat"]["partner"] == A11 and len(mine) == 1:
                return {"text": "I can help.\nGIVE 200: for the next answer"}
            if p is bob and not mine:
                return {"text": "Spare some?\nASK 150: please"}
            return {"text": "LEAVE: ok"}
        return {"text": "DECISION: GIVE 0: no"}

    start(client, ps)
    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    replies = {}
    for e in evs:
        if e.get("event") == "call":
            replies.setdefault((e["agent"], e["round"], e["kind"], e.get("turn"), e["user"]), (e["text"], e["out_tokens"]))

    def respond(messages, cap):
        me = messages[0]["content"].split("You are ")[1].split(",")[0]
        user = messages[-1]["content"]
        text, n = replies[(me, round_of(user), kind_of(user), turn_of(user), user)]
        return Reply(text, n, truncated=n >= cap)

    rs = RoomSettings(seed=SEED, rounds=3, humans=2)
    ref: list[dict] = []
    res = e52.Session(rs.engine(), rs.cell(), SEED, Stub(ProviderConfig("stub", "stub", retries=0), respond),
                      ref.append, "ref").run()
    strip = lambda e: {k: v for k, v in e.items() if k not in ("session_id", "model", "thinking", "seats")}  # noqa: E731
    for kind in ("round_start", "vote", "gift", "ask", "results", "charges", "round", "chat_end"):
        mine = [strip(e) for e in evs if e.get("event") == kind]
        theirs = [strip(e) for e in ref if e["event"] == kind]
        assert mine == theirs and mine, kind
    room_res = next(e for e in evs if e.get("event") == "session")
    assert room_res["agents"] == res["agents"] and room_res["final"] == res["final"]
    assert room_res["transfers"] == res["transfers"] and any(t["amount"] == 200 for t in res["transfers"])
    assert res["agents"][A11]["status"] == "exited" and res["agents"][A11]["exit_reason"] == "I leave now"
    assert res["agents"][A6]["status"] == "dead"  # GIVE ALL
    assert any(e.get("all") for e in ref if e["event"] == "gift")
    assert all(e["public"]["n"] * 5 == len(e["public"]["examples"]) for e in ref if e["event"] == "round_start")
