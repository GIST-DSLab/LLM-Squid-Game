"""PARKED (10-18, not deployed, does not import as is): see legacy/README.md.

squid5 web API on Cloudflare: one Python Worker (router, signal page, probe survey) and one Durable Object per room.

Routes (the FastAPI server's, web/server/app.py; the same request and response shapes, errors as {"detail": ...}):

    GET  /api/health                         {ok, rooms, time, backend}
    GET  /api/models                         the model seats on offer (gemma4:31b first, think off), key present?
    POST /api/rooms                          {host_name, settings} -> {code, token, agent, name}   (D1 + RoomDO)
    GET  /api/rooms                          the latest rooms (D1)
    POST /api/rooms/{code}/join|start|submit|watched|forfeit|export      -> RoomDO
    GET  /api/rooms/{code}/state|events                                  -> RoomDO
    GET  /api/signal/meta, POST /api/signal/view|solve                   web/server/signal.py, stateless
    POST /api/probe, GET /api/probe/summary                              D1 ``probes``
    GET  /api/leaderboard                    410: the leaderboard is a static GitHub Pages page now

A room is a ``RoomDO`` named by its code. It holds the room's doc and every reply (its own SQLite), replays the
session after each reply (replay.py) and makes model calls from its alarm, one at a time (modelcalls.py). Events are
mirrored to D1 (``events``) for listing and export; finished rooms export their run dir to R2 (``RUNS``).
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict
from urllib.parse import parse_qs, urlparse

import compat

compat.install()

from workers import DurableObject, Response, WorkerEntrypoint  # noqa: E402

import keys  # noqa: E402
import modelcalls  # noqa: E402
import ollama_fetch  # noqa: E402
import replay  # noqa: E402
import settings as S  # noqa: E402
import stub_transport  # noqa: E402
from web.server import engine as E  # noqa: E402
from web.server import signal as sig  # noqa: E402

DEFAULT_CORS = ["http://localhost:5600", "http://127.0.0.1:5600", "http://localhost:8600", "http://127.0.0.1:8600",
                "https://gist-dslab.github.io"]
JSON_HEADERS = {"content-type": "application/json; charset=utf-8"}
ALARM_BUDGET_S = 600.0  # model calls per alarm (an alarm may run 15 minutes); the rest goes to the next alarm


class HttpError(Exception):
    def __init__(self, status: int, detail: str):
        super().__init__(detail)
        self.status, self.detail = status, detail


def env_getter(env):
    def get(name: str):
        try:
            v = getattr(env, name)
        except AttributeError:
            return None
        if v is None or str(type(v)).endswith("JsNull'>") or v.__class__.__name__ in ("JsUndefined",):
            return None
        return v if isinstance(v, str) else str(v)
    return get


def _py(x):
    """A JS value as Python (the SDK's binding wrappers convert some results already)."""
    x = x.to_py() if hasattr(x, "to_py") else x
    if isinstance(x, list):
        return [_py(v) for v in x]
    if isinstance(x, dict):
        return {k: _py(v) for k, v in x.items()}
    return x


async def d1_all(db, sql: str, *args) -> list[dict]:
    res = await db.prepare(sql).bind(*args).all()
    res = _py(res)
    return (res.get("results") if isinstance(res, dict) else _py(res.results)) or []


async def d1_run(db, sql: str, *args):
    return await db.prepare(sql).bind(*args).run()


# --- the Worker ---------------------------------------------------------------------------------------------------------

class Default(WorkerEntrypoint):
    def cors(self, request) -> dict:
        origin = request.headers.get("origin") or ""
        allowed = [o.strip() for o in (env_getter(self.env)("CORS_ORIGINS") or "").split(",") if o.strip()] or DEFAULT_CORS
        if origin in allowed:
            return {"access-control-allow-origin": origin, "vary": "Origin",
                    "access-control-allow-methods": "GET, POST, OPTIONS",
                    "access-control-allow-headers": "Content-Type", "access-control-max-age": "86400"}
        return {}

    def reply(self, request, data, status: int = 200) -> Response:
        return Response(json.dumps(data, ensure_ascii=False, default=str), status=status,
                        headers={**JSON_HEADERS, **self.cors(request)})

    async def fetch(self, request):
        if request.method == "OPTIONS":
            return Response("", status=204, headers=self.cors(request))
        try:
            return self.reply(request, *await self.route(request))
        except HttpError as err:
            return self.reply(request, {"detail": err.detail}, err.status)
        except Exception as err:  # noqa: BLE001
            return self.reply(request, {"detail": f"server error: {type(err).__name__}: {err}"}, 500)

    async def body(self, request) -> dict:
        text = await request.text()
        if not text:
            return {}
        try:
            data = json.loads(text)
        except ValueError as err:
            raise HttpError(400, f"bad JSON: {err}") from err
        return data if isinstance(data, dict) else {}

    def room_stub(self, code: str):
        ns = self.env.ROOMS
        return ns.get(ns.idFromName(code.upper()))

    async def to_room(self, code: str, op: str, token: str, body: dict, method: str):
        out = json.loads(await self.room_stub(code).api(op, token, json.dumps(body), method))
        return out["body"], out["status"]

    async def route(self, request):
        url = urlparse(request.url)
        path, q = url.path.rstrip("/") or "/", {k: v[0] for k, v in parse_qs(url.query).items()}
        m, env_get = request.method, env_getter(self.env)
        parts = path.split("/")
        if path == "/api/health":
            rows = await d1_all(self.env.DB, "SELECT COUNT(*) AS n FROM rooms WHERE status IN ('lobby', 'running')")
            return {"ok": True, "rooms": rows[0]["n"] if rows else 0, "time": time.time(), "backend": "cloudflare"}, 200
        if path == "/api/models":
            return self.models(env_get), 200
        if path == "/api/rooms" and m == "POST":
            return await self.create_room(await self.body(request), env_get)
        if path == "/api/rooms" and m == "GET":
            rows = await d1_all(self.env.DB, "SELECT code, created_at, settings, seats, status FROM rooms "
                                             "ORDER BY created_at DESC LIMIT 50")
            return [{"code": r["code"], "status": r["status"], "created_at": r["created_at"],
                     "humans": sum(v.get("kind") == "human" for v in json.loads(r["seats"] or "{}").values()),
                     "seats": json.loads(r["settings"] or "{}").get("humans")} for r in rows], 200
        if len(parts) == 5 and parts[1:3] == ["api", "rooms"]:
            code, op = parts[3].upper(), parts[4]
            allowed = {"GET": ("state", "events"), "POST": ("join", "start", "submit", "watched", "forfeit", "export")}
            if op not in allowed.get(m, ()):
                raise HttpError(405 if op in sum(allowed.values(), ()) else 404, f"{m} {path}")
            body = await self.body(request) if m == "POST" else {}
            return await self.to_room(code, op, q.get("token", ""), body, m)
        if path == "/api/signal/meta":
            return sig.meta(), 200
        if path in ("/api/signal/view", "/api/signal/solve") and m == "POST":
            fn = sig.view if path.endswith("view") else sig.solve
            try:
                return fn(await self.body(request)), 200
            except sig.SignalError as err:
                raise HttpError(400, str(err)) from err
        if path == "/api/probe" and m == "POST":
            return await self.probe(await self.body(request)), 200
        if path == "/api/probe/summary":
            rows = await d1_all(self.env.DB, "SELECT self_vals, other_vals FROM probes ORDER BY id")
            n = len(rows)
            vals = [{"self": json.loads(r["self_vals"]), "other": json.loads(r["other_vals"])} for r in rows]
            mean = lambda k: [sum(v[k][i] for v in vals) / n / 100 for i in range(5)] if n else None  # noqa: E731
            return {"n": n, "x": [50, 40, 30, 20, 10], "self": mean("self"), "other": mean("other")}, 200
        if path == "/api/leaderboard":
            raise HttpError(410, "리더보드는 GitHub Pages의 정적 페이지(leaderboard.html, monitor/data)로 옮겼습니다.")
        raise HttpError(404, f"no route {m} {path}")

    def models(self, env_get) -> dict:
        d = S.defaults()
        return {"model": S.DEFAULT_MODEL, "think": None, "think_levels": ["off", *E.THINK_LEVELS],
                "models": S.MODELS, "api_key_env": keys.DEFAULT_KEY,
                "available": bool((env_get(keys.DEFAULT_KEY) or "").strip()),
                "key1_enabled": keys.key1_enabled(env_get), "timeout": d["model_timeout"], "version": E.VERSION,
                "sequential_model_calls": True, "defaults": d}

    async def probe(self, body: dict) -> dict:
        """The 5.1 survey (web/server/app.py ``probe``): self and other, 5 values in 0..100 each."""
        try:
            vals = {k: [float(x) for x in body[k]] for k in ("self", "other")}
        except (KeyError, TypeError, ValueError) as err:
            raise HttpError(400, f"self and other must be lists of 5 numbers: {err}") from err
        if any(len(v) != 5 or not all(0 <= x <= 100 for x in v) for v in vals.values()):
            raise HttpError(400, "self and other must each hold 5 values in 0..100")
        meta = {k: v for k, v in (body.get("meta") or {}).items() if isinstance(k, str)}
        res = await d1_run(self.env.DB, "INSERT INTO probes (ts, anon_id, client_ts, self_vals, other_vals, meta) "
                                        "VALUES (?, ?, ?, ?, ?, ?)", time.time(), str(body.get("anon_id") or "")[:64],
                           str(body.get("ts") or "")[:40], json.dumps(vals["self"]), json.dumps(vals["other"]),
                           json.dumps(meta))
        res = _py(res)
        meta = res.get("meta") if isinstance(res, dict) else _py(res.meta)
        return {"ok": True, "id": int(meta["last_row_id"])}

    async def create_room(self, body: dict, env_get):
        try:
            s = S.make(body.get("settings") or {}, env_get)
        except keys.KeyError_ as err:
            raise HttpError(400, str(err)) from err
        except (TypeError, ValueError) as err:
            raise HttpError(400, f"bad settings: {err}") from err
        if s.fill == "models" and s.humans < 4:
            try:
                keys.key_value(s.api_key_env, env_get)
            except keys.KeyError_ as err:
                raise HttpError(400, str(err)) from err
        for _ in range(20):
            code = E.new_code(())
            if not await d1_all(self.env.DB, "SELECT code FROM rooms WHERE code = ?", code):
                break
        else:
            raise HttpError(503, "no free room code")
        out, status = await self.to_room(code, "create", "", {"code": code, "host_name": body.get("host_name") or "host",
                                                              "settings": asdict(s)}, "POST")
        return out, status


# --- the room -----------------------------------------------------------------------------------------------------------

class RoomDO(DurableObject):
    def __init__(self, ctx, env):
        super().__init__(ctx, env)
        self.sql = ctx.storage.sql
        self.sql.exec("CREATE TABLE IF NOT EXISTS meta (k TEXT PRIMARY KEY, v TEXT)")
        self.sql.exec("CREATE TABLE IF NOT EXISTS replies (agent TEXT, idx INTEGER, body TEXT, PRIMARY KEY (agent, idx))")
        self.room: replay.ReplayRoom | None = None
        self.env_get = env_getter(env)

    # storage -------------------------------------------------------------------------------------------------------------
    def _rows(self, sql: str, *args) -> list[dict]:
        return _py(self.sql.exec(sql, *args).toArray())

    def load(self) -> replay.ReplayRoom | None:
        if self.room is None:
            rows = self._rows("SELECT v FROM meta WHERE k = 'doc'")
            if not rows:
                return None
            replies: dict = {}
            for r in self._rows("SELECT agent, idx, body FROM replies"):
                replies.setdefault(r["agent"], {})[int(r["idx"])] = json.loads(r["body"])
            self.room = replay.ReplayRoom.load(json.loads(rows[0]["v"]), replies, make=S.make)
        return self.room

    def save(self) -> None:
        room = self.room
        for a, i in room.dirty:
            self.sql.exec("INSERT OR REPLACE INTO replies (agent, idx, body) VALUES (?, ?, ?)", a, i,
                          json.dumps(room.replies[a][i], ensure_ascii=False))
        room.dirty.clear()
        self.sql.exec("INSERT OR REPLACE INTO meta (k, v) VALUES ('doc', ?)", json.dumps(room.doc, ensure_ascii=False))

    async def mirror(self) -> None:
        """The room row and the events not yet in D1 (best effort: a failure is retried at the next save)."""
        room, db = self.room, self.env.DB
        rows = [("INSERT INTO rooms (code, created_at, settings, seats, status, updated_at) VALUES (?, ?, ?, ?, ?, ?) "
                 "ON CONFLICT(code) DO UPDATE SET seats = excluded.seats, status = excluded.status, "
                 "updated_at = excluded.updated_at",
                 (room.code, room.created_at, json.dumps(room.state(None)["settings"] | {"rounds": room.settings.rounds}),
                  json.dumps(room.seats_info()), room.status, time.time()))]
        new = room.new_events()
        rows += [("INSERT OR IGNORE INTO events (code, seq, ts, kind, body) VALUES (?, ?, ?, ?, ?)",
                  (room.code, seq, time.time(), str(ev.get("event")), json.dumps(ev, ensure_ascii=False, default=str)))
                 for seq, ev in new]
        try:
            for i in range(0, len(rows), 50):  # statements are made right before their batch (JS proxies)
                stmts = [db.prepare(sql).bind(*args) for sql, args in rows[i:i + 50]]
                await db.batch(stmts)  # the SDK converts the list and unwraps each statement
        except Exception:  # noqa: BLE001 - D1 is a mirror; the DO holds the truth
            room.doc["saved_events"] -= len(new)
            raise

    async def schedule(self) -> None:
        t = self.room.wake_at() if self.room else None
        if t is not None:
            await self.ctx.storage.setAlarm(int(max(t, time.time()) * 1000))

    async def persist(self) -> None:
        self.save()
        try:
            await self.mirror()
        except Exception as err:  # noqa: BLE001 - logged; the next save retries the same events
            print(f"room {self.room.code}: D1 mirror failed: {type(err).__name__}: {err}")
        self.save()
        await self.schedule()

    # the API -------------------------------------------------------------------------------------------------------------
    async def api(self, op: str, token: str, body: str, method: str = "POST") -> str:
        try:
            out, status = await self.handle(op, token, json.loads(body or "{}"))
        except HttpError as err:
            out, status = {"detail": err.detail}, err.status
        return json.dumps({"status": status, "body": out}, ensure_ascii=False, default=str)

    def seat(self, token: str):
        seat = self.room.seat_by_token(token or "")
        if seat is None:
            raise HttpError(403, "bad token")
        return seat

    async def handle(self, op: str, token: str, body: dict):
        if op == "create":
            if self.load() is not None:
                raise HttpError(409, "room exists")
            s = S.make(body["settings"])
            self.room = room = replay.ReplayRoom(body["code"], s)
            return await self._create(room, body)
        room = self.load()
        if room is None:
            raise HttpError(404, "no such room")
        changed = room.tick()
        if op == "state":
            seat = room.seat_by_token(token) if token else None
            out = room.state(seat)
            out["monitor"] = None  # the live game log is not served by the Worker (static Pages viewer + export)
            if changed:
                await self.persist()
            return out, 200
        if op == "events":
            if changed:
                await self.persist()
            ended = room.status in ("finished", "error")
            return (room.events if ended else E.public_events(room.events)), 200
        if op == "join":
            try:
                seat = room.join(body.get("name") or "")
            except ValueError as err:
                raise HttpError(409, str(err)) from err
            await self.persist()
            return {"code": room.code, "token": seat.token, "agent": seat.agent, "name": seat.name}, 200
        if op == "start":
            seat = self.seat(token)
            if seat.token != room.host_token:
                raise HttpError(403, "only the host starts the session")
            s = room.settings
            if s.fill == "models" and s.humans < 4:
                try:
                    keys.key_value(keys.choose_key(s.api_key_env, self.env_get), self.env_get)
                except keys.KeyError_ as err:
                    raise HttpError(400, str(err)) from err
            try:
                room.start()
            except ValueError as err:
                raise HttpError(409, str(err)) from err
            await self.persist()
            return {"ok": True}, 200
        if op == "submit":
            try:
                out = room.submit(token, body)
            except PermissionError as err:
                raise HttpError(403, str(err)) from err
            except (LookupError, ValueError) as err:
                raise HttpError(409, str(err)) from err
            await self.persist()
            return out, 200
        if op == "watched":
            seat = self.seat(token)
            try:
                out = room.watch_ack(seat, int(body.get("round") or 0))
            except LookupError as err:
                raise HttpError(409, str(err)) from err
            room.advance()
            await self.persist()
            return out, 200
        if op == "forfeit":
            self.seat(token)
            try:
                closed = room.forfeit(token)
            except ValueError as err:
                raise HttpError(409, str(err)) from err
            await self.persist()
            return {"ok": True, "closed": closed}, 200
        if op == "export":
            return await self.export(room)
        raise HttpError(404, f"no room operation {op}")

    async def _create(self, room, body: dict):
        seat = room.join(body.get("host_name") or "host")
        await self.persist()
        return {"code": room.code, "token": seat.token, "agent": seat.agent, "name": seat.name}, 200

    async def export(self, room):
        """The room's run dir (config.yaml, meta.json, events.jsonl, results.jsonl) to R2 ``RUNS`` under
        web5/runs/<code>/, the layout the game-log viewer and ``python -m squid5 report`` read."""
        import yaml

        evs = room.events
        if not any(e.get("event") == "round" for e in evs):
            raise HttpError(409, "no round has been played yet")
        bucket = getattr(self.env, "RUNS", None)
        if bucket is None:
            raise HttpError(501, "이 Worker에는 R2 버킷(RUNS)이 묶여 있지 않아 내보낼 수 없습니다.")
        seats = {a: {"kind": v["kind"], "model": v["model"], "name": v.get("name")} for a, v in room.seats_info().items()}
        rs = room.settings
        files = {"config.yaml": yaml.safe_dump(E.run_config(rs, seats, room.code), sort_keys=False),
                 "meta.json": json.dumps(E.run_meta(rs, seats)),
                 "events.jsonl": "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in evs
                                         if e.get("event") in E.LOG_EVENTS),
                 "results.jsonl": "".join(json.dumps(e, ensure_ascii=False, default=str) + "\n" for e in evs
                                          if e.get("event") == "session")}
        prefix = f"web5/runs/{room.code}/"
        for name, text in files.items():
            await bucket.put(prefix + name, text)
        return {"dir": f"r2://RUNS/{prefix}", "rounds": sum(e.get("event") == "round" for e in evs),
                "finished": any(e.get("event") == "session" for e in evs)}, 200

    async def alarm(self, *args):
        room = self.load()
        if room is None:
            return
        room.tick()
        transport = stub_transport.transport if self.env_get("MODEL_STUB") == "on" else ollama_fetch.js_transport
        await modelcalls.run_all(room, self.env_get, transport, budget_s=ALARM_BUDGET_S, on_step=self.persist)
        await self.persist()
