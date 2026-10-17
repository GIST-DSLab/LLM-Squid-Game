"""The thread-free room: a whole game through replay(), with people, bots and stub models (no network)."""

import asyncio
import json

import pytest

import modelcalls
import replay as R
from replay import E
from squid5.core.puzzle import ACTIONS


class Clock:
    def __init__(self, t=1_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def clock(monkeypatch):
    c = Clock()
    monkeypatch.setattr(E.time, "time", c)  # HumanSeat.cost reads time.time()
    return c


def human_reply(p) -> dict:
    """A plain person: opens no chat, leaves chats, gives nothing, answers SOLVE with the first action."""
    if p.kind == "solve":
        return {"kind": "solve", "round": p.round, "actions": [ACTIONS[0]] * max(1, p.view.get("n") or 1)}
    text = {"opening": "DONE", "chat": "LEAVE: thanks.", "decision": "DECISION: GIVE 0: no."}[p.kind]
    return {"kind": p.kind, "round": p.round, "turn": p.turn, "text": text}


def stub_model(info) -> E.Reply:
    """A deterministic model: DONE / LEAVE / GIVE 0, and the first action at SOLVE."""
    user = info["messages"][-1]["content"]
    ph = E.phase_of(user)
    text = {"opening": "DONE", "chat": "LEAVE: ok", "decision": "DECISION: GIVE 0: no"}.get(ph)
    if text is None:
        text = "BELIEF: " + ", ".join(f"{a} {100 if a == ACTIONS[0] else 0}" for a in ACTIONS) + "\nACTIONS: " + ACTIONS[0]
    return E.Reply(text, 40)


def play(room, clock, max_steps=2000, models=False):
    """Drive the room to its end: people answer after 2 s, watchers ack, models answer from the stub."""
    for _ in range(max_steps):
        if room.status != "running":
            return
        clock.t += 2
        for seat in room.humans():
            if seat.pending is not None:
                room.submit(seat.token, human_reply(seat.pending))
                break
        else:
            if room.watch and any(k[0] == "watch" for k in room.needs):
                for seat in room.humans():
                    try:
                        room.watch_ack(seat, room.watch["round"])
                    except LookupError:
                        pass
                room.advance()
            elif models and room.model_jobs():
                key, info = room.model_jobs()[0]
                room.record_model(key, stub_model(info), 1.0, None)
                room.advance()
            else:
                room.tick()
    raise AssertionError(f"not finished after {max_steps} steps: {room.status} needs={list(room.needs)}")


def me(room, token):
    """Seats are rebuilt on every replay; a token finds the current one."""
    return room.seat_by_token(token)


def new_room(clock, **kw):
    s = E.RoomSettings(seed=kw.pop("seed", 4101), **kw)
    room = R.ReplayRoom("TEST01", s, clock=clock)
    return room


def test_one_person_three_bots_full_game(clock):
    room = new_room(clock, humans=1, fill="bots")
    seat = room.join("me").token
    room.start()
    assert room.status == "running" and me(room, seat).pending is not None  # the opening turn waits for the person
    st = room.state(me(room, seat))
    assert st["pending"]["kind"] == "opening" and st["you"]["agent"] == me(room, seat).agent
    play(room, clock)
    assert room.status == "finished", room.error
    assert room.result["rounds_played"] >= 1
    kinds = [e.get("event") for e in room.events]
    assert kinds[0] == "room" and "session_start" in kinds and kinds[-1] == "session"
    # rebuilt from what a Durable Object stores: the same events, the same end
    doc = json.loads(json.dumps(room.doc))
    replies = json.loads(json.dumps({a: {str(i): r for i, r in v.items()} for a, v in room.replies.items()}))
    again = R.ReplayRoom.load(doc, replies, clock=clock)
    assert again.status == "finished"
    assert json.dumps(again.events, default=str) == json.dumps(room.events, default=str)


def test_new_events_are_only_the_tail(clock):
    room = new_room(clock, humans=1, fill="bots")
    seat = room.join("me").token
    room.start()
    first = room.new_events()
    assert [s for s, _ in first] == list(range(1, len(first) + 1))
    room.submit(seat, human_reply(me(room, seat).pending))
    tail = room.new_events()
    assert tail and tail[0][0] == len(first) + 1
    assert [e for _, e in first] == room.events[:len(first)]


def test_human_timeout_and_overdraw(clock):
    room = new_room(clock, humans=1, fill="bots", talk_timeout_s=30)
    seat = room.join("me").token
    room.start()
    p = me(room, seat).pending
    assert room.wake_at() == pytest.approx(min(p.created_at + 30, p.opened_at + p.balance / room.settings.rate))
    clock.t += 31
    assert room.tick()
    rec = room.replies[me(room, seat).agent][0]
    assert rec["outcome"] == "timeout" and rec["text"] == "" and rec["charged"] == round(31 * room.settings.rate)


def test_two_people_one_batch(clock):
    room = new_room(clock, humans=2, fill="bots")
    a, b = room.join("a").token, room.join("b").token
    room.start()
    assert me(room, a).pending and me(room, b).pending  # the opening turn calls every agent at once
    room.submit(a, human_reply(me(room, a).pending))
    assert room.needs and me(room, b).pending is not None and me(room, a).pending is None  # still waiting for b: no replay yet
    room.submit(b, human_reply(me(room, b).pending))
    assert ("human", me(room, a).agent, 0) not in room.needs
    play(room, clock)
    assert room.status == "finished"


def test_forfeit_answers_for_the_seat(clock):
    room = new_room(clock, humans=2, fill="bots")
    a, b = room.join("a").token, room.join("b").token
    room.start()
    assert room.forfeit(a) == "opening"
    assert room.replies[me(room, a).agent][0]["outcome"] == "forfeit"
    play(room, clock)
    assert room.status == "finished"
    assert room.result["agents"][me(room, a).agent]["status"] == "exited"


def test_model_seats_with_stub_one_call_at_a_time(clock):
    room = new_room(clock, humans=1, fill="models", rounds=2)
    seat = room.join("me").token
    room.start()
    jobs = room.model_jobs()
    assert len(jobs) == 3 and all(k[0] == "model" for k, _ in jobs)  # the opening batch: three model seats
    rows = {r["agent"]: r for r in room.state(me(room, seat))["seats"]}
    assert all(rows[k[1]]["thinking"] for k, _ in jobs)
    play(room, clock, models=True)
    assert room.status == "finished"
    calls = [e for e in room.events if e.get("event") == "model_call"]
    assert calls and all(c["error"] is None for c in calls)


def test_modelcalls_run_all_sequential_and_no_key1_fallback(clock):
    room = new_room(clock, humans=1, fill="models", rounds=1)
    seat = room.join("me").token
    room.start()
    asked, live = [], {"n": 0, "max": 0}

    def env_get(name):
        asked.append(name)
        return {"OLLAMA_API_KEY3": "k3", "OLLAMA_API_KEY1": "k1", "OLLAMA_KEY1_ENABLED": "on"}.get(name)

    async def failing(url, headers, payload, timeout, stream):
        live["n"] += 1
        live["max"] = max(live["max"], live["n"])
        await asyncio.sleep(0)
        live["n"] -= 1
        assert headers["Authorization"] == "Bearer k3"
        raise ollama_error()

    def ollama_error():
        return modelcalls.ollama_fetch.OllamaError("HTTP 429: busy")

    async def nosleep(_):
        return None

    made = asyncio.run(modelcalls.run_all(room, env_get, failing, clock=clock, sleep=nosleep))
    assert made >= 3 and live["max"] == 1  # one call at a time
    assert "OLLAMA_API_KEY1" not in asked  # key 3 failed: key 1 is never read
    room.submit(seat, human_reply(me(room, seat).pending))  # the person's opening completes the batch: replay
    errs = [e for e in room.events if e.get("event") == "model_call"]
    assert errs and all("429" in e["error"] for e in errs)
    assert room.status == "running"  # failed calls are empty replies (DONE at the opening); the game goes on


def test_modelcalls_streams_solve_to_watchers(clock):
    room = new_room(clock, humans=1, fill="models", rounds=4)  # the rotation draws every agent once in 4 rounds
    seat = room.join("me").token
    room.start()

    def env_get(name):
        return {"OLLAMA_API_KEY3": "k3"}.get(name)

    seen = []

    async def transport(url, headers, payload, timeout, stream):
        user = payload["messages"][-1]["content"]
        rep = stub_model({"messages": payload["messages"]})
        if not stream:
            return {"message": {"content": rep.text, "thinking": "hm"}, "eval_count": 40, "prompt_eval_count": 9}

        async def lines():
            yield json.dumps({"message": {"thinking": "let me see "}})
            w = room.watch  # people poll state between pieces: the watched SOLVE already shows this thinking
            seen.append((w["status"], w["thinking"]))
            yield json.dumps({"message": {"content": rep.text}})
            yield json.dumps({"done": True, "eval_count": 55, "prompt_eval_count": 9, "done_reason": "stop"})
        assert "SOLVE" in user
        return lines()

    for _ in range(200):
        if room.status != "running":
            break
        clock.t += 2
        if me(room, seat).pending is not None:
            room.submit(seat, human_reply(me(room, seat).pending))
        elif room.model_jobs():
            asyncio.run(modelcalls.run_all(room, env_get, transport, clock=clock))
        elif any(k[0] == "watch" for k in room.needs):
            room.watch_ack(me(room, seat), room.watch["round"])
            room.advance()
        else:
            room.tick()
    assert room.status == "finished"
    assert len(seen) >= 3 and all(x == ("streaming", "let me see ") for x in seen)
    solves = [e for e in room.events if e.get("event") == "model_call" and e["kind"] == "solve"]
    assert len(solves) == len(seen) and all(e["out_tokens"] == 55 for e in solves)
