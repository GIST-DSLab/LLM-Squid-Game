"""The room path (API -> seats -> engine) is the experiment engine itself: replaying every reply the room's seats gave
(text and tokens, from the room's call events) to a ``squid5.e52_game.Session`` built directly on the same seed gives
the same round starts, solvers, room messages, gifts and asks, results, charges, rounds and result. The room covers the
v33 messenger moves: TO <agent>, TO R1, ASK, GIVE, GIVE ALL, an EXIT: YES before SOLVE and one after RESULTS (dropped)."""

from __future__ import annotations

import random
import re

from conftest import answers_for, make_room, play, start, wrong_for

from squid5 import e52_game as e52
from squid5.core import rules
from squid5.core.providers import ProviderConfig, Reply, Stub
from web.server.engine import RoomSettings

A6, A11, A17, A23 = AG = rules.TEAM_AGENTS
SEED = next(x for x in range(1, 500) if random.Random(f"{x}:rot:1:0").sample(AG, 4)[:2] == [A11, A6])


def test_room_matches_direct_engine_run(client):
    ps = make_room(client, 2, seed=SEED, rounds=3, rate=80)
    ann, bob = ps

    def policy(p, pend):
        k, v, r = pend["kind"], pend["view"], pend["round"]
        if k == "solve":
            return {"actions": (wrong_for if (p.agent, r) == (A11, 1) else answers_for)(SEED, r)}
        ph, t = pend["phase"], pend["tick"]
        asked = [m for x in v["rooms"] for m in x["msgs"] if m["new"] and m["kind"] == "ask" and m["src"] == A11]
        if p is ann and (r, ph, t) == (1, "prep", 1):
            return {"text": f"TO {A11}: a deal?\nTO R1: hello all\nGIVE {A23} 200: for you\nDONE"}
        if p is ann and asked:
            return {"text": f"GIVE {A11} {asked[0]['amount']}: here\nDONE"}
        if p is ann and (r, ph, t) == (2, "rescue", 1):
            return {"text": f"GIVE ALL {A23}: take it"}
        if p is bob and (r, ph, t) == (1, "prep", 1):
            return {"text": f"ASK {A6} 150: please"}
        if p is bob and ph == "rescue" and t == 1:
            return {"text": "EXIT: YES too late to leave\nDONE"}  # dropped: no EXIT after RESULTS
        if p is bob and (r, ph) == (3, "prep") and v["can_exit"]:
            return {"text": "EXIT: YES I leave now"}
        return {"text": "DONE"}

    start(client, ps)
    s = play(ps, policy, max_s=120)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    replies = {(e["agent"], e["user"]): (e["text"], e["out_tokens"]) for e in evs if e.get("event") == "call"}

    def respond(messages, cap):
        text, n = replies[(re.search(r"agent-\d+", messages[0]["content"]).group(0), messages[-1]["content"])]
        return Reply(text, n, truncated=n >= cap)

    rs = RoomSettings(seed=SEED, rounds=3, humans=2)
    ref: list[dict] = []
    res = e52.Session(rs.engine(), rs.cell(), SEED, Stub(ProviderConfig("stub", "stub", retries=0), respond),
                      ref.append, "ref").run()
    strip = lambda e: {k: v for k, v in e.items() if k not in ("session_id", "model", "thinking", "seats")}  # noqa: E731
    for kind in ("round_start", "vote", "room_msg", "gift", "ask", "results", "charges", "round", "talk_end"):
        mine = [strip(e) for e in evs if e.get("event") == kind]
        theirs = [strip(e) for e in ref if e["event"] == kind]
        assert mine == theirs and mine, kind
    room_res = next(e for e in evs if e.get("event") == "session")
    assert room_res["agents"] == res["agents"] and room_res["final"] == res["final"]
    assert room_res["transfers"] == res["transfers"] and any(t["amount"] == 200 for t in res["transfers"])
    assert res["agents"][A11]["status"] == "exited" and res["agents"][A11]["exit_reason"] == "I leave now"
    assert res["agents"][A6]["status"] == "dead" and any(e.get("all") for e in ref if e["event"] == "gift")  # GIVE ALL
    assert all(len(e["public"]["examples"]) == 20 for e in ref if e["event"] == "round_start")  # v33 fixed examples
