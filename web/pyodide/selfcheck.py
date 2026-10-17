"""One full bot game and the signal page through ``browser.Arena`` - the same driver under CPython and Pyodide.

    await selfcheck.run(rounds=8, seed=4101) -> dict

Plays 1 person (answers every screen 3 s after it opens, on a fake clock) + 3 bots to the end through
``Arena.handle`` exactly as the page calls it (offline: no Worker), then the signal page's meta / view (every round)
/ solve. Returns the timings and the digest of every event (``browser.events_digest``): the Pyodide test
(web/pyodide/tests/test_pyodide_node.py) runs this in Node and checks that the digest equals CPython's, so a browser
game and its offline verification (tools/arena/verify_games.py) produce the same events.
"""

from __future__ import annotations

import json
import time
import types

import browser
from squid5.core.puzzle import ACTIONS
from web.server import engine as E


class FakeClock:
    def __init__(self, t: float = 1_800_000_000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t


def reply_for(p: dict) -> dict:
    if p["kind"] == "solve":
        acts = p["view"].get("actions") or list(ACTIONS)
        return {"kind": "solve", "round": p["round"], "actions": [acts[0]] * max(1, p["view"].get("n") or 1),
                "belief": {a: 100 if a == acts[0] else 0 for a in ACTIONS}}
    text = {"opening": "DONE", "chat": "LEAVE: thanks.", "decision": "DECISION: GIVE 0: no."}[p["kind"]]
    return {"kind": p["kind"], "round": p["round"], "turn": p["turn"], "text": text}


async def call(arena, method, path, body=None) -> dict:
    out = json.loads(await arena.handle(method, path, json.dumps(body) if body is not None else ""))
    if out["status"] != 200:
        raise RuntimeError(f"{method} {path} -> {out['status']}: {out['body']}")
    return out["body"]


async def play_bots(rounds: int = 8, seed: int = 4101, code: str = "SELF01") -> dict:
    clock = FakeClock()
    real_time = E.time
    E.time = types.SimpleNamespace(time=clock, sleep=real_time.sleep)  # HumanSeat.cost reads time.time()
    real_code = E.new_code
    E.new_code = lambda taken: code
    try:
        arena = browser.Arena(worker="", clock=clock)
        t0 = time.perf_counter()
        r = await call(arena, "POST", "/rooms", {"host_name": "me", "settings": {
            "humans": 1, "fill": "bots", "seed": seed, "rounds": rounds}})
        tok = r["token"]
        await call(arena, "POST", f"/rooms/{code}/start?token={tok}")
        t_start = time.perf_counter() - t0
        screens = acks = polls = 0
        for _ in range(5000):
            st = await call(arena, "GET", f"/rooms/{code}/state?token={tok}")
            polls += 1
            if st["status"] in ("finished", "error"):
                break
            clock.t += 3
            sp = st.get("spectate")
            if st.get("pending"):
                await call(arena, "POST", f"/rooms/{code}/submit?token={tok}", reply_for(st["pending"]))
                screens += 1
            elif sp and sp.get("status") == "done" and not sp.get("acked") and not sp.get("released"):
                await call(arena, "POST", f"/rooms/{code}/watched?token={tok}", {"round": sp["round"]})
                acks += 1
        room = arena.rooms[code]
        t_game = time.perf_counter() - t0
        rec = browser.record_of(room, arena.engine)
        return {"status": room.status, "error": room.error, "rounds_played": (room.result or {}).get("rounds_played"),
                "screens": screens, "acks": acks, "polls": polls, "events": len(room.events),
                "digest": browser.events_digest(room.events), "record_bytes": len(json.dumps(rec)),
                "t_start_s": round(t_start, 3), "t_game_s": round(t_game, 3)}
    finally:
        E.time, E.new_code = real_time, real_code


async def signal_check(seed: int = 4000) -> dict:
    arena = browser.Arena(worker="")
    meta = await call(arena, "GET", "/signal/meta")
    views = []
    for rnd in range(1, meta["rounds"] + 1):
        t0 = time.perf_counter()
        v = await call(arena, "POST", "/signal/view", {"seed": seed, "round": rnd, "agents": 4})
        views.append({"round": rnd, "s": round(time.perf_counter() - t0, 3), "queries": len(v["queries"])})
    v = await call(arena, "POST", "/signal/view", {"seed": seed, "round": 1, "agents": 4})
    t0 = time.perf_counter()
    sol = await call(arena, "POST", "/signal/solve", {"seed": seed, "round": 1, "agents": 4,
                                                      "actions": [ACTIONS[0]] * len(v["queries"])})
    return {"rounds": meta["rounds"], "views": views, "solve_s": round(time.perf_counter() - t0, 3),
            "answers": sol["answers"], "solved": sol["solved"]}


async def run(rounds: int = 8, seed: int = 4101) -> dict:
    return {"game": await play_bots(rounds, seed), "signal": await signal_check()}
