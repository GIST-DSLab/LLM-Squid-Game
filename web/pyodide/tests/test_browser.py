"""browser.Arena in CPython: the page's API, model seats through a fake Worker, the record, restore after a reload,
and the offline verifier on what the browser uploads (tools/arena/verify_games.py)."""

import asyncio
import gzip
import json
import sys
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parents[3]
for _p in (REPO, REPO / "web" / "pyodide", REPO / "tools" / "arena", REPO / "web" / "cloudflare" / "src"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import browser  # noqa: E402
import entry as worker_entry  # noqa: E402  the thin Worker's request check (web/cloudflare/src/entry.py)
import ollama_fetch  # noqa: E402
import replay  # noqa: E402
import room_settings  # noqa: E402
import selfcheck  # noqa: E402
import stub_transport  # noqa: E402
import verify_games  # noqa: E402
from web.server import engine as E  # noqa: E402


class FakeWorker:
    """The thin Worker as the browser sees it: /api/models, /api/games, /llm/api/chat (logged like llm_calls)."""

    def __init__(self, fail_status=None):
        self.calls, self.games, self.live, self.max_live = [], [], 0, 0
        self.fail_status = fail_status

    async def net(self, method, url, body):
        if url.endswith("/api/models"):
            return 200, {"available": True, "key1_enabled": False, "limits": {"GAME_CALLS": 600}}
        if url.endswith("/api/games"):
            self.games.append(body)
            return 200, {"game": f"g{len(self.games)}", "token": "tok", "expires_at": 9e9}
        return 404, {"detail": "no"}

    async def transport(self, url, headers, payload, timeout, stream):
        assert url == "https://w.example/llm/api/chat" and headers["Authorization"] == "Bearer tok"
        worker_entry.chat_payload(json.loads(json.dumps(payload)), "gemma4:31b", worker_entry.LIMITS["MAX_PREDICT"])
        self.live += 1
        self.max_live = max(self.max_live, self.live)
        await asyncio.sleep(0)
        self.live -= 1
        user = payload["messages"][-1]["content"]
        n = len(self.calls) + 1
        if self.fail_status:
            self.calls.append({"n": n, "prompt_h": replay.digest(user), "status": self.fail_status, "stream": 0})
            raise ollama_fetch.http_error(self.fail_status, json.dumps({"detail": "한도에 닿았습니다", "code": "limit_game"}))
        text = stub_transport.answer(user)
        if not stream:
            self.calls.append({"n": n, "prompt_h": replay.digest(user), "status": 200, "stream": 0, "eval_count": 37,
                               "content_h": replay.digest(text)})
            return {"message": {"content": text}, "eval_count": 37, "prompt_eval_count": 9, "done_reason": "stop"}
        self.calls.append({"n": n, "prompt_h": replay.digest(user), "status": 200, "stream": 1})

        async def lines():
            yield json.dumps({"message": {"thinking": "hm "}})
            yield json.dumps({"message": {"content": text}})
            yield json.dumps({"done": True, "eval_count": 61, "prompt_eval_count": 9, "done_reason": "stop"})
        return lines()


class Hooks:
    def __init__(self):
        self.saved, self.uploads = {}, []

    def persist(self, code, text):
        self.saved[code] = text

    async def upload(self, url, token, text, summary):
        self.uploads.append((url, json.loads(text), json.loads(summary)))
        return {"status": 200, "body": {"ok": True}}


@pytest.fixture
def clock(monkeypatch):
    c = selfcheck.FakeClock()
    monkeypatch.setattr(E, "time", types.SimpleNamespace(time=c, sleep=lambda s: None))
    return c


async def call(arena, method, path, body=None):
    out = json.loads(await arena.handle(method, path, json.dumps(body) if body is not None else ""))
    return out["status"], out["body"]


async def settle(arena):
    for t in list(arena.pumps.values()) + list(arena.uploads.values()):
        await t
    await asyncio.sleep(0)


async def play(arena, clock, code, tok, limit=4000):
    for _ in range(limit):
        await settle(arena)
        st, s = await call(arena, "GET", f"/rooms/{code}/state?token={tok}")
        assert st == 200, s
        if s["status"] in ("finished", "error"):
            await settle(arena)
            return s
        clock.t += 3
        sp = s.get("spectate")
        if s.get("pending"):
            st, out = await call(arena, "POST", f"/rooms/{code}/submit?token={tok}", selfcheck.reply_for(s["pending"]))
            assert st == 200, out
        elif sp and sp.get("status") == "done" and not sp.get("acked") and not sp.get("released"):
            await call(arena, "POST", f"/rooms/{code}/watched?token={tok}", {"round": sp["round"]})
    raise AssertionError("game did not end")


def new_arena(clock, worker=None, hooks=None):
    w = worker or FakeWorker()
    return browser.Arena("https://w.example", {"bundle": "test"}, hooks or Hooks(), w.net, w.transport, clock), w


def test_settings_defaults_and_one_person_only():
    s = room_settings.make({})
    assert s.model == "gemma4:31b" and s.think is None and s.api_key_env == "OLLAMA_API_KEY3"
    assert room_settings.make({"think": "medium"}).think == "medium"
    with pytest.raises(ValueError):
        room_settings.make({"api_key_env": "OLLAMA_API_KEY2"})

    async def go():
        arena = browser.Arena("")
        st, out = await call(arena, "POST", "/rooms", {"settings": {"humans": 2, "fill": "bots"}})
        assert st == 400 and "다음 버전" in out["detail"]
        st, out = await call(arena, "POST", "/rooms/ABCDEF/join", {"name": "x"})
        assert st == 404 and "다음 버전" in out["detail"]
    asyncio.run(go())


def test_model_game_through_the_worker_records_and_verifies(clock, tmp_path):
    async def go():
        arena, w = new_arena(clock)
        st, m = await call(arena, "GET", "/models")
        assert m["available"] and m["model"] == "gemma4:31b"
        st, r = await call(arena, "POST", "/rooms", {"host_name": "me", "settings": {
            "humans": 1, "fill": "models", "seed": 4101, "rounds": 4}})
        code, tok = r["code"], r["token"]
        st, out = await call(arena, "POST", f"/rooms/{code}/start?token={tok}")
        assert st == 200 and out["game"] == "g1" and w.games[0]["settings"]["model"] == "gemma4:31b"
        s = await play(arena, clock, code, tok)
        assert s["status"] == "finished" and s["record"]["uploaded_final"]
        return arena, w, code, tok

    arena, w, code, tok = asyncio.run(go())
    hooks = arena.hooks
    assert w.max_live == 1 and len(w.calls) > 12  # one model call at a time
    rounds_seen = [u[2]["rounds"] for u in hooks.uploads]
    assert rounds_seen == sorted(rounds_seen) and rounds_seen[-1] == 4 and len(hooks.uploads) >= 4  # each round + end
    url, rec, summ = hooks.uploads[-1]
    assert url == "https://w.example/api/games/g1/record" and summ["status"] == "finished"
    assert '"tok"' not in json.dumps(rec["doc"]) and tok not in json.dumps(rec)  # no seat or game token in it
    v = verify_games.verify(json.loads(json.dumps(rec)), w.calls)
    assert v["ok"], v["problems"]
    path = verify_games.write_run(v["room"], rec, tmp_path)
    assert (path / "events.jsonl").stat().st_size > 0 and (path / "results.jsonl").read_text().count("\n") == 1

    # tampering is caught: a model reply rewritten, a person's charge lowered, an unlogged call
    bad = json.loads(json.dumps(rec))
    a, i = next((a, i) for a, v in bad["replies"].items() for i, r in v.items() if "info" in r)
    bad["replies"][a][i]["out_tokens"] = 1
    assert not verify_games.verify(bad, w.calls)["ok"]
    bad = json.loads(json.dumps(rec))
    h = bad["doc"]["humans"][0]["agent"]
    first = bad["replies"][h]["0"]
    first["charged"] = first["out_tokens"] = 0
    assert any("charged" in p for p in verify_games.verify(bad, w.calls)["problems"])
    assert any("no relayed call" in p for p in verify_games.verify(json.loads(json.dumps(rec)), [])["problems"])


def test_reload_restores_the_room(clock):
    async def go():
        arena, w = new_arena(clock)
        _, r = await call(arena, "POST", "/rooms", {"settings": {"humans": 1, "fill": "bots", "seed": 9, "rounds": 2}})
        code, tok = r["code"], r["token"]
        await call(arena, "POST", f"/rooms/{code}/start?token={tok}")
        _, s = await call(arena, "GET", f"/rooms/{code}/state?token={tok}")
        clock.t += 4
        await call(arena, "POST", f"/rooms/{code}/submit?token={tok}", selfcheck.reply_for(s["pending"]))
        await settle(arena)
        _, before = await call(arena, "GET", f"/rooms/{code}/state?token={tok}")
        fresh = browser.Arena("https://w.example", {"bundle": "test"}, Hooks(), w.net, w.transport, clock)
        assert fresh.restore(code, arena.hooks.saved[code])
        _, after = await call(fresh, "GET", f"/rooms/{code}/state?token={tok}")
        keep = ("status", "live", "round", "pending", "you", "ledger", "spectate")
        assert {k: after[k] for k in keep} == {k: before[k] for k in keep}
        assert not fresh.restore("ZZZZZZ", "{not json")
        s = await play(fresh, clock, code, tok)
        assert s["status"] == "finished"
    asyncio.run(go())


def test_quota_errors_are_final_and_korean(clock):
    async def go():
        arena, w = new_arena(clock, FakeWorker(fail_status=429))
        _, r = await call(arena, "POST", "/rooms", {"settings": {"humans": 1, "fill": "models", "seed": 5, "rounds": 1}})
        code, tok = r["code"], r["token"]
        await call(arena, "POST", f"/rooms/{code}/start?token={tok}")
        await settle(arena)
        _, s = await call(arena, "GET", f"/rooms/{code}/state?token={tok}")
        return w, s
    w, s = asyncio.run(go())
    assert len(w.calls) == 3  # three model seats, each refused once: a limit is not retried
    assert any("한도에 닿았습니다" in x["text"] for x in s["warnings"])


def test_bot_game_offline_without_worker(clock):
    async def go():
        arena = browser.Arena("", hooks=Hooks(), clock=clock)
        _, r = await call(arena, "POST", "/rooms", {"settings": {"humans": 1, "fill": "bots", "seed": 3, "rounds": 1}})
        st, out = await call(arena, "POST", f"/rooms/{r['code']}/start?token={r['token']}")
        assert st == 200 and out["game"] is None
        st, out = await call(arena, "POST", f"/rooms/{r['code']}/export?token={r['token']}")
        assert st == 409 and "오프라인" in out["detail"]
        st, out = await call(arena, "POST", "/rooms", {"settings": {"humans": 1, "fill": "models"}})
        _, out2 = await call(arena, "POST", f"/rooms/{out['code']}/start?token={out['token']}")
        assert "Worker" in out2["detail"]
    asyncio.run(go())


def test_selfcheck_matches_the_recorded_digest():
    """The same driver the Pyodide test runs in Node; its digest is checked against this one there."""
    out = asyncio.run(selfcheck.run(rounds=2))
    assert out["game"]["status"] == "finished" and len(out["game"]["digest"]) == 64
    assert out["signal"]["rounds"] == 8 and len(out["signal"]["answers"]) >= 1


def test_record_file_round_trip(clock, tmp_path):
    """verify_games reads a gzip record file (what R2 holds) from the command line."""
    async def go():
        arena = browser.Arena("", hooks=Hooks(), clock=clock)
        _, r = await call(arena, "POST", "/rooms", {"settings": {"humans": 1, "fill": "bots", "seed": 11, "rounds": 2}})
        await call(arena, "POST", f"/rooms/{r['code']}/start?token={r['token']}")
        await play(arena, clock, r["code"], r["token"])
        _, rec = await call(arena, "GET", f"/rooms/{r['code']}/record?token={r['token']}")
        return rec
    rec = asyncio.run(go())
    f = tmp_path / "rec.json.gz"
    f.write_bytes(gzip.compress(json.dumps(rec).encode()))
    out = tmp_path / "runs"
    assert verify_games.main(["--records", str(f), "--out", str(out), "--strict"]) == 0
    assert len(list(out.iterdir())) == 1


def test_warm_step_makes_the_rounds_early_but_never_on_a_running_clock(clock):
    async def go():
        arena = browser.Arena("", hooks=Hooks(), clock=clock)
        _, r = await call(arena, "POST", "/rooms", {"settings": {"humans": 1, "fill": "bots", "seed": 21, "rounds": 3}})
        steps = []
        while (s := arena.warm_step()) is not None:
            steps.append(s)
        assert steps == ["base", f"{r['code']}:R1", f"{r['code']}:R2", f"{r['code']}:R3"]
        arena2 = browser.Arena("", hooks=Hooks(), clock=clock)
        _, r2 = await call(arena2, "POST", "/rooms", {"settings": {"humans": 1, "fill": "bots", "seed": 22}})
        arena2.warmed_base = True
        await call(arena2, "POST", f"/rooms/{r2['code']}/start?token={r2['token']}")
        assert arena2.rooms[r2["code"]].humans()[0].pending is not None and arena2.warm_step() is None
    asyncio.run(go())


def test_signal_page_next_round_is_warmed():
    async def go():
        arena = browser.Arena("")
        arena.warmed_base = True
        st, v = await call(arena, "POST", "/signal/view", {"seed": 123, "round": 2, "agents": 3})
        assert st == 200 and v["round"] == 2
        assert arena.warm_step() == "signal:123:R3" and arena.warm_step() is None
    asyncio.run(go())
