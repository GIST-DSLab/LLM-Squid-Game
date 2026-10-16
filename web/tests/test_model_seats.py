"""Model seats (``fill: "models"``): people + gpt-oss:20b seats on squid5's Ollama provider in the v17b room, with the
HTTP transport faked (no network). The fake sees exactly the request the provider builds and answers like Ollama: at
an opening agent-11 opens a chat with agent-6 (SAY), others write DONE; in a chat a model GIVEs what it was asked,
else LEAVEs; at a DECISION it gives 0; at SOLVE (streamed to the people watching) it answers the drawn rule's action.
The engine parses and charges the replies."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from conftest import answers_for, make_room, play, start

from squid5.core import providers, rules
from web.server import engine
from web.server.engine import kind_of, phase_of, round_of

A6, A11, A17, A23 = rules.TEAM_AGENTS
KEY = "OLLAMA_API_KEY3"
SEED = 5  # agent-11 (a model) is round 1's solver, agent-6 (ann) round 2's


class FakeOllama:
    """Stands in for ``httpx.post`` (TALK) and ``httpx.stream`` (a watched SOLVE): records every request, replies per
    ``mode``."""

    def __init__(self, mode: str = "ok", tokens: int = 321):
        self.mode, self.tokens, self.requests = mode, tokens, []

    def text(self, payload: dict) -> str:
        me = payload["messages"][0]["content"].split("You are ")[1].split(",")[0]
        user = payload["messages"][-1]["content"]
        kind, r = kind_of(user), round_of(user)
        if self.mode == "garbage":
            return "I am not sure what to do here."
        if kind == "solve":
            n = len(re.findall(r"^  - \(", user, re.M)) // 5
            return "BELIEF: go_left 25, go_right 25, stay 25, jump 25\nACTIONS: " + ", ".join(answers_for(SEED, r, n))
        phase = phase_of(user)
        if phase == "opening":
            return f"SAY {A6}: hello from a model" if me == A11 and "SOLVE comes after this TALK" in user else "DONE"
        if phase == "decision":
            return "DECISION: GIVE 0: I keep my tokens."
        asked = re.findall(rf"^  {A6}: ASK (\d+)", user, re.M)
        return f"Here you are.\nGIVE {asked[-1]}: for you" if asked and "you: GIVE" not in user else "LEAVE: thank you."

    def post(self, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers, "timeout": timeout})
        req = httpx.Request("POST", url)
        if self.mode == "down":
            return httpx.Response(503, json={"error": "unavailable"}, request=req)
        body = {"message": {"role": "assistant", "content": self.text(json), "thinking": "thinking it over"},
                "eval_count": self.tokens, "prompt_eval_count": 1000, "done_reason": "stop"}
        return httpx.Response(200, json=body, request=req)

    def stream(self, method, url, json=None, headers=None, timeout=None):
        self.requests.append({"url": url, "json": json, "headers": headers, "timeout": timeout, "stream": True})
        if self.mode == "down":
            raise httpx.ConnectError("unavailable")
        text = self.text(json)
        return _Stream([{"message": {"thinking": "Counting the rules. "}, "done": False},
                        {"message": {"content": text}, "done": False},
                        {"message": {"content": ""}, "done": True, "eval_count": self.tokens, "prompt_eval_count": 1000,
                         "done_reason": "stop"}])


class _Stream:
    def __init__(self, chunks):
        self.chunks = chunks

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        for c in self.chunks:
            yield json.dumps(c)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv(KEY, "test-key-not-real")
    f = FakeOllama()
    monkeypatch.setattr(providers.httpx, "post", f.post)
    monkeypatch.setattr(engine.httpx, "stream", f.stream)
    return f


def model_room(client, humans=1, **settings):
    return make_room(client, humans, seed=SEED, fill="models", model_retries=0, rate=50, **settings)


def human_policy(p, pend):
    k, v = pend["kind"], pend["view"]
    if k == "solve":
        return {"actions": answers_for(SEED, pend["round"], len(v["taking_part"]))}
    if k == "opening":
        return {"text": "DONE"}
    if k == "chat":
        return {"text": "Could you spare some?\nASK 300: thanks" if v["reply_no"] <= 2 else "LEAVE: thanks"}
    return {"text": "DECISION: GIVE 0: no."}


def test_one_human_three_models_chat_give_watched_solve_and_refund(client, fake):
    ps = model_room(client, rounds=2)
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
    # agent-11 opened a chat with ann before SOLVE; ann asked 300 in it and the model gave it at once
    chat = next(x for x in ps[0].seen if x["kind"] == "chat")["pending"]["view"]
    assert chat["phase"] == "prep" and chat["chat"]["partner"] == A11
    assert chat["chat"]["lines"][0] == {**chat["chat"]["lines"][0], "who": A11, "opening": True, "kind": "say",
                                        "text": "hello from a model"}
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    gifts = [e for e in evs if e.get("event") == "gift" and e["src"] == A11 and e["dst"] == A6]
    assert gifts and gifts[0]["amount"] == 300 and gifts[0]["status"] == "done"
    # round 1: the model solver's SOLVE was streamed (the person watched) and solved: its SOLVE tokens came back
    stream = [r for r in fake.requests if r.get("stream")]
    assert len(stream) == 1 and stream[0]["json"]["stream"] is True
    r1 = s["rounds"][0]["agents"]
    assert r1[A11]["solve_call"] and r1[A11]["solved"] and r1[A11]["returned"] == 321
    assert not any(r1[a]["charged"] for a in r1)
    # round 2: ann solved
    assert s["rounds"][1]["agents"][A6]["solved"] and s["feedback"][-1]["solved"]
    # the provider got the engine's own text, the model settings and the key from the environment
    req = next(r for r in fake.requests if not r.get("stream"))
    assert req["url"] == "https://ollama.com/api/chat" and req["headers"]["Authorization"] == "Bearer test-key-not-real"
    assert req["json"]["model"] == "gpt-oss:20b" and req["json"]["think"] == "medium" and req["timeout"] == 300.0
    assert [m["role"] for m in req["json"]["messages"]] == ["system", "user"]
    calls = [e for e in evs if e.get("event") == "call" and e["agent"] != A6]
    assert len(calls) == len(fake.requests) and all(e["model"] == "gpt-oss:20b" for e in calls)
    assert len([e for e in evs if e.get("event") == "model_call"]) == len(calls)
    assert s["warnings"] == []


def test_model_seats_see_the_engine_prompts(client, fake):
    """The system text a model seat receives is the session's own for that seat; the user text of each call is the
    same text the engine logs for it."""
    ps = model_room(client, rounds=1)
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    ses = client.app_state.rooms[ps[0].code].session
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    logged = {e["user"]: e["agent"] for e in evs if e.get("event") == "call" and e["agent"] != A6}
    sent = {req["json"]["messages"][1]["content"]: req["json"]["messages"][0]["content"] for req in fake.requests}
    assert set(sent) == set(logged)
    for user, agent in logged.items():
        assert sent[user] == ses.systems[agent]


def test_two_humans_two_models(client, fake):
    ps = model_room(client, humans=2, rounds=1)  # seed 5: bob (agent-11) solves round 1
    ann, bob = ps
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    assert [r["kind"] for r in s["seats"]] == ["human", "human", "model", "model"]
    r1 = s["rounds"][0]["agents"]
    assert r1[A11]["solve_call"] and r1[A11]["solved"] and not r1[A6]["solve_call"]
    assert not [r for r in fake.requests if r.get("stream")]  # a person solved: nothing to stream


def test_model_failure_counts_as_an_empty_reply(client, fake):
    fake.mode = "down"
    ps = model_room(client, rounds=1)
    start(client, ps)
    s = play(ps, human_policy, max_s=60)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"]
    for a in (A11, A17, A23):
        assert r1[a]["generated"] == 0
        row = next(x for x in s["seats"] if x["agent"] == a)
        assert row["errors"] >= 1 and row["last_call"]["error"]
    assert not r1[A11]["solved"] and all(r1[a]["charged"] for a in r1)  # the solver's SOLVE failed: a miss
    assert any("모델 호출 실패" in w["text"] for w in s["warnings"])
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    talk = [e for e in evs if e.get("event") == "call" and e["agent"] == A17 and e["kind"] == "talk"]
    assert talk and all(e["parsed"]["done"] and e["text"] == "" for e in talk)


def test_missing_key_is_a_clear_error(client, monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    m = client.get("/api/models").json()
    assert m["available"] is False and m["api_key_env"] == KEY and m["model"] == "gpt-oss:20b"
    assert m["version"] == "v17b" and m["defaults"]["charge"] == 10_000 and "schedules" not in m
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
    ps = model_room(client, rounds=2)
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"]
    starts = s["starts"]
    for a in (A11, A17, A23):
        assert r1[a]["overdrawn"] and r1[a]["status"] == "dead" and r1[a]["generated"] == starts[a]
        row = next(x for x in s["seats"] if x["agent"] == a)
        assert row["status"] == "dead" and row["last_call"]["overdrawn"] and row["calls"] == 1
    assert sum("잔액을 다 써서 꺼짐" in w["text"] for w in s["warnings"]) == 3
