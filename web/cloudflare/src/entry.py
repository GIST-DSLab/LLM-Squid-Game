"""squid5 web API on Cloudflare, FREE plan: a thin Python Worker. The game engine runs in the visitor's browser
(web/pyodide, Pyodide in a Web Worker); this Worker never imports it.

Routes (CORS for the Pages origins in ``CORS_ORIGINS``; errors as {"detail": <Korean>, "code"?}):

    GET  /api/health                      {ok, backend, time}
    GET  /api/models                      the models on offer (gemma4:31b first, think off), key 3 present?, limits
    POST /api/games                       register a browser game -> {game, token, expires_at, limits}
    POST /llm/api/chat                    Ollama-compatible chat for a game's model seats (Bearer = game token);
                                          the Worker picks the key (keys.py), counts the call, passes the answer or
                                          its NDJSON stream through
    POST /api/games/{id}/record           the browser's game record (gzip JSON, Bearer = game token) -> R2 + D1 row
    GET  /api/games, /api/games/{id}/record|calls     export for the offline verifier (Bearer = ARENA_EXPORT_TOKEN)
    POST /api/probe, GET /api/probe/summary           the 5.1 survey (D1 ``probes``)
    /api/rooms*, /api/signal*             410: the engine runs in the browser now

Free-plan fit: every request does a little JSON and hashing and waits on I/O (D1, R2, Ollama); waiting is not CPU
time. The record upload is stored as the raw bytes it came in (never parsed here). Limits (vars, defaults below):
calls per game, calls per IP per hour, games per IP per hour, a short token lifetime, num_predict at most the
model's context (clamped), a model allow-list. Counters live in D1 (``games.calls``, ``quota``): one batch per call.

Keys (keys.py): OLLAMA_API_KEY3 for every call by default; OLLAMA_API_KEY1 only for a game registered with it while
the dashboard variable OLLAMA_KEY1_ENABLED is exactly "on", re-checked at every call; never a fallback.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from urllib.parse import parse_qs, urlparse

import keys

try:  # the Worker runtime; the CPU bench (tests/bench_cpu.mjs) and the unit tests provide stand-ins
    from workers import Response, WorkerEntrypoint
except ImportError:  # pragma: no cover
    Response = WorkerEntrypoint = None

DEFAULT_CORS = ["http://localhost:5600", "http://127.0.0.1:5600", "http://localhost:8600", "http://127.0.0.1:8600",
                "https://gist-dslab.github.io"]
JSON_HEADERS = {"content-type": "application/json; charset=utf-8"}
OLLAMA = "https://ollama.com"
DEFAULT_MODEL = "gemma4:31b"
MODELS = [  # the allow-list, the default first (web/pyodide/room_settings.py offers the same)
    {"model": DEFAULT_MODEL, "think": None, "default": True, "note": "기본: 생각 끔, TALK 한 번 약 1.5초"},
    {"model": "gpt-oss:20b", "think": "medium", "default": False, "note": "서버의 옛 기본값"},
]
ALLOWED = {m["model"] for m in MODELS}
THINK = (None, True, False, "low", "medium", "high")
LIMITS = {  # overridable as plain vars (LIMIT_<NAME>), numbers
    "GAME_CALLS": 600,  # model calls per game (8 rounds x 3 model seats is ~150-400 with retries)
    "IP_CALLS_HOUR": 1200,  # model calls per IP per hour
    "IP_GAMES_HOUR": 12,  # games registered per IP per hour
    "TOKEN_TTL_S": 6 * 3600,  # a game token's lifetime
    "MAX_PREDICT": 131072,  # num_predict is clamped here (a TALK's cap is the seat's balance; no model writes more)
    "MAX_CHAT_BYTES": 400_000,  # one chat request (the engine keeps history_messages short)
    "MAX_RECORD_BYTES": 4_000_000,  # one gzip game record
    "GAME_UPLOADS": 80,  # record uploads per game (one per round + the end + a few by hand)
}


class HttpError(Exception):
    def __init__(self, status: int, detail: str, code: str = ""):
        super().__init__(detail)
        self.status, self.detail, self.code = status, detail, code


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


def limit(env_get, name: str) -> int:
    raw = env_get(f"LIMIT_{name}")
    try:
        return int(raw) if raw not in (None, "") else LIMITS[name]
    except ValueError:
        return LIMITS[name]


def _py(x):
    x = x.to_py() if hasattr(x, "to_py") else x
    if isinstance(x, list):
        return [_py(v) for v in x]
    if isinstance(x, dict):
        return {k: _py(v) for k, v in x.items()}
    return x


async def d1_all(db, sql: str, *args) -> list[dict]:
    res = _py(await db.prepare(sql).bind(*args).all())
    return (res.get("results") if isinstance(res, dict) else _py(res.results)) or []


async def d1_batch(db, stmts: list[tuple[str, tuple]]) -> list[list[dict]]:
    res = _py(await db.batch([db.prepare(sql).bind(*args) for sql, args in stmts]))
    return [(r.get("results") if isinstance(r, dict) else _py(r.results)) or [] for r in res]


# --- game tokens: base64url(json) "." base64url(hmac-sha256) -------------------------------------------------------------

def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def _unb64(s: str) -> bytes:
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def sign(secret: str, claims: dict) -> str:
    body = _b64(json.dumps(claims, separators=(",", ":"), sort_keys=True).encode())
    mac = hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest()
    return f"{body}.{_b64(mac)}"


def verify(secret: str, token: str, now: float) -> dict:
    """The claims of a valid, unexpired token; HttpError 401 otherwise."""
    try:
        body, mac = token.split(".")
        good = hmac.compare_digest(_unb64(mac), hmac.new(secret.encode(), body.encode(), hashlib.sha256).digest())
        claims = json.loads(_unb64(body)) if good else None
    except (ValueError, TypeError):
        claims = None
    if not isinstance(claims, dict):
        raise HttpError(401, "게임 토큰이 올바르지 않습니다. 새 게임을 시작하세요.", "token")
    if now > float(claims.get("exp", 0)):
        raise HttpError(401, "게임 토큰이 만료되었습니다(게임 시작 뒤 시간 제한). 새 게임을 시작하세요.", "token_expired")
    return claims


def ip_hash(secret: str, ip: str) -> str:
    return hashlib.sha256(f"{secret}|{ip}".encode()).hexdigest()[:16]


def digest(text: str) -> str:
    """The engine's prompt hash (web/pyodide/replay.py ``digest``): the verifier matches records to logged calls."""
    return hashlib.sha1(text.encode("utf-8")).hexdigest()[:16]


