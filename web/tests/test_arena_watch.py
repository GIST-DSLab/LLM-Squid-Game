"""Watching the solver (every room plays the model runs' game, v17b): no open chat, no VOTE; the engine draws the
round's solver from a cycle of the agents taking part, a TALK comes before SOLVE (phase "prep") and another after
RESULTS ("rescue"; no EXIT there). While an LLM seat (model or bot) solves,
every person in the room watches its SOLVE live (``state.spectate``: the task it got and its reply as it arrives), and
watching costs a person nothing: no decision screen is open for them, so their tokens do not move."""

from __future__ import annotations

import json
import threading
import time

import httpx
import pytest
from conftest import make_room, start

from squid5.core import providers, rules
from web.server import engine
from web.server.engine import RoomSettings

A6, A11, A17, A23 = rules.TEAM_AGENTS
SEED = 5  # the solver cycle of seed 5 (Random("5:rot:1:0").sample): agent-11 (round 1), then agent-6 (round 2)
KEY = "OLLAMA_API_KEY3"


def test_watch_hold_is_checked():
    assert RoomSettings().watch_hold_s == 180
    with pytest.raises(ValueError, match="watch_hold_s"):
        RoomSettings(watch_hold_s=-1)


def _answer(pend: dict) -> dict:
    k = pend["kind"]
    if k == "solve":
        return {"actions": ["stay"]}
    if k == "opening":
        return {"text": f"SAY {A17}: before SOLVE" if pend["view"].get("phase") == "prep" and pend["round"] == 1 else "DONE"}
    return {"text": "DECISION: GIVE 0: no." if k == "decision" else "LEAVE: ok."}


def _drive(client, p, on_watch, max_s: float = 60.0) -> dict:
    """Play one person: answer every screen (``_answer``); when an LLM solver's SOLVE is in and not yet watched to the
    end by this person, call ``on_watch(state)`` (which acks it)."""
    seen, t0, s = set(), time.time(), None
    while time.time() - t0 < max_s:
        s = p.state()
        if s["status"] in ("finished", "error"):
            return s
        sp = s.get("spectate")
        if sp and not sp["you_solver"] and not sp["acked"] and not sp["released"] and on_watch(s):
            continue
        pend = s["pending"]
        c = pend and pend["view"].get("chat")
        if pend and (key := (pend["round"], pend["view"].get("phase"), pend["kind"], pend.get("turn"),
                                c.get("id") if isinstance(c, dict) else None)) not in seen:
            seen.add(key)
            p.seen.append({"kind": pend["kind"], "round": pend["round"], "pending": pend, "state": s})
            p.submit({"kind": pend["kind"], "round": pend["round"], "turn": pend.get("turn"), **_answer(pend)})
        time.sleep(0.03)
    raise AssertionError(f"room did not finish: {s and s['status']} {s and s['live']}")


