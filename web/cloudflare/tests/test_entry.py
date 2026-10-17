"""The thin Worker's routes in CPython: a sqlite D1 (the real migrations), a dict R2, a fake Ollama upstream."""

import asyncio
import json
import sqlite3
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "src"))

import entry  # noqa: E402

SECRET = "test-secret-0123456789"


class Stmt:
    def __init__(self, db, sql):
        self.db, self.sql, self.args = db, sql, ()

    def bind(self, *args):
        self.args = args
        return self

    def _exec(self):
        cur = self.db.conn.execute(self.sql, self.args)
        rows = [dict(r) for r in cur.fetchall()] if cur.description else []
        self.db.conn.commit()
        return {"results": rows, "meta": {"last_row_id": cur.lastrowid}}

    async def all(self):
        return self._exec()

    async def run(self):
        return self._exec()


class FakeD1:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.row_factory = sqlite3.Row
        for f in sorted((HERE.parent / "migrations").glob("*.sql")):
            self.conn.executescript(f.read_text())

    def prepare(self, sql):
        return Stmt(self, sql)

    async def batch(self, stmts):
        return [s._exec() for s in stmts]


class FakeR2(dict):
    async def put(self, key, value):
        self[key] = value

    async def get(self, key):
        return SimpleNamespace(body=self[key]) if key in self else None


class Upstream:
    def __init__(self, status=200, body=None):
        self.status, self.calls = status, []
        self.body = body or {"message": {"content": "DONE", "thinking": ""}, "eval_count": 42, "done_reason": "stop"}

    async def __call__(self, payload, key):
        self.calls.append((payload, key))
        text = json.dumps(self.body)

        async def read():
            return text
        return self.status, SimpleNamespace(text=read, body="<stream>")


def make(now=1_800_000_000.0, upstream=None, **env):
    e = SimpleNamespace(DB=FakeD1(), RUNS=FakeR2(), GAME_TOKEN_SECRET=SECRET, OLLAMA_API_KEY3="k3",
                        ARENA_EXPORT_TOKEN="export-token-0123456789", **env)
    api = entry.Api(e, now=lambda: api.t)
    api.t = now
    api.upstream = upstream or Upstream()
    return api


def call(api, method, path, body=None, headers=None, ip="1.2.3.4"):
    text = body if isinstance(body, str) else json.dumps(body) if body is not None else ""
    h = {k.lower(): v for k, v in (headers or {}).items()}

    async def read_text():
        return text

    async def read_body():
        return text.encode()

    async def go():
        try:
            return await api.route(method, "https://w.example" + path, h, read_text, read_body, len(text), ip)
        except entry.HttpError as err:
            return err.status, {}, {"detail": err.detail, "code": err.code}
    return asyncio.run(go())


def game(api, **settings):
    s = {"fill": "models", "humans": 1, "model": "gemma4:31b", "seed": 7, **settings}
    st, _, out = call(api, "POST", "/api/games", {"code": "ABC234", "settings": s, "engine": {"bundle": "x"}})
    assert st == 200, out
    return out


def chat(api, tok, user="R1 opening", **kw):
    body = {"model": "gemma4:31b", "messages": [{"role": "system", "content": "s"}, {"role": "user", "content": user}],
            "stream": False, "options": {"temperature": 1.0, "num_predict": 512}, **kw}
    return call(api, "POST", "/llm/api/chat", body, {"Authorization": f"Bearer {tok}"})


def test_models_and_health():
    api = make()
    st, _, m = call(api, "GET", "/api/models")
    assert st == 200 and m["model"] == "gemma4:31b" and m["available"] and m["engine"] == "browser"
    assert m["limits"]["GAME_CALLS"] == 600
    assert call(api, "GET", "/api/health")[0] == 200
    assert call(api, "POST", "/api/rooms", {})[0] == 410 and call(api, "POST", "/api/signal/view", {})[0] == 410


def test_game_token_and_one_relayed_call_with_key3():
    api = make()
    g = game(api)
    st, hdr, text = chat(api, g["token"])
    assert st == 200 and json.loads(text)["eval_count"] == 42
    payload, key = api.upstream.calls[0]
    assert key == "k3" and payload["model"] == "gemma4:31b" and "think" not in payload
    row = api.env.DB.conn.execute("SELECT * FROM llm_calls").fetchone()
    assert row["prompt_h"] == entry.digest("R1 opening") and row["eval_count"] == 42 and row["status"] == 200
    assert api.env.DB.conn.execute("SELECT calls FROM games").fetchone()[0] == 1


def test_bad_forged_and_expired_tokens():
    api = make()
    g = game(api)
    assert chat(api, "nope")[0] == 401
    forged = entry.sign("another-secret-0123456789", {"g": g["game"], "m": "gemma4:31b", "k": "OLLAMA_API_KEY3",
                                                      "exp": api.t + 100})
    assert chat(api, forged)[0] == 401
    api.t += 6 * 3600 + 1
    st, _, out = chat(api, g["token"])
    assert st == 401 and out["code"] == "token_expired"
    assert not api.upstream.calls