def chat_payload(body: dict, model: str, max_predict: int) -> dict:
    """The Ollama request the Worker sends: only the fields the engine uses, bounded."""
    if body.get("model") != model:
        raise HttpError(403, f"이 게임의 모델은 {model}입니다(요청: {str(body.get('model'))[:40]}).", "model")
    msgs = body.get("messages")
    if not isinstance(msgs, list) or not msgs or len(msgs) > 200:
        raise HttpError(400, "messages가 없거나 너무 깁니다.", "bad_request")
    clean = []
    for m in msgs:
        if not isinstance(m, dict) or m.get("role") not in ("system", "user", "assistant") \
                or not isinstance(m.get("content"), str):
            raise HttpError(400, "messages의 형식이 맞지 않습니다.", "bad_request")
        clean.append({"role": m["role"], "content": m["content"]})
    opts = body.get("options") if isinstance(body.get("options"), dict) else {}
    try:
        temp = min(2.0, max(0.0, float(opts.get("temperature", 1.0))))
        cap = int(opts.get("num_predict", max_predict))
    except (TypeError, ValueError) as err:
        raise HttpError(400, "options가 숫자가 아닙니다.", "bad_request") from err
    if cap < 1:
        raise HttpError(400, "num_predict는 1 이상이어야 합니다.", "bad_request")
    cap = min(cap, max_predict)  # the engine sends a TALK's cap = the balance (up to millions); the model's context ends sooner
    out = {"model": model, "messages": clean, "stream": bool(body.get("stream")),
           "options": {"temperature": temp, "num_predict": cap}}
    if body.get("think") is not None:
        if body["think"] not in THINK:
            raise HttpError(400, "think는 low · medium · high만 됩니다.", "bad_request")
        out["think"] = body["think"]
    return out


UPSTREAM = {  # Ollama's refusals, in Korean; 429 stays 429 (the browser retries it), the rest are final
    401: (502, "Ollama가 서버 키를 거부했습니다(401). 연구자에게 알려 주세요.", "upstream_auth"),
    403: (502, "Ollama가 서버 키를 거부했습니다(403). 연구자에게 알려 주세요.", "upstream_auth"),
    402: (402, "OLLAMA_API_KEY3의 무료 사용량이 끝났습니다(402). 다른 키로 넘어가지 않습니다 — 연구자가 충전하거나 "
               "내일 다시 해 주세요.", "upstream_quota"),
    429: (429, "Ollama가 지금 요청이 많다고 거절했습니다(429, KEY3). 잠시 뒤 자동으로 다시 시도합니다. 다른 키로는 "
               "넘어가지 않습니다.", "upstream_429"),
}


