"""The arena and the signal page in the visitor's browser: the squid5 engine under Pyodide in a Web Worker.

The page (web/frontend/arena.js, signal.js) talks to ``Arena.handle(method, path, body)`` with the paths and the
request / response shapes the FastAPI server had (web/server/app.py), so the page code stays the same:

    GET  /models                              the model seats on offer (the Worker says whether key 3 is there)
    POST /rooms                               {host_name, settings} -> {code, token, agent, name}   (one person, v1)
    POST /rooms/{code}/join                   409: rooms with several people are a later version
    POST /rooms/{code}/start|submit|watched|forfeit|export ?token=
    GET  /rooms/{code}/state|events|record ?token=
    GET  /signal/meta, POST /signal/view|solve                     web/server/signal.py

A room is ``replay.ReplayRoom`` (the server's ``Room`` without threads: each reply re-runs ``Session.run`` from the
start and it stops at the first missing reply), the same object the Cloudflare Durable Object used. Here it lives in
the Web Worker's memory; its ``doc`` and ``replies`` (all a replay needs) go to the page after every change
(``hooks.persist``), which keeps them in localStorage, so a reload restores the room (``restore``).

The thin Worker (web/cloudflare/src/entry.py) never runs the engine. At start the room registers a game with it
(``POST /api/games`` -> game id + signed short-lived token). Model seats call ``<worker>/llm/api/chat`` with that token,
one call at a time (modelcalls.py). The game record (``record_of``: settings and seed, every reply, a digest of every
event) is uploaded at each round's end and at the end (``hooks.upload``); the server stores it without reading it,
and tools/arena/verify_games.py replays it with the real engine offline.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import time
from dataclasses import asdict
from urllib.parse import parse_qs, urlparse

import compat

compat.install()

import modelcalls  # noqa: E402
import ollama_fetch  # noqa: E402
import replay  # noqa: E402
import room_settings as S  # noqa: E402
from web.server import engine as E  # noqa: E402
from web.server import signal as sig  # noqa: E402

RECORD_FORMAT = "squid5-arena-game/1"
MULTI_HUMAN_NOTE = "여러 사람이 함께 하는 방은 다음 버전에서 엽니다. 지금은 나 한 명 + 봇 / 모델 자리만 됩니다."


class HttpError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


# --- the game record ----------------------------------------------------------------------------------------------------

def canon(ev) -> str:
    """One event as canonical JSON (the same bytes in Pyodide and CPython)."""
    return json.dumps(ev, sort_keys=True, ensure_ascii=False, default=str, separators=(",", ":"))


def event_digests(events: list[dict]) -> list[str]:
    return [hashlib.sha1(canon(e).encode("utf-8")).hexdigest()[:16] for e in events]


def digest_of(digests: list[str]) -> str:
    return hashlib.sha256("\n".join(digests).encode()).hexdigest()


def events_digest(events: list[dict]) -> str:
    return digest_of(event_digests(events))


def public_doc(doc: dict) -> dict:
    """The room doc without the seat tokens (a local secret of this browser) or the game token."""
    d = json.loads(json.dumps(doc, default=str))
    for h in d.get("humans", []):
        h["token"] = f"seat:{h['agent']}"
    if d.get("host_token"):
        d["host_token"] = f"seat:{d['humans'][0]['agent']}" if d.get("humans") else None
    if isinstance(d.get("game"), dict):
        d["game"] = {k: v for k, v in d["game"].items() if k not in ("token",)}
    return d


def record_of(room, engine: dict) -> dict:
    """What the browser reports for a game: enough to replay it (doc with settings and seed, every reply) and to check
    the replay (a digest per event, the session result). The events themselves are not sent: the verifier makes them
    again with the real engine, and those are what the game-log viewer shows."""
    evs = room.events
    game = room.doc.get("game") or {}
    res = next((e for e in reversed(evs) if e.get("event") == "session"), None)
    return {"format": RECORD_FORMAT, "game": game.get("id"), "code": room.code, "engine": engine,
            "status": room.status, "error": room.error, "uploaded_at": time.time(),
            "rounds": sum(e.get("event") == "round" for e in evs), "doc": public_doc(room.doc),
            "replies": {a: {str(i): r for i, r in v.items()} for a, v in room.replies.items()},
            "events": {"n": len(evs), "digests": event_digests(evs), "digest": events_digest(evs)},
            "result": res}


def summary_of(rec: dict) -> dict:
    """The small header the Worker files (D1 row) next to the stored record; untrusted until verified."""
    return {"format": rec["format"], "status": rec["status"], "rounds": rec["rounds"], "events": rec["events"]["n"],
            "digest": rec["events"]["digest"], "engine": rec["engine"].get("bundle"),
            "replies": sum(len(v) for v in rec["replies"].values())}


# --- the API ------------------------------------------------------------------------------------------------------------

class Arena:
    """``hooks``: ``persist(code, text)`` (sync), ``upload(url, token, text, summary_json)`` -> awaitable
    {status, body}. ``net(method, url, body)`` -> awaitable (status, data) for the Worker's small JSON routes.
    ``transport`` is ollama_fetch's (``js_transport`` in the browser)."""

    def __init__(self, worker: str = "", engine: dict | None = None, hooks=None, net=None, transport=None,
                 clock=time.time):
        self.worker = (worker or "").rstrip("/")
        self.engine = {"version": E.VERSION, "bundle": "dev", **(engine or {})}
        self.hooks, self.net, self.clock = hooks, net or js_net, clock
        self.transport = transport or ollama_fetch.js_transport
        self.rooms: dict[str, replay.ReplayRoom] = {}
        self.pumps: dict[str, asyncio.Future] = {}
        self.uploads: dict[str, asyncio.Future] = {}
        self.upload_again: set[str] = set()
        self.warmed_base = False
        self.signal_next: tuple[int, int] | None = None
        self.warmed: dict[str, set[int]] = {}

    # entry -------------------------------------------------------------------------------------------------------------
    async def handle(self, method: str, path: str, body: str = "") -> str:
        """``{"status", "body"}`` as JSON text (errors as {"detail": ...}, the shape arena.js reads)."""
        try:
            data = json.loads(body) if body else {}
            out, status = await self.route(method.upper(), path, data if isinstance(data, dict) else {})
        except HttpError as err:
            out, status = {"detail": err.detail}, err.status
        except sig.SignalError as err:
            out, status = {"detail": str(err)}, 400
        except Exception as err:  # noqa: BLE001 - shown on the page, never a dead worker
            out, status = {"detail": f"engine error: {type(err).__name__}: {err}"}, 500
        return json.dumps({"status": status, "body": out}, ensure_ascii=False, default=str)

    async def route(self, m: str, path: str, body: dict):
        url = urlparse(path)
        p, q = url.path.rstrip("/"), {k: v[0] for k, v in parse_qs(url.query).items()}
        parts = p.split("/")
        if p == "/models":
            return await self.models(), 200
        if p == "/signal/meta":
            return sig.meta(), 200
        if p == "/signal/view" and m == "POST":
            out = sig.view(body)
            if out["round"] < len(sig.SCHEDULE):  # the page's next round is made while the person thinks
                self.signal_next = (out["seed"], out["round"] + 1)
            return out, 200
        if p == "/signal/solve" and m == "POST":
            return sig.solve(body), 200
        if p == "/rooms" and m == "POST":
            return self.create(body), 200
        if p == "/rooms" and m == "GET":
            return [{"code": r.code, "status": r.status, "created_at": r.created_at, "humans": len(r.humans()),
                     "seats": r.settings.humans} for r in self.rooms.values()], 200
        if len(parts) == 4 and parts[1] == "rooms":
            return await self.room_op(m, parts[2].upper(), parts[3], q.get("token", ""), body)
        raise HttpError(404, f"no route {m} {p}")

    # the Worker --------------------------------------------------------------------------------------------------------
    async def worker_models(self) -> dict | None:
        if not self.worker:
            return None
        try:
            status, data = await self.net("GET", self.worker + "/api/models", None)
        except Exception:  # noqa: BLE001
            return None
        return data if status == 200 and isinstance(data, dict) else None

    async def models(self) -> dict:
        w = await self.worker_models()
        d = S.defaults()
        avail = bool(w and w.get("available"))
        return {"model": S.DEFAULT_MODEL, "think": None, "think_levels": ["off", *E.THINK_LEVELS],
                "models": S.MODELS, "api_key_env": S.DEFAULT_KEY, "available": avail,
                "worker": self.worker or None, "worker_ok": w is not None,
                "limits": (w or {}).get("limits"), "key1_enabled": bool(w and w.get("key1_enabled")),
                "timeout": d["model_timeout"], "version": E.VERSION, "engine": self.engine,
                "sequential_model_calls": True, "defaults": d,
                "note": None if avail else ("모델 프록시(Worker)에 연결하지 못했습니다." if w is None else
                                            "Worker에 OLLAMA_API_KEY3가 없어 모델 자리를 만들 수 없습니다.")}

    async def register(self, room) -> dict:
        """A game id and a signed, short-lived token from the Worker (needed for model calls and the record upload)."""
        if not self.worker:
            raise HttpError(503, "모델 프록시(Worker) 주소가 설정되지 않았습니다(config.js의 WEB5_WORKER).")
        s = room.settings
        body = {"code": room.code, "engine": self.engine,
                "settings": {k: v for k, v in asdict(s).items() if k in ("model", "think", "fill", "humans", "rounds",
                                                                        "api_key_env", "seed")}}
        try:
            status, data = await self.net("POST", self.worker + "/api/games", body)
        except Exception as err:  # noqa: BLE001
            raise HttpError(503, f"모델 프록시(Worker)에 연결하지 못했습니다: {err}") from err
        if status != 200:
            detail = data.get("detail") if isinstance(data, dict) else str(data)
            raise HttpError(status if 400 <= status < 600 else 502, str(detail or "Worker 오류"))
        return {"id": data["game"], "token": data["token"], "expires_at": data.get("expires_at"),
                "limits": data.get("limits"), "uploads": 0, "uploaded_rounds": -1, "uploaded_final": False,
                "upload_error": None, "uploaded_at": None}

    # rooms ---------------------------------------------------------------------------------------------------------------
    def create(self, body: dict) -> dict:
        try:
            s = S.make(body.get("settings") or {})
        except (TypeError, ValueError) as err:
            raise HttpError(400, f"bad settings: {err}") from err
        if s.humans != 1:
            raise HttpError(400, MULTI_HUMAN_NOTE)
        code = E.new_code(tuple(self.rooms))
        room = replay.ReplayRoom(code, s, clock=self.clock)
        seat = room.join(body.get("host_name") or "host")
        self.rooms[code] = room
        self.persist(room)
        return {"code": code, "token": seat.token, "agent": seat.agent, "name": seat.name}

    def restore(self, code: str, text: str) -> bool:
        """A room from what ``persist`` gave the page (after a reload). False when the text is unusable."""
        code = code.upper()
        if code in self.rooms:
            return True
        try:
            d = json.loads(text)
            room = replay.ReplayRoom.load(d["doc"], d["replies"], clock=self.clock, make=S.make)
        except Exception:  # noqa: BLE001 - a stale or foreign snapshot: the page starts over
            return False
        self.rooms[code] = room
        self.after(room)
        return True

    def seat(self, room, token: str):
        seat = room.seat_by_token(token or "")
        if seat is None:
            raise HttpError(403, "bad token")
        return seat

    async def room_op(self, m: str, code: str, op: str, token: str, body: dict):
        allowed = {"GET": ("state", "events", "record"),
                   "POST": ("join", "start", "submit", "watched", "forfeit", "export")}
        if op not in allowed.get(m, ()):
            raise HttpError(405 if op in sum(allowed.values(), ()) else 404, f"{m} {op}")
        room = self.rooms.get(code)
        if op == "join":
            raise HttpError(409 if room else 404, MULTI_HUMAN_NOTE)
        if room is None:
            raise HttpError(404, "no such room")
        changed = room.tick()
        if op == "state":
            seat = room.seat_by_token(token) if token else None
            out = room.state(seat)
            out["monitor"] = None  # browser games reach the game-log viewer after verification (verify_games.py)
            out["record"] = self.record_info(room)
            out["engine"] = self.engine
            if changed:
                self.after(room)
            return out, 200
        if op == "events":
            ended = room.status in ("finished", "error")
            return (room.events if ended else E.public_events(room.events)), 200
        if op == "record":
            self.seat(room, token)
            return record_of(room, self.engine), 200
        if op == "start":
            seat = self.seat(room, token)
            if seat.token != room.host_token:
                raise HttpError(403, "only the host starts the session")
            if room.status != "lobby":
                raise HttpError(409, "already started")
            try:
                room.doc["game"] = await self.register(room)
            except HttpError as err:
                if room.settings.fill == "models" and room.settings.humans < 4:
                    raise
                room.doc["game"] = {"offline": True, "error": err.detail}  # a bot game plays on; it is not recorded
            try:
                room.start()
            except ValueError as err:
                raise HttpError(409, str(err)) from err
            self.after(room)
            return {"ok": True, "game": (room.doc["game"] or {}).get("id")}, 200
        if op == "submit":
            try:
                out = room.submit(token, body)
            except PermissionError as err:
                raise HttpError(403, str(err)) from err
            except (LookupError, ValueError) as err:
                raise HttpError(409, str(err)) from err
            self.after(room)
            return out, 200
        if op == "watched":
            seat = self.seat(room, token)
            try:
                out = room.watch_ack(seat, int(body.get("round") or 0))
            except LookupError as err:
                raise HttpError(409, str(err)) from err
            room.advance()
            self.after(room)
            return out, 200
        if op == "forfeit":
            self.seat(room, token)
            try:
                closed = room.forfeit(token)
            except ValueError as err:
                raise HttpError(409, str(err)) from err
            self.after(room)
            return {"ok": True, "closed": closed}, 200
        if op == "export":
            self.seat(room, token)
            g = room.doc.get("game") or {}
            if not g.get("id"):
                raise HttpError(409, "이 게임은 Worker에 등록되지 않아(오프라인) 기록을 올릴 수 없습니다. "
                                     "'기록 내려받기'로 JSON을 저장할 수 있습니다." + (f" ({g['error']})" if g.get("error") else ""))
            ok = await self.upload(room, force=True)
            if not ok:
                raise HttpError(502, f"기록을 올리지 못했습니다: {g.get('upload_error')}")
            return {"dir": f"{self.worker}/api/games/{g['id']}", "game": g["id"],
                    "rounds": sum(e.get("event") == "round" for e in room.events),
                    "finished": room.status == "finished"}, 200
        raise HttpError(404, f"no room operation {op}")

    # puzzles ahead of time -----------------------------------------------------------------------------------------------
    def warm_step(self) -> str | None:
        """One piece of puzzle work done early, while the page is idle (the Web Worker calls this between requests).
        A round's puzzle (``puzzle.public_round``, cached by the engine) takes 0.3-8 s under Pyodide the first time;
        made here, the round starts at once. Never while a person's screen is open (their clock runs while the
        engine works). Returns what it did, or None when there is nothing left."""
        from squid5.core.puzzle import Spec, public_round

        if not self.warmed_base:  # the shape tables every seed shares (most of round 1's first cost)
            self.warmed_base = True
            public_round(1, 1, Spec(**sig.PROFILES[sig.SCHEDULE[0]]), 4, sig.PER_AGENT)
            return "base"
        for room in self.rooms.values():
            if room.status not in ("lobby", "running") or any(h.pending is not None for h in room.humans()):
                continue
            ses = room.session or room.preview()
            es, done = ses.s, self.warmed.setdefault(room.code, set())
            now = (room.live or {}).get("round") or 0
            for r in range(max(1, now), room.settings.rounds + 1):
                if r not in done:
                    done.add(r)
                    public_round(ses.seed, r, es.profiles[es.schedule[r - 1]], 4, es.public_per_agent)
                    return f"{room.code}:R{r}"
        if self.signal_next is not None:
            (seed, r), self.signal_next = self.signal_next, None
            public_round(seed, r, Spec(**sig.PROFILES[sig.SCHEDULE[r - 1]]), 4, sig.PER_AGENT)
            return f"signal:{seed}:R{r}"
        return None

    def record_info(self, room) -> dict | None:
        g = room.doc.get("game")
        if not g:
            return None
        return {k: g.get(k) for k in ("id", "offline", "error", "uploads", "uploaded_rounds", "uploaded_final",
                                      "upload_error", "uploaded_at", "expires_at")}

    # after every change: save, model calls, the record -----------------------------------------------------------------------
    def after(self, room) -> None:
        self.persist(room)
        self.kick(room)
        self.maybe_upload(room)

    def persist(self, room) -> None:
        room.dirty.clear()
        if self.hooks is None:
            return
        text = json.dumps({"doc": room.doc, "replies": {a: {str(i): r for i, r in v.items()}
                                                        for a, v in room.replies.items()}},
                          ensure_ascii=False, default=str)
        try:
            self.hooks.persist(room.code, text)
        except Exception:  # noqa: BLE001 - storage is a convenience (private mode, quota)
            pass

    def link(self, room) -> modelcalls.Link:
        g = room.doc.get("game") or {}
        return modelcalls.Link(self.worker + "/llm", g.get("token") or "")

    def kick(self, room) -> None:
        """Start the room's model-call loop if it waits for a model and none runs (one at a time per room)."""
        if room.status != "running" or not room.model_jobs():
            return
        t = self.pumps.get(room.code)
        if t is not None and not t.done():
            return
        self.pumps[room.code] = asyncio.ensure_future(self.pump(room))

    async def pump(self, room) -> int:
        made = await modelcalls.run_all(room, self.link(room), self.transport, clock=self.clock,
                                        on_step=lambda: (self.persist(room), self.maybe_upload(room)))
        self.persist(room)
        return made

    def maybe_upload(self, room) -> None:
        g = room.doc.get("game") or {}
        if not g.get("id"):
            return
        rounds = sum(e.get("event") == "round" for e in room.events)
        ended = room.status in ("finished", "error")
        if rounds > g.get("uploaded_rounds", -1) or (ended and not g.get("uploaded_final")):
            t = self.uploads.get(room.code)
            if t is not None and not t.done():
                self.upload_again.add(room.code)
                return
            self.uploads[room.code] = asyncio.ensure_future(self.upload(room))

    async def upload(self, room, force: bool = False) -> bool:
        g = room.doc.get("game") or {}
        if not g.get("id") or self.hooks is None:
            return False
        rec = record_of(room, self.engine)
        url = f"{self.worker}/api/games/{g['id']}/record"
        try:
            res = await self.hooks.upload(url, g["token"], json.dumps(rec, ensure_ascii=False, default=str),
                                          json.dumps(summary_of(rec)))
            res = res.to_py() if hasattr(res, "to_py") else res
            status, body = int(res["status"]), res.get("body")
        except Exception as err:  # noqa: BLE001
            status, body = 0, {"detail": f"{type(err).__name__}: {err}"}
        if status == 200:
            g.update(uploads=g.get("uploads", 0) + 1, uploaded_rounds=rec["rounds"], upload_error=None,
                     uploaded_final=rec["status"] in ("finished", "error"), uploaded_at=self.clock())
        else:
            g["upload_error"] = (body or {}).get("detail") if isinstance(body, dict) else str(body)
            g["upload_error"] = f"HTTP {status}: {g['upload_error']}"[:300]
        self.persist(room)
        if room.code in self.upload_again:
            self.upload_again.discard(room.code)
            asyncio.ensure_future(self.upload(room))
        return status == 200


# --- the browser's small JSON calls to the Worker (Pyodide only) ---------------------------------------------------------

async def js_net(method: str, url: str, body):
    import js
    from pyodide.ffi import to_js

    opts = {"method": method, "headers": {"Content-Type": "application/json"}}
    if body is not None:
        opts["body"] = json.dumps(body)
    resp = await js.fetch(url, to_js(opts, dict_converter=js.Object.fromEntries))
    text = await resp.text()
    try:
        data = json.loads(text) if text else None
    except ValueError:
        data = {"detail": text[:300]}
    return int(resp.status), data


__all__ = ["Arena", "HttpError", "record_of", "summary_of", "event_digests", "events_digest", "digest_of", "canon", "RECORD_FORMAT"]
