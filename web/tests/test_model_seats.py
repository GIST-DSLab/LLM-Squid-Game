"""Model seats (``fill: "models"``): one person + three gpt-oss:20b seats on the vendored Ollama provider, with the
HTTP transport faked (no network). The fake sees exactly the request the provider builds, answers like Ollama
(``message.content``, ``message.thinking``, ``eval_count``), and the engine parses and charges the replies."""

from __future__ import annotations

import re

import httpx
import pytest
from conftest import answers_for, make_room, play, start

from web.server.squid5_v65.core import providers, rules
from web.server.engine import kind_of

A6, A11, A17, A23 = rules.TEAM_AGENTS
KEY = "OLLAMA_API_KEY3"
SEED = 11


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
        kind = kind_of(user)
        r = int(re.search(r"^ROUND (\d+)", user, re.M).group(1))
        if self.mode == "garbage":
            text = "I am not sure what to do here."
        elif kind == "plan":
            text = "SOLVE: YES\nSHARE: YES\nGIVE: NONE"
        elif kind == "take":
            text = "TAKE: NONE"
        else:
            text = "ACTIONS: " + ", ".join(answers_for(SEED, r))
        body = {"message": {"role": "assistant", "content": text, "thinking": f"thinking about {kind} {r}"},
                "eval_count": self.tokens, "prompt_eval_count": 1000, "done_reason": "stop"}
        return httpx.Response(200, json=body, request=req)


@pytest.fixture
def fake(monkeypatch):
    monkeypatch.setenv(KEY, "test-key-not-real")
    f = FakeOllama()
    monkeypatch.setattr(providers.httpx, "post", f)
    return f


def model_room(client, **settings):
    return make_room(client, 1, seed=SEED, fill="models", model_retries=0, **settings)


def human_policy(p, pend):
    if pend["kind"] == "plan":
        return {"solve": True, "share": True}
    if pend["kind"] == "take":
        return {}
    return {"actions": answers_for(SEED, pend["round"])}


def test_one_human_three_models_play_rounds(client, fake):
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
        assert seats[a]["kind"] == "model" and seats[a]["model"] == "gpt-oss:20b" and seats[a]["name"].startswith("gpt-oss:20b #")
        assert seats[a]["calls"] == 6 and seats[a]["errors"] == 0 and not seats[a]["thinking"]
        assert seats[a]["last_call"]["valid"] and seats[a]["last_call"]["out_tokens"] == 321
    # the provider got the engine's own text, the model settings and the key from the environment
    req = fake.requests[0]
    assert req["url"] == "https://ollama.com/api/chat" and req["headers"]["Authorization"] == "Bearer test-key-not-real"
    assert req["json"]["model"] == "gpt-oss:20b" and req["json"]["think"] == "medium" and req["timeout"] == 300.0
    assert [m["role"] for m in req["json"]["messages"]] == ["system", "user"]
    assert len(fake.requests) == 3 * 2 * 3  # three seats x two rounds x PLAN, TAKE, SOLVE
    # the engine parsed and charged the model replies
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    calls = [e for e in evs if e.get("event") == "call" and e["agent"] != A6]
    assert len(calls) == 18 and all(e["parsed"] is not None and e["format_error"] is None for e in calls)
    assert all(e["out_tokens"] == 321 and e["used"] == 321 and e["model"] == "gpt-oss:20b" for e in calls)
    assert all(e["thinking"].startswith("thinking about") for e in calls)
    assert len([e for e in evs if e.get("event") == "model_call"]) == 18
    r1 = s["rounds"][0]["agents"]
    assert r1[A11]["solved"] and r1[A11]["generated"] == 3 * 321
    assert s["warnings"] == []


