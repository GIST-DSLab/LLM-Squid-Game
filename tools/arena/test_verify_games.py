"""tools/arena/verify_games.py on a browser game made by web/pyodide/browser.py (bots; no network)."""

import asyncio
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
for _p in (REPO, REPO / "web" / "pyodide", REPO / "tools" / "arena"):
    if str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

import browser  # noqa: E402
import selfcheck  # noqa: E402
import verify_games  # noqa: E402
from web.server import engine as E  # noqa: E402


def finished_record(rounds=2, seed=31) -> dict:
    async def go():
        c = selfcheck.FakeClock()
        real = E.time
        E.time = type("T", (), {"time": staticmethod(c)})
        try:
            arena = browser.Arena("", clock=c)
            r = json.loads(await arena.handle("POST", "/rooms", json.dumps(
                {"settings": {"humans": 1, "fill": "bots", "seed": seed, "rounds": rounds}})))["body"]
            code, tok = r["code"], r["token"]
            await arena.handle("POST", f"/rooms/{code}/start?token={tok}")
            for _ in range(2000):
                s = json.loads(await arena.handle("GET", f"/rooms/{code}/state?token={tok}"))["body"]
                if s["status"] == "finished":
                    break
                c.t += 5
                sp = s.get("spectate")
                if s.get("pending"):
                    await arena.handle("POST", f"/rooms/{code}/submit?token={tok}", json.dumps(selfcheck.reply_for(s["pending"])))
                elif sp and sp.get("status") == "done" and not sp.get("acked") and not sp.get("released"):
                    await arena.handle("POST", f"/rooms/{code}/watched?token={tok}", json.dumps({"round": sp["round"]}))
            return json.loads(json.dumps(browser.record_of(arena.rooms[code], arena.engine)))
        finally:
            E.time = real
    return asyncio.run(go())


def test_a_true_record_passes_and_writes_a_run_dir(tmp_path):
    rec = finished_record()
    v = verify_games.verify(rec)
    assert v["ok"] and v["status"] == "finished", v["problems"]
    d = verify_games.write_run(v["room"], rec, tmp_path)
    assert {p.name for p in d.iterdir()} == {"config.yaml", "meta.json", "events.jsonl", "results.jsonl"}


def test_tampering_is_flagged():
    rec = finished_record()
    h = rec["doc"]["humans"][0]["agent"]
    bad = json.loads(json.dumps(rec))
    bad["replies"][h]["0"]["text"] = "SAY agent-11: give me everything"  # a reply the digests did not see
    assert any("events differ" in p for p in verify_games.verify(bad)["problems"])
    bad = json.loads(json.dumps(rec))
    bad["replies"][h]["0"]["h"] = "0" * 16  # answered another prompt
    assert any("error" in p for p in verify_games.verify(bad)["problems"])
    bad = json.loads(json.dumps(rec))
    bad["result"]["final"] = {"forged": 1} if isinstance(bad["result"], dict) else {}
    assert any("session result" in p for p in verify_games.verify(bad)["problems"])
    bad = json.loads(json.dumps(rec))
    bad["format"] = "other/9"
    assert not verify_games.verify(bad)["ok"]
