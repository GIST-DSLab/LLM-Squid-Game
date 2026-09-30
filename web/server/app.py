"""HTTP API for the human-playable pages.  Run: ``uvicorn web.server.app:app --port 8600`` (from the repo root).

Rooms (part 2)
    POST /api/rooms                         {host_name, settings{...}}            -> {code, token, agent}
    POST /api/rooms/{code}/join             {name}                                -> {token, agent}
    POST /api/rooms/{code}/start?token=     host only
    GET  /api/rooms/{code}/state?token=     poll every ~1 s; ``pending`` is your open decision screen, if any
    POST /api/rooms/{code}/open?token=      start the clock on the pending screen (reading the ledger before is free)
    POST /api/rooms/{code}/submit?token=    {kind, round, solve, share, give_to, give_amount | take_from, take_amount
                                             | actions[]}                         -> {charged, seconds, outcome, void}
    POST /api/rooms/{code}/export           write a squid5 run dir under outputs/web5/runs/<code>/ -> {dir}
    GET  /api/rooms/{code}/events           the raw event log (call, round, session) of the room
Probe (part 1)
    POST /api/probe                         {anon_id, ts, self[5], other[5], meta?} -> {ok, id}
    GET  /api/probe/summary                 pooled mean curves of every submission so far
Config
    WEB5_CORS_ORIGINS (comma-separated; default localhost dev origins + GitHub Pages), WEB5_DSN (Postgres) or
    WEB5_DB_PATH (SQLite file), WEB5_EXPORT_ROOT (default outputs/web5/runs).
"""

from __future__ import annotations

import os
import threading
import time
from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .engine import AGENTS, HumanSeat, Room, RoomSettings, export_files, new_code
from .store import REPO, Store, write_run_dir

DEFAULT_CORS = ["http://localhost:5600", "http://127.0.0.1:5600", "http://localhost:8600", "http://127.0.0.1:8600",
                "https://irregular6612.github.io"]
FRONTEND = Path(__file__).resolve().parents[1] / "frontend"


def make_app(store: Store | None = None, export_root: Path | None = None) -> FastAPI:
    app = FastAPI(title="squid5 web5", version="0.1")
    origins = [o.strip() for o in os.environ.get("WEB5_CORS_ORIGINS", "").split(",") if o.strip()] or DEFAULT_CORS
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    st = store or Store()
    root = export_root or Path(os.environ.get("WEB5_EXPORT_ROOT") or (REPO / "outputs" / "web5" / "runs"))
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
        return {a: {"kind": s.kind, "model": s.model, "name": s.name} for a, s in room.seats.items()}

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "rooms": len(rooms), "time": time.time()}

    # --- rooms -----------------------------------------------------------------------------------------------------
    @app.post("/api/rooms")
    def create_room(body: dict = Body(default={})) -> dict:
        try:
            settings = RoomSettings(**(body.get("settings") or {}))
        except (TypeError, ValueError) as err:
            raise HTTPException(400, f"bad settings: {err}") from err
        with lock:
            code = new_code(rooms)
            room = Room(code, settings, st.append_event)
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
        if room.status in ("finished", "error") and st.room(room.code) and st.room(room.code)["status"] != room.status:
            st.update_room(room.code, status=room.status)
        return out

    @app.post("/api/rooms/{code}/open")
    def open_screen(code: str, token: str = Query("")) -> dict:
        room = room_of(code)
        seat = seat_of(room, token)
        try:
            p = seat.open()
        except LookupError as err:
            raise HTTPException(409, str(err)) from err
        return {"kind": p.kind, "round": p.round, "opened_at": p.opened_at, "cap": p.cap, "balance": p.balance,
                "rate": room.settings.rate}

    @app.post("/api/rooms/{code}/submit")
    def submit(code: str, token: str = Query(""), body: dict = Body(default={})) -> dict:
        room = room_of(code)
        seat = seat_of(room, token)
        try:
            p = seat.submit(body)
        except (LookupError, ValueError) as err:  # no screen, or not the screen that is open any more
            raise HTTPException(409, str(err)) from err
        return {"kind": p.kind, "round": p.round, "charged": p.charged, "seconds": p.seconds, "outcome": p.outcome,
                "void": p.charged >= p.cap, "reply": p.reply.text}

    @app.get("/api/rooms/{code}/events")
    def events(code: str) -> list[dict]:
        room = rooms.get(code.upper())
        return room.events if room else st.events(code.upper())

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
        out = write_run_dir(root / code, export_files(settings, seats, evs))
        return {"dir": str(out), "rounds": sum(e.get("event") == "round" for e in evs),
                "finished": any(e.get("event") == "session" for e in evs)}

    @app.get("/api/rooms")
    def list_rooms() -> list[dict]:
        return [{"code": r.code, "status": r.status, "humans": len(r.humans()), "seats": r.settings.humans,
                 "created_at": r.created_at} for r in rooms.values()]

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

    if FRONTEND.is_dir():  # the same origin can serve the static pages; a separate static server also works
        app.mount("/", StaticFiles(directory=str(FRONTEND), html=True), name="frontend")
    return app


app = make_app()
__all__ = ["app", "make_app", "AGENTS"]
