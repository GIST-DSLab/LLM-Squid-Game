// CPU per request of the thin Worker's Python, measured under Pyodide (the Workers runtime runs the same wasm Python).
//
//   npm ci --prefix web/pyodide && node web/cloudflare/tests/bench_cpu.mjs [--n 200]
//
// Loads src/entry.py and src/keys.py into Pyodide (no `workers` package: entry.Api is runtime-independent), gives it a
// D1 / R2 / Ollama whose awaits resolve at once, and times Api.route for each route. What is measured is the Python
// work of a request (JSON, HMAC, hashing, SQL argument building); waiting on D1, R2 and Ollama is not CPU time on
// Workers and is zero here. Not measured: the runtime's own per-request overhead outside Python (JS <-> Python
// conversion of the Request / Response objects), so treat the numbers as the Python part of the 10 ms free-plan budget.
import { readFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const require = createRequire(join(here, "..", "..", "pyodide", "package.json"));
const { loadPyodide } = require("pyodide");
const n = Number((process.argv.indexOf("--n") > 0 && process.argv[process.argv.indexOf("--n") + 1]) || 200);

const py = await loadPyodide();
for (const f of ["entry.py", "keys.py"]) py.FS.writeFile(`/home/pyodide/${f}`, readFileSync(join(here, "..", "src", f), "utf8"));
const out = await py.runPythonAsync(`
import asyncio, json, sys, time
sys.path.insert(0, "/home/pyodide")
import entry

class Stmt:
    def __init__(self, sql): self.sql = sql
    def bind(self, *a): self.a = a; return self
    async def all(self): return {"results": [{"n": 1, "calls": 1, "uploads": 1}], "meta": {"last_row_id": 1}}
    async def run(self): return await self.all()

class D1:
    def prepare(self, sql): return Stmt(sql)
    async def batch(self, stmts): return [await s.all() for s in stmts]

class R2:
    async def put(self, k, v): pass

class Env:
    DB, RUNS = D1(), R2()
    GAME_TOKEN_SECRET = "bench-secret-0123456789"
    OLLAMA_API_KEY3 = "k3"
    ARENA_EXPORT_TOKEN = "x" * 20

class Resp:
    def __init__(self, text): self._t = text; self.body = None
    async def text(self): return self._t

ANSWER = json.dumps({"message": {"content": "SAY agent-11: hello\\nDONE", "thinking": ""}, "eval_count": 212,
                     "prompt_eval_count": 3000, "done_reason": "stop"})

def make():
    api = entry.Api(Env())
    async def upstream(payload, key): return 200, Resp(ANSWER)
    api.upstream = upstream
    return api

def chat_body(kb):
    sys_msg = "You are agent-6. " + "rules " * (kb * 60)
    msgs = [{"role": "system", "content": sys_msg}]
    for i in range(6):
        msgs.append({"role": "user" if i % 2 == 0 else "assistant", "content": "R1 TALK " + "x " * 400})
    return json.dumps({"model": "gemma4:31b", "messages": msgs, "stream": False,
                       "options": {"temperature": 1.0, "num_predict": 60000}})

async def bench(name, method, path, body="", headers=None, n=${n}):
    api = make()
    h = {k.lower(): v for k, v in (headers or {}).items()}
    async def rt(): return body
    async def rb(): return body.encode()
    ts = []
    for _ in range(n):
        t = time.perf_counter()
        try:
            await api.route(method, "https://w" + path, h, rt, rb, len(body), "1.2.3.4")
        except entry.HttpError as e:
            raise RuntimeError(f"{name}: {e.status} {e.detail}")
        ts.append((time.perf_counter() - t) * 1000)
    ts.sort()
    return {"route": name, "mean_ms": round(sum(ts) / len(ts), 3), "p95_ms": round(ts[int(0.95 * len(ts))], 3),
            "max_ms": round(ts[-1], 3), "body_kb": round(len(body) / 1024, 1)}

async def main():
    tok = entry.sign(Env.GAME_TOKEN_SECRET, {"g": "abc", "m": "gemma4:31b", "k": "OLLAMA_API_KEY3", "exp": time.time() + 3600})
    auth = {"Authorization": f"Bearer {tok}"}
    rows = [await bench("GET /api/models", "GET", "/api/models"),
            await bench("POST /api/games", "POST", "/api/games",
                        json.dumps({"code": "ABC234", "settings": {"fill": "models", "model": "gemma4:31b"}})),
            await bench("POST /llm/api/chat (8 KB)", "POST", "/llm/api/chat", chat_body(8), auth),
            await bench("POST /llm/api/chat (64 KB)", "POST", "/llm/api/chat", chat_body(64), auth),
            await bench("POST /api/games/{id}/record", "POST", "/api/games/abc/record", "x" * 30000,
                        {**auth, "X-Squid5-Summary": json.dumps({"status": "finished", "rounds": 8})}),
            await bench("POST /api/probe", "POST", "/api/probe", json.dumps({"self": [1, 2, 3, 4, 5], "other": [5, 4, 3, 2, 1]}))]
    return json.dumps(rows)

await main()
`);
for (const r of JSON.parse(out)) console.log(JSON.stringify(r));
