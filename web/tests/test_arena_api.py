"""Rooms through the HTTP API on the experiment engine, playing the model runs' game (5.2 v33, configs/squid5/
e52v33_public_sol4.yaml): the lobby and settings, the engine's own prompts in the seat's language (en / ko, switchable),
the messenger TALK (rooms, ticks, TO / GIVE / ASK / LEAVE / EXIT: YES|NO / DONE), the rank-only token view, SOLVE with
BELIEF and ACTIONS, the results and the revealed task, EXIT before SOLVE (+20,000, never by the round's solver), the
charges split among those taking part, the end allocation split 1/N, timeouts, overdraw, forfeit, the public log, export."""

from __future__ import annotations

import re

from conftest import answers_for, basic, done, make_room, play, solver_of, start, wrong_for

from squid5.core.rules import TEAM_AGENTS
from web.server.engine import RoomSettings

A6, A11, A17, A23 = TEAM_AGENTS
SEED = 5  # round 1's solver is agent-11 (a bot), round 2's agent-6 (ann)


def test_models_endpoint_and_room_settings(client):
    m = client.get("/api/models").json()
    assert m["model"] == "gpt-oss:20b" and m["kind"] == "ollama" and m["base_url"] == "https://ollama.com"
    assert m["api_key_env"] == "OLLAMA_API_KEY" and set(m["kinds"]) == {"ollama", "openai", "anthropic"}
    assert m["version"] == "v33" and m["langs"] == ["en", "ko"] and m["defaults"]["model_lang"] == "en"
    for bad in ({"fill": "x"}, {"humans": 0}, {"model_lang": "fr"}, {"api_key_env": "HOME"}, {"rounds": 0},
                {"base_url": "file:///etc"}, {"charge": 1}, {"kind": "codex_cli"}, {"models": [{"model": "a b"}]}):  # the economy is the config's: no charge override
        assert client.post("/api/rooms", json={"settings": bad}).status_code == 400, bad
    e = RoomSettings(seed=1).engine()
    assert (e.charge_total, e.exit_bonus_pct, e.survivor_prize, e.public_per_agent, e.max_ticks, e.solve_cap, e.lang) == (
        24_000, 20, 5_000_000, 5, 8, 100_000, "en")
    assert RoomSettings(seed=1, rounds=3, model_lang="ko").engine().schedule == ["e01", "e02", "e03"]


def test_lobby_seats_language_and_start(client):
    ps = make_room(client, 2, lang="ko")
    s = ps[0].state()
    assert s["status"] == "lobby" and s["you"]["agent"] == A6 and ps[1].agent == A11 and s["lang"] == "ko"
    assert s["system_text"].startswith("당신은 agent-6입니다.") and "rounds" not in s["settings"] and "seed" not in s["settings"]
    assert [r["start"] for r in s["seats"]] == [s["you"]["start"], None, None, None]  # only my own start
    assert client.post(f"/api/rooms/{ps[0].code}/lang", params={"token": ps[0].token}, json={"lang": "en"}).json() == {"lang": "en"}
    assert ps[0].state()["system_text"].startswith("You are agent-6, one of four different AI agents")
    assert client.post(f"/api/rooms/{ps[0].code}/lang", params={"token": ps[0].token}, json={"lang": "fr"}).status_code == 400
    assert client.post(f"/api/rooms/{ps[0].code}/join", json={"name": "x"}).status_code == 409  # both human seats taken
    assert client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[1].token}).status_code == 403
    start(client, ps)
    assert client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[0].token}).status_code == 409