def test_model_allow_list_and_game_model_only():
    api = make()
    st, _, out = call(api, "POST", "/api/games", {"settings": {"fill": "models", "model": "llama9:400b"}})
    assert st == 400 and out["code"] == "model"
    g = game(api)
    body = {"model": "gpt-oss:20b", "messages": [{"role": "user", "content": "x"}], "options": {"num_predict": 5}}
    assert call(api, "POST", "/llm/api/chat", body, {"Authorization": f"Bearer {g['token']}"})[0] == 403
    assert chat(api, g["token"], options={"num_predict": 0})[0] == 400
    assert chat(api, g["token"], options={"num_predict": 5_000_000})[0] == 200  # a TALK's cap is the balance: clamped
    assert api.upstream.calls[-1][0]["options"]["num_predict"] == entry.LIMITS["MAX_PREDICT"]


def test_per_game_and_per_ip_limits():
    api = make(LIMIT_GAME_CALLS="3", LIMIT_IP_CALLS_HOUR="5")
    g1, g2 = game(api), game(api)
    assert [chat(api, g1["token"])[0] for _ in range(4)] == [200, 200, 200, 429]
    st, _, out = chat(api, g1["token"])
    assert out["code"] == "limit_game"
    st, _, out = chat(api, g2["token"])  # every attempt counts toward the IP's hour: 3 + 2 refused = 5 already
    assert st == 429 and out["code"] == "limit_ip"
    assert len(api.upstream.calls) == 3
    api.t += 3600  # the next hour
    assert chat(api, g2["token"])[0] == 200


def test_games_per_ip_per_hour():
    api = make(LIMIT_IP_GAMES_HOUR="2")
    game(api)
    game(api)
    st, _, out = call(api, "POST", "/api/games", {"settings": {"fill": "bots"}})
    assert st == 429 and out["code"] == "limit_ip_games"
    assert call(api, "POST", "/api/games", {"settings": {"fill": "bots"}}, ip="5.6.7.8")[0] == 200


def test_key1_only_while_switched_on_never_a_fallback():
    api = make(OLLAMA_API_KEY1="k1")
    st, _, out = call(api, "POST", "/api/games", {"settings": {"fill": "models", "api_key_env": "OLLAMA_API_KEY1"}})
    assert st == 400 and out["code"] == "key"
    api.env.OLLAMA_KEY1_ENABLED = "on"
    g = game(api, api_key_env="OLLAMA_API_KEY1")
    assert chat(api, g["token"])[0] == 200 and api.upstream.calls[-1][1] == "k1"
    api.env.OLLAMA_KEY1_ENABLED = "off"  # switched off mid-game: the next call fails, it does not move to key 3
    assert chat(api, g["token"])[0] == 403 and len(api.upstream.calls) == 1
    k3 = make(OLLAMA_API_KEY1="k1", OLLAMA_KEY1_ENABLED="on")
    g3 = game(k3)
    del k3.env.OLLAMA_API_KEY3  # key 3 gone: refused, key 1 never used in its place
    assert chat(k3, g3["token"])[0] == 403 and not k3.upstream.calls


@pytest.mark.parametrize("status,code,final", [(402, "upstream_quota", 402), (429, "upstream_429", 429),
                                               (500, "upstream", 502)])
def test_upstream_errors_in_korean(status, code, final):
    api = make(upstream=Upstream(status=status))
    g = game(api)
    st, _, out = chat(api, g["token"])
    assert st == final and out["code"] == code and any("가" <= ch <= "힣" for ch in out["detail"])
    assert api.env.DB.conn.execute("SELECT status FROM llm_calls").fetchone()[0] == status


def test_record_upload_and_admin_export():
    api = make()
    g = game(api, fill="bots")
    summ = json.dumps({"status": "finished", "rounds": 8, "events": 258, "digest": "d" * 64})
    st, _, out = call(api, "POST", f"/api/games/{g['game']}/record", "GZIPBYTES",
                      {"Authorization": f"Bearer {g['token']}", "X-Squid5-Summary": summ})
    assert st == 200 and out["uploads"] == 1
    assert api.env.RUNS[f"arena/games/{g['game']}/record.json.gz"] == b"GZIPBYTES"
    other = game(api, fill="bots")
    assert call(api, "POST", f"/api/games/{g['game']}/record", "x", {"Authorization": f"Bearer {other['token']}"})[0] == 403
    assert call(api, "GET", "/api/games")[0] == 401
    adm = {"Authorization": "Bearer export-token-0123456789"}
    st, _, rows = call(api, "GET", "/api/games", headers=adm)
    assert st == 200 and [r["id"] for r in rows] == [g["game"]] and rows[0]["rounds"] == 8
    st, hdr, body = call(api, "GET", f"/api/games/{g['game']}/record", headers=adm)
    assert st == 200 and body == b"GZIPBYTES" and hdr["content-type"] == "application/gzip"
    assert call(api, "GET", f"/api/games/{g['game']}/calls", headers=adm)[0] == 200


def test_probe_round_trip():
    api = make()
    assert call(api, "POST", "/api/probe", {"self": [1, 2, 3, 4, 5], "other": [5, 4, 3, 2, 1]})[0] == 200
    st, _, s = call(api, "GET", "/api/probe/summary")
    assert st == 200 and s["n"] == 1 and s["self"][0] == pytest.approx(0.01)
    assert call(api, "POST", "/api/probe", {"self": [1], "other": []})[0] == 400


def test_worker_imports_no_engine():
    src = (HERE.parent / "src" / "entry.py").read_text()
    assert "squid5" not in src.split('"""', 2)[2].replace("squid5-", "") or "import squid5" not in src
    assert "import squid5" not in src and "web.server" not in src
    assert sorted(p.name for p in (HERE.parent / "src").glob("*.py")) == ["entry.py", "keys.py"]
