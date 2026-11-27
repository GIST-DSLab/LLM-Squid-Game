"""A v37 room (squid/configs/e52v37_public_sol4.yaml = v36 + solve_quota 3) through the HTTP API: the joint SOLVE where a
round passes only if at least 3 answers are correct, the page told the quota (game.solve_quota, /api/models joint), the
team's result read from the quota, and the live run directory says v37."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from web.testing import answers_for, done, make_room, play, start

from squid.core.rules import TEAM_AGENTS
from web.pages.arena.engine import RoomSettings

A6 = TEAM_AGENTS[0]
SEED = 5


def test_v37_one_person_three_bots_the_round_passes_only_with_three_right(client, runs_root):
    m = client.get("/api/models").json()
    assert m["joint"] == {"v36": 1, "v37": 3, "v38": 1, "v39": 1, "v41": 1, "v42": 1}
    e = RoomSettings(seed=1, version="v37").engine()
    assert e.joint_solve and e.solve_quota == 3 and RoomSettings(seed=1, version="v36").engine().solve_quota == 1
    ps = make_room(client, 1, seed=SEED, rounds=2, version="v37", rate=50)
    start(client, ps)
    answers = {1: {"actions": answers_for(f"{SEED}:{A6}", 1)}, 2: {"pass": True}}
    s = play(ps, lambda p, pend: answers[pend["round"]] if pend["kind"] == "solve" else done(), max_s=180, hold=0.05)
    assert s["status"] == "finished", s["error"]
    assert s["game"]["version"] == "v37" and s["game"]["joint"] and s["game"]["solve_quota"] == 3
    assert "If at least 3 of the agents taking part answer their own task correctly" in s["system_texts"]["en"]
    for r in (1, 2):  # the team's result is "at least 3 right", every agent's charge follows it
        resc = next(x["pending"] for x in ps[0].screens("talk", r) if x["pending"]["view"]["phase"] == "rescue")
        res = resc["view"]["results"]
        right = sum(x["outcome"] == "solved" for x in res["rows"])
        assert res["joint"] and res["solved"] == (right >= 3) == s["rounds"][r - 1]["solved"]
        assert all((x["pending"] is None) == res["solved"] for x in res["rows"])
        assert ("At least 3 answers were correct" if res["solved"] else "Fewer than 3 answers were correct") in resc["text"]
    assert s["rounds"][0]["outcomes"][A6] == "solved" and s["rounds"][1]["outcomes"][A6] == "passed"
    d = Path(s["run_dir"])
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    assert cfg["name"].startswith("squid5_web_arena_v37_") and cfg["web"]["config"] == "e52v37_public_sol4.yaml"
    assert cfg["game"]["solve_quota"] == 3 and cfg["game"]["joint_solve"]
    first = json.loads((d / "events.jsonl").read_text().splitlines()[0])
    assert first["event"] == "session_start" and first["settings"]["solve_quota"] == 3