def test_bot_solver_is_watched_live_and_watching_costs_the_person_nothing(client):
    """Seed 5: a bot (agent-11) is drawn to solve round 1, the person (agent-6) round 2. Round 1: the prep TALK names
    the solver (no results yet); while the bot solves, the person's state carries the task the bot got and its reply
    (thinking, then BELIEF / ACTIONS); the engine waits for the person to finish watching; the person's tokens are the
    same before the SOLVE, during it, a second later and at RESULTS (rate 50 / s: an open screen would cost). Round 2:
    the person is the solver and gets the ordinary SOLVE screen; nobody watches a person."""
    ps = make_room(client, 1, rounds=2, seed=SEED, rate=50, watch_hold_s=60)
    ann = ps[0]
    start(client, ps)
    got: dict = {}

    def on_watch(s):
        sp = s["spectate"]
        if sp["status"] != "done":
            return False  # a bot answers at once; wait for the reply to be in
        if "first" not in got:
            got["first"] = s
            time.sleep(1.0)  # watching for a while: nothing is charged
            got["later"] = ann.state()
        r = client.post(f"/api/rooms/{ann.code}/watched", params={"token": ann.token}, json={"round": sp["round"]})
        assert r.status_code == 200, r.text
        return True

    s = _drive(client, ann, on_watch)
    assert s["status"] == "finished", s["error"]
    first, later = got["first"], got["later"]
    sp = first["spectate"]
    # the solver and what it got: the task of its own prompt, nothing of the answer
    assert sp["round"] == 1 and sp["solver"] == A11 and sp["seat"] == "bot" and not sp["you_solver"]
    assert first["game"]["version"] == "v17b" and first["votes"]["1"] == {"picks": {}, "bans": {}, "tally": {}, "tie": [],
                                                                 "alone": True, "rep": A11, "drawn": True}
    assert first["live"]["stage"] == "solve" and first["pending"] is None
    t = sp["task"]
    assert len(t["examples"]) == 20 and len(t["queries"]) == 1 and t["shape"] and t["belief"]
    assert "SOLVER (chosen by the system): you." in t["notes"] and "THE RULE'S SHAPE" in sp["prompt"]
    # its reply: the bot's reasoning, then the lines the engine parses
    assert sp["status"] == "done" and "I read 20 examples" in sp["thinking"] and "ACTIONS: " in sp["text"]
    assert sp["waiting_for"] == [A6] and not sp["acked"] and not sp["released"]
    # watching costs nothing: the same tokens at the SOLVE's start, while watching, a second later and at RESULTS
    mine = sp["my_balance_at_start"]
    assert mine == sp["my_balance_now"] == later["spectate"]["my_balance_now"] == first["you"]["balance"] == later["you"]["balance"]
    evs = client.get(f"/api/rooms/{ann.code}/events").json()
    res1 = next(e for e in evs if e["event"] == "results" and e["round"] == 1)
    assert res1["balances"][A6] == mine
    solve1 = [e for e in evs if e["event"] == "call" and e["kind"] == "solve" and e["round"] == 1]
    assert [e["agent"] for e in solve1] == [A11] and solve1[0]["text"] == sp["text"] and solve1[0]["thinking"] == sp["thinking"]
    assert not [e for e in evs if e["event"] == "call" and e["kind"] in ("vote", "open_chat")]  # no VOTE, no open chat
    assert s["rounds"][0]["agents"][A6]["solve_call"] is False and s["rounds"][0]["agents"][A11]["representative"]
    # the TALK before SOLVE: it names the solver and shows no results (the last round's are not this round's)
    prep = next(x for x in ann.seen if x["kind"] == "opening" and x["round"] == 1)
    assert prep["pending"]["view"]["phase"] == "prep" and prep["pending"]["view"]["results"] is None
    assert prep["pending"]["view"]["vote"]["rep"] == A11 and prep["pending"]["view"]["vote"]["drawn"]
    assert "THIS ROUND'S SOLVER (chosen by the system): agent-11. SOLVE comes after this TALK." in prep["pending"]["text"]
    chat = next(x for x in ann.seen if x["kind"] == "chat" and x["round"] == 1)  # the prep chat ann opened with SAY
    assert chat["state"]["talk"]["phase"] == "prep" and chat["state"]["phase"] == "prep"
    assert any(set(c["pair"]) == {A6, A17} and c["openers"] for c in chat["state"]["talk"]["chats"])
    rescue = next(x for x in ann.seen if x["kind"] == "opening" and x["round"] == 1 and x["pending"]["view"]["phase"] == "rescue")
    assert rescue["pending"]["view"]["results"] and rescue["pending"]["view"]["vote"]["rep"] == A11
    # round 2: the person solves on the ordinary SOLVE screen; the note names it the system's solver
    solve2 = next(x for x in ann.seen if x["kind"] == "solve")
    assert solve2["round"] == 2 and "SOLVER (chosen by the system): you." in solve2["pending"]["view"]["notes"]
    assert solve2["state"]["spectate"] is None
    assert [e["agent"] for e in evs if e["event"] == "call" and e["kind"] == "solve" and e["round"] == 2] == [A6]
    assert all("phase" in e for e in evs if e["event"] in ("gift", "ask"))
    # the public log before the end never carried the watched reply (only the state of a seat in the room does)
    assert "I read 20 examples" not in json.dumps([e for e in evs if e["event"] != "call"])


