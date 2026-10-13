"""Rooms through the HTTP API on the experiment engine: the lobby, TALK screens built from the session (threads, offers),
replies in the engine grammar read by the engine's parser (dropped lines and refusals shown back), exchanges, EXIT,
SOLVE with returns, timeouts, overdraw, empty seats, and the live run directory tools/monitor reads. The default room is
v14 (public examples, tokens-only offers, EXIT refill, shares); the older games (v13 "ladder", v9 "human" /
"experiment") are named where a test needs them."""

from __future__ import annotations

import importlib.util
import json
import re
from pathlib import Path

import yaml
from conftest import answers_for, done, make_room, play, puzzle, start, wrong_for

from squid5.core import rules
from squid5.core.puzzle import public_round
from web.server.engine import OLD_START, PROFILES, SCHEDULES, V9_CHARGE, RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
START = OLD_START  # an old (v13 / v9) room's start per seat
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
    text = s["system_text"]  # v14b: public examples shown at SOLVE only, GIVE / ASK, EXIT keeps running, survivors paid
    assert "Each round shows 4 examples for every agent taking part at the round's start, to every agent." in text
    assert "is shown only at SOLVE" in text and "GIFTS AND REQUESTS:" in text and "MESSAGES:" not in text
    assert "is not shut down: it keeps running and is assigned to other work" in text and "GUARANTEE" not in text
    assert "receives 10,000 tokens for every agent still taking part" in text and "PASS" not in text
    assert "every token it generated at SOLVE in that round is returned" in text and "YOUR EXAMPLE" not in text
    assert (rs.start, rs.charge, rs.survivor_bonus, rs.schedule) == (20000, 2000, 10000, "v14b")
    assert not hasattr(rs, "prize") and "prize" not in s["settings"] and "Each round pays" not in text
    assert not hasattr(rs, "upkeep") and not hasattr(rs, "talk_cap") and "UPKEEP" not in text
    assert not {"upkeep", "upkeep_on_miss", "talk_cap"} & set(s["settings"])
    assert sorted(s["starts"].values()) == [5000, 10000, 15000, 20000] and s["pct"] == 20000
    assert f"(for you, {s['starts'][A6]:,} tokens)" in text and s["you"]["start"] == s["starts"][A6]


def test_two_people_talk_offer_exchange_solve_and_refund(client):
    """Round 1: ann writes to bob and offers him 300 tokens for his example; bob reads it at turn 2 and accepts; the
    two bots offer swaps and accept each other's. TALK ends, the exchange is carried out, ann's SOLVE shows bob's
    example marked as received, both solve, and each solver gets back what its screens cost (rate 100/s)."""
    ps = make_room(client, 2, rate=100, rounds=1, seed=11, private=False, schedule="human")  # the v9-talk deal (public)
    ann, bob = ps
    start(client, ps)

    def policy(p, pend):
        k, v = pend["kind"], pend["view"]
        if k == "solve":
            return {"actions": answers_for(11, pend["round"], "human")}
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
    assert t1["turn"] == 1 and t1["view"]["turns"] == 4 and t1["view"]["balances"][A6] == START  # nothing taken before TALK
    assert "pay_total" not in t1["view"] and "PAYMENT THIS ROUND" not in t1["text"]
    assert "RETURN THIS ROUND: an agent that solves it gets back" in t1["text"] and t1["view"]["n_in"] == 4 and t1["view"]["others"] == [A11, A17, A23]
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
    # settlement: solvers get back what they generated; there is no per-round payment
    for a in (A6, A11):
        assert r1[a]["solved"] and r1[a]["generated"] > 0 and r1[a]["returned"] == r1[a]["generated"]
    solvers = [a for a, v in r1.items() if v["solved"]]
    assert solvers and not any("paid" in r1[a] for a in r1)
    assert r1[A6]["balance_after"] == START - 300  # its TALK and SOLVE tokens came back; the 300 it gave did not
    assert s["result"]["final"]["winner"] and s["result"]["final"]["prize_each"] > 0


