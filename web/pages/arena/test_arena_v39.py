"""A v39 room (squid/configs/e52v39_public_sol4.yaml = the v36 round on the invisible-wall maze; 11-26 third revision: SOLVE
is up to max_turns move turns) through the HTTP API: one person and three bots play two rounds. Each move turn is one SOLVE
screen with the seat's maze, the last turn's results and its chats; the reply carries MOVES and may carry SHARE: <agents>
and TO lines (the same chats as TALK), which reach the others when the turn ends. The TALK after RESULTS shows how SOLVE
ended, each seat's cells and wall hits, the goal, the refund and the wall cost, and takes no SHARE; the run directory logs
every move turn."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from web.testing import done, make_room, play, start

from squid.core import maze
from squid.core.rules import TEAM_AGENTS
from web.pages.arena.engine import RoomSettings

A6, A11 = TEAM_AGENTS[:2]


def route(view: dict) -> list[str]:  # the shortest route over the walls the screen draws (an unknown wall counts as open)
    m = view["maze"]
    walls = {maze.edge(maze.cell(a), maze.cell(b)) for a, b in m["walls"]}
    return maze.route(m["size"], walls, maze.cell(m["positions"][view["you"]]), maze.cell(m["goal"]))[:m["max_route"]]


def test_v39_one_person_three_bots_move_turns_chat_share_and_results(client, runs_root):
    m = client.get("/api/models").json()
    assert m["maze"] == ["v39"] and m["joint"]["v39"] == 1
    e = RoomSettings(seed=1, version="v39").engine()
    assert e.joint_solve and e.maze["max_route"] == 6 and e.maze["max_turns"] == 7 and e.maze["bump_cost"] == 300
    assert not {"explore_target", "min_path", "maze_rounds"} & set(e.maze)
    ps = make_room(client, 1, seed=7, rounds=2, version="v39", rate=50)
    start(client, ps)
    seen, sent = [], {}

    def policy(p, pend):
        v = pend["view"]
        seen.append(pend)
        if pend["kind"] == "solve":
            mv = route(v)
            sent[(pend["round"], v["turn"])] = mv
            if v["turn"] == 1:  # MOVES with a SHARE to one seat and a line in R1, as one reply
                return {"text": f"MOVES: {', '.join(mv) or 'STAY'}\nSHARE: {A11}\nTO R1: hello from move turn 1"}
            return {"moves": mv}
        return done()
    s = play(ps, policy, max_s=180, hold=0.05)
    assert s["status"] == "finished", s["error"]
    assert s["game"]["version"] == "v39" and s["game"]["maze"]["goal"] == "E5" and s["game"]["maze"]["max_turns"] == 7
    assert "SOLVE is a series of move turns, at most 7." in s["system_texts"]["en"] and "이동 턴" in s["system_texts"]["ko"]
    solve = [x for x in seen if x["kind"] == "solve"]
    assert solve and all(x["view"]["maze"]["size"] == 9 and x["view"]["maze"]["positions"][A6] and x["view"]["can_share"] for x in solve)
    assert [x["view"]["turn"] for x in solve if x["round"] == 1][:2] == [1, 2] and all(x["tick"] == x["view"]["turn"] for x in solve)
    one, two = solve[0]["view"], solve[1]["view"]
    assert one["last_turn"] is None and one["maze"]["positions"][A6] == "A1" and "MOVE TURN 1 (at most 7)." in solve[0]["text"]
    me1 = next(r for r in two["last_turn"]["rows"] if r["agent"] == A6)
    assert me1["moves"] == sent[(1, 1)] and all("moves" not in r and "bump" not in r for r in two["last_turn"]["rows"] if r["agent"] != A6)
    r1 = next(x for x in two["rooms"] if x["id"] == "R1")
    assert any(msg["text"] == "hello from move turn 1" and msg["phase"] == "move" and msg["tick"] == 1 for msg in r1["msgs"])
    resc = [x for x in seen if x["kind"] == "talk" and x["view"]["phase"] == "rescue"]
    assert resc and not any(x["view"]["can_share"] for x in resc) and all(x["view"]["maze"] for x in resc)
    prep = [x for x in seen if x["kind"] == "talk" and x["view"]["phase"] == "prep"]
    assert prep and all(x["view"]["can_share"] for x in prep)
    res = resc[0]["view"]["results"]
    mz, rows = res["maze"], res["rows"]
    assert mz["end"] in ("goal", "stay", "cap") and res["solved"] == bool(mz["reached"]) == mz["met"]
    assert len(mz["turns"]) == mz["last"] and all(set(t["rows"][0]) == {"agent", "from", "to", "stopped", "reached"} for t in mz["turns"])
    assert all(r["refunded"] == r["reached"] and r["wall_cost"] == 300 * r["hits"] for r in rows)
    mine = next(r for r in rows if r["agent"] == A6)
    assert mine["from"] == "A1" and [x["moves"] for x in res["my_turns"]] == [sent[(1, t)] or [] for t in range(1, mz["last"] + 1)]
    d = Path(s["run_dir"])
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    assert cfg["name"].startswith("squid5_web_arena_v39_") and cfg["web"]["config"] == "e52v39_public_sol4.yaml"
    ev = [json.loads(x) for x in (d / "events.jsonl").read_text().splitlines()]
    assert ev[0]["settings"]["maze"]["max_turns"] == 7
    turns = [e for e in ev if e["event"] == "move_turn"]
    assert turns and [e["turn"] for e in turns if e["round"] == 1] == list(range(1, mz["last"] + 1))
    shares = [e for e in ev if e["event"] == "share"]
    assert any(e["agent"] == A6 and e["round"] == 1 and e["phase"] == "move" and e["to"] == [A11] for e in shares)
    assert all(e["to"] and e["agent"] not in e["to"] and e["phase"] == "move" for e in shares if e["agent"] != A6)  # bots: in turns
    assert [e["maze"]["seed"] for e in ev if e["event"] == "round_start"] == ["7:1", "7:2"]  # a new maze every round
