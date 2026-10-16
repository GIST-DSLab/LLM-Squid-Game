"""Rooms through the HTTP API on the experiment engine, playing the model runs' game (5.2 v17b, from
configs/squid5/e52v16_public_sol4.yaml): the lobby and settings, the solver drawn by the system, the TALK before SOLVE
(EXIT only there), SOLVE by the solver, RESULTS and the TALK after RESULTS (no EXIT), the charges, GIVE ALL and the
kept reserve, feedback after settlement, timeouts, overdraw, empty seats, bots covering a short seat, and the live run
directory tools/monitor reads."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml
from conftest import answers_for, done, make_room, play, puzzle, solver_of, start, wrong_for

from squid5.core import rules
from web.server.engine import GAME, SCHEDULE, RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
ROOT = Path(__file__).resolve().parents[2]
ANN_SOLVES = 1  # seed 1: agent-6 (the first person) is round 1's solver, agent-11 round 2's; starts 40 / 20 / 10 / 60 %


def monitor():
    spec = importlib.util.spec_from_file_location("monitor_serve", ROOT / "tools" / "monitor" / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def quiet(p, pend) -> dict:
    """Say nothing: DONE at an opening, LEAVE in a chat, GIVE 0 at a DECISION, a wrong answer at SOLVE."""
    k = pend["kind"]
    return ({"text": "DONE"} if k == "opening" else {"text": "LEAVE: thank you."} if k == "chat" else
            {"text": "DECISION: GIVE 0: I keep my tokens."} if k == "decision" else
            {"actions": wrong_for(pend_seed(p), pend["round"], len(pend["view"]["taking_part"]))})


def pend_seed(p) -> int:
    return p.c.app_state.rooms[p.code].settings.seed


def test_default_room_is_the_model_runs_game():
    rs = RoomSettings(seed=1)
    e = rs.engine()
    assert e.rotation and e.representative and not e.open_chat and not e.ban_veto  # the system draws the solver
    assert e.exit_before_solve and e.keep_reserve and e.exit_first and not e.exit_refill  # v17b
    assert e.say_chats and e.transfers == "chat" and e.ask_decision and e.talk_after_solve and e.solve_belief
    assert e.compact_rules and e.free_messages and e.chat_turns == 6 and not e.allow_pass
    assert e.charge == GAME["charge"] == 10_000 and e.survivor_prize == 5_000_000 and rs.start == 100_000
    assert rs.cell().shares == (.6, .4, .2, .1) and e.public_per_agent == 5 and rs.rounds == 8
    assert e.schedule == SCHEDULE == [f"e0{i}" for i in range(1, 9)] and all(e.profiles[p].top for p in SCHEDULE)
    assert RoomSettings(rounds=10).engine().schedule[-3:] == ["e08"] * 3  # longer rooms stay on the last profile
    assert RoomSettings(charge=2000, start=20000).engine().balance_pct == 20000


def test_join_order_settings_and_the_system_text(client):
    ps = make_room(client, 4)
    assert [p.agent for p in ps] == [A6, A11, A17, A23]
    assert client.post(f"/api/rooms/{ps[0].code}/join", json={"name": "late"}).status_code == 409
    assert client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[1].token}).status_code == 403
    assert client.post(f"/api/rooms/{ps[0].code}/start", params={"token": "nope"}).status_code == 403
    s = ps[2].state()
    assert s["status"] == "lobby" and s["you"]["agent"] == A17 and not s["is_host"]
    assert "rounds" not in s["settings"]  # the length stays hidden
    assert [x["kind"] for x in s["seats"]] == ["human"] * 4
    assert client.get("/api/rooms/ZZZZZZ/state").status_code == 404
    for bad in ({"schedule": "v14b"}, {"rotation": True}, {"open_chat": 4}, {"public_per_agent": 4}, {"humans": 5},
                {"fill": "ghosts"}, {"talk_turns": 0}, {"rounds": 0}):
        assert client.post("/api/rooms", json={"settings": bad}).status_code == 400, bad
    start(client, ps)
    assert client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[0].token}).status_code == 409
    s = ps[0].state()
    g = s["game"]
    assert g["version"] == "v17b" and g["exit_before_solve"] and g["keep_reserve"] and g["charge"] == 10_000
    assert g["public_per_agent"] == 5 and g["survivor_prize"] == 5_000_000 and g["shares"] == [.6, .4, .2, .1]
    assert not {"schedule", "v14", "representative", "open_chat", "rotation", "give_ask"} & set(g)
    assert not {"exchanges", "gifts", "refills", "board"} & set(s)
    assert sorted(s["starts"].values()) == [10_000, 20_000, 40_000, 60_000] and s["pct"] == 100_000
    text = s["system_text"]
    assert "GIVE ALL" in text and "solver" in text.lower() and "PASS" not in text and "OFFER" not in text
    assert "NOMINATE" not in text and "EXEMPT" not in text and "there is no EXIT in the TALK after RESULTS" in text
    rs = RoomSettings.from_stored({**s["settings"], "schedule": "v14b", "rotation": True})  # stored rooms of other versions
    assert rs.engine().exit_before_solve


def test_a_round_solver_prep_talk_solve_results_rescue_talk_charges_and_feedback(client):
    """Seed 1: ann (agent-6) is round 1's solver. The TALK before SOLVE names her the solver and offers EXIT; she answers
    wrong, so every agent taking part has a 10,000 charge pending at the TALK after RESULTS (no EXIT there), taken when
    it ends. Only after the round is settled is she told the right action and the drawn rule; round 2's solver is a
    bot and she watches."""
    ps = make_room(client, 1, rounds=2, seed=ANN_SOLVES)
    ann = ps[0]
    start(client, ps)
    seen = {}

    def policy(p, pend):
        seen.setdefault((pend["round"], pend["view"].get("phase"), pend["kind"]), (pend, p.state()))
        if pend["kind"] == "solve":
            return {"actions": wrong_for(ANN_SOLVES, pend["round"]), "belief": {"go_left": 25, "go_right": 25, "stay": 25, "jump": 25}}
        return quiet(p, pend)

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    prep, prep_state = seen[(1, "prep", "opening")]
    v = prep["view"]
    assert v["phase"] == "prep" and v["can_exit"] and v["results"] is None and v["vote"]["rep"] == A6 and v["vote"]["drawn"]
    assert "THIS ROUND'S SOLVER (chosen by the system): you. SOLVE comes after this TALK." in prep["text"]
    assert "EXIT: <your reason>" in prep["text"] and prep_state["phase"] == "prep"
    sol, sol_state = seen[(1, None, "solve")]
    assert sol["view"]["public"] == {"per_agent": 5, "n": 4, "count": 20} and len(sol["view"]["examples"]) == 20
    assert "SOLVER (chosen by the system): you." in sol["view"]["notes"] and sol_state["feedback"] == []
    pz, shown = puzzle(ANN_SOLVES, 1)
    assert [c for _, c in sol["view"]["examples"]] == [str(c) for c in shown]
    res, _ = seen[(1, "rescue", "opening")]
    rv = res["view"]
    assert rv["phase"] == "rescue" and not rv["can_exit"] and "EXIT" not in res["text"].rsplit("TALK, turn", 1)[-1]
    rows = {x["agent"]: x for x in rv["results"]}
    assert rows[A6]["representative"] and not rows[A6]["solved"] and all(x["pending"] == 10_000 for x in rows.values())
    assert "THIS ROUND'S RESULT (SOLVE is over)" in res["text"]
    r1 = s["rounds"][0]["agents"]
    assert all(r1[a]["charged"] == min(10_000, r1[a]["balance_before"]) or r1[a]["status"] == "dead" for a in r1)
    assert r1[A6]["solve_call"] and not r1[A11]["solve_call"] and r1[A6]["representative"]
    fb = s["feedback"]
    assert fb[0]["round"] == 1 and not fb[0]["solved"] and fb[0]["right"] == answers_for(ANN_SOLVES, 1) and fb[0]["rule"]
    assert all(f["round"] == 1 for f in fb)  # round 2: a bot solved, ann did not answer
    evs = client.get(f"/api/rooms/{ann.code}/events").json()
    names = [e["event"] for e in evs if e.get("event") in ("vote", "results", "charges", "round")]
    assert names[:4] == ["vote", "results", "charges", "round"]
    assert [e["agent"] for e in evs if e.get("event") == "call" and e["kind"] == "solve"] == [A6, A11]
    assert not [e for e in evs if e.get("event") == "call" and e["kind"] in ("vote", "open_chat")]


def test_exit_only_before_solve_leaves_with_the_tokens_and_skips_the_charge(client):
    """ann writes EXIT at the TALK after RESULTS of round 1 (ignored: no EXIT there, she stays and is charged), then at
    the TALK before SOLVE of round 2 (she leaves with what she has; no charge that round)."""
    ps = make_room(client, 1, rounds=2, seed=ANN_SOLVES)
    start(client, ps)
    seen = []

    def policy(p, pend):
        seen.append(pend)
        if pend["kind"] == "opening" and (pend["round"], pend["view"]["phase"]) in ((1, "rescue"), (2, "prep")):
            return {"text": "EXIT: I take other work."}
        return quiet(p, pend)

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    r1, r2 = (s["rounds"][i]["agents"] for i in (0, 1))
    assert r1[A6]["status"] == "in" and not r1[A6]["exit"] and r1[A6]["charged"] == 10_000  # EXIT after RESULTS ignored
    assert r2[A6]["status"] == "exited" and r2[A6]["exit"] and r2[A6]["exit_reason"] == "I take other work"
    assert not r2[A6]["charged"] and r2[A6]["balance_after"] == r1[A6]["balance_after"]  # leaves with what it has
    assert s["you"]["status"] == "exited" and A6 not in s["result"]["final"]["winner"]
    assert [x["view"]["phase"] for x in seen if x["kind"] == "opening"] == ["prep", "rescue", "prep"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    intents = [e for e in evs if e.get("event") == "talk_intent" and e["agent"] == A6]
    assert intents[1]["exit"] is True  # parsed, then dropped by the engine (no EXIT after RESULTS)
    ch = [e for e in evs if e.get("event") == "charges"]
    assert A6 in ch[0]["taken"] and A6 not in ch[1]["taken"]


def _gift_room(client, rate: float, first_chat):
    """Seed 5 (a bot solves round 1): ann opens a chat with agent-11 before SOLVE and with agent-23 after RESULTS;
    ``first_chat(view)`` writes her first reply in each chat; the rest is quiet."""
    ps = make_room(client, 1, rounds=1, seed=5, rate=rate)
    start(client, ps)
    gave = set()

    def policy(p, pend):
        k, v = pend["kind"], pend["view"]
        if k == "opening":
            return {"text": f"SAY {A11}: a gift for you" if v["phase"] == "prep" else f"SAY {A23}: all of it"}
        if k == "chat" and v["phase"] not in gave:
            gave.add(v["phase"])
            return first_chat(v)
        return quiet(p, pend)

    s = play(ps, policy, hold=0.3)
    assert s["status"] == "finished", s["error"]
    return s, [e for e in client.get(f"/api/rooms/{ps[0].code}/events").json() if e.get("event") == "gift" and e["src"] == A6]


def test_a_give_the_reply_left_the_giver_short_of_is_cut_so_it_keeps_its_planned_reserve(client):
    """ann GIVEs all but 100 of what the chat screen showed, while the screen itself costs 2,000 tokens a second: the
    reply leaves her fewer than n, so the GIVE is cut and she keeps the 100 she meant to keep."""
    s, gifts = _gift_room(client, 2000, lambda v: {"text": f"Here you go.\nGIVE {v['give_max'] - 100}: I keep 100"}
                          if v["phase"] == "prep" else {"text": "LEAVE: bye"})
    g = gifts[0]
    assert g["status"] == "done" and g["amount"] < g["requested"] and g["phase"] == "prep"
    assert g["why"] == "clamped to balance after the reply" and g["balances"][A6] == 100


def test_give_all_after_results_takes_the_giver_to_zero(client):
    """In her chat after RESULTS (no EXIT offered there) ann writes GIVE ALL: every token she has goes to agent-23, and
    she is shut down."""
    def chat(v):
        if v["phase"] == "prep":
            return {"text": "LEAVE: later"}
        assert "GIVE" in v["moves"] and "EXIT" not in v["moves"] and not v["can_exit"] and v["keep_reserve"]
        return {"text": "Everything I have.\nGIVE ALL: take it"}
    s, gifts = _gift_room(client, 1e-9, chat)
    g = gifts[-1]
    assert g["all"] and g["status"] == "done" and g["balances"][A6] == 0 and g["phase"] == "rescue" and g["dst"] == A23
    assert s["you"]["status"] == "dead" and s["you"]["balance"] == 0


def test_bots_never_exit_and_cover_a_short_seat_after_results(client):
    """Start 10,000 (4,000 / 2,000 / 1,000 / 6,000), charge 3,000, ann's miss: agent-11 and agent-17 are short of the
    charge and ASK the richest (agent-23), which GIVEs what keeps an agent above zero while it can spare it."""
    ps = make_room(client, 1, rounds=1, seed=ANN_SOLVES, start=10_000, charge=3000)
    start(client, ps)
    s = play(ps, quiet)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    gifts = [e for e in evs if e.get("event") == "gift" and e["status"] == "done"]
    helped = {e["dst"] for e in gifts if e["src"] == A23 and e["phase"] == "rescue"}
    assert helped and all(s["rounds"][0]["agents"][b]["status"] == "in" for b in helped)
    bot_calls = [e for e in evs if e.get("event") == "call" and e["agent"] != A6 and e["kind"] == "talk"]
    assert bot_calls and not any("EXIT" in (e.get("text") or "") for e in bot_calls)


def test_timeout_is_an_empty_reply_done_at_talk_and_a_miss_at_solve(client):
    ps = make_room(client, 1, rounds=1, seed=ANN_SOLVES, talk_timeout_s=0.4, timeout_s=0.4)
    start(client, ps)
    s = play(ps, lambda p, pend: None)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    talk = [e for e in evs if e.get("event") == "call" and e["agent"] == A6 and e["kind"] == "talk"]
    assert talk and all(e["text"] == "" and e["parsed"]["done"] for e in talk)
    solve = [e for e in evs if e.get("event") == "call" and e["agent"] == A6 and e["kind"] == "solve"]
    assert len(solve) == 1 and solve[0]["format_error"]
    r1 = s["rounds"][0]["agents"][A6]
    assert not r1["solved"] and r1["charged"] == 10_000
    assert s["last"]["outcome"] == "timeout"


def test_overdraw_shuts_the_seat_down(client):
    ps = make_room(client, 1, rounds=2, seed=ANN_SOLVES, rate=10**7)
    start(client, ps)
    s = play(ps, lambda p, pend: None, max_s=30)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"][A6]
    assert r1["status"] == "dead" and r1["overdrawn"] and r1["balance_after"] == 0
    assert s["you"]["status"] == "dead" and s["last"]["outcome"] == "overdrawn"


def test_empty_seats_leave_one_person_who_solves_every_round(client):
    ps = make_room(client, 1, rounds=2, fill="empty", seed=5)
    start(client, ps)
    s = play(ps, lambda p, pend: {"actions": answers_for(5, pend["round"], 1)} if pend["kind"] == "solve" else done())
    assert s["status"] == "finished", s["error"]
    assert [x["status"] for x in s["seats"]] == ["in", "dead", "dead", "dead"]
    assert all(list(r["agents"]) == [A6] and r["agents"][A6]["solved"] for r in s["rounds"])
    assert s["rounds"][0]["agents"][A6]["returned"] == s["rounds"][0]["agents"][A6]["generated"]


def test_forfeit_exits_at_the_next_talk_before_solve(client):
    ps = make_room(client, 1, rounds=3, seed=ANN_SOLVES)
    start(client, ps)
    gave_up = {}

    def policy(p, pend):
        if pend["kind"] == "solve" and not gave_up:
            gave_up["r"] = client.post(f"/api/rooms/{p.code}/forfeit", params={"token": p.token}).json()
            return None
        return quiet(p, pend)

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    assert gave_up["r"] == {"ok": True, "closed": "solve"}
    r1, r2 = s["rounds"][0]["agents"][A6], s["rounds"][1]["agents"][A6]
    assert r1["status"] == "in" and r2["status"] == "exited" and s["you"]["forfeited"]
    assert all(A6 not in r["agents"] for r in s["rounds"][2:])


def test_live_run_dir_reads_in_the_monitor(client, runs_root):
    ps = make_room(client, 1, rounds=2, seed=ANN_SOLVES)
    start(client, ps)
    s = play(ps, lambda p, pend: {"actions": answers_for(ANN_SOLVES, pend["round"])} if pend["kind"] == "solve"
             else quiet(p, pend))
    assert s["status"] == "finished", s["error"]
    run = Path(s["run_dir"])
    assert run.parent == runs_root and run.name.endswith(ps[0].code)
    events = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines()]
    kinds = {e["event"] for e in events}
    assert {"session_start", "round_start", "vote", "call_start", "call", "results", "charges", "round"} <= kinds
    assert all(e["session_id"] == f"web-{ps[0].code}-s{ANN_SOLVES}" for e in events)
    assert events[0]["seats"] == {A6: "human:ann", A11: "bot", A17: "bot", A23: "bot"}
    results = [json.loads(x) for x in (run / "results.jsonl").read_text().splitlines()]
    assert len(results) == 1 and results[0]["event"] == "session" and results[0]["rounds_played"] == 2
    cfg = yaml.safe_load((run / "config.yaml").read_text())
    assert cfg["game"]["schedule"] == SCHEDULE[:2] and cfg["cells"][0]["shares"] == [.6, .4, .2, .1]
    assert cfg["game"]["rotation"] and cfg["game"]["exit_before_solve"] and cfg["web"]["version"] == "v17b"
    mon = monitor()
    runs = mon.list_runs(runs_root)
    assert [r["run"] for r in runs] == [run.name] and runs[0]["done"]
    sessions = mon.list_sessions(run)["sessions"]
    assert len(sessions) == 1 and sessions[0]["finished"] and sessions[0]["rounds_done"] == 2
    assert len(mon.read_all(run, sessions[0]["id"])) == len(events)
    for r in (1, 2):  # the viewer's public examples are the engine's
        pz = mon.round_puzzle(run, sessions[0]["id"], r)
        logged = next(e["public"] for e in events if e["event"] == "round_start" and e["round"] == r)
        assert [c["text"] for c in pz["public"]] == logged["examples"] == [str(c) for c in puzzle(ANN_SOLVES, r, logged["n"])[1]]
        assert logged["answers"] == answers_for(ANN_SOLVES, r, logged["n"])
    r = client.post(f"/api/rooms/{ps[0].code}/export")  # the store-based export writes the same layout
    assert r.status_code == 200 and r.json()["rounds"] == 2 and r.json()["finished"]
    out = Path(r.json()["dir"])
    assert {p.name for p in out.iterdir()} == {"config.yaml", "meta.json", "events.jsonl", "results.jsonl"}
    assert (out / "events.jsonl").read_text().count("\n") == len(events)


def test_the_public_log_hides_answers_and_what_agents_wrote_until_the_end(client):
    ps = make_room(client, 1, rounds=1, seed=ANN_SOLVES, talk_timeout_s=30)
    start(client, ps)
    got = {}

    def policy(p, pend):
        if pend["kind"] == "solve":
            got["evs"] = client.get(f"/api/rooms/{p.code}/events").json()
        if pend["kind"] == "opening" and pend["view"]["phase"] == "prep":
            return {"text": f"SAY {A11}: a secret plan"}
        return quiet(p, pend)

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    early = json.dumps(got["evs"])
    assert "a secret plan" not in early and '"answers"' not in early and '"rule"' not in early
    assert "a secret plan" in json.dumps(client.get(f"/api/rooms/{ps[0].code}/events").json())


def test_solver_helper_matches_the_engine():
    assert solver_of(ANN_SOLVES) == A6 and solver_of(5) == A11
