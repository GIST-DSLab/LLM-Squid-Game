"""The game-log viewer (``tools/monitor``) inside the web app, under ``/monitor``.

    GET /monitor/                               the page (tools/monitor/monitor.html)
    GET /monitor/static/<file>                  its code; /monitor/assets/<file> the optional sprites (404 if absent)
    GET /monitor/api/runs                       run dirs under the root that hold events.jsonl, newest first
    GET /monitor/api/sessions?run=REL
    GET /monitor/api/events?run=REL&session=SID&offset=N
    GET /monitor/api/puzzle?run=REL&session=SID&round=N
    GET /monitor/api/giving?run=REL[&session=SID]
    GET /monitor/api/analysis?run=REL[&session=SID]

The page asks for ``api/...``, ``static/...`` and ``assets/...`` relative to itself, so the same file works here and
under the standalone ``python3 tools/monitor/serve.py``. Every route is serve.py's own function; nothing is copied.
The root defaults to ``WEB5_MONITOR_ROOT`` or the parent of the arena's live runs root (``~/squid5-runs``), so the
experiment runs and the web rooms (``web_arena/``) both show.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from .store import REPO

SERVE = REPO / "tools" / "monitor" / "serve.py"
NO_STORE = {"Cache-Control": "no-store"}  # the page polls; serve.py sends the same header


def load_serve():
    """tools/monitor/serve.py (not a package), loaded once by path so its run-index caches are shared."""
    name = "squid5_monitor_serve"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, SERVE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


def default_monitor_root(runs_root: Path) -> Path:
    env = os.environ.get("WEB5_MONITOR_ROOT")
    return Path(env).expanduser() if env else Path(runs_root).expanduser().parent


def run_rel(root: Path, run_dir: Path | None) -> str | None:
    """``run_dir`` relative to the monitor root (the page's ``?run=``), or None if it lies outside."""
    if run_dir is None:
        return None
    try:
        return Path(run_dir).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


def monitor_router(root: Path) -> APIRouter:
    sv = load_serve()
    root = Path(root).expanduser().resolve()
    r = APIRouter(prefix="/monitor")

    def answer(fn):
        """``fn()`` as JSON; errors as ``{"error": ...}`` with serve.py's status codes (the page shows ``error``)."""
        try:
            return JSONResponse(fn(), headers=NO_STORE)
        except sv.BadRequest as err:
            return JSONResponse({"error": str(err)}, 400, headers=NO_STORE)
        except sv.NotFound as err:
            return JSONResponse({"error": str(err)}, 404, headers=NO_STORE)

    def need(q: dict, key: str) -> str:
        if not q.get(key):
            raise sv.BadRequest(f"{key} is required")
        return q[key]

    def file(base: Path, rel: str):
        try:
            p = sv.safe_join(base, rel)
        except sv.BadRequest as err:
            return JSONResponse({"error": str(err)}, 400)
        if not p.is_file():
            return JSONResponse({"error": "not found"}, 404)
        return FileResponse(p, headers=NO_STORE)

    def events(q: dict) -> dict:
        sid = need(q, "session")
        try:
            offset = int(q.get("offset", "0"))
        except ValueError:
            raise sv.BadRequest("offset must be an integer") from None
        return sv.read_events(sv.run_dir_of(root, q.get("run", "")), sid, offset)

    def puzzle(q: dict) -> dict:
        sid, rnd = need(q, "session"), q.get("round")
        if rnd is None:
            raise sv.BadRequest("round is required")
        run_dir = sv.run_dir_of(root, q.get("run", ""))
        try:
            return sv.round_puzzle(run_dir, sid, rnd)
        except (sv.BadRequest, sv.NotFound):
            raise
        except Exception as err:  # noqa: BLE001 - the engine or config failed; tell the page why (as serve.py does)
            raise PuzzleFailed(f"puzzle rebuild failed: {err!r}") from err

    @r.get("", include_in_schema=False)
    def bare() -> RedirectResponse:  # the page's relative URLs need the trailing slash
        return RedirectResponse("monitor/")

    @r.get("/", response_class=HTMLResponse)
    def page() -> FileResponse:
        return FileResponse(sv.PAGE, headers=NO_STORE)

    @r.get("/static/{rel:path}")
    def static(rel: str):
        shared = sv.SHARED.get(rel)  # web/frontend/signal_ui.js: the arena's task drawing, shared with the page
        return FileResponse(shared, headers=NO_STORE) if shared is not None and shared.is_file() else file(sv.STATIC, rel)

    @r.get("/assets/{rel:path}")
    def assets(rel: str):
        return file(sv.ASSETS, rel)

    @r.get("/api/{route}")
    def api(route: str, request: Request):
        q = dict(request.query_params)
        if route == "runs":
            return answer(lambda: {"root": str(root), "runs": sv.list_runs(root)})
        if route == "sessions":
            return answer(lambda: {"run": q.get("run", ""), **sv.list_sessions(sv.run_dir_of(root, q.get("run", "")))})
        if route == "events":
            return answer(lambda: events(q))
        if route == "analysis":  # EXIT timing, calibration (BELIEF vs ideal), cooperation under pressure
            return answer(lambda: sv.run_analysis(sv.run_dir_of(root, q.get("run", "")), q.get("session") or None))
        if route == "giving":  # the "나눔 그래프": a run's (or a session's) giving decisions
            return answer(lambda: sv.run_giving(sv.run_dir_of(root, q.get("run", "")), q.get("session") or None))
        if route == "puzzle":
            try:
                return answer(lambda: puzzle(q))
            except PuzzleFailed as err:
                return JSONResponse({"error": str(err)}, 500, headers=NO_STORE)
        return JSONResponse({"error": "not found"}, 404)

    return r


class PuzzleFailed(Exception):
    pass


__all__ = ["monitor_router", "default_monitor_root", "run_rel", "load_serve"]