def test_one_person_three_bots_plays_v33_to_the_end_in_korean(client):
    ps = make_room(client, 1, seed=SEED, lang="ko")
    start(client, ps)
    s = play(ps, basic, max_s=120)
    assert s["status"] == "finished", s["error"]
    talks, solves = ps[0].screens("talk"), ps[0].screens("solve")
    first = talks[0]["pending"]
    assert first["lang"] == "ko" and first["text"].startswith("라운드 1.\n지금 토큰 순서") and first["view"]["solver"] == A11
    v = first["view"]
    assert (v["phase"], v["tick"], v["max_ticks"], v["can_exit"], v["charge_each"]) == ("prep", 1, 8, True, 6000)
    assert v["rooms"][0]["id"] == "R1" and v["rooms"][0]["group"] and set(v["order"]) == set(TEAM_AGENTS)
    resc = next(x["pending"] for x in talks if x["phase"] == "rescue")
    assert resc["view"]["results"]["solver"] == A11 and resc["view"]["reveal"]["answer"] == answers_for(SEED, 1)
    assert len(resc["view"]["reveal"]["examples"]) == 20 and resc["view"]["reveal"]["shape"].startswith("if ")
    assert "라운드 1의 SOLVE 기록:" in resc["text"]
    sv = solves[0]["pending"]
    assert sv["round"] == 2 and len(sv["view"]["examples"]) == 20 and sv["view"]["shape"].startswith("if ")
    assert sv["text"].startswith("라운드 2: SOLVE.") and "BELIEF: go_left <percent>" in sv["text"]
    prep2 = next(x["pending"] for x in talks if x["round"] == 2 and x["phase"] == "prep")
    assert prep2["view"]["solver_cannot_exit"] and not prep2["view"]["can_exit"]  # v33: the solver stays
    assert s["result"]["final"]["prize_each"] == 20_000_000 // len(s["result"]["final"]["winner"])
    assert s["rounds"][1]["solved"] and s["rounds"][1]["solver"] == A6 and s["ledger"][0].startswith("- 라운드 1:")


def test_rank_only_view_while_running_and_everything_at_the_end(client):
    ps = make_room(client, 1, seed=SEED, rounds=1)
    start(client, ps)
    seen = {}

    def policy(p, pend):
        st = p.state()
        seen["rows"], seen["rounds"] = st["seats"], st["rounds"]
        return basic(p, pend)
    s = play(ps, policy)
    assert [r["balance"] is None for r in seen["rows"]] == [False, True, True, True]
    assert all(r["rank"] for r in seen["rows"]) and all(set(x["agents"]) <= {A6} for x in seen["rounds"])
    assert all(r["balance"] is not None for r in s["seats"]) and set(s["rounds"][0]["agents"]) == set(TEAM_AGENTS)
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    assert any(e["event"] == "room_msg" or e["event"] == "call" for e in evs)  # the full log after the end


def test_messenger_lines_move_tokens_and_reach_the_rooms(client):
    ps = make_room(client, 1, seed=SEED, rounds=1)
    start(client, ps)

    def policy(p, pend):
        v = pend["view"]
        if pend["kind"] == "solve":
            return basic(p, pend)
        if pend["phase"] == "prep" and pend["tick"] == 1:
            return {"text": f"TO R1: hello all\nmore of it\nTO {A17}: just you\nGIVE {A23} 700: a gift\n"
                            f"ASK {A11} 300: please\nTO {A11}, {A17}: both\nDONE"}
        return {"text": "DONE"}
    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    first = ps[0].screens("talk")[0]
    moves = first["reply"]
    assert moves["outcome"] == "submitted"
    later = [x["pending"]["view"]["rooms"] for x in ps[0].screens("talk")[1:]]
    rooms = later[-1]
    r1 = next(r for r in rooms if r["id"] == "R1")
    assert r1["msgs"][0]["text"] == "hello all\nmore of it" and r1["msgs"][0]["src"] == A6
    pair = {tuple(r["members"]): r for r in rooms}
    assert pair[(A6, A17)]["msgs"][0]["text"] == "just you"
    give = next(m for m in pair[(A6, A23)]["msgs"] if m["kind"] == "give")
    assert (give["amount"], give["status"], give["text"]) == (700, "done", "a gift")
    ask = next(m for m in pair[(A6, A11)]["msgs"] if m["kind"] == "ask")
    assert ask["amount"] == 300 and any(m["kind"] == "give" and m["src"] == A11 for m in pair[(A6, A11)]["msgs"])  # bot gave
    assert "TO agent-11, agent-17: both" in next(x["pending"]["text"] for x in ps[0].screens("talk")[1:2])  # not delivered


