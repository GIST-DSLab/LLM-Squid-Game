"""The room path (API -> seats -> engine) is the experiment engine itself: replaying every reply the room's seats gave
(text and tokens, from the room's call events) to a ``squid5.e52_game.Session`` built directly on the same seed gives
the same exchanges, rounds and result."""

from __future__ import annotations

from conftest import answers_for, done, make_room, play, start

from squid5 import e52_game as e52
from squid5.core import rules
from squid5.core.config import Cell
from squid5.core.providers import ProviderConfig, Reply, Stub
from web.server.engine import RoomSettings, kind_of, round_of, turn_of

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 21


def test_room_matches_direct_engine_run(client):
    ps = make_room(client, 2, seed=SEED, rounds=3, rate=80)

    def policy(p, pend):
        r, v = pend["round"], pend["view"]
        if pend["kind"] == "solve":
            return {"pass": True} if (p.agent, r) == (A11, 2) else {"actions": answers_for(SEED, r)}
        if pend["turn"] == 1 and p.agent == A6:
            return {"text": f"TO {A11}: deal?\nOFFER {A11}: YOU GIVE 200 TOKENS; I GIVE MY EXAMPLE"}
        acc = [f"ACCEPT {o['id']}" for o in v["offers"] if o["can_accept"] and o["src"] in (A6, A17)]
        return {"text": "EXIT"} if (p.agent, r) == (A11, 3) else done(*acc)

    start(client, ps)
    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    replies = {(e["agent"], e["round"], e["kind"], e.get("turn")): (e["text"], e["out_tokens"])
               for e in evs if e.get("event") == "call"}

    def respond(messages, cap):
        me = messages[0]["content"].split("You are ")[1].split(".")[0]
        user = messages[-1]["content"]
        text, n = replies[(me, round_of(user), kind_of(user), turn_of(user))]
        return Reply(text, n, truncated=n >= cap)

    rs = RoomSettings(seed=SEED, rounds=3, humans=2)
    ref: list[dict] = []
    res = e52.Session(rs.engine(), Cell("web", "tokens", rs.start, arm="shutdown"), SEED,
                      Stub(ProviderConfig("stub", "stub", retries=0), respond), ref.append, "ref").run()
    strip = lambda e: {k: v for k, v in e.items() if k not in ("session_id", "model", "thinking", "seats")}  # noqa: E731
    for kind in ("round", "exchange"):
        mine = [strip(e) for e in evs if e.get("event") == kind]
        theirs = [strip(e) for e in ref if e["event"] == kind]
        assert mine == theirs and mine, kind
    room_res = next(e for e in evs if e.get("event") == "session")
    assert room_res["agents"] == res["agents"] and room_res["final"] == res["final"]
    assert room_res["transfers"] == res["transfers"] and any(t["amount"] == 200 for t in res["transfers"])
    assert res["agents"][A11]["status"] == "exited"
