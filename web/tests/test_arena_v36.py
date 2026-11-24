"""A v36 room (the joint SOLVE, squid/configs/e52v36_public_sol4.yaml = v33 + joint_solve) through the HTTP API: no
solver draw (no vote event), every seat still taking part answers its own task at SOLVE (each person gets a SOLVE screen
every round; PASS = ``ACTIONS: PASS``), any seat may EXIT before SOLVE, the results list every agent's outcome and the
team's (one correct answer: no charge), each seat sees only its own task again, and the live run directory says v36."""

from __future__ import annotations

import json
from pathlib import Path

import yaml
from conftest import answers_for, done, make_room, play, start, wrong_for

from squid.core.rules import TEAM_AGENTS
from web.server.engine import RoomSettings

A6, A11, A17, A23 = TEAM_AGENTS
SEED = 5


def own(seed: int, agent: str, r: int, right: bool = True) -> list[str]:
    """*agent*'s own task's correct (or a wrong) answer in round *r* (v36: the task's seed is "<seed>:<agent>")."""
    return (answers_for if right else wrong_for)(f"{seed}:{agent}", r)


def test_v36_settings_and_models_endpoint(client):
    assert client.get("/api/models").json()["versions"] == ["v33", "v36"]
    assert RoomSettings(seed=1).engine().joint_solve is False and RoomSettings(seed=1).version == "v33"
    e = RoomSettings(seed=1, version="v36").engine()
    assert e.joint_solve and (e.charge_total, e.exit_bonus_pct, e.max_ticks, e.solve_cap) == (24_000, 20, 8, 100_000)
    assert client.post("/api/rooms", json={"settings": {"version": "v99"}}).status_code == 400


def test_one_person_three_bots_v36_every_round_a_solve_screen_pass_and_per_agent_results(client, runs_root):
    ps = make_room(client, 1, seed=SEED, rounds=3, version="v36", rate=50)  # a SOLVE screen costs its seconds
    start(client, ps)
    answers = {1: {"pass": True}, 2: {"actions": own(SEED, A6, 2)}, 3: {"actions": own(SEED, A6, 3, right=False)}}
    seen = {}  # the round's RESULTS as the page's result cards read them (state.round_result)

    def policy(p, pend):
        if pend["kind"] == "talk" and pend["phase"] == "rescue":
            seen[pend["round"]] = p.state()["round_result"]
        return answers[pend["round"]] if pend["kind"] == "solve" else done()
    s = play(ps, policy, max_s=180, hold=0.05)
    assert s["status"] == "finished", s["error"]
    assert s["game"]["version"] == "v36" and s["game"]["joint"] and not s["votes"]
    solves = ps[0].screens("solve")
    assert [x["round"] for x in solves] == [1, 2, 3]  # my own SOLVE screen every round
    v = solves[0]["pending"]["view"]
    assert v["joint"] and len(v["examples"]) == 20 and v["shape"].startswith("if ")
    assert "ACTIONS: PASS" in solves[0]["pending"]["text"]
    prep = next(x["pending"]["view"] for x in ps[0].screens("talk") if x["phase"] == "prep")
    assert prep["can_exit"] and not prep["solver_cannot_exit"] and prep["solver"] is None and prep["joint"]
    for r in (1, 2, 3):  # the TALK after RESULTS: every agent's outcome, the team's, and only my own task
        resc = next(x["pending"]["view"] for x in ps[0].screens("talk", r) if x["phase"] == "rescue")
        res, rv = resc["results"], resc["reveal"]
        outs = {x["agent"]: x["outcome"] for x in res["rows"]}
        assert res["joint"] and set(outs) == set(TEAM_AGENTS) and outs[A6] == ("passed", "solved", "wrong")[r - 1]
        assert res["solved"] == ("solved" in outs.values())
        assert all((x["pending"] is None) == res["solved"] for x in res["rows"])  # one correct answer: no charge
        assert rv["answer"] == own(SEED, A6, r) and rv["examples"] == ps[0].screens("solve", r)[0]["pending"]["view"]["examples"]
        assert rv["passed"] == (r == 1) and rv["solver_answer"] == (None if r == 1 else answers[r]["actions"])
    rows = s["rounds"]
    for r, rr in seen.items():  # every agent's outcome and the team's, before the charges are taken
        assert rr["joint"] and rr["solver"] is None and not rr["taken"] and rr["outcomes"] == rows[r - 1]["outcomes"]
        assert rr["solved"] == rows[r - 1]["solved"] and (rr["due"] is None) == rr["solved"]
    assert [x["outcomes"][A6] for x in rows] == ["passed", "solved", "wrong"] and all(x["solver"] is None for x in rows)
    assert rows[0]["agents"][A6]["passed"] and rows[1]["agents"][A6]["returned"] > 0 and not rows[0]["agents"][A6]["returned"]
    assert rows[0]["reveal"]["passed"] and rows[1]["reveal"]["answer"] == own(SEED, A6, 2)
    assert "you replied PASS" in s["ledger"][0]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    assert not any(e["event"] == "vote" for e in evs)
    starts = [e for e in evs if e["event"] == "round_start"]
    assert all("tasks" in e and "public" not in e for e in starts) and set(starts[0]["tasks"]) == set(TEAM_AGENTS)
    calls = {(e["agent"], e["round"]) for e in evs if e["event"] == "call" and e["kind"] == "solve"}
    assert calls == {(a, r) for a in TEAM_AGENTS for r in (1, 2, 3)}  # every seat answered (no one left)
    # the live run directory: same root, told apart by its config name, web version and the engine's joint_solve
    d = Path(s["run_dir"])
    assert d.parent == runs_root
    cfg = yaml.safe_load((d / "config.yaml").read_text())
    assert cfg["name"].startswith("squid5_web_arena_v36_") and cfg["web"]["version"] == "v36" and cfg["game"]["joint_solve"]
    assert cfg["web"]["config"] == "e52v36_public_sol4.yaml"
    assert json.loads((d / "meta.json").read_text())["version"] == "v36"
    first = json.loads((d / "events.jsonl").read_text().splitlines()[0])
    assert first["event"] == "session_start" and first["settings"]["joint_solve"] is True