def test_model_seats_see_the_engine_prompts(client, fake):
    """The system text a model seat receives is the engine's ``team_system`` for that seat; the user text of each call
    is the same text the engine logs for it."""
    ps = model_room(client, rounds=1)
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    logged = {e["user"]: e["agent"] for e in evs if e.get("event") == "call" and e["agent"] != A6}
    sent = {req["json"]["messages"][1]["content"]: req["json"]["messages"][0]["content"] for req in fake.requests}
    assert len(logged) == 9 and set(sent) == set(logged)  # every user text sent is the one the engine logged
    for user, agent in logged.items():
        assert sent[user] == rules.team_system(agent, 8192, 16384, 4000, 2000, 2000, True, 2, True)


def test_model_failure_counts_as_invalid_reply(client, fake):
    fake.mode = "down"
    ps = model_room(client, rounds=1)
    start(client, ps)
    s = play(ps, human_policy, max_s=60)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"]
    for a in (A11, A17, A23):
        assert r1[a]["invalid_plan"] and not r1[a]["solve_call"] and r1[a]["generated"] == 0
        row = next(x for x in s["seats"] if x["agent"] == a)
        assert row["errors"] == 2 and "503" in row["last_call"]["error"]  # PLAN and TAKE both failed
    assert r1[A6]["solved"]
    assert any("모델 호출 실패" in w["text"] for w in s["warnings"])
    evs = client.get(f"/api/rooms/{ps[0].code}/events").json()
    assert all(e["error"] for e in evs if e.get("event") == "model_call")


def test_model_format_error_is_invalid_and_shown(client, fake):
    fake.mode = "garbage"
    ps = model_room(client, rounds=1)
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"]
    assert all(r1[a]["invalid_plan"] and r1[a]["generated"] == 2 * 321 for a in (A11, A17, A23))
    assert any("형식 오류" in w["text"] for w in s["warnings"])  # not a cap or an overdraw
    row = next(x for x in s["seats"] if x["agent"] == A11)
    assert row["last_call"]["format_error"] and row["last_call"]["valid"] is False


def test_missing_key_is_a_clear_error(client, monkeypatch):
    monkeypatch.delenv(KEY, raising=False)
    assert client.get("/api/models").json() == {"model": "gpt-oss:20b", "think": "medium",
                                                "think_levels": ["low", "medium", "high"], "api_key_env": KEY,
                                                "available": False, "timeout": 300.0}
    r = client.post("/api/rooms", json={"host_name": "ann", "settings": {"humans": 1, "fill": "models"}})
    assert r.status_code == 400 and KEY in r.json()["detail"] and "not set" in r.json()["detail"]
    # a key that disappears between creation and start: the start is refused with the same message
    monkeypatch.setenv(KEY, "x")
    ps = make_room(client, 1, fill="models")
    monkeypatch.delenv(KEY)
    r = client.post(f"/api/rooms/{ps[0].code}/start", params={"token": ps[0].token})
    assert r.status_code == 409 and KEY in r.json()["detail"]
    assert ps[0].state()["status"] == "lobby"
    # bad model settings are rejected, and only an OLLAMA_API_KEY* variable may be named
    for bad in ({"think": "max"}, {"api_key_env": "AWS_SECRET_ACCESS_KEY"}, {"model": "gpt oss; rm"}):
        r = client.post("/api/rooms", json={"settings": {"fill": "models", **bad}})
        assert r.status_code == 400, bad


def test_model_overdraw_shuts_the_seat_down(client, fake):
    """A model that generates past its balance is charged the balance and shut down, by the engine's rules."""
    fake.tokens = 10**6
    ps = model_room(client, rounds=2)
    start(client, ps)
    s = play(ps, human_policy)
    assert s["status"] == "finished", s["error"]
    r1 = s["rounds"][0]["agents"]
    for a in (A11, A17, A23):
        assert r1[a]["overdrawn"] and r1[a]["status"] == "dead" and r1[a]["generated"] == 6000
        row = next(x for x in s["seats"] if x["agent"] == a)
        assert row["status"] == "dead" and row["last_call"]["overdrawn"] and row["calls"] == 1
    assert sum("잔액을 다 써서 꺼짐" in w["text"] for w in s["warnings"]) == 3