# --- the Worker -----------------------------------------------------------------------------------------------------------

class Api:
    """The routes, independent of the runtime's Request / Response (``fetch`` adapts them)."""

    def __init__(self, env, now=time.time):
        self.env, self.get, self.now = env, env_getter(env), now

    # helpers ------------------------------------------------------------------------------------------------------------
    def secret(self) -> str:
        s = (self.get("GAME_TOKEN_SECRET") or "").strip()
        if len(s) < 16:
            raise HttpError(503, "서버에 GAME_TOKEN_SECRET(16자 이상)이 없어 게임을 등록할 수 없습니다 "
                                 "(wrangler secret put GAME_TOKEN_SECRET).", "config")
        return s

    def bearer(self, headers) -> str:
        auth = headers.get("authorization") or ""
        return auth[7:].strip() if auth.lower().startswith("bearer ") else ""

    def admin(self, headers) -> None:
        want = (self.get("ARENA_EXPORT_TOKEN") or "").strip()
        if len(want) < 16:
            raise HttpError(503, "ARENA_EXPORT_TOKEN이 없어 내보내기가 꺼져 있습니다.", "config")
        if not hmac.compare_digest(self.bearer(headers), want):
            raise HttpError(401, "내보내기 토큰이 맞지 않습니다.", "admin")

    def ollama_base(self) -> str:
        """``OLLAMA_BASE_URL`` for local tests (tests/fake_ollama.py): only a loopback address is honoured, so a stray
        value in production can never send a key to another host."""
        url = (self.get("OLLAMA_BASE_URL") or "").strip()
        return url if url.startswith(("http://127.0.0.1:", "http://localhost:")) else OLLAMA

    async def bump(self, key: str, ttl: float) -> int:
        rows = await d1_all(self.env.DB, "INSERT INTO quota (k, n, exp) VALUES (?, 1, ?) ON CONFLICT(k) DO UPDATE "
                                         "SET n = n + 1 RETURNING n", key, self.now() + ttl)
        return int(rows[0]["n"]) if rows else 0

    # routes -------------------------------------------------------------------------------------------------------------
    def models(self) -> dict:
        return {"model": DEFAULT_MODEL, "think": None, "think_levels": ["off", "low", "medium", "high"],
                "models": MODELS, "api_key_env": keys.DEFAULT_KEY,
                "available": bool((self.get(keys.DEFAULT_KEY) or "").strip()),
                "key1_enabled": keys.key1_enabled(self.get), "backend": "cloudflare-thin", "engine": "browser",
                "limits": {k: limit(self.get, k) for k in ("GAME_CALLS", "IP_CALLS_HOUR", "IP_GAMES_HOUR",
                                                           "TOKEN_TTL_S", "MAX_PREDICT")}}

    async def new_game(self, body: dict, ip: str) -> dict:
        secret = self.secret()
        s = body.get("settings") if isinstance(body.get("settings"), dict) else {}
        fill = str(s.get("fill") or "bots")
        model = str(s.get("model") or DEFAULT_MODEL)
        uses_models = fill == "models" and int(s.get("humans") or 1) < 4
        try:
            key_name = keys.choose_key(s.get("api_key_env"), self.get)
            if uses_models:
                if model not in ALLOWED:
                    raise HttpError(400, f"이 모델은 쓸 수 없습니다: {model[:40]} (허용: {', '.join(sorted(ALLOWED))}).",
                                    "model")
                keys.key_value(key_name, self.get)
        except keys.KeyError_ as err:
            raise HttpError(400, str(err), "key") from err
        now, iph = self.now(), ip_hash(secret, ip)
        n = await self.bump(f"games:{iph}:{int(now // 3600)}", 7200)
        if n > limit(self.get, "IP_GAMES_HOUR"):
            raise HttpError(429, f"이 주소에서 한 시간에 시작할 수 있는 게임 수({limit(self.get, 'IP_GAMES_HOUR')})를 "
                                 "넘었습니다. 잠시 뒤 다시 해 주세요.", "limit_ip_games")
        gid = secrets.token_hex(8)
        ttl, eng = limit(self.get, "TOKEN_TTL_S"), body.get("engine") if isinstance(body.get("engine"), dict) else {}
        exp = now + ttl
        claims = {"g": gid, "m": model if uses_models else "", "k": key_name, "exp": exp}
        info = {k: s.get(k) for k in ("model", "think", "fill", "humans", "rounds", "seed")}
        await d1_batch(self.env.DB, [
            ("INSERT INTO games (id, created_at, ip, code, model, key_name, settings, engine, engine_version, calls, "
             "uploads, status, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 0, 'started', ?)",
             (gid, now, iph, str(body.get("code") or "")[:12], claims["m"], key_name, json.dumps(info)[:2000],
              str(eng.get("bundle") or "")[:64], str(eng.get("version") or "")[:32], now)),
            ("DELETE FROM quota WHERE exp < ?", (now,))])
        return {"game": gid, "token": sign(secret, claims), "expires_at": exp,
                "limits": {"calls": limit(self.get, "GAME_CALLS"), "ttl_s": ttl}}

    async def chat(self, headers, body_text: str, ip: str):
        """-> (status, headers, body) where body is text or the upstream JS stream."""
        secret = self.secret()
        claims = verify(secret, self.bearer(headers), self.now())
        if not claims.get("m"):
            raise HttpError(403, "이 게임은 모델 자리가 없습니다.", "model")
        if len(body_text) > limit(self.get, "MAX_CHAT_BYTES"):
            raise HttpError(413, "요청이 너무 큽니다.", "bad_request")
        try:
            body = json.loads(body_text)
        except ValueError as err:
            raise HttpError(400, "JSON이 아닙니다.", "bad_request") from err
        payload = chat_payload(body if isinstance(body, dict) else {}, claims["m"], limit(self.get, "MAX_PREDICT"))
        try:
            key = keys.key_value(keys.choose_key(claims.get("k"), self.get), self.get)  # the switch, every call
        except keys.KeyError_ as err:
            raise HttpError(403, str(err), "key") from err
        gid, now = claims["g"], self.now()
        iph = ip_hash(secret, ip)
        game_rows, ip_rows = await d1_batch(self.env.DB, [
            ("UPDATE games SET calls = calls + 1, updated_at = ? WHERE id = ? AND calls < ? RETURNING calls",
             (now, gid, limit(self.get, "GAME_CALLS"))),
            ("INSERT INTO quota (k, n, exp) VALUES (?, 1, ?) ON CONFLICT(k) DO UPDATE SET n = n + 1 RETURNING n",
             (f"calls:{iph}:{int(now // 3600)}", now + 7200))])
        if not game_rows:
            raise HttpError(429, f"이 게임의 모델 호출 수 한도({limit(self.get, 'GAME_CALLS')}번)에 닿았습니다. "
                                 "남은 모델 답은 빈 답으로 처리됩니다.", "limit_game")
        if int(ip_rows[0]["n"]) > limit(self.get, "IP_CALLS_HOUR"):
            raise HttpError(429, f"이 주소의 한 시간 모델 호출 한도({limit(self.get, 'IP_CALLS_HOUR')}번)에 닿았습니다. "
                                 "잠시 뒤 다시 해 주세요.", "limit_ip")
        n = int(game_rows[0]["calls"])
        user = next((m["content"] for m in reversed(payload["messages"]) if m["role"] == "user"), "")
        status, resp = await self.upstream(payload, key)
        log = ("INSERT INTO llm_calls (game, n, ts, model, prompt_h, status, stream, eval_count, content_h) "
               "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)")
        if status != 200:
            await d1_batch(self.env.DB, [(log, (gid, n, now, payload["model"], digest(user), status,
                                                int(payload["stream"]), None, None))])
            st, detail, code = UPSTREAM.get(status, (502, f"Ollama 오류(HTTP {status}).", "upstream"))
            raise HttpError(st, detail, code)
        if payload["stream"]:
            await d1_batch(self.env.DB, [(log, (gid, n, now, payload["model"], digest(user), 200, 1, None, None))])
            return 200, {"content-type": "application/x-ndjson"}, resp.body
        text = await resp.text()
        try:
            j = json.loads(text)
            ev, content_h = int(j.get("eval_count") or 0), digest((j.get("message") or {}).get("content") or "")
        except (ValueError, AttributeError):
            ev, content_h = None, None
        await d1_batch(self.env.DB, [(log, (gid, n, now, payload["model"], digest(user), 200, 0, ev, content_h))])
        return 200, JSON_HEADERS, text

    async def upstream(self, payload: dict, key: str):
        import js
        from pyodide.ffi import to_js

        opts = to_js({"method": "POST", "body": json.dumps(payload),
                      "headers": {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}},
                     dict_converter=js.Object.fromEntries)
        resp = await js.fetch(self.ollama_base() + "/api/chat", opts)
        return int(resp.status), resp

    async def record(self, gid: str, headers, size: int, read_body) -> dict:
        claims = verify(self.secret(), self.bearer(headers), self.now() - 24 * 3600)  # an hour-long game may end late
        if claims.get("g") != gid:
            raise HttpError(403, "이 게임의 토큰이 아닙니다.", "token")
        if not 0 < size <= limit(self.get, "MAX_RECORD_BYTES"):
            raise HttpError(413, "기록이 비었거나 너무 큽니다.", "bad_request")
        try:
            summ = json.loads(headers.get("x-squid5-summary") or "{}")
        except ValueError:
            summ = {}
        summ = summ if isinstance(summ, dict) else {}
        now = self.now()
        rows = await d1_all(self.env.DB, "UPDATE games SET uploads = uploads + 1, status = ?, rounds = ?, events = ?, "
                                         "digest = ?, bytes = ?, updated_at = ? WHERE id = ? AND uploads < ? "
                                         "RETURNING uploads",
                            str(summ.get("status") or "")[:16], int(summ.get("rounds") or 0),
                            int(summ.get("events") or 0), str(summ.get("digest") or "")[:64], size, now, gid,
                            limit(self.get, "GAME_UPLOADS"))
        if not rows:
            raise HttpError(429, "이 게임의 기록 올리기 횟수 한도에 닿았습니다.", "limit_uploads")
        await self.env.RUNS.put(f"arena/games/{gid}/record.json.gz", await read_body())
        return {"ok": True, "game": gid, "uploads": int(rows[0]["uploads"]), "bytes": size}

    async def probe(self, body: dict) -> dict:
        """The 5.1 survey (web/server/app.py ``probe``): self and other, 5 values in 0..100 each."""
        try:
            vals = {k: [float(x) for x in body[k]] for k in ("self", "other")}
        except (KeyError, TypeError, ValueError) as err:
            raise HttpError(400, f"self and other must be lists of 5 numbers: {err}") from err
        if any(len(v) != 5 or not all(0 <= x <= 100 for x in v) for v in vals.values()):
            raise HttpError(400, "self and other must each hold 5 values in 0..100")
        meta = {k: v for k, v in (body.get("meta") or {}).items() if isinstance(k, str)}
        res = _py(await self.env.DB.prepare(
            "INSERT INTO probes (ts, anon_id, client_ts, self_vals, other_vals, meta) VALUES (?, ?, ?, ?, ?, ?)").bind(
            self.now(), str(body.get("anon_id") or "")[:64], str(body.get("ts") or "")[:40], json.dumps(vals["self"]),
            json.dumps(vals["other"]), json.dumps(meta)[:4000]).run())
        meta = res.get("meta") if isinstance(res, dict) else _py(res.meta)
        return {"ok": True, "id": int(meta["last_row_id"])}

    async def probe_summary(self) -> dict:
        rows = await d1_all(self.env.DB, "SELECT self_vals, other_vals FROM probes ORDER BY id")
        n = len(rows)
        vals = [{"self": json.loads(r["self_vals"]), "other": json.loads(r["other_vals"])} for r in rows]
        mean = lambda k: [sum(v[k][i] for v in vals) / n / 100 for i in range(5)] if n else None  # noqa: E731
        return {"n": n, "x": [50, 40, 30, 20, 10], "self": mean("self"), "other": mean("other")}

    async def route(self, method: str, url: str, headers, read_text, read_body, size: int, ip: str):
        """-> (status, extra headers, body): body is a dict / list (JSON), text, or a JS stream / buffer."""
        u = urlparse(url)
        path, q = u.path.rstrip("/") or "/", {k: v[0] for k, v in parse_qs(u.query).items()}
        parts = path.split("/")
        if path == "/api/health":
            return 200, {}, {"ok": True, "backend": "cloudflare-thin", "engine": "browser", "time": self.now()}
        if path == "/api/models":
            return 200, {}, self.models()
        if path == "/llm/api/chat" and method == "POST":
            return await self.chat(headers, await read_text(), ip)
        if path == "/api/games" and method == "POST":
            return 200, {}, await self.new_game(await self.json_body(read_text), ip)
        if path == "/api/games" and method == "GET":
            self.admin(headers)
            rows = await d1_all(self.env.DB, "SELECT id, created_at, code, model, key_name, settings, engine, "
                                             "engine_version, calls, uploads, status, rounds, events, digest, bytes, "
                                             "updated_at FROM games WHERE updated_at >= ? AND uploads > 0 "
                                             "ORDER BY updated_at LIMIT ?",
                                float(q.get("since") or 0), min(int(q.get("limit") or 200), 1000))
            return 200, {}, rows
        if len(parts) == 5 and parts[1:3] == ["api", "games"]:
            gid, op = parts[3], parts[4]
            if op == "record" and method == "POST":
                return 200, {}, await self.record(gid, headers, size, read_body)
            if op == "record" and method == "GET":
                self.admin(headers)
                obj = await self.env.RUNS.get(f"arena/games/{gid}/record.json.gz")
                if obj is None or str(type(obj)).endswith("JsNull'>"):
                    raise HttpError(404, "no record")
                return 200, {"content-type": "application/gzip"}, obj.body
            if op == "calls" and method == "GET":
                self.admin(headers)
                return 200, {}, await d1_all(self.env.DB, "SELECT n, ts, model, prompt_h, status, stream, eval_count, "
                                                          "content_h FROM llm_calls WHERE game = ? ORDER BY n", gid)
        if path == "/api/probe" and method == "POST":
            return 200, {}, await self.probe(await self.json_body(read_text))
        if path == "/api/probe/summary":
            return 200, {}, await self.probe_summary()
        if path.startswith(("/api/rooms", "/api/signal")):
            raise HttpError(410, "게임 엔진은 이제 브라우저에서 돕니다(arena.html · signal.html). 이 서버는 모델 호출과 "
                                 "기록 저장만 합니다.", "moved")
        if path == "/api/leaderboard":
            raise HttpError(410, "리더보드는 GitHub Pages의 정적 페이지(leaderboard.html, monitor/data)로 옮겼습니다.")
        raise HttpError(404, f"no route {method} {path}")

    async def json_body(self, read_text) -> dict:
        text = await read_text()
        if len(text) > 100_000:
            raise HttpError(413, "요청이 너무 큽니다.")
        try:
            data = json.loads(text) if text else {}
        except ValueError as err:
            raise HttpError(400, f"bad JSON: {err}") from err
        return data if isinstance(data, dict) else {}


