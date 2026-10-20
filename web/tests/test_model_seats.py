"""Model seats (``fill: "models"``): people + API model seats in the v33 room, by default ``gpt-oss:20b`` on Ollama Cloud
(squid5's ``Ollama`` provider, https://ollama.com/api/chat, key OLLAMA_API_KEY), with the HTTP transport faked (no network). The fake sees
exactly the request the provider builds and answers like Ollama: agent-11 opens a chat with agent-6 at round 1's first
tick and GIVEs what agent-6 ASKs; at SOLVE (streamed to the people watching) a model answers the drawn rule's action.
The engine parses and charges the replies; ``model_lang: ko`` sends the models the Korean prompts."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from conftest import answers_for, basic, make_room, play, start

from squid5.core import providers, rules
from web.server import engine

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 5  # agent-11 (a model) is round 1's solver, agent-6 (ann) round 2's
SOLVE = re.compile(r"^(?:Round|라운드) (\d+): SOLVE\.")


class FakeOllama:
    """Stands in for ``httpx.post`` (TALK) and ``httpx.stream`` (a watched SOLVE): records every request, replies per
    ``mode``."""

    def __init__(self, mode: str = "ok", tokens: int = 321):
        self.mode, self.tokens, self.requests = mode, tokens, []

    def text(self, payload: dict) -> str:
        me = re.search(r"agent-\d+", payload["messages"][0]["content"]).group(0)
        user = payload["messages"][-1]["content"]
        if self.mode == "garbage":
            return "I am not sure what to do here."
        if m := SOLVE.match(user):
            return "BELIEF: go_left 25, go_right 25, stay 25, jump 25\nACTIONS: " + ", ".join(answers_for(SEED, int(m.group(1))))
        ask = re.search(rf"NEW \[R\d+ T\d+ [a-zA-Z ]+\] {A6}: ASK ([\d,]+)", user)
        if me == A11 and ask:
            return f"GIVE {A6} {ask.group(1).replace(',', '')}: for you\nDONE"
        if me == A11 and re.match(r"^(Round|라운드) 1\.", user) and re.search(r"(tick|틱) 1 \((at most|최대)", user) and "BEFORE SOLVE" in user:
            return f"TO {A6}: hello from a model\nDONE"
        return "DONE"

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
        return _Stream([{"message": {"thinking": "Counting the rules. "}, "done": False},
                        {"message": {"content": self.text(json)}, "done": False},
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
    f = FakeOllama()
    monkeypatch.setattr(providers.httpx, "post", f.post)
    monkeypatch.setattr(engine.httpx, "stream", f.stream)
    monkeypatch.setattr(engine, "ENV_FILES", [])  # never the real .env
    monkeypatch.setenv("OLLAMA_API_KEY", "test-key-not-real")
    return f


def model_room(client, humans=1, **settings):
    return make_room(client, humans, seed=SEED, fill="models", model_retries=0, rate=50, **settings)


def human(p, pend):
    """Ask agent-11 for 300 at round 1's first tick before SOLVE; else as ``basic``."""
    if pend["kind"] == "talk" and (pend["round"], pend["phase"], pend["tick"]) == (1, "prep", 1):
        return {"text": f"ASK {A11} 300: could you spare some?\nDONE"}
    return basic(p, pend)


def test_one_person_three_models_on_the_ollama_cloud_api(client, fake):
    ps = model_room(client)
    start(client, ps)
    s = play(ps, human, max_s=90)
    assert s["status"] == "finished", s["error"]
    req = fake.requests
    assert req and all(r["url"] == "https://ollama.com/api/chat" for r in req)
    assert all(r["headers"]["Authorization"] == "Bearer test-key-not-real" for r in req)
    assert {r["json"]["model"] for r in req} == {"gpt-oss:20b"} and {r["json"]["think"] for r in req} == {"medium"}
    assert any(r.get("stream") for r in req)  # agent-11's SOLVE streamed to the person watching
    gifts = [m for x in ps[0].screens("talk")[-1]["pending"]["view"]["rooms"] for m in x["msgs"] if m["kind"] == "give"]
    assert any(g["src"] == A11 and g["amount"] == 300 for g in gifts)
    assert s["rounds"][0]["solved"] and s["rounds"][0]["solver"] == A11
    assert s["rounds"][0]["agents"][A11]["generated"] >= 321 and [r["tokens"] for r in s["seats"][1:]] != [None] * 3


def test_model_seats_read_the_engine_prompts_in_their_language(client, fake):
    ps = model_room(client, rounds=1, model_lang="ko")
    start(client, ps)
    s = play(ps, human, max_s=90)
    assert s["status"] == "finished", s["error"]
    ses = client.app_state.rooms[ps[0].code].session
    sent = {}
    for r in fake.requests:
        m = r["json"]["messages"]
        sent[re.search(r"agent-\d+", m[0]["content"]).group(0)] = m
    for a, m in sent.items():
        assert m[0]["content"] == ses.systems[a] and m[0]["content"].startswith(f"당신은 {a}입니다.")
        assert m[-1]["content"].startswith("라운드 1")
    assert ses.systems[A6].startswith("You are agent-6")  # the person reads English (make_room's lang)


def test_a_failed_model_call_is_an_empty_reply_and_the_room_goes_on(client, fake):
    fake.mode = "down"
    ps = model_room(client, rounds=1)
    start(client, ps)
    s = play(ps, basic, max_s=90)
    assert s["status"] == "finished" and any("모델 호출 실패" in w["text"] for w in s["warnings"])
    assert not s["rounds"][0]["solved"]


def test_model_seats_need_the_key_and_take_any_api_model_per_seat(client, fake, monkeypatch, tmp_path):
    monkeypatch.delenv("OLLAMA_API_KEY")
    assert client.get("/api/models").json()["available"] is False
    r = client.post("/api/rooms", json={"settings": {"fill": "models"}})
    assert r.status_code == 400 and "OLLAMA_API_KEY" in r.json()["detail"]
    assert client.post("/api/rooms", json={"settings": {"fill": "bots"}}).status_code == 200
    assert client.post("/api/rooms", json={"settings": {"fill": "models", "kind": "local"}}).status_code == 400
    (tmp_path / ".env").write_text("OTHER=1\nOLLAMA_API_KEY=from-dotenv  # comment\n")  # the server reads only that line
    monkeypatch.setattr(engine, "ENV_FILES", [tmp_path / ".env"])
    m = client.get("/api/models").json()
    assert m["available"] and m["model"] == "gpt-oss:20b" and m["kind"] == "ollama" and "from-dotenv" not in str(m)
    ps = make_room(client, 1, seed=SEED, rounds=1, fill="models", model_retries=0,
                   models=[{"model": "gpt-oss:20b"}, {"kind": "ollama", "model": "gpt-oss:120b"}])
    start(client, ps)
    assert play(ps, basic, max_s=90)["status"] == "finished"
    assert [r["model"] for r in ps[0].state()["seats"][1:]] == ["gpt-oss:20b", "gpt-oss:120b", "gpt-oss:20b"]
    assert {r["json"]["model"] for r in fake.requests} == {"gpt-oss:20b", "gpt-oss:120b"}
    assert all(r["headers"]["Authorization"] == "Bearer from-dotenv" for r in fake.requests)