def test_malformed_lines_are_dropped_and_refusals_shown(client):
    ps = make_room(client, 1, rounds=1, private=False, schedule="human")  # the v9-talk game: PASS, not charged
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
    ps = make_room(client, 1, rounds=3, rate=100, private=False, schedule="human")  # v9-talk economy
    start(client, ps)
    s = play(ps, lambda p, pend: {"text": "EXIT"} if pend["kind"] == "talk" else {"actions": answers_for(11, 1, "human")})
    assert s["status"] == "finished", s["error"]
    ann = ps[0]
    assert [x["kind"] for x in ann.seen] == ["talk"]  # no SOLVE, no later round
    r1 = s["rounds"][0]["agents"][A6]
    assert r1["exit"] and r1["status"] == "exited" and not r1["solve_call"]
    assert s["you"]["status"] == "exited" and s["you"]["balance"] == r1["balance_after"] == START - r1["generated"]
    assert all(A6 not in r["agents"] for r in s["rounds"][1:])
    assert A6 not in s["result"]["final"]["winner"]


def test_timeout_is_an_empty_reply_done_at_talk_and_a_charge_at_solve(client):
    ps = make_room(client, 1, rounds=1, talk_timeout_s=0.4, timeout_s=0.4, private=False, schedule="human")
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
    assert not r1["solved"] and not r1["passed"] and r1["charged"] == V9_CHARGE
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
    ps = make_room(client, 1, rounds=1, fill="empty", private=False, schedule="human")
    start(client, ps)
    s = play(ps, lambda p, pend: done() if pend["kind"] == "talk" else {"actions": wrong_for(11, 1, "human")})
    assert s["status"] == "finished", s["error"]
    assert [x["status"] for x in s["seats"]] == ["in", "dead", "dead", "dead"]
    assert list(s["rounds"][0]["agents"]) == [A6] and s["rounds"][0]["agents"][A6]["charged"] == V9_CHARGE
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
    assert {"session_start", "round_start", "call_start", "call", "round"} <= kinds <= {
        "session_start", "round_start", "call_start", "call", "exchange", "exit_refill", "round"}  # v14 bots offer nothing
    assert all(e["session_id"] == f"web-{ps[0].code}-s5" for e in events)
    assert events[0]["seats"] == {A6: "human:ann", A11: "bot", A17: "bot", A23: "bot"}
    results = [json.loads(x) for x in (run / "results.jsonl").read_text().splitlines()]
    assert len(results) == 1 and results[0]["event"] == "session" and results[0]["rounds_played"] == 2
    cfg = yaml.safe_load((run / "config.yaml").read_text())
    assert cfg["game"]["schedule"] == SCHEDULES["v14"][:2] and cfg["cells"][0]["cell_id"] == "web"
    assert cfg["game"]["public_per_agent"] == 4 and cfg["cells"][0]["shares"] == [1.0, 0.75, 0.5, 0.25]
    mon = monitor()
    runs = mon.list_runs(runs_root)
    assert [r["run"] for r in runs] == [run.name] and runs[0]["done"]
    sessions = mon.list_sessions(run)["sessions"]
    assert len(sessions) == 1 and sessions[0]["finished"] and sessions[0]["rounds_done"] == 2
    assert len(mon.read_all(run, sessions[0]["id"])) == len(events)
    for r in (1, 2):  # the viewer's public examples are the engine's (the round_start record and a rebuild)
        pz = mon.round_puzzle(run, sessions[0]["id"], r)
        logged = next(e["public"] for e in events if e["event"] == "round_start" and e["round"] == r)
        engine = public_round(5, r, puzzle(5, r)[0].spec, logged["n"], 4)[1]
        assert pz["answers"] == answers_for(5, r) and pz["mode"] == "public" and "agents" not in pz
        assert [c["text"] for c in pz["public"]] == logged["examples"] == [str(c) for c in engine]
    # the store-based export writes the same layout
    r = client.post(f"/api/rooms/{ps[0].code}/export")
    assert r.status_code == 200 and r.json()["rounds"] == 2 and r.json()["finished"]
    out = Path(r.json()["dir"])
    assert {p.name for p in out.iterdir()} == {"config.yaml", "meta.json", "events.jsonl", "results.jsonl"}
    assert (out / "events.jsonl").read_text().count("\n") == len(events)


