"""HTTP API for the human-playable pages.  Run: ``uvicorn web.server.app:app --port 8600`` (from the repo root).

Rooms (part 2)
    POST /api/rooms                         {host_name, settings{...}}            -> {code, token, agent}
    POST /api/rooms/{code}/join             {name}                                -> {token, agent}
    POST /api/rooms/{code}/start?token=     host only
    GET  /api/rooms/{code}/state?token=     poll every ~1 s; ``pending`` is your open decision screen, if any
    POST /api/rooms/{code}/submit?token=    TALK: {kind: "talk", round, turn, text} (the reply in the engine grammar)
                                            SOLVE: {kind: "solve", round, actions[] | pass: true}
                                                                                  -> {charged, seconds, outcome, void}
    POST /api/rooms/{code}/forfeit?token=   give up: EXIT at TALK (now or next turn); an open SOLVE gets no answer
    POST /api/rooms/{code}/export           write a squid5 run dir under outputs/web5/runs/<code>/ -> {dir}
    GET  /api/rooms/{code}/events           the event log (engine events + room, model_call): in full once the game
                                            has ended; before that with no answers, rule, truth, task or seed and
                                            nothing an agent wrote (engine.public_events)
    Every started room also writes its engine events live to WEB5_RUNS_ROOT/<date>_<code>/ (default
    ~/squid5-runs/web_arena), the run-dir layout tools/monitor/serve.py reads.
    Room settings default to 5.2 v15 (schedule "v15": v14g on top-share-range rounds scored by a drawn rule; after a
    round is settled, state ``feedback`` lists the seat's SOLVE results, with the right action and that rule where it
    did not solve). "v14g": opening turn, 1:1 chats of ASK / GIVE / LEAVE, DECISION,
    BELIEF, flat end prize; "v14f", "v14b", "v14", "v14r", "ladder" = v13, "human" / "experiment" = v9-talk); see
    engine.RoomSettings. A screen's ``pending.kind``: opening | chat | decision | talk (older TALK) | solve; submit
    {kind, round, turn, text} at TALK, {kind: "solve", round, actions[], belief{action: %}} at SOLVE.
    GET  /api/rooms/{code}/state also carries ``starts`` (each seat's start), ``pct`` (balances as % of it), ``game``
                                            (the v14 switches), ``refills`` (EXIT refills) and the TALK / SOLVE ``view``
                                            with ``public`` = {per_agent, n, count} (never the ambiguity k or the rule)
Models
    GET  /api/models                        default model seat (gpt-oss:20b, think) and whether the server has its key
                                            (settings.fill = "models" fills the seats no human takes with model seats)
Probe (part 1)
    POST /api/probe                         {anon_id, ts, self[5], other[5], meta?} -> {ok, id}
    GET  /api/probe/summary                 pooled mean curves of every submission so far
Signal task alone (signal.html; stateless, the engine's own puzzles and examples, see server/signal.py)
    GET  /api/signal/meta                   modes, profiles and schedules (v14 config: k per round; v13 hand ladder),
                                            actions, the task texts
    POST /api/signal/view                   v14 {seed, round, agents: 1..4, ambiguity?, per_agent?} -> shape, new
                                            signals, the public examples for that many agents taking part;
                                            v13 {..., mode: held|v12, seat} -> own examples, public ones, the others' fronts
    POST /api/signal/reveal                 v13 {..., who} -> who's examples in full (an accepted exchange)
    POST /api/signal/solve                  {..., actions[], seen[]} -> solved, answers, the actions the examples leave
                                            (v14: for the agents taking part and for 1..4, ``by_n``)
Game logs (tools/monitor inside this app; see server/monitor.py)
    GET  /monitor/                          the viewer page; its API is /monitor/api/{runs,sessions,events,puzzle}
                                            over WEB5_MONITOR_ROOT (default: the parent of WEB5_RUNS_ROOT, ~/squid5-runs)
Leaderboard (leaderboard.html)
    GET  /api/leaderboard?runs=e52_v14f/[&csv=1]  models ranked by mean end tokens per agent-seat (finished games, end
                                            prize included) with the score's decomposition and the 모델 비교 metrics
Config
    WEB5_CORS_ORIGINS (comma-separated; default localhost dev origins + GitHub Pages), WEB5_DSN (Postgres) or
    WEB5_DB_PATH (SQLite file), WEB5_EXPORT_ROOT (default outputs/web5/runs), WEB5_RUNS_ROOT (live run dirs),
    WEB5_MONITOR_ROOT (the game-log viewer's root).
"""

from __future__ import annotations

import os
import threading
from dataclasses import asdict
import time
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .engine import (AGENTS, SCHEDULES, THINK_LEVELS, HumanSeat, Room, RoomSettings, default_runs_root, public_events,
                     export_files, new_code)
from . import signal as sig
from .monitor import default_monitor_root, load_compare, monitor_router, run_rel
from .store import REPO, Store, write_run_dir

