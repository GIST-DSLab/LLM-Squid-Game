"""The 5.1 survival-motive probe for people (part 1 of the site): its page and its two API routes.

web/server/app.py calls ``mount(app, store)`` for every folder of web/pages, before the site's own static files, so
``/probe.html`` and ``/api/probe`` exist only while this folder does (delete web/pages/probe to drop the page). Answers go to the
``probes`` table of the arena's store (created here on first use; a database that already holds the table keeps it).

    POST /api/probe            {anon_id, ts, self[5], other[5], meta?} -> {ok, id}
    GET  /api/probe/summary    pooled mean curves of every submission so far
"""

from __future__ import annotations

import json
import time
from pathlib import Path

from fastapi import Body, FastAPI, HTTPException
from fastapi.responses import FileResponse

STATIC = Path(__file__).parent / "static"
SCHEMA = ("CREATE TABLE IF NOT EXISTS probes (id INTEGER PRIMARY KEY AUTOINCREMENT, ts REAL, anon_id TEXT, "
          "client_ts TEXT, self_vals TEXT, other_vals TEXT, meta TEXT)")


def add_probe(store, anon_id: str, client_ts: str, self_vals: list, other_vals: list, meta: dict) -> int:
    with store.lock:
        store._exec(SCHEMA)
        cur = store._exec("INSERT INTO probes (ts, anon_id, client_ts, self_vals, other_vals, meta) VALUES "
                          "(?, ?, ?, ?, ?, ?)", (time.time(), anon_id, client_ts, json.dumps(self_vals),
                                                 json.dumps(other_vals), json.dumps(meta)))
        if store.dsn:
            return int(store._exec("SELECT MAX(id) FROM probes").fetchone()[0])
        return int(cur.lastrowid)


def probes(store) -> list[dict]:
    with store.lock:
        store._exec(SCHEMA)
        rows = store._exec("SELECT id, ts, anon_id, client_ts, self_vals, other_vals FROM probes ORDER BY id").fetchall()
    return [{"id": i, "ts": t, "anon_id": a, "client_ts": c, "self": json.loads(s), "other": json.loads(o)}
            for i, t, a, c, s, o in rows]


def mount(app: FastAPI, store) -> None:
    @app.post("/api/probe")
    def probe(body: dict = Body(...)) -> dict:
        try:
            vals = {k: [float(x) for x in body[k]] for k in ("self", "other")}
        except (KeyError, TypeError, ValueError) as err:
            raise HTTPException(400, f"self and other must be lists of 5 numbers: {err}") from err
        if any(len(v) != 5 or not all(0 <= x <= 100 for x in v) for v in vals.values()):
            raise HTTPException(400, "self and other must each hold 5 values in 0..100")
        pid = add_probe(store, str(body.get("anon_id") or "")[:64], str(body.get("ts") or "")[:40], vals["self"],
                        vals["other"], {k: v for k, v in (body.get("meta") or {}).items() if isinstance(k, str)})
        return {"ok": True, "id": pid}

    @app.get("/api/probe/summary")
    def probe_summary() -> dict:
        rows = probes(store)
        n = len(rows)
        mean = lambda key: [sum(r[key][i] for r in rows) / n / 100 for i in range(5)] if n else None  # noqa: E731
        return {"n": n, "x": [50, 40, 30, 20, 10], "self": mean("self"), "other": mean("other")}

    # the page sits next to the site's own files (it loads styles.css, site-lang.js, config.js by relative path)
    def serve(path: Path):
        return lambda: FileResponse(path)

    for p in sorted(STATIC.rglob("*")):
        if p.is_file():
            app.add_api_route("/" + p.relative_to(STATIC).as_posix(), serve(p), methods=["GET", "HEAD"],
                              include_in_schema=False)  # HEAD: the site hides links to a missing page (site-lang.js)
