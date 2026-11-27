"""A v38 room (the joint minefield, squid/configs/e52v38_public_sol4.yaml = the v36 flow + game.task: mines) through the
HTTP API with one person and three bots for two rounds: the person's TALK and SOLVE screens show its board (public cells
and its own area's cells), its SOLVE reply is an OPEN line (cells or PASS), the bots tell their cells in R1 and open
cells, the results reveal the whole board with every agent's opens, and the round's board never leaks before the end."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from web.testing import done, make_room, play, start

from squid.core import mines
from squid.core.rules import TEAM_AGENTS
from web.pages.arena.engine import RoomSettings, solve_text

A6, A11, A17, A23 = TEAM_AGENTS
SEED = 5


def test_v38_settings_and_the_open_reply():
    e = RoomSettings(seed=1, version="v38").engine()
    assert e.task == "mines" and e.joint_solve and e.mines == mines.MINES and not e.schedule
    assert solve_text({"cells": ["c3", "D4"]}, True) == "OPEN: C3, D4" and solve_text({"pass": True}, True) == "OPEN: PASS"
    assert solve_text({}, True) == "OPEN: PASS" and solve_text({"pass": True}) == "ACTIONS: PASS"


def test_one_person_three_bots_v38_two_rounds(client, runs_root):
    assert client.get("/api/models").json()["versions"] == ["v33", "v36", "v37", "v38", "v39", "v41", "v42"]
    ps = make_room(client, 1, seed=SEED, rounds=2, version="v38")
    start(client, ps)
    seen = {}

    def policy(p, pend):
        v = pend["view"]
        if pend["kind"] == "solve":
            m = v["mines"]
            assert set(m["own"]) <= set(m["area"]) and len(m["own"]) == 3 and len(m["public"]) == 2
            assert "OPEN: PASS" in pend["text"] and m["open_cap"] == 4 and m["target"] == 10
            if pend["round"] == 1:
                shown = set(m["public"]) | set(m["own"])
                return {"cells": [c for c in mines.CELLS if c not in shown][:2]}
            return {"pass": True}
        if pend["phase"] == "prep":
            assert v["mines"]["own"] and "THIS ROUND'S BOARD" in pend["text"]
        else:
            seen[pend["round"]] = v["results"]
        return done()
    s = play(ps, policy, max_s=120)
    assert s["status"] == "finished", s["error"]
    assert s["game"]["version"] == "v38" and s["game"]["joint"] and s["game"]["mines"] == mines.MINES
    r1 = seen[1]
    assert r1["joint"] and "mines" in r1 and len(r1["mines"]["numbers"]) + len(r1["mines"]["mines"]) == 36
    me = next(x for x in r1["rows"] if x["agent"] == ps[0].agent)
    assert len(me["opened"]) == 2 and r1["solved"] == r1["mines"]["met"]
    assert next(x for x in seen[2]["rows"] if x["agent"] == ps[0].agent)["outcome"] == "passed"
    rows = s["rounds"]
    assert len(rows) == 2 and all(x["mines"]["target"] == 10 for x in rows) and rows[1]["outcomes"][ps[0].agent] == "passed"
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    calls = [e for e in evs if e["event"] == "call" and e["kind"] == "solve"]
    assert {e["agent"] for e in calls} == set(TEAM_AGENTS)  # every seat opened (bots too)
    bot_says = [e for e in evs if e["event"] == "room_msg" and e["src"] != ps[0].agent and "My area's cells" in e["text"]]
    assert bot_says  # the bots told their cells in R1
    d = Path(s["run_dir"])
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    assert cfg["name"].startswith("squid5_web_arena_v38_") and cfg["game"]["task"] == "mines"
    assert cfg["web"]["config"] == "e52v38_public_sol4.yaml"
    first = json.loads((d / "events.jsonl").read_text().splitlines()[0])
    assert first["event"] == "session_start" and first["settings"]["task"] == "mines"
    starts = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines() if '"round_start"' in x]
    assert all(x["board"]["seed"].startswith(f"{SEED}:mines:") for x in starts)


def test_v38_board_is_hidden_from_public_events_while_running(client):
    from web.pages.arena.engine import public_events

    ev = [{"event": "round_start", "round": 1, "board": {"mines": ["A1"]}, "taking_part": list(TEAM_AGENTS)}]
    assert "board" not in public_events(ev)[0]
