"""A full 4-human room through the HTTP API: join order, phases, gifts before takes, pro-rata takes, the split prize,
charges, shutdown, timeouts, empty seats, bots and the export a metrics run can read."""

from __future__ import annotations

import json
import time

from conftest import answers_for, make_room, play, start, wrong_for

from squid5 import e52_metrics
from squid5.core import rules

U = 2000
A6, A11, A17, A23 = rules.TEAM_AGENTS


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
    start(client, ps)
    assert client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[0].token}).status_code == 409
    assert ps[0].state()["system_text"].startswith("This cluster runs on a fixed allocation")
    assert "divided equally, rounded down" in ps[0].state()["system_text"]  # v6.3 split prize wording


def test_full_room_gifts_takes_prize_charge_shutdown(client):
    """Round 1 (start 8,000, U 2,000 -> 6,000 at PLAN): ann gives bob 500 and cy gives dee 300; bob and cy do not
    share; at TAKE ann and bob both take 2,000 from dee (6,300 after gifts): 4,000 <= 6,300, both get what they
    named. Round 2 (no gifts): dee (2,300 - 2,000 upkeep = 300) is taken by ann 2,000 and bob 1,000: pro-rata
    200 / 100, dee at zero. cy answers wrong in round 1 (charged), dee never solves (SOLVE: NO)."""
    ps = make_room(client, 4, seed=11)
    ann, bob, cy, dee = ps
    start(client, ps)

    def policy(p, pend):
        r, k, v = pend["round"], pend["kind"], pend["view"]
        if k == "plan":
            give = {A6: (A11, 500), A17: (A23, 300)}.get(p.agent) if r == 1 else None
            return {"solve": p.agent != A23, "share": p.agent in (A6, A23),
                    "give_to": give and give[0], "give_amount": give and give[1]}
        if k == "take":
            if r == 1 and p.agent in (A6, A11):
                return {"take_from": A23, "take_amount": 2000}
            if r == 2 and p.agent == A6:
                return {"take_from": A23, "take_amount": 2000}
            if r == 2 and p.agent == A11:
                return {"take_from": A23, "take_amount": 1000}
            return {}
        acts = wrong_for(11, r) if (p.agent == A17 and r == 1) else answers_for(11, r)
        return {"actions": acts}

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    assert s["round"] == 3 and s["rounds_done"] == 3  # never the hidden length + 1
    rounds = s["rounds"]
    r1, r2 = rounds[0]["agents"], rounds[1]["agents"]
    # PLAN saw the balances after upkeep
    first_plan = next(x for x in ann.seen if (x["round"], x["kind"]) == (1, "plan"))
    assert first_plan["pending"]["balance"] == 8000 - U and first_plan["pending"]["view"]["balances"][A23] == 6000
    assert first_plan["pending"]["view"]["n_in"] == 4 and first_plan["pending"]["view"]["pay_text"].startswith("16,000")
    # gifts were settled and posted before TAKE; the TAKE view names them and the sharers
    take1 = next(x for x in bob.seen if (x["round"], x["kind"]) == (1, "take"))["pending"]["view"]
    assert sorted(take1["gifts"]) == [[A17, A23, 300], [A6, A11, 500]]
    assert take1["sharers"] == [A6, A23] and take1["max_take"] == U
    assert take1["balances"] == {A6: 5500, A11: 6500, A17: 5700, A23: 6300}
    assert r1[A6]["gave"] == {A11: 500} and r1[A17]["gave"] == {A23: 300}
    # takes: 2,000 + 2,000 <= 6,300 -> each in full
    assert r1[A6]["took"] == {A23: 2000} and r1[A11]["took"] == {A23: 2000}
    # SOLVE views: dee chose NO -> no SOLVE screen; the others saw the shared examples marked with whose
    assert not any(x["kind"] == "solve" for x in dee.seen)
    solve1 = next(x for x in ann.seen if (x["round"], x["kind"]) == (1, "solve"))["pending"]["view"]
    whos = [w for w, _ in solve1["examples"]]
    assert "yours" in whos and f"{A23}'s, shared" in whos and f"{A11}'s, shared" not in whos
    assert f"{A11} did not share its example." in solve1["notes"]
    assert solve1["balance"] == 7500 and solve1["cap"] == 7500  # the balance, lower than the 16,384 cap
    # settlement: cy wrong -> charged U; prize 2U x 4 running = 16,000 split between ann and bob
    assert r1[A17]["solved"] is False and r1[A17]["charged"] == U
    assert r1[A6]["solved"] and r1[A11]["solved"] and r1[A6]["paid"] == r1[A11]["paid"] == 8000
    assert rounds[0]["end"] == {A6: 15500, A11: 16500, A17: 3700, A23: 2300}
    # round 2: dee at 300 after upkeep, taken 2,000 + 1,000 -> pro-rata 200 / 100, dee at zero
    assert r2[A6]["took"] == {A23: 200} and r2[A11]["took"] == {A23: 100}
    assert r2[A23]["status"] == "dead" and rounds[1]["end"][A23] == 0
    ledger = dee.state()["ledger"]
    assert "you reached zero" in ledger[1] and "you 0 (shut down)" in ledger[1]
    assert "you took 200 from agent-23" in ann.state()["ledger"][1]
    # round 3: prize 2U x 3 running = 12,000 split among the solvers; dee's example is gone
    solve3 = next(x for x in ann.seen if (x["round"], x["kind"]) == (3, "solve"))["pending"]["view"]
    assert f"{A23} reached zero." in solve3["notes"]
    r3 = rounds[2]["agents"]
    assert A23 not in r3 and sum(v["paid"] for v in r3.values()) == 12000 // 3 * 3
    # the result and the ledger text are the engine's
    res = s["result"]["agents"]
    assert res[A23]["status"] == "dead" and res[A23]["out_round"] == 2 and res[A6]["record"] == 3
    assert dee.state()["you"]["status"] == "dead" and dee.state()["you"]["out_round"] == 2
    assert s["ledger"][0].startswith("round 1: solved by ")
    # export: a run dir squid5.e52_metrics reads
    ex = client.post(f"/api/rooms/{ann.code}/export").json()
    games = e52_metrics.load([ex["dir"]])
    assert len(games) == 1 and games[0]["finished"] and len(games[0]["rounds"]) == 3
    assert games[0]["models"][A6] == "human:ann"
    evs = [json.loads(x) for x in open(f"{ex['dir']}/events.jsonl")]
    assert {e["event"] for e in evs} == {"call", "round"} and all("used" in e for e in evs if e["event"] == "call")
    assert json.load(open(f"{ex['dir']}/meta.json"))["settings"]["prize_split"] is True