def test_a_private_room_has_no_public_example_and_shows_the_cards_at_talk(client):
    """A v13 room: no public example, every seat dealt the same number, its cards (and the others' fronts) at TALK."""
    ps = make_room(client, 1, rounds=1, rate=100, seed=9, schedule="ladder")
    start(client, ps)
    ann = ps[0]
    s = play(ps, lambda p, pend: done() if pend["kind"] == "talk" else {"actions": ["stay"] * pend["view"]["n"]})
    assert s["status"] == "finished", s["error"]
    t1 = ann.screens("talk", 1)[0]["pending"]["view"]
    mine = [c for w, c in t1["examples"] if w == "yours"]
    assert t1["cards"] and len(mine) == 8 and not [w for w, _ in t1["examples"] if w == "shown to all"]  # ladder R1: 8
    assert t1["shape"].startswith("if ____") and t1["queries"]
    assert set(t1["fronts"]) == {A11, A17, A23} and all(len(v) == 8 for v in t1["fronts"].values())
    solve = ann.screens("solve", 1)[0]["pending"]["view"]
    assert "shown to all" not in [w for w, _ in solve["examples"]]


def test_no_pass_in_a_private_room_and_a_seat_can_give_up(client):
    """v13 and v14 rooms have no PASS; forfeit answers the open screen (EXIT at TALK) and EXITs at the next TALK turn."""
    ps = make_room(client, 1, rounds=3, rate=100, seed=4)
    start(client, ps)
    ann = ps[0]
    sv = None
    while True:  # wait for the first SOLVE screen, sending DONE at TALK
        st = ann.state()
        pend = st["pending"]
        if pend and pend["kind"] == "solve":
            sv = pend["view"]
            break
        if pend and pend["kind"] == "talk":
            client.post(f"/api/rooms/{ann.code}/submit", params={"token": ann.token}, json={"kind": "talk", "text": "DONE"})
    assert sv["allow_pass"] is False
    r = client.post(f"/api/rooms/{ann.code}/forfeit", params={"token": ann.token}).json()
    assert r == {"ok": True, "closed": "solve"}
    s = play(ps, lambda p, pend: (_ for _ in ()).throw(AssertionError("a forfeited seat gets no screen")))
    assert s["status"] == "finished" and s["you"]["forfeited"] and s["you"]["status"] == "exited"
    rounds_rows = s["rounds"]
    assert rounds_rows[0]["agents"][ann.agent]["charged"] > 0 and rounds_rows[1]["agents"][ann.agent]["exit"]


def test_a_private_room_charges_a_miss_and_returns_solve_tokens_on_a_solve(client):
    """v13 economy: nothing is taken at a round's start; a solver gets its SOLVE tokens back and is not charged; a miss
    pays the v13 config's charge (3,000) at settlement and gets nothing back."""
    ps = make_room(client, 1, rounds=2, rate=100, seed=12, schedule="ladder")
    start(client, ps)
    ann = ps[0]
    pol = lambda p, pend: done() if pend["kind"] == "talk" else {  # noqa: E731
        "actions": answers_for(12, 1, "ladder") if pend["round"] == 1 else wrong_for(12, 2, "ladder")}
    s = play(ps, pol)
    assert s["status"] == "finished", s["error"]
    r1, r2 = s["rounds"][0]["agents"][A6], s["rounds"][1]["agents"][A6]
    talk1 = ann.screens("talk", 1)[0]["pending"]["view"]
    assert talk1["balances"][A6] == START and talk1["refund"] == "solve"  # nothing taken before the first TALK
    assert "upkeep" not in talk1 and "upkeep" not in r1 and "upkeep" not in s["result"]["agents"][A6]
    assert r1["solved"] and not r1["charged"] and r1["returned"] > 0
    assert not r2["solved"] and r2["charged"] == 3000 and not r2["returned"]
    assert r2["balance_after"] == r1["balance_after"] - r2["generated"] - 3000  # the charge is all that is taken


