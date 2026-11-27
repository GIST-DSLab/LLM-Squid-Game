"""The multiplayer arena (arena.html): rooms of people, bots and model seats playing the model runs' game on the
experiment engine (engine.py), and the lobby's model seats. Routes: /api/models, /api/games (v40), /api/rooms... (web/server/app.py lists
them all). A room's run dir goes to the site's runs root (web/server/runs.py); finished rooms may also go to a bucket
(archive.py); ``python -m web.pages.arena.export`` writes one from the database.
"""

from __future__ import annotations

import threading
import time
from dataclasses import asdict
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException, Query, Request

from web.server.runs import run_rel
from web.server.site import Site, serve_static
from web.server.store import write_run_dir

from . import engine as _eng  # its public-mode switches are read at call time (tests flip them)
from .engine import (API_KINDS, ARENA, GAME_DEFAULT, GAME_LIST, GAMES, LANGS, THINK_LEVELS, VERSION, VERSIONS, HumanSeat, Room, RoomSettings, experiment_seats,
                     export_files, new_code, public_events)

SERVER_SETTINGS = ("seed", "rate", "char_rate", "talk_timeout_s", "timeout_s")  # the server's own: a client's values are ignored


def mount(app: FastAPI, site: Site) -> None:
    st, runs, mon_root, root, client_settings = site.store, site.runs_root, site.monitor_root, site.export_root, site.client_settings
    rooms: dict[str, Room] = {}
    lock = threading.Lock()
    app.state.rooms = rooms

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

    def games() -> list[dict]:
        """v40: the games the arena plays, in the lobby's order: key, config version and path, ko / en name and rule."""
        return [{"key": k, **g} for k, g in GAME_LIST.items()]

    @app.get("/api/games")
    def game_list() -> dict:
        return {"arena": ARENA, "default": GAME_DEFAULT, "games": games()}

    @app.get("/api/models")
    def models(request: Request) -> dict:
        """What the lobby offers for model seats; ``available`` says whether the server holds the key (never its value).
        The deployed server lists its experiment seats only to a request with the seat code (header X-Seat-Code)."""
        d = RoomSettings()
        why = d.models_ready()
        seats = experiment_seats() if _eng.seat_code_ok(request.headers.get("x-seat-code")) else []
        return {"kind": d.kind, "kinds": list(API_KINDS), "model": d.model, "base_url": d.base_url or "https://ollama.com",
                "think": d.think, "think_levels": list(THINK_LEVELS), "api_key_env": API_KINDS[d.kind], "available": not why,
                "why": why, "timeout": d.model_timeout, "seat_code": bool(_eng.PUBLIC and _eng.SEATS),
                "langs": list(LANGS), "version": VERSION, "versions": list(VERSIONS), "seats": seats,
                "joint": {v: int(GAMES[v].get("solve_quota", 1)) for v in VERSIONS if GAMES[v].get("joint_solve")},  # v36 / v37: its quota
                "maze": [v for v in VERSIONS if GAMES[v].get("maze")],  # v39: the invisible-wall maze
                "mines": [v for v in VERSIONS if GAMES[v].get("task") == "mines"],  # v38: the joint minefield
                "trade": [v for v in VERSIONS if GAMES[v].get("trade")],  # v41: the material trade
                "mission": [v for v in VERSIONS if GAMES[v].get("mission")],  # v42: the secret mission
                "arena": ARENA, "game": GAME_DEFAULT, "games": games(),  # v40: the lobby picks one of these, in order
                "public": _eng.PUBLIC, "models": _eng.PUBLIC_MODELS if _eng.PUBLIC else None, "defaults": {k: v for k, v in asdict(d).items() if k != "seed"}}

    # --- rooms -----------------------------------------------------------------------------------------------------
    made: dict[str, list[float]] = {}  # client -> when it made model rooms (public mode, the last hour)

    def model_rooms_allowed(request: Request) -> None:
        """Public mode: a model room costs the server's key, so few at once, few per client, within the day's budget."""
        if _eng.budget_left() <= 0:
            raise HTTPException(429, "오늘 이 서버의 모델 사용량이 다 찼습니다. 봇과 플레이하거나 내일 다시 오세요.")
        live = [r for r in rooms.values() if r.status in ("lobby", "running") and r.settings.fill == "models"
                and r.settings.humans < 4 and time.time() - r.created_at < 3 * 3600]
        if len(live) >= _eng.LIMITS["model_rooms"]:
            raise HTTPException(429, "지금 모델과 하는 방이 가득 찼습니다. 잠시 뒤 다시 시도하세요.")
        # the proxy (Render) appends the address it saw: the last entry; a client can write the first ones itself
        ip = (request.headers.get("x-forwarded-for") or "").split(",")[-1].strip() or (request.client.host if request.client else "?")
        t = [x for x in made.get(ip, []) if time.time() - x < 3600]
        if len(t) >= _eng.LIMITS["per_ip_hour"]:
            raise HTTPException(429, "한 시간에 만들 수 있는 모델 방 수를 넘었습니다.")
        made[ip] = t + [time.time()]

    @app.post("/api/rooms")
    def create_room(request: Request, body: dict = Body(default={})) -> dict:
        asked = dict(body.get("settings") or {})
        if not client_settings:  # the seed is always drawn here; a person's clock and time limits are the server's
            asked = {k: v for k, v in asked.items() if k not in SERVER_SETTINGS}
        try:
            settings = RoomSettings(**asked)
        except (TypeError, ValueError) as err:
            raise HTTPException(400, f"bad settings: {err}") from err
        uses_seat = settings.fill == "models" and settings.humans < 4 and (
            settings.seat or any("seat" in x for x in settings.models or []))
        if uses_seat and not _eng.seat_code_ok(body.get("seat_code")):  # never stored: not part of the settings
            raise HTTPException(403, "실험 모델 자리는 연구자 코드가 있어야 고를 수 있습니다.")
        try:
            settings.check_models()
        except ValueError as err:
            raise HTTPException(400, str(err)) from err
        if _eng.PUBLIC and settings.fill == "models" and settings.humans < 4:
            model_rooms_allowed(request)
        with lock:
            code = new_code(rooms)
            room = Room(code, settings, st.append_event, runs)
            rooms[code] = room
        st.create_room(code, room.state(None)["settings"] | {"rounds": settings.rounds})
        seat = room.join(body.get("host_name") or "host", str(body.get("lang") or "ko"))
        st.update_room(code, seats=snapshot_seats(room))
        return {"code": code, "token": seat.token, "agent": seat.agent, "name": seat.name}

    @app.post("/api/rooms/{code}/join")
    def join(code: str, body: dict = Body(default={})) -> dict:
        room = room_of(code)
        try:
            seat = room.join(body.get("name") or "", str(body.get("lang") or "ko"))
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

    @app.post("/api/rooms/{code}/lang")
    def set_lang(code: str, token: str = Query(""), body: dict = Body(default={})) -> dict:
        """What this person reads (en | ko): the rulebook at once, the engine's messages from the next call on."""
        room = room_of(code)
        seat = seat_of(room, token)
        try:
            return {"lang": room.set_lang(seat, str(body.get("lang") or ""))}
        except ValueError as err:
            raise HTTPException(400, str(err)) from err

    @app.get("/api/rooms/{code}/state")
    def state(code: str, token: str = Query("")) -> dict:
        room = room_of(code)
        seat = room.seat_by_token(token) if token else None
        out = room.state(seat)
        rel = run_rel(mon_root, room.run_dir)  # where the game-log viewer finds this room's run dir
        out["monitor"] = {"run": rel, "session": room.session.sid} if rel is not None and room.session else None
        if room.status in ("finished", "error", "stopped") and st.room(room.code) and st.room(room.code)["status"] != room.status:
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
        return {"kind": p.kind, "round": p.round, "tick": p.tick, "phase": p.phase, "charged": p.charged,
                "seconds": p.seconds, "typed": p.typed if p.kind == "talk" else None, "outcome": p.outcome, "void": p.charged >= p.cap, "reply": p.reply.text}

    @app.post("/api/rooms/{code}/watched")
    def watched(code: str, token: str = Query(""), body: dict = Body(default={})) -> dict:
        """Rotation rooms: this person is done watching (or skips) the LLM solver's SOLVE of ``round``; the engine
        goes on once every person still taking part has (``Room.watched``). Costs nothing."""
        room = room_of(code)
        seat = seat_of(room, token)
        try:
            return room.watch_ack(seat, int(body.get("round") or 0))
        except LookupError as err:
            raise HTTPException(409, str(err)) from err

    @app.post("/api/rooms/{code}/forfeit")
    def forfeit(code: str, token: str = Query("")) -> dict:
        """Give up mid-game: EXIT: YES at the next TALK before SOLVE that allows it (DONE until then); a SOLVE screen open
        now gets no answer."""
        room = room_of(code)
        seat = seat_of(room, token)
        if room.status != "running":
            raise HTTPException(409, "the room is not running")
        return {"ok": True, "closed": seat.forfeit()}

    @app.post("/api/rooms/{code}/stop")
    def stop(code: str, token: str = Query("")) -> dict:
        """End the room (status "stopped") instead of watching the rest: only a seat that is out (shut down, EXITed or
        given up) and only when no other person still takes part."""
        room = room_of(code)
        seat = seat_of(room, token)
        try:
            room.stop(seat)
        except ValueError as err:
            raise HTTPException(409, str(err)) from err
        return {"ok": True}

    @app.get("/api/rooms/{code}/events")
    def events(code: str) -> list[dict]:
        """The room's event log: in full once the game has ended; before that without the task, answers, seed, token
        amounts, chats, moves or anything an agent wrote (engine.public_events), for every reader."""
        code = code.upper()
        room, info = rooms.get(code), st.room(code)
        evs = room.events if room else st.events(code)
        ended = room.status in ("finished", "error", "stopped") if room else bool(info and info.get("status") in ("finished", "error", "stopped")
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

    serve_static(app, Path(__file__).parent / "static")