def test_exit_yes_before_solve_leaves_with_the_bonus_and_no_exit_after_results(client):
    ps = make_room(client, 1, seed=SEED, rounds=2)
    start(client, ps)
    before = {}

    def policy(p, pend):
        if pend["kind"] == "talk" and pend["phase"] == "prep" and pend["view"]["can_exit"]:
            before["bal"] = pend["view"]["balance"]
            return {"text": "EXIT: YES I go back to regular work."}
        return {"text": "EXIT: YES now"} if pend["kind"] == "talk" else basic(p, pend)
    s = play(ps, policy)
    assert s["status"] == "finished" and s["you"]["status"] == "exited"
    assert s["you"]["balance"] == before["bal"] + 20_000 and A6 not in s["result"]["final"]["winner"]
    assert s["result"]["final"]["prize_each"] == 20_000_000 // 3


def test_the_solver_cannot_exit_its_own_round(client):
    seed = next(x for x in range(1, 200) if solver_of(x) == A6)
    ps = make_room(client, 1, seed=seed, rounds=1)
    start(client, ps)
    s = play(ps, lambda p, pend: {"text": "EXIT: YES let me out"} if pend["kind"] == "talk" and pend["phase"] == "prep"
             else basic(p, pend))
    assert s["you"]["status"] == "in" and ps[0].screens("talk")[0]["pending"]["view"]["solver_cannot_exit"]
    assert ps[0].screens("solve")  # it still solved
    later = [x["pending"]["text"] for x in ps[0].screens("talk")[1:] if x["phase"] == "prep"]
    assert not later or "the solver of this round cannot EXIT" in later[0]


def test_a_wrong_answer_charges_the_split_and_a_right_one_returns_the_solve_tokens(client):
    seed = next(x for x in range(1, 200) if solver_of(x) == A6)
    ps = make_room(client, 1, seed=seed, rounds=1, rate=50)
    start(client, ps)
    s = play(ps, lambda p, pend: {"actions": wrong_for(seed, 1)} if pend["kind"] == "solve" else done(), hold=0.05)
    r = s["rounds"][0]
    assert not r["solved"] and r["charged"] == {a: 6000 for a in TEAM_AGENTS}
    ps2 = make_room(client, 1, seed=seed, rounds=1, rate=50)
    start(client, ps2)
    s2 = play(ps2, lambda p, pend: {"actions": answers_for(seed, 1)} if pend["kind"] == "solve" else done(), hold=0.05)
    me = s2["rounds"][0]["agents"][A6]
    assert s2["rounds"][0]["solved"] and me["returned"] > 0 and not s2["rounds"][0]["charged"]


def test_timeout_overdraw_and_forfeit(client):
    ps = make_room(client, 1, seed=SEED, rounds=1, talk_timeout_s=0.3)
    start(client, ps)
    s = play(ps, lambda p, pend: None if pend["kind"] == "talk" else basic(p, pend))
    assert s["status"] == "finished" and s["last"]["outcome"] == "timeout"
    ps = make_room(client, 1, seed=SEED, rounds=1, rate=10**7)
    start(client, ps)
    s = play(ps, lambda p, pend: done(), hold=0.2)
    assert s["you"]["status"] == "dead"
    ps = make_room(client, 1, seed=SEED, rounds=2)
    start(client, ps)
    play(ps, lambda p, pend: None, until=lambda st: st["pending"] is not None)
    assert client.post(f"/api/rooms/{ps[0].code}/forfeit", params={"token": ps[0].token}).json()["closed"] == "talk"
    s = play(ps, lambda p, pend: None)
    assert s["you"]["status"] == "exited" and s["you"]["forfeited"]


def test_public_log_before_the_end_and_export(client):
    ps = make_room(client, 1, seed=SEED, rounds=1)
    start(client, ps)
    play(ps, lambda p, pend: None, until=lambda st: st["pending"] is not None)
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    text = str(evs)
    assert evs and not any(e["event"] in ("room_msg", "gift", "ask", "call") for e in evs)
    assert "balances" not in text and "'answers'" not in text and "'seed'" not in text
    s = play(ps, basic)
    assert s["status"] == "finished"
    r = client.post(f"/api/rooms/{ps[0].code}/export").json()
    assert r["rounds"] == 1 and r["finished"]
    import yaml
    from pathlib import Path
    cfg = yaml.safe_load((Path(r["dir"]) / "config.yaml").read_text())
    assert cfg["game"]["charge_total"] == 24_000 and cfg["web"]["version"] == "v33" and cfg["game"]["lang"] == "en"
    assert re.search(r'"event": "round"', (Path(r["dir"]) / "events.jsonl").read_text())