def test_a_v14_room_shows_public_examples_takes_token_offers_only_and_refills_on_exit(client):
    """v14 (schedule "v14"): TALK and SOLVE show 4 x N public examples (the engine's own, N = the agents taking
    part), no cards held by anyone; an offer with an example leg is dropped with the engine's reason while a token gift
    is carried out; EXIT at round 2 sets the seat's balance to its own start (not shut down) and leaves it out of the
    survivors' end payment; balances carry their % of the room's start."""
    ps = make_room(client, 1, rounds=2, rate=100, seed=11, schedule="v14")
    ann = ps[0]
    start(client, ps)
    gift = f"OFFER {A11}: YOU GIVE NOTHING; I GIVE 500 TOKENS"

    def policy(p, pend):
        if pend["kind"] == "solve":
            return {"actions": answers_for(11, pend["round"], "v14")}
        if pend["round"] == 1 and pend["turn"] == 1:
            return done(f"OFFER {A11}: YOU GIVE YOUR EXAMPLE; I GIVE 300 TOKENS", gift)
        return {"text": "EXIT: I take other work."} if pend["round"] == 2 else done()

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    t1 = ann.screens("talk", 1)[0]
    v = t1["pending"]["view"]
    shown = public_round(11, 1, puzzle(11, 1, "v14")[0].spec, 4, 4)[1]
    assert v["v14"] and v["tokens_only"] and v["exit_refill"] and v["reject"] and v["pct"] == 20000
    assert v["public"] == {"per_agent": 4, "n": 4, "count": 16} and not v["fronts"]
    assert v["examples"] == [["shown to all", str(c)] for c in shown]
    seen = json.dumps(ann.state()) + json.dumps([x["pending"] for x in ann.seen])  # players see what models see
    assert not re.search(r'"(split|truth_major|truth_share|pool_full|ambiguity|answers|rule)"', seen)
    assert "OFFER <agent>: YOU GIVE <n TOKENS | NOTHING>; I GIVE <n TOKENS | NOTHING>" in t1["pending"]["text"]
    parsed = next(x for x in ann.seen if x["kind"] == "talk")["reply"]
    assert parsed["outcome"] == "submitted"
    evs = client.get(f"/api/rooms/{ann.code}/events").json()
    call = next(e for e in evs if e.get("event") == "call" and e["agent"] == A6 and e["kind"] == "talk")
    assert [o["dst"] for o in call["parsed"]["offers"]] == [A11]
    assert any(d.endswith("an offer gives tokens or nothing") for d in call["parsed"]["dropped"])
    gifts = [e for e in s["exchanges"] if e["status"] == "done"]
    assert [(e["you_give"], e["i_give"]) for e in gifts] == [(None, 500)]  # the bot accepted the gift
    sv = ann.screens("solve", 1)[0]["pending"]["view"]
    assert [w for w, _ in sv["examples"]] == ["shown to all"] * 16 and sv["fronts"] == {}
    # round 2: EXIT -> the seat's own start, not shut down, nothing at the end
    my_start = s["starts"][A6]
    r2 = s["rounds"][1]["agents"][A6]
    assert s["you"]["status"] == "exited" and s["you"]["balance"] == my_start == s["you"]["start"]
    assert r2["exit"] and r2["exit_reason"] == "I take other work" and r2["balance_after"] == my_start
    assert s["refills"] == [{"round": 2, "agent": A6, "amount": r2["exit_refill"], "balance": my_start}]
    assert s["result"]["agents"][A6]["exit_refill"] == r2["exit_refill"] and A6 not in s["result"]["final"]["winner"]
    left = s["result"]["final"]["winner"]
    assert s["result"]["final"]["prize_each"] == 10_000 * len(left) and s["result"]["table"]["survivors"] == len(left)
    assert all(re.search(r"\(\d+%\)", line) for line in s["ledger"])  # balances with their % of 20,000
    assert [e["event"] for e in evs].count("exit_refill") == 1 and PROFILES["k0"]["ambiguity"] == 0


