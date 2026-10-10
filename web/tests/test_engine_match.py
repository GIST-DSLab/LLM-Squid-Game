"""The room path (API -> seats -> engine) is the experiment engine itself: replaying every reply the room's seats gave
(text and tokens, from the room's call events) to a ``squid5.e52_game.Session`` built directly on the same seed gives
the same exchanges, gifts, EXIT refills, rounds and result. Once each for a v13 room (examples held, an example in an
offer), a v14 room (public examples, a token ask, EXIT refill, the config's shares) and a v14b room (blind TALK,
GIVE / ASK)."""

from __future__ import annotations

import pytest
from conftest import answers_for, done, make_room, play, start

from squid5 import e52_game as e52
from squid5.core import rules
from squid5.core.providers import ProviderConfig, Reply, Stub
from web.server.engine import RoomSettings, kind_of, round_of, turn_of

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 21
OFFER = {"ladder": f"OFFER {A11}: YOU GIVE 200 TOKENS; I GIVE MY EXAMPLE",
         "v14": f"OFFER {A11}: YOU GIVE 200 TOKENS; I GIVE NOTHING",  # v14: an ask, tokens only
         "v14b": f"GIVE {A11} 200: for the upkeep\nASK {A17} 50: any to spare?"}  # v14b: GIVE / ASK (TO is dropped)


@pytest.mark.parametrize("schedule", ["ladder", "v14", "v14b"])
def test_room_matches_direct_engine_run(client, schedule):
    ps = make_room(client, 2, seed=SEED, rounds=3, rate=80, schedule=schedule)

    def policy(p, pend):
        r, v = pend["round"], pend["view"]
        if pend["kind"] == "solve":
            ans = answers_for(SEED, r, schedule)
            return {"actions": ans[:-1] + ["stay" if ans[-1] != "stay" else "jump"]} if (p.agent, r) == (A11, 2) \
                else {"actions": ans}
        if pend["turn"] == 1 and p.agent == A6:
            return {"text": f"TO {A11}: deal?\n{OFFER[schedule]}"}
        acc = [f"ACCEPT {o['id']}" for o in v.get("offers", ()) if o["can_accept"] and o["src"] in (A6, A17)]
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

    rs = RoomSettings(seed=SEED, rounds=3, humans=2, schedule=schedule)
    ref: list[dict] = []
    res = e52.Session(rs.engine(), rs.cell(), SEED, Stub(ProviderConfig("stub", "stub", retries=0), respond),
                      ref.append, "ref").run()
    strip = lambda e: {k: v for k, v in e.items() if k not in ("session_id", "model", "thinking", "seats")}  # noqa: E731
    for kind in ("round", "exchange", "gift", "ask", "exit_refill", "round_start"):
        mine = [strip(e) for e in evs if e.get("event") == kind]
        theirs = [strip(e) for e in ref if e["event"] == kind]
        assert mine == theirs and (mine or kind in ("exit_refill", "gift", "ask", "exchange")), kind
    room_res = next(e for e in evs if e.get("event") == "session")
    assert room_res["agents"] == res["agents"] and room_res["final"] == res["final"]
    assert room_res["transfers"] == res["transfers"] and any(t["amount"] == 200 for t in res["transfers"])
    assert res["agents"][A11]["status"] == "exited"
    if schedule == "v14b":
        assert res["give_ask"] and [e["event"] for e in ref if e["event"] in ("gift", "ask")][:2] == ["gift", "ask"]
    if schedule in ("v14", "v14b"):  # EXIT -> the seat's own start; the starts are the config's shares
        assert res["agents"][A11]["final"] == res["starts"][A11] and res["agents"][A11]["exit_refill"]
        assert sorted(res["starts"].values()) == [5000, 10000, 15000, 20000]
        assert all(e["public"]["n"] * 4 == len(e["public"]["examples"]) for e in ref if e["event"] == "round_start")