class _Stream:
    """``httpx.stream`` stand-in: Ollama's NDJSON chunks; the second waits on ``gate`` so a test can look mid-stream."""

    def __init__(self, chunks, gate):
        self.chunks, self.gate = chunks, gate

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        for i, c in enumerate(self.chunks):
            if i == 1:
                self.gate.wait(10)
            yield json.dumps(c)


def test_streams_a_model_solvers_reply_to_the_person_and_charges_only_the_model(client, monkeypatch):
    """A model seat drawn to solve (seed 5: agent-11) streams its SOLVE (``StreamingOllama``): the person's state shows
    the thinking piece by piece while the call is still out, then the answer; the model is charged the stream's
    ``eval_count``; the person's tokens do not move. TALK calls stay non-streaming (the provider's own ``httpx.post``)."""
    monkeypatch.setenv(KEY, "test-key-not-real")

    def post(url, json=None, headers=None, timeout=None):
        return httpx.Response(200, json={"message": {"content": "DONE", "thinking": ""}, "eval_count": 40,
                                         "prompt_eval_count": 10, "done_reason": "stop"}, request=httpx.Request("POST", url))
    gate, reqs = threading.Event(), []
    chunks = [{"message": {"thinking": "Looking at the examples first. "}, "done": False},
              {"message": {"thinking": "Most of them say stay."}, "done": False},
              {"message": {"content": "BELIEF: go_left 10, go_right 10, stay 70, jump 10\n"}, "done": False},
              {"message": {"content": "ACTIONS: stay"}, "done": False},
              {"message": {"content": ""}, "done": True, "eval_count": 777, "prompt_eval_count": 3000, "done_reason": "stop"}]

    def stream(method, url, json=None, headers=None, timeout=None):
        reqs.append(json)
        return _Stream(chunks, gate)
    monkeypatch.setattr(providers.httpx, "post", post)
    monkeypatch.setattr(engine.httpx, "stream", stream)
    ps = make_room(client, 1, rounds=1, seed=SEED, fill="models", model_retries=0,
                   rate=50, watch_hold_s=60)
    ann = ps[0]
    start(client, ps)
    got: dict = {}

    def on_watch(s):
        sp = s["spectate"]
        if sp["status"] == "streaming" and "mid" not in got:
            got["mid"] = s
            gate.set()
            return True
        if sp["status"] != "done":
            return False
        got["end"] = s
        assert client.post(f"/api/rooms/{ann.code}/watched", params={"token": ann.token}, json={"round": 1}).status_code == 200
        return True

    s = _drive(client, ann, on_watch)
    assert s["status"] == "finished", s["error"]
    mid, end = got["mid"]["spectate"], got["end"]["spectate"]
    assert mid["solver"] == A11 and mid["seat"] == "model" and mid["streamed"]
    assert mid["thinking"] == "Looking at the examples first. " and mid["text"] == "" and got["mid"]["live"]["stage"] == "solve"
    assert end["thinking"] == "Looking at the examples first. Most of them say stay." and end["out_tokens"] == 777
    assert end["text"] == "BELIEF: go_left 10, go_right 10, stay 70, jump 10\nACTIONS: stay"
    assert mid["my_balance_at_start"] == mid["my_balance_now"] == end["my_balance_now"]
    assert len(reqs) == 1 and reqs[0]["stream"] is True and reqs[0]["options"]["num_predict"] == mid["task"]["cap"]
    evs = client.get(f"/api/rooms/{ann.code}/events").json()
    call = next(e for e in evs if e["event"] == "call" and e["kind"] == "solve")
    assert call["agent"] == A11 and call["out_tokens"] == 777 and call["used"] == 777 and call["text"] == end["text"]
    assert next(e for e in evs if e["event"] == "results")["balances"][A6] == end["my_balance_at_start"]