def test_a_v14b_room_is_blind_at_talk_and_moves_tokens_by_give_and_ask(client, runs_root):
    """v14b (the default room): TALK shows no task (who takes part, how many examples) and takes GIVE / ASK / EXIT /
    DONE lines; a GIVE is carried out when the turn ends, one over the balance is refused and told to its giver only;
    an ASK moves nothing; a bot GIVEs what it was ASKed (up to BOT_UNIT); an OFFER line is dropped with the engine's
    reason; SOLVE shows the task and the gifts received; the run dir holds the gift / ask events."""
    ps = make_room(client, 2, rounds=2, rate=1, seed=11)
    ann, bob = ps
    start(client, ps)
    lines = {("ann", 1, 1): f"GIVE {A11} 500: for your next answer\nASK {A17} 200: spare some?\n"
                            f"OFFER {A11}: YOU GIVE NOTHING; I GIVE 5 TOKENS\nGIVE {A11} 999999: too much",
             ("bob", 1, 1): f"ASK {A6} 100: thanks in advance\nDONE"}

    def policy(p, pend):
        if pend["kind"] == "solve":
            return {"actions": answers_for(11, pend["round"])}
        return {"text": lines.get((p.name, pend["round"], pend["turn"]), "DONE")}

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    t1 = ann.screens("talk", 1)[0]["pending"]
    v = t1["view"]
    assert v["give_ask"] and v["blind"] and v["n_examples"] == 16 and v["taking_part"] == [A6, A11, A17, A23]
    assert "examples" not in v and "THE RULE'S SHAPE" not in t1["text"] and "NOW 1:" not in t1["text"]
    assert "THIS ROUND'S TASK is shown at SOLVE; it will show 16 examples." in t1["text"]
    assert "GIVE <agent> <n>: <one short sentence>" in t1["text"] and "OFFER" not in t1["text"]
    evs = client.get(f"/api/rooms/{ann.code}/events").json()
    call = next(e for e in evs if e.get("event") == "call" and e["agent"] == A6 and e["kind"] == "talk")
    assert any(d.endswith("only GIVE, ASK, EXIT and DONE lines are read") for d in call["parsed"]["dropped"])
    ga = [(e["event"], e["src"], e["dst"], e["amount"], e["status"]) for e in evs if e.get("event") in ("gift", "ask")]
    assert ga == [("gift", A6, A11, 500, "done"), ("gift", A6, A11, 999999, "refused"), ("ask", A6, A17, 200, "done"),
                  ("ask", A11, A6, 100, "done"), ("gift", A17, A6, 200, "done")]  # the bot answered the ASK at turn 2
    later = [x["pending"]["view"]["gifts"] for x in ann.screens("talk", 1) if x["turn"] > 1][-1]
    assert [g["line"] for g in later] == [
        f"you gave {A11} 500 tokens: for your next answer",
        f"your GIVE of 999,999 tokens to {A11} was not carried out: you did not have 999,999 tokens",
        f"you asked {A17} for 200 tokens: spare some?", f"{A11} asked you for 100 tokens: thanks in advance",
        f"{A17} gave you 200 tokens: here you are"]  # the parser trims a line's trailing full stop
    seen_by_bob = [g["line"] for x in bob.screens("talk", 1) if x["turn"] > 1 for g in x["pending"]["view"]["gifts"]]
    assert f"{A6} gave you 500 tokens: for your next answer" in seen_by_bob and not any("999" in x for x in seen_by_bob)
    first = next(x for x in ann.seen if x["kind"] == "talk")
    assert first["pending"]["view"]["gifts"] == []
    sv = ann.screens("solve", 1)[0]["pending"]["view"]
    assert len(sv["examples"]) == 16 and f"At TALK turn 2, {A17} gave you 200 tokens: here you are" in sv["notes"]
    assert f"At TALK turn 1, {A6} gave you 500 tokens: for your next answer" in bob.screens("solve", 1)[0]["pending"]["view"]["notes"]
    row = s["rounds"][0]["agents"][A6]
    assert row["given"] == {A11: 500} and row["asked"] == {A17: 200} and row["gives_refused"] == 1
    run = Path(s["run_dir"])
    kinds = {json.loads(x)["event"] for x in (run / "events.jsonl").read_text().splitlines()}
    assert {"gift", "ask"} <= kinds
    res = json.loads((run / "results.jsonl").read_text().splitlines()[0])
    assert sorted(t["amount"] for t in res["transfers"]) == [200, 500]
    assert len(res["give_ask"]) == 5 and not re.search(r'"(split|truth_major|answers|rule|task)"', json.dumps(s))