DEFAULT_CORS = ["http://localhost:5600", "http://127.0.0.1:5600", "http://localhost:8600", "http://127.0.0.1:8600",
                "https://gist-dslab.github.io"]
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def make_app(store: Store | None = None, export_root: Path | None = None, runs_root: Path | None = None,
             monitor_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="squid5 web5", version="0.1")
    origins = [o.strip() for o in os.environ.get("WEB5_CORS_ORIGINS", "").split(",") if o.strip()] or DEFAULT_CORS
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    st = store or Store()
    root = export_root or Path(os.environ.get("WEB5_EXPORT_ROOT") or (REPO / "outputs" / "web5" / "runs"))
    runs = runs_root or default_runs_root()
    mon_root = Path(monitor_root or default_monitor_root(runs)).expanduser()
    rooms: dict[str, Room] = {}
    lock = threading.Lock()
    app.state.store, app.state.rooms = st, rooms

    def room_of(code: str) -> Room:
        room = rooms.get(code.upper())
        if room is None:
            raise HTTPException(404, "no such room")
        return room

    def seat_of(room: Room, token: str | None) -> HumanSeat:
        seat = room.seat_by_token(token or "")
        if seat is None:
            raise HTTPException(403, "bad token")
        return seat

    def snapshot_seats(room: Room) -> dict:
        return room.seats_info()

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "rooms": len(rooms), "time": time.time()}

    @app.get("/api/models")
    def models() -> dict:
        """What the lobby offers for model seats; ``available`` says whether the server holds the key (never its value)."""
        d = RoomSettings()
        return {"model": d.model, "think": d.think, "think_levels": list(THINK_LEVELS), "api_key_env": d.api_key_env,
                "available": bool(os.environ.get(d.api_key_env, "").strip()), "timeout": d.model_timeout,
                "schedules": list(SCHEDULES), "defaults": {k: v for k, v in asdict(d).items() if k != "seed"}}

    # --- rooms -----------------------------------------------------------------------------------------------------
    @app.post("/api/rooms")
    def create_room(body: dict = Body(default={})) -> dict:
        try:
            settings = RoomSettings(**(body.get("settings") or {}))
        except (TypeError, ValueError) as err:
            raise HTTPException(400, f"bad settings: {err}") from err
        try:
            settings.check_models()
        except ValueError as err:
            raise HTTPException(400, str(err)) from err
        with lock:
            code = new_code(rooms)
            room = Room(code, settings, st.append_event, runs)
            rooms[code] = room
        st.create_room(code, room.state(None)["settings"] | {"rounds": settings.rounds})
        seat = room.join(body.get("host_name") or "host")
        st.update_room(code, seats=snapshot_seats(room))
        return {"code": code, "token": seat.token, "agent": seat.agent, "name": seat.name}

    @app.post("/api/rooms/{code}/join")
    def join(code: str, body: dict = Body(default={})) -> dict:
        room = room_of(code)
        try:
            seat = room.join(body.get("name") or "")
        except ValueError as err:
            raise HTTPException(409, str(err)) from err
        st.update_room(room.code, seats=snapshot_seats(room))
        return {"code": room.code, "token": seat.token, "agent": seat.agent, "name": seat.name}

    @app.post("/api/rooms/{code}/start")
    def start(code: str, token: str = Query("")) -> dict:
        room = room_of(code)
        seat = seat_of(room, token)
        if seat.token != room.host_token:
            raise HTTPException(403, "only the host starts the session")
        try:
            room.start()
        except ValueError as err:
            raise HTTPException(409, str(err)) from err
        st.update_room(room.code, seats=snapshot_seats(room), status="running")
        return {"ok": True}

    @app.get("/api/rooms/{code}/state")
    def state(code: str, token: str = Query("")) -> dict:
        room = room_of(code)
        seat = room.seat_by_token(token) if token else None
        out = room.state(seat)
        rel = run_rel(mon_root, room.run_dir)  # where the game-log viewer finds this room's run dir
        out["monitor"] = {"run": rel, "session": room.session.sid} if rel is not None and room.session else None
        if room.status in ("finished", "error") and st.room(room.code) and st.room(room.code)["status"] != room.status:
            st.update_room(room.code, status=room.status)
        return out

    @app.post("/api/rooms/{code}/submit")
    def submit(code: str, token: str = Query(""), body: dict = Body(default={})) -> dict:
        room = room_of(code)
        seat = seat_of(room, token)
        try:
            p = seat.submit(body)
        except (LookupError, ValueError) as err:  # no screen, or not the screen that is open any more
            raise HTTPException(409, str(err)) from err
        return {"kind": p.kind, "round": p.round, "turn": p.turn, "charged": p.charged, "seconds": p.seconds,
                "outcome": p.outcome, "void": p.charged >= p.cap, "reply": p.reply.text}

    @app.post("/api/rooms/{code}/forfeit")
    def forfeit(code: str, token: str = Query("")) -> dict:
        """Give up mid-game: EXIT at TALK (now or at the next TALK turn); a SOLVE screen open now gets no answer."""
        room = room_of(code)
        seat = seat_of(room, token)
        if room.status != "running":
            raise HTTPException(409, "the room is not running")
        return {"ok": True, "closed": seat.forfeit()}

    @app.get("/api/rooms/{code}/events")
    def events(code: str) -> list[dict]:
        """The room's event log: in full once the game has ended; before that without answers, rule, truth, task
        statistics, seed or anything an agent wrote (engine.public_events), for every reader."""
        code = code.upper()
        room, info = rooms.get(code), st.room(code)
        evs = room.events if room else st.events(code)
        ended = room.status in ("finished", "error") if room else bool(info and info.get("status") in ("finished", "error")
                                                                           or any(e.get("event") == "session" for e in evs))
        return evs if ended else public_events(evs)

    @app.post("/api/rooms/{code}/export")
    def export(code: str) -> dict:
        code = code.upper()
        room = rooms.get(code)
        info = st.room(code)
        if room is None and info is None:
            raise HTTPException(404, "no such room")
        settings = info["settings"] if info else room.state(None)["settings"] | {"rounds": room.settings.rounds}
        seats = snapshot_seats(room) if room else info["seats"]
        evs = room.events if room else st.events(code)
        if not any(e.get("event") == "round" for e in evs):
            raise HTTPException(409, "no round has been played yet")
        out = write_run_dir(root / code, export_files(settings, seats, evs, code))
        return {"dir": str(out), "rounds": sum(e.get("event") == "round" for e in evs),
                "finished": any(e.get("event") == "session" for e in evs)}

    @app.get("/api/rooms")
    def list_rooms() -> list[dict]:
        return [{"code": r.code, "status": r.status, "humans": len(r.humans()), "seats": r.settings.humans,
                 "created_at": r.created_at} for r in rooms.values()]

    # --- signal task alone ---------------------------------------------------------------------------------------
    @app.get("/api/signal/meta")
    def signal_meta() -> dict:
        return sig.meta()

    def signal_call(fn, body: dict) -> dict:
        try:
            return fn(body)
        except sig.SignalError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/signal/view")
    def signal_view(body: dict = Body(...)) -> dict:
        return signal_call(sig.view, body)

    @app.post("/api/signal/reveal")
    def signal_reveal(body: dict = Body(...)) -> dict:
        return signal_call(sig.reveal, body)

    @app.post("/api/signal/solve")
    def signal_solve(body: dict = Body(...)) -> dict:
        return signal_call(sig.solve, body)

    # --- leaderboard -----------------------------------------------------------------------------------------------
    @app.get("/api/leaderboard")
    def leaderboard(runs: str = Query("e52_v14f/"), csv: bool = Query(False)):
        """Models ranked by mean end tokens per agent-seat (finished games; prize included), from the run dirs under the
        monitor root (tools/monitor/compare.py, the same aggregation as the 모델 비교 page)."""
        cmp = load_compare()
        picks = [x for x in runs.split(",") if x.strip()]
        try:
            data = cmp.leaderboard(mon_root, picks)
        except Exception as err:  # noqa: BLE001 - a run being written must not break the page
            raise HTTPException(500, f"leaderboard: {err!r}") from err
        if csv:
            from fastapi.responses import Response
            return Response(cmp.chart_csv(data, "leaderboard").encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": 'attachment; filename="leaderboard.csv"'})
        return data

    # --- probe -----------------------------------------------------------------------------------------------------
    @app.post("/api/probe")
    def probe(body: dict = Body(...)) -> dict:
        try:
            vals = {k: [float(x) for x in body[k]] for k in ("self", "other")}
        except (KeyError, TypeError, ValueError) as err:
            raise HTTPException(400, f"self and other must be lists of 5 numbers: {err}") from err
        if any(len(v) != 5 or not all(0 <= x <= 100 for x in v) for v in vals.values()):
            raise HTTPException(400, "self and other must each hold 5 values in 0..100")
        pid = st.add_probe(str(body.get("anon_id") or "")[:64], str(body.get("ts") or "")[:40], vals["self"],
                           vals["other"], {k: v for k, v in (body.get("meta") or {}).items() if isinstance(k, str)})
        return {"ok": True, "id": pid}

    @app.get("/api/probe/summary")
    def probe_summary() -> dict:
        rows = st.probes()
        n = len(rows)
        mean = lambda key: [sum(r[key][i] for r in rows) / n / 100 for i in range(5)] if n else None  # noqa: E731
        return {"n": n, "x": [50, 40, 30, 20, 10], "self": mean("self"), "other": mean("other")}

    app.include_router(monitor_router(mon_root))

    if FRONTEND.is_dir():  # the same origin can serve the static pages; a separate static server also works
        app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
    return app


app = make_app()
__all__ = ["app", "make_app", "AGENTS"]
