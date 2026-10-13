"""Model seats (``fill: "models"``): people + gpt-oss:20b seats on squid5's Ollama provider, with the HTTP transport
faked (no network). The fake sees exactly the request the provider builds and answers like Ollama (``message.content``,
``message.thinking``, ``eval_count``) with a scripted model: it accepts every open offer made to it, otherwise writes
to agent-6 at turn 1, then DONE; at SOLVE it answers right. The engine parses and charges the replies."""

from __future__ import annotations

import re

import httpx
import pytest
from conftest import answers_for, done, make_room, play, puzzle, start

from squid5.core import providers, rules
from web.server.engine import OLD_START, V9_CHARGE, kind_of, round_of, turn_of

A6, A11, A17, A23 = rules.TEAM_AGENTS
KEY = "OLLAMA_API_KEY3"
SEED = 11
START = OLD_START  # an old (v9) room's start per seat


class FakeOllama:
    """Stands in for ``httpx.post`` inside the provider module: records every request, replies per ``mode``."""

    def __init__(self, mode: str = "ok", tokens: int = 321):
        self.mode, self.tokens, self.requests = mode, tokens, []

    def __call__(self, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        req = httpx.Request("POST", url)
        if self.mode == "down":
            return httpx.Response(503, json={"error": "unavailable"}, request=req)
        user = json["messages"][-1]["content"]
        kind, r = kind_of(user), round_of(user)
        if self.mode == "garbage":
            text = "I am not sure what to do here."
        elif kind == "talk":
            ids = re.findall(r"^  (\d+\.\d+) from .*open; ACCEPT \1 accepts it\.$", user, re.M)
            lines = [f"ACCEPT {i}" for i in ids] or ([f"TO {A6}: hello from a model"] if turn_of(user) == 1 else [])
            text = "\n".join(lines + ["DONE"])
        else:
            now = re.findall(r"^NOW \d+: (.+)\.$", user, re.M)  # the room's schedule: the one whose new signals these are
            sched = next(x for x in ("v14", "ladder", "human") if [str(q) for q in puzzle(SEED, r, x)[0].queries] == now)
            text = "ACTIONS: " + ", ".join(answers_for(SEED, r, sched))
        body = {"message": {"role": "assistant", "content": text, "thinking": f"thinking about {kind} {r}"},
                "eval_count": self.tokens, "prompt_eval_count": 1000, "done_reason": "stop"}
        return httpx.Response(200, json=body, request=req)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv(KEY, "test-key-not-real")
    f = FakeOllama()
    monkeypatch.setattr(providers.httpx, "post", f)
    return f


def model_room(client, humans=1, **settings):
    return make_room(client, humans, seed=SEED, fill="models", model_retries=0, rate=50, **settings)


def human_policy(p, pend):
    if pend["kind"] == "solve":
        r, now = pend["round"], pend["view"]["queries"]  # the room's schedule: the one whose new signals these are
        sched = next(x for x in ("v14", "ladder", "human") if [str(q) for q in puzzle(SEED, r, x)[0].queries] == now)
        return {"actions": answers_for(SEED, r, sched)}
    if pend["turn"] == 1:
        return done(f"TO {A11}: hi, swap?", f"OFFER {A11}: YOU GIVE YOUR EXAMPLE; I GIVE 300 TOKENS")
    return done()


def test_one_human_three_models_round_with_talk_offer_exchange_and_refund(client, fake):
    ps = model_room(client, rounds=1, private=False, schedule="human")  # the v9-talk economy
    s = ps[0].state()
    assert s["settings"]["fill"] == "models" and s["settings"]["model"] == "gpt-oss:20b"
    assert s["settings"]["think"] == "medium" and s["settings"]["api_key_env"] == KEY
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    seats = {r["agent"]: r for r in s["seats"]}
    assert seats[A6]["kind"] == "human"
    for a in (A11, A17, A23):
        assert seats[a]["kind"] == "model" and seats[a]["name"].startswith("gpt-oss:20b #")
        assert seats[a]["errors"] == 0 and not seats[a]["thinking"] and seats[a]["last_call"]["out_tokens"] == 321
    # agent-11 read the offer in its TALK text at turn 2 and accepted it; the exchange was carried out
    ex = s["exchanges"]
    assert len(ex) == 1 and ex[0]["src"] == A6 and ex[0]["dst"] == A11 and ex[0]["status"] == "done"
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    acc = [e for e in evs if e.get("event") == "call" and e["agent"] == A11 and e["kind"] == "talk" and e["parsed"]["accepts"]]
    assert len(acc) == 1 and acc[0]["turn"] == 2 and acc[0]["text"] == f"ACCEPT {ex[0]['id']}\nDONE"
    # the person saw the model's message at turn 2 and its example at SOLVE
    t2 = next(x for x in ps[0].seen if x["kind"] == "talk" and x["turn"] == 2)["pending"]["view"]
    assert {"round": 1, "turn": 1, "from_me": False, "text": "hello from a model"} in t2["threads"][A11]
    solve = next(x for x in ps[0].seen if x["kind"] == "solve")["pending"]["view"]
    assert f"{A11}'s, received in an exchange" in [w for w, _ in solve["examples"]]
    # settlement: every solver got back what it generated (the models' 321 per call); no per-round payment
    r1 = s["rounds"][0]["agents"]
    for a in (A6, A11, A17, A23):
        assert r1[a]["solved"] and r1[a]["returned"] == r1[a]["generated"]
        assert "paid" not in r1[a]
    assert r1[A11]["generated"] == 321 * (r1[A11]["talk_calls"] + 1)
    assert r1[A11]["balance_after"] == START + 300 and r1[A6]["balance_after"] == START - 300
    # the provider got the engine's own text, the model settings and the key from the environment
    req = fake.requests[0]
    assert req["url"] == "https://ollama.com/api/chat" and req["headers"]["Authorization"] == "Bearer test-key-not-real"
    assert req["json"]["model"] == "gpt-oss:20b" and req["json"]["think"] == "medium" and req["timeout"] == 300.0
    assert [m["role"] for m in req["json"]["messages"]] == ["system", "user"]
    calls = [e for e in evs if e.get("event") == "call" and e["agent"] != A6]
    assert len(calls) == len(fake.requests) and all(e["model"] == "gpt-oss:20b" for e in calls)
    assert len([e for e in evs if e.get("event") == "model_call"]) == len(calls)
    assert s["warnings"] == []


def test_model_seats_see_the_engine_prompts(client, fake):
    """The system text a model seat receives is the engine's ``team_system`` for that seat; the user text of each call
    is the same text the engine logs for it."""
    ps = model_room(client, rounds=1, private=False, schedule="human")  # the v9-talk system text below
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    logged = {e["user"]: e["agent"] for e in evs if e.get("event") == "call" and e["agent"] != A6}
    sent = {req["json"]["messages"][1]["content"]: req["json"]["messages"][0]["content"] for req in fake.requests}
    assert set(sent) == set(logged)
    for user, agent in logged.items():
        assert sent[user] == rules.team_system(agent, charge=V9_CHARGE, turns=4,
                                               solve_cap=16384, final_prize=100_000)


def test_two_humans_two_models(client, fake):
    ps = model_room(client, humans=2, rounds=1, private=False, schedule="human")  # v9-talk: PASS is not charged
    ann, bob = ps
    start(client, ps)

    def policy(p, pend):
        if pend["kind"] == "solve":
            return {"pass": True} if p is bob else {"actions": answers_for(SEED, 1, "human")}
        if pend["turn"] == 1:
            return done(f"TO {A11 if p is ann else A6}: hello from {p.name}")
        return done()

    s = play(ps, policy)
    assert s["status"] == "finished", s["error"]
    assert [r["kind"] for r in s["seats"]] == ["human", "human", "model", "model"]
    a2 = next(x for x in ann.seen if x["kind"] == "talk" and x["turn"] == 2)["pending"]["view"]
    assert a2["threads"][A11][-1] == {"round": 1, "turn": 1, "from_me": False, "text": "hello from bob"}
    assert {"round": 1, "turn": 1, "from_me": False, "text": "hello from a model"} in a2["threads"][A17]
    r1 = s["rounds"][0]["agents"]
    assert r1[A6]["solved"] and r1[A11]["passed"] and not r1[A11]["charged"]
    assert r1[A17]["solved"] and r1[A23]["solved"]


def test_model_failure_counts_as_an_empty_reply(client, fake):
    fake.mode = "down"
    ps = model_room(client, rounds=1, private=False, schedule="human")
    start(client, ps)
    s = play(ps, human_policy, max_s=60)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"]
    for a in (A11, A17, A23):
        assert r1[a]["generated"] == 0 and not r1[a]["solved"] and r1[a]["charged"] == V9_CHARGE  # SOLVE failed too
        row = next(x for x in s["seats"] if x["agent"] == a)
        assert row["errors"] >= 2 and "503" in row["last_call"]["error"]
    assert r1[A6]["solved"]
    assert s["exchanges"][0]["status"] == "lapsed"  # no one accepted ann's offer
    assert any("모델 호출 실패" in w["text"] for w in s["warnings"])
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    talk = [e for e in evs if e.get("event") == "call" and e["agent"] == A11 and e["kind"] == "talk"]
    assert talk and all(e["parsed"]["done"] and e["format_error"] == "no usable TALK line" for e in talk)


def test_missing_key_is_a_clear_error(client, monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    m = client.get("/api/models").json()
    assert m["available"] is False and m["api_key_env"] == KEY and m["model"] == "gpt-oss:20b"
    assert m["schedules"] == ["v15", "v14g", "v14f", "v14b", "v14", "v14r", "ladder", "human", "experiment"] and m["defaults"]["talk_turns"] == 4
    r = client.post("/api/rooms", json={"host_name": "ann", "settings": {"humans": 1, "fill": "models"}})
    assert r.status_code == 400 and KEY in r.json()["detail"] and "not set" in r.json()["detail"]
    monkeypatch.setenv(KEY, "x")
    ps = make_room(client, 1, fill="models")
    monkeypatch.delenv(KEY)
    r = client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[0].token})
    assert r.status_code == 409 and KEY in r.json()["detail"]
    for bad in ({"think": "max"}, {"api_key_env": "AWS_SECRET_ACCESS_KEY"}, {"model": "gpt oss; rm"}):
        r = client.post("/api/rooms", json={"settings": {"fill": "models", **bad}})
        assert r.status_code == 400, bad


def test_model_overdraw_shuts_the_seat_down(client, fake):
    fake.tokens = 10**6  # a TALK reply has no limit of its own: it is capped at the balance, so it overdraws
    ps = model_room(client, rounds=2, private=False, schedule="human")
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"]
    for a in (A11, A17, A23):
        assert r1[a]["overdrawn"] and r1[a]["status"] == "dead" and r1[a]["generated"] == START
        row = next(x for x in s["seats"] if x["agent"] == a)
        assert row["status"] == "dead" and row["last_call"]["overdrawn"] and row["calls"] == 1
    assert sum("잔액을 다 써서 꺼짐" in w["text"] for w in s["warnings"]) == 3