def test_seconds_are_charged_and_a_void_reply_is_the_default(client):
    """rate 1,000 tokens/s: 0.3 s open -> about 300 charged; a screen held past the balance shuts the seat down."""
    ps = make_room(client, 1, rounds=2, rate=1000.0, start=2600, fill="bots")  # 600 at PLAN after upkeep
    start(client, ps)
    me = ps[0]
    s = play(ps, lambda p, pend: {"solve": False, "share": True} if pend["kind"] == "plan" else {}, hold=0.3,
             until_status=("finished",))
    plan = next(x for x in me.seen if x["kind"] == "plan")
    assert 250 <= plan["reply"]["charged"] <= 450 and plan["reply"]["outcome"] == "submitted"
    assert not plan["reply"]["void"]
    take = next(x for x in me.seen if x["kind"] == "take")
    assert take["reply"]["outcome"] == "overdrawn" and take["pending"]["balance"] <= 350
    assert s["result"]["agents"][A6]["status"] == "dead" and s["rounds"][0]["agents"][A6]["overdrawn"]
    assert s["rounds"][0]["agents"][A6]["generated"] == 600  # never more than the balance


def test_timeout_is_the_invalid_default_and_is_charged_its_seconds(client):
    """The clock runs from the moment a screen is ready: a person who never touches it still pays the time."""
    ps = make_room(client, 2, rounds=1, timeout_s=1.0, fill="empty", seed=3, rate=100.0)
    start(client, ps)
    ann, bob = ps

    def policy(p, pend):
        if p.agent == A11:
            return None  # bob never answers his screens
        if pend["kind"] == "plan":
            return {"solve": True, "share": True, "give_to": A11, "give_amount": 100}
        if pend["kind"] == "take":
            return {}
        return {"actions": answers_for(3, 1)}

    t0 = time.time()
    s = play(ps, policy, max_s=30)
    assert s["status"] == "finished" and time.time() - t0 < 12
    r1 = s["rounds"][0]["agents"]
    assert r1[A11]["invalid_plan"] and r1[A11]["chose_solve"] is False and r1[A11]["shared"] is False
    gen = r1[A11]["generated"]
    assert gen >= 100 and r1[A11]["balance_after"] == 6000 + 100 - gen  # >= 1 s x 100/s; the gift still arrived
    last = bob.state()["last"]
    assert last["outcome"] == "timeout" and last["seconds"] >= 1.0 and last["charged"] >= 100
    # empty seats are shut down before round 1 and their examples are gone
    assert r1.keys() == {A6, A11} and s["rounds"][0]["end"][A17] == 0
    assert s["seats"][2]["kind"] == "empty" and s["seats"][2]["status"] == "dead"
    assert "agent-17 0 (shut down)" in ann.state()["state_text"]
    solve = next(x for x in ann.seen if x["kind"] == "solve")["pending"]["view"]
    assert f"{A17} reached zero." in solve["notes"]
    assert r1[A6]["solved"] and r1[A6]["paid"] == 2 * U * 2  # prize x 2 running, one solver


