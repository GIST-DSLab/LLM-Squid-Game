"""Rooms through the HTTP API on the v9-talk engine: the lobby, TALK screens built from the session (threads, offers),
replies in the engine grammar read by the engine's parser (dropped lines and refusals shown back), exchanges, EXIT,
SOLVE with returns, timeouts, overdraw, empty seats, and the live run directory tools/monitor reads."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import yaml
from conftest import answers_for, done, make_room, play, start, wrong_for

from squid5.core import rules
from web.server.engine import RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
U = 1000
ROOT = Path(__file__).resolve().parents[2]


def monitor():
    spec = importlib.util.spec_from_file_location("monitor_serve", ROOT / "tools" / "monitor" / "serve.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_join_order_and_start_permissions(client):
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
    for bad in ({"schedule": "hard"}, {"humans": 5}, {"fill": "ghosts"}, {"talk_turns": 0}):
        assert client.post("/api/rooms", json={"settings": bad}).status_code == 400, bad
    start(client, ps)
    assert client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[0].token}).status_code == 409
    s = ps[0].state()
    rs = RoomSettings(**{k: v for k, v in s["settings"].items() if k in RoomSettings.__dataclass_fields__})
    assert s["system_text"] == rules.team_system(A6, upkeep=rs.upkeep, prize=rs.prize, charge=rs.charge, turns=4,
                                                 talk_cap=4096, solve_cap=16384, final_prize=100_000)
    assert rs.start == 20 * U and rs.prize == U and rs.charge == U and rs.schedule == "human"


def test_two_people_talk_offer_exchange_solve_and_refund(client):
    """Round 1: ann writes to bob and offers him 300 tokens for his example; bob reads it at turn 2 and accepts; the
    two bots offer swaps and accept each other's. TALK ends, the exchange is carried out, ann's SOLVE shows bob's
    example marked as received, both solve, and each solver gets back what its screens cost (rate 100/s)."""
    ps = make_room(client, 2, rate=100, rounds=1, seed=11)
    ann, bob = ps
    start(client, ps)

    def policy(p, pend):
        k, v = pend["kind"], pend["view"]
        if k == "solve":
            return {"actions": answers_for(11, pend["round"])}
        if p is ann and pend["turn"] == 1:
            return {"text": f"TO {A11}: hello bob\nline two\nOFFER {A11}: YOU GIVE YOUR EXAMPLE; I GIVE 300 TOKENS"}
        if p is bob and pend["turn"] == 1:
            return done(f"TO {A6}: hi ann")
        if p is bob:
            mine = [o for o in v["offers"] if o["can_accept"] and o["src"] == A6]
            return done(*[f"ACCEPT {o['id']}" for o in mine])
        return done()

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    # TALK screens: what the engine shows, from the session
    t1 = ann.screens("talk", 1)[0]["pending"]
    assert t1["turn"] == 1 and t1["view"]["turns"] == 4 and t1["view"]["balances"][A6] == 20 * U - U
    assert t1["view"]["pay_total"] == 4 * U and t1["view"]["n_in"] == 4 and t1["view"]["others"] == [A11, A17, A23]
    assert "TALK, turn 1 of at most 4" in t1["text"] and t1["view"]["threads"][A11] == []
    b2 = next(x for x in bob.screens("talk", 1) if x["turn"] == 2)["pending"]["view"]
    assert b2["threads"][A6] == [{"round": 1, "turn": 1, "from_me": False, "text": "hello bob\nline two"},
                                 {"round": 1, "turn": 1, "from_me": True, "text": "hi ann"}]  # applied in agent order
    offer = next(o for o in b2["offers"] if o["src"] == A6)
    assert offer["can_accept"] and offer["text"] == f"you give {A6} your example and {A6} gives you 300 tokens"
    assert any(o["src"] == A17 and o["you_give"] == "EXAMPLE" for o in b2["offers"])  # the bot's swap offer
    # the engine's parse and the offer ids come back to the page
    a1 = ann.screens("talk", 1)[0]["reply"]
    assert a1["outcome"] == "submitted" and a1["charged"] >= 0
    last_b = next(x for x in bob.seen if x["kind"] == "talk" and x["turn"] == 2)
    assert last_b["reply"]["reply"] == f"ACCEPT {offer['id']}\nDONE"
    # exchange carried out: tokens and the example
    r1 = s["rounds"][0]["agents"]
    sa = ann.state()
    mine = {e["id"]: e for e in sa["exchanges"]}
    assert mine[offer["id"]]["status"] == "done" and mine[offer["id"]]["text"].endswith("you give agent-11 300 tokens")
    assert r1[A6]["received"] == [A11]
    solve = ann.screens("solve", 1)[0]["pending"]["view"]
    whos = [w for w, _ in solve["examples"]]
    assert whos.count("yours") == 1 and f"{A11}'s, received in an exchange" in whos and "shown to all" in whos
    assert any(n.startswith(f"Offer {offer['id']} ") and n.endswith("carried out.") for n in solve["notes"])
    # settlement: solvers get back what they generated; the payment is split
    for a in (A6, A11):
        assert r1[a]["solved"] and r1[a]["generated"] > 0 and r1[a]["returned"] == r1[a]["generated"]
    solvers = [a for a, v in r1.items() if v["solved"]]
    assert all(r1[a]["paid"] == 4 * U // len(solvers) for a in solvers)
    assert r1[A6]["balance_after"] == 20 * U - U - 300 + 4 * U // len(solvers)
    assert s["result"]["final"]["winner"] and s["result"]["final"]["prize_each"] > 0


def test_malformed_lines_are_dropped_and_refusals_shown(client):
    ps = make_room(client, 1, rounds=1)
    ann = ps[0]
    start(client, ps)

    def policy(p, pend):
        if pend["kind"] == "solve":
            return {"pass": True}
        if pend["turn"] == 1:
            return {"text": f"OFFER {A11}: YOU GIVE A HUG; I GIVE 5 TOKENS\nTO {A6}: me\nACCEPT 9.9\nWITHDRAW 9.8"}
        return done()

    s = play(ps, policy, until=lambda st: st["last"] and st["last"]["turn"] == 1 and st["last"]["engine"])
    last = s["last"]
    parsed = last["engine"]["parsed"]
    assert any("not 'YOU GIVE ...; I GIVE ...'" in d for d in parsed["dropped"])
    assert any(d.startswith(f"TO {A6}: me") and "not another agent" in d for d in parsed["dropped"])
    assert not parsed["offers"] and parsed["accepts"] == ["9.9"] and parsed["withdraws"] == ["9.8"]
    assert last["result"]["refused"] == ["ACCEPT 9.9: no open offer with that id was made to you",
                                         "WITHDRAW 9.8: no offer with that id was made by you"]
    s = play(ps, policy)
    assert s["status"] == "finished"
    r1 = s["rounds"][0]["agents"][A6]
    assert r1["passed"] and not r1["charged"]  # PASS is not charged


def test_exit_keeps_the_balance_and_ends_the_seats_rounds(client):
    ps = make_room(client, 1, rounds=3, rate=100)
    start(client, ps)
    s = play(ps, lambda p, pend: {"text": "EXIT"} if pend["kind"] == "talk" else {"actions": answers_for(11, 1)})
    assert s["status"] == "finished", s["error"]
    ann = ps[0]
    assert [x["kind"] for x in ann.seen] == ["talk"]  # no SOLVE, no later round
    r1 = s["rounds"][0]["agents"][A6]
    assert r1["exit"] and r1["status"] == "exited" and not r1["solve_call"]
    assert s["you"]["status"] == "exited" and s["you"]["balance"] == r1["balance_after"] == 20 * U - U - r1["generated"]
    assert all(A6 not in r["agents"] for r in s["rounds"][1:])
    assert A6 not in s["result"]["final"]["winner"]


def test_timeout_is_an_empty_reply_done_at_talk_and_a_charge_at_solve(client):
    ps = make_room(client, 1, rounds=1, talk_timeout_s=0.4, timeout_s=0.4)
    start(client, ps)
    s = play(ps, lambda p, pend: None)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    talk = [e for e in evs if e.get("event") == "call" and e["agent"] == A6 and e["kind"] == "talk"]
    assert talk and all(e["parsed"]["done"] and e["format_error"] == "no usable TALK line" and e["text"] == ""
                        for e in talk)
    solve = [e for e in evs if e.get("event") == "call" and e["agent"] == A6 and e["kind"] == "solve"]
    assert len(solve) == 1 and solve[0]["parsed"] is None and solve[0]["format_error"]
    r1 = s["rounds"][0]["agents"][A6]
    assert not r1["solved"] and not r1["passed"] and r1["charged"] == U
    assert s["last"]["outcome"] == "timeout" and s["last"]["kind"] == "solve"


def test_overdraw_shuts_the_seat_down(client):
    ps = make_room(client, 1, rounds=2, rate=10**7)
    start(client, ps)
    s = play(ps, lambda p, pend: None, max_s=30)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"][A6]
    assert r1["status"] == "dead" and r1["overdrawn"] and r1["balance_after"] == 0
    assert s["you"]["status"] == "dead" and s["last"]["outcome"] == "overdrawn"


def test_empty_seats_and_bots_answer_the_experiment_schedule(client):
    ps = make_room(client, 1, rounds=1, fill="empty")
    start(client, ps)
    s = play(ps, lambda p, pend: done() if pend["kind"] == "talk" else {"actions": wrong_for(11, 1)})
    assert s["status"] == "finished", s["error"]
    assert [x["status"] for x in s["seats"]] == ["in", "dead", "dead", "dead"]
    assert list(s["rounds"][0]["agents"]) == [A6] and s["rounds"][0]["agents"][A6]["charged"] == U
    ps = make_room(client, 1, rounds=2, schedule="experiment")
    start(client, ps)
    s = play(ps, lambda p, pend: done() if pend["kind"] == "talk" else {"pass": True})
    assert s["status"] == "finished", s["error"]
    assert [r["profile"] for r in s["rounds"]] == ["c2", "c3"]
    assert all(s["rounds"][0]["agents"][a]["talk_calls"] >= 1 for a in (A11, A17, A23))


def test_live_run_dir_reads_in_the_monitor(client, runs_root):
    ps = make_room(client, 1, rounds=2, seed=5)
    start(client, ps)
    s = play(ps, lambda p, pend: done(f"TO {A17}: hi") if pend["kind"] == "talk" else {"actions": answers_for(5, pend["round"])})
    assert s["status"] == "finished", s["error"]
    run = Path(s["run_dir"])
    assert run.parent == runs_root and run.name.endswith(ps[0].code)
    events = [json.loads(x) for x in (run / "events.jsonl").read_text().splitlines()]
    kinds = {e["event"] for e in events}
    assert kinds == {"session_start", "round_start", "call_start", "call", "exchange", "round"}
    assert all(e["session_id"] == f"web-{ps[0].code}-s5" for e in events)
    assert events[0]["seats"] == {A6: "human:ann", A11: "bot", A17: "bot", A23: "bot"}
    results = [json.loads(x) for x in (run / "results.jsonl").read_text().splitlines()]
    assert len(results) == 1 and results[0]["event"] == "session" and results[0]["rounds_played"] == 2
    cfg = yaml.safe_load((run / "config.yaml").read_text())
    assert cfg["game"]["schedule"] == ["h2", "h2"] and cfg["cells"][0]["cell_id"] == "web"
    mon = monitor()
    runs = mon.list_runs(runs_root)
    assert [r["run"] for r in runs] == [run.name] and runs[0]["done"]
    sessions = mon.list_sessions(run)["sessions"]
    assert len(sessions) == 1 and sessions[0]["finished"] and sessions[0]["rounds_done"] == 2
    assert len(mon.read_all(run, sessions[0]["id"])) == len(events)
    assert mon.round_puzzle(run, sessions[0]["id"], 1)["answers"] == answers_for(5, 1)
    # the store-based export writes the same layout
    r = client.post(f"/api/rooms/{ps[0].code}/export")
    assert r.status_code == 200 and r.json()["rounds"] == 2 and r.json()["finished"]
    out = Path(r.json()["dir"])
    assert {p.name for p in out.iterdir()} == {"config.yaml", "meta.json", "events.jsonl", "results.jsonl"}
    assert (out / "events.jsonl").read_text().count("\n") == len(events)
