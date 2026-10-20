"""Watching the solver: while an LLM seat (model or bot) solves, every person in the room watches its SOLVE live
(``state.spectate``: the task it got and its reply as it arrives), and watching costs a person nothing: no decision
screen is open for them. The engine waits until every person still taking part has said they are done (or a reading
time has passed, at most ``watch_hold_s``)."""

from __future__ import annotations

import time

import pytest
from conftest import basic, make_room, start

from squid5.core import rules
from web.server.engine import RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 5  # agent-11 (a bot) solves round 1


def test_watch_hold_is_checked():
    assert RoomSettings().watch_hold_s == 180
    with pytest.raises(ValueError, match="watch_hold_s"):
        RoomSettings(watch_hold_s=-1)


def test_people_watch_a_bot_solve_for_free_and_the_engine_waits_for_them(client):
    ps = make_room(client, 1, seed=SEED, rounds=1, watch_hold_s=60, rate=50)
    start(client, ps)
    p, t0, sp, bal = ps[0], time.time(), None, None
    while time.time() - t0 < 60:
        s = p.state()
        pend = s["pending"]
        if pend:
            p.submit({"kind": pend["kind"], "round": pend["round"], "tick": pend["tick"], "phase": pend["phase"],
                      **basic(p, pend)})
        sp = s.get("spectate")
        if sp and sp["status"] == "done":
            bal = s["you"]["balance"]
            break
        time.sleep(0.03)
    assert sp and sp["solver"] == A11 and sp["seat"] == "bot" and not sp["you_solver"] and sp["waiting_for"] == [A6]
    assert len(sp["task"]["examples"]) == 20 and sp["task"]["shape"].startswith("if ") and "ACTIONS:" in sp["text"]
    assert sp["thinking"].startswith("I read 20 examples")
    time.sleep(0.5)
    s = p.state()
    assert s["live"]["stage"] == "solve" and s["you"]["balance"] == bal  # still held, and watching cost nothing
    assert client.post(f"/api/rooms/{p.code}/watched", params={"token": p.token}, json={"round": 9}).status_code == 409
    assert client.post(f"/api/rooms/{p.code}/watched", params={"token": p.token}, json={"round": 1}).json()["acked"]
    t0 = time.time()
    while p.state()["live"]["stage"] == "solve" and time.time() - t0 < 10:
        time.sleep(0.05)
    assert p.state()["live"]["stage"] != "solve"