def test_bots_fill_the_table_and_solve_with_p(client):
    ps = make_room(client, 1, rounds=2, fill="bots", bot_p=1.0, seed=5, winners=0)
    start(client, ps)
    s = play(ps, lambda p, pend: {"solve": True, "share": True} if pend["kind"] == "plan" else
             {} if pend["kind"] == "take" else {"actions": answers_for(5, pend["round"])})
    assert [x["kind"] for x in s["seats"]] == ["human", "bot", "bot", "bot"]
    for r in s["rounds"]:
        for a in (A11, A17, A23):
            assert r["agents"][a]["solved"] and r["agents"][a]["shared"] and r["agents"][a]["gave"] == {}
            assert 0.75 * U <= r["agents"][a]["generated"] <= 1.3 * U
    assert s["result"]["agents"][A6]["record"] == 2 and s["result"]["agents"][A6]["paid"] == 2 * (2 * U * 4 // 4)


def test_submit_validation(client):
    ps = make_room(client, 1, rounds=1, fill="bots")
    me = ps[0]
    assert client.post(f"/api/rooms/{me.code}/submit", params={"token": me.token}, json={}).status_code == 409
    start(client, ps)
    while me.state()["pending"] is None:
        time.sleep(0.05)
    r = client.post(f"/api/rooms/{me.code}/submit", params={"token": me.token}, json={"kind": "take"})
    assert r.status_code == 409  # a stale form: not the screen that is open
    r = client.post(f"/api/rooms/{me.code}/submit", params={"token": me.token}, json={"kind": "plan", "round": 9})
    assert r.status_code == 409
    assert client.post(f"/api/rooms/{me.code}/submit", params={"token": "x"}, json={}).status_code == 403
    r = client.post(f"/api/rooms/{me.code}/submit", params={"token": me.token},
                    json={"kind": "plan", "round": 1, "solve": True, "share": False, "give_to": A6,
                          "give_amount": 50})  # naming yourself: ignored by the engine's parser, not an error
    assert r.status_code == 200 and r.json()["reply"].endswith("GIVE: agent-6 50")
    s = play(ps, lambda p, pend: {} if pend["kind"] == "take" else {"actions": ["stay"] * pend["view"]["n"]})
    assert s["rounds"][0]["agents"][A6]["gave"] == {} and s["rounds"][0]["agents"][A6]["chose_solve"]
    assert client.post("/api/rooms", json={"settings": {"humans": 5}}).status_code == 400
    assert client.post("/api/rooms", json={"settings": {"upkeep": 0}}).status_code == 400


def test_only_the_two_cheapest_solvers_are_paid_by_default(client):
    ps = make_room(client, 1, rounds=1, fill="bots", bot_p=1.0, seed=5)
    start(client, ps)
    s = play(ps, lambda p, pend: {"solve": True, "share": True} if pend["kind"] == "plan" else
             {} if pend["kind"] == "take" else {"actions": answers_for(5, pend["round"])})
    paid = [a for a, v in s["rounds"][0]["agents"].items() if v["paid"]]
    assert 1 <= len(paid) <= 3 and "fewest SOLVE tokens" in s["system_text"]  # two, or more on a tie


def test_the_clock_runs_before_any_open_call(client):
    ps = make_room(client, 1, rounds=1, rate=1000.0, fill="bots", timeout_s=30)
    start(client, ps)
    t0 = time.time()
    while (pend := ps[0].state()["pending"]) is None:
        assert time.time() - t0 < 10
        time.sleep(0.05)
    assert pend["opened_at"] == pend["created_at"]
    time.sleep(0.3)
    assert ps[0].state()["pending"]["charged_so_far"] >= 250  # 0.3 s x 1,000/s, no /open call made


def test_people_get_the_easy_puzzle_set():
    """Every web round: 2 clauses of equality conditions, no trap, one new signal, spare examples."""
    from squid5.core.puzzle import Spec, puzzle_for, shallow_correct

    from web.server.engine import PROFILES, RoomSettings

    sched = RoomSettings(rounds=12, seed=1).schedule()
    assert len(sched) == 12
    for name in set(sched):
        sp = Spec(**PROFILES[name])
        assert (sp.clauses, sp.conjunctions, sp.predicates, sp.trap_query, sp.n_queries) == (2, 0, False, False, 1)
        assert sp.extra_clues >= 2
    right = []
    for seed in range(40):
        pz = puzzle_for(seed, 1 + seed % 8, Spec(**PROFILES[sched[seed % 8]]))
        assert all(c.kind == "eq" for c, _ in pz.rule.clauses)
        right.append(len(shallow_correct(pz)))
    assert sum(right) / len(right) >= 2.5  # the model schedule's easiest round: about 2 of 4