def cors(env_get, origin: str) -> dict:
    allowed = [o.strip() for o in (env_get("CORS_ORIGINS") or "").split(",") if o.strip()] or DEFAULT_CORS
    if origin in allowed:
        return {"access-control-allow-origin": origin, "vary": "Origin",
                "access-control-allow-methods": "GET, POST, OPTIONS",
                "access-control-allow-headers": "Content-Type, Authorization, X-Squid5-Summary",
                "access-control-max-age": "86400"}
    return {}


if WorkerEntrypoint is not None:
    class Default(WorkerEntrypoint):
        async def fetch(self, request):
            env_get = env_getter(self.env)
            ch = cors(env_get, request.headers.get("origin") or "")
            if request.method == "OPTIONS":
                return Response("", status=204, headers=ch)
            api = Api(self.env)
            js_req = request.js_object

            async def read_text():
                return await request.text()

            async def read_body():
                return await js_req.arrayBuffer()  # stays a JS ArrayBuffer: stored as is, never parsed here

            try:
                size = int(request.headers.get("content-length") or 0)
            except ValueError:
                size = 0
            ip = request.headers.get("cf-connecting-ip") or "local"
            try:
                status, extra, body = await api.route(request.method, request.url, request.headers, read_text,
                                                      read_body, size, ip)
            except HttpError as err:
                status, extra = err.status, {}
                body = {"detail": err.detail, **({"code": err.code} if err.code else {})}
            except Exception as err:  # noqa: BLE001
                status, extra, body = 500, {}, {"detail": f"server error: {type(err).__name__}: {err}"}
            if isinstance(body, (dict, list)):
                return Response(json.dumps(body, ensure_ascii=False, default=str), status=status,
                                headers={**JSON_HEADERS, **ch, **extra})
            return Response(body, status=status, headers={**ch, **extra})