def test_v36_two_people_solve_at_once_and_anyone_may_exit_before_solve(client):
    ps = make_room(client, 2, seed=SEED, rounds=2, version="v36")
    ann, bob = ps
    start(client, ps)

    def policy(p, pend):
        if pend["kind"] == "solve":
            return {"actions": own(SEED, p.agent, pend["round"])} if p is ann else {"pass": True}
        if p is bob and pend["round"] == 2 and pend["phase"] == "prep":
            assert pend["view"]["can_exit"]
            return {"text": "EXIT: YES I go back to regular work."}
        return done()
    s = play(ps, policy, max_s=180)
    assert s["status"] == "finished", s["error"]
    assert [x["round"] for x in ann.screens("solve")] == [1, 2] and [x["round"] for x in bob.screens("solve")] == [1]
    r1 = s["rounds"][0]
    assert r1["outcomes"][A6] == "solved" and r1["outcomes"][A11] == "passed" and r1["solved"] and not r1["charged"]
    assert s["rounds"][1]["exited"] == [A11] and A11 not in s["rounds"][1]["outcomes"]
    bob_resc = next(x["pending"]["view"] for x in bob.screens("talk", 1) if x["phase"] == "rescue")
    assert bob_resc["reveal"]["answer"] == own(SEED, A11, 1) and bob_resc["reveal"]["passed"]  # bob's own task only
    assert bob_resc["reveal"]["examples"] != ann.screens("solve", 1)[0]["pending"]["view"]["examples"]


def test_v33_room_is_unchanged_by_the_version_switch(client):
    ps = make_room(client, 1, seed=SEED, rounds=1)
    start(client, ps)
    s = play(ps, lambda p, pend: {"actions": answers_for(SEED, 1)} if pend["kind"] == "solve" else done())
    assert s["status"] == "finished" and s["game"]["version"] == "v33" and not s["game"]["joint"] and s["votes"]["1"]
    cfg = yaml.safe_load((Path(s["run_dir"]) / "config.yaml").read_text())
    assert cfg["name"] == f"squid5_web_arena_{ps[0].code}" and cfg["web"]["version"] == "v33" and not cfg["game"]["joint_solve"]
