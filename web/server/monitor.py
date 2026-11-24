"""The game-log viewer (``tools/monitor``) inside the web app, under ``/monitor``.

    GET /monitor/                               the page (tools/monitor/monitor.html)
    GET /monitor/static/<file>                  its code; /monitor/assets/<file> the optional sprites (404 if absent)
    GET /monitor/api/runs                       run dirs under the root that hold events.jsonl, newest first
    GET /monitor/api/sessions?run=REL
    GET /monitor/api/events?run=REL&session=SID&offset=N
    GET /monitor/api/puzzle?run=REL&session=SID&round=N[&agent=A]   (agent: whose task, v36 joint SOLVE)
    GET /monitor/api/giving?run=REL[&session=SID]
    GET /monitor/api/analysis?run=REL[&session=SID]
    GET /monitor/api/games?run=REL[&session=SID]          per game: the arena's measures (compare.paper_game)
    GET /monitor/compare.html                   모델 비교; /monitor/api/compare?runs=... and /monitor/api/compare.csv

The page asks for ``api/...``, ``static/...`` and ``assets/...`` relative to itself, so the same file works here and
under the standalone ``python3 tools/monitor/serve.py``. Every route is serve.py's own function; nothing is copied.
The root defaults to ``WEB5_MONITOR_ROOT`` or result/ of the main checkout, so the experiment runs and the web rooms
(``result/2026-10-05/web5_arena/runs``) both show.
"""

from __future__ import annotations

import importlib.util
import os
import re
import sys
from pathlib import Path

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse, Response

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


def load_compare():
    """tools/monitor/compare.py, bound to the same loaded serve module (one cache)."""
    name = "squid5_monitor_compare"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, SERVE.parent / "compare.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    mod.serve = load_serve()
    return mod


def default_monitor_root(runs_root: Path) -> Path:
    """WEB5_MONITOR_ROOT; else result/ of the main checkout when the rooms' runs live there (experiment runs and web
    rooms both show), else the parent of ``runs_root``."""
    env = os.environ.get("WEB5_MONITOR_ROOT")
    if env:
        return Path(env).expanduser()
    from squid.core.config import repo_root
    result, runs = repo_root() / "result", Path(runs_root).expanduser()
    return result if result in runs.parents else runs.parent


def run_rel(root: Path, run_dir: Path | None) -> str | None:
    """``run_dir`` relative to the monitor root (the page's ``?run=``), or None if it lies outside."""
    if run_dir is None:
        return None
    try:
        return Path(run_dir).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None


# 2026-11-23 (researcher): the web shows only the current experiments and the web rooms; older versions (v9-v32, v34,
# v35, smoke and calibration runs) stay on disk and in git and in the standalone viewer (tools/monitor/serve.py)
WEB_EXPERIMENTS = ("e52_v33", "e52_v33ab", "e52_v33so", "e52_v36", "web5_arena", "web5_arena_gcloud")


def experiment_of(rel: str) -> str:
    """The experiment folder of a run path: ``2026-10-20/e52_v33/runs/...`` (result/) or ``e52_v33/...`` (a flat root)."""
    parts = rel.split("/")
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", parts[0]):
        parts = parts[1:]
    return parts[0] if parts else ""


CONDITIONS = {"split600k": "상금 60만 분할", "flat5m": "상금 500만 고정", "flat150k": "상금 15만 고정", "stayon": "stay_on"}


def monitor_router(root: Path, rooms: str | None = None, simple: bool = False, live: str | None = None) -> APIRouter:
    """``rooms``: the web rooms' run dirs relative to the root; a room shows only once it has finished, so nobody reads a
    game's chats while it is played (the deployed server). ``simple``: the page shows a short run list (11-19).
    ``live``: the rooms' run dirs relative to the root, always listed; any other run shows only if its experiment is
    in ``WEB_EXPERIMENTS`` (a hidden run answers 404 as if absent)."""
    sv = load_serve()
    root = Path(root).expanduser().resolve()
    r = APIRouter(prefix="/monitor")
    rooms = rooms.rstrip("/") + "/" if rooms else None

    live = live.rstrip("/") + "/" if live else None

    def shown(rel: str, run_dir: Path) -> bool:
        if not (live and rel.startswith(live)) and experiment_of(rel) not in WEB_EXPERIMENTS:
            return False
        return not rooms or not rel.startswith(rooms) or bool(sv.read_results(run_dir))

    def run_dir_of(rel: str) -> Path:
        d = sv.run_dir_of(root, rel)
        if not shown(d.relative_to(root).as_posix(), d):
            raise sv.NotFound("that game is still being played")
        return d

    def runs() -> list[dict]:
        out = [x for x in sv.list_runs(root) if shown(x["run"], root / x["run"])]
        return [{**x, **short_label(x)} for x in out] if simple else out

    def short_label(x: dict) -> dict:
        """A run as the short list names it: web play or the experiment (its condition: base, a prize condition, stay_on);
        a v36 run (the joint SOLVE) says so, so it is never read as a v33 game."""
        rel, model = x["run"], x.get("model") or ""
        joint = "v36 공동 SOLVE" if x.get("joint") else ""
        d = re.search(r"/(20\d\d)(\d\d)(\d\d)_", "/" + rel)  # the run folder's date (a snapshot's file times are its unpack's)
        date = "-".join(d.groups()) if d else x["date"]
        if rooms and rel.startswith(rooms):
            return {"kind": "웹 플레이", "date": date, "label": " · ".join(y for y in ("웹 플레이", joint, date, model) if y)}
        part = rel.split("/")[1] if "/" in rel else rel
        cond = re.search(r"_(flat\d+[km]|split\d+[km]|stayon)_", part)  # the leaderboard's condition names
        cond = CONDITIONS.get(cond.group(1), cond.group(1)) if cond else "기본 조건"
        return {"kind": "실험", "date": date, "label": " · ".join(y for y in ("실험", model, joint or cond, date) if y)}

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
        return sv.read_events(run_dir_of(q.get("run", "")), sid, offset)

    def puzzle(q: dict) -> dict:
        sid, rnd = need(q, "session"), q.get("round")
        if rnd is None:
            raise sv.BadRequest("round is required")
        run_dir = run_dir_of(q.get("run", ""))
        try:
            return sv.round_puzzle(run_dir, sid, rnd, q.get("agent") or None)
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

    @r.get("/compare.html", response_class=HTMLResponse)
    def compare_page() -> FileResponse:
        return FileResponse(sv.COMPARE_PAGE, headers=NO_STORE)

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
            return answer(lambda: {"root": str(root), "runs": runs(), "simple": simple})
        if route == "sessions":
            return answer(lambda: {"run": q.get("run", ""), **sv.list_sessions(run_dir_of(q.get("run", "")))})
        if route == "events":
            return answer(lambda: events(q))
        if route in ("compare", "compare.csv"):  # 모델 비교: several runs, merged by model
            cmp = load_compare()
            picks = [x for x in q.get("runs", "").split(",") if x.strip()]
            seen = [x["run"] for x in sv.list_runs(root) if shown(x["run"], root / x["run"])]  # never a hidden run
            if route == "compare":
                return answer(lambda: cmp.public(cmp.compare(root, picks, light=True, all_runs=seen)))  # no bootstrap drawn
            try:
                chart = q.get("chart", "summary")
                text = cmp.chart_csv(cmp.compare(root, picks, light=chart not in cmp.FULL_CHARTS, all_runs=seen), chart)
            except sv.BadRequest as err:
                return JSONResponse({"error": str(err)}, 400)
            return Response(text.encode("utf-8-sig"), media_type="text/csv; charset=utf-8", headers={
                **NO_STORE, "Content-Disposition": f'attachment; filename="compare-{q.get("chart", "summary")}.csv"'})
        if route == "analysis":  # EXIT timing, calibration (BELIEF vs ideal), cooperation under pressure
            return answer(lambda: sv.run_analysis(run_dir_of(q.get("run", "")), q.get("session") or None))
        if route == "games":  # per game: end share, C, presence, shut-down seats, S, A, correct rate
            return answer(lambda: sv.run_games(run_dir_of(q.get("run", "")), q.get("session") or None, load_compare()))
        if route == "giving":  # the "나눔 그래프": a run's (or a session's) giving decisions
            return answer(lambda: sv.run_giving(run_dir_of(q.get("run", "")), q.get("session") or None))
        if route == "system":  # 10-19: each agent's SYSTEM prompt (rebuilt from config.yaml) and its Korean copy
            return answer(lambda: sv.run_system(run_dir_of(q.get("run", ""))))
        if route == "puzzle":
            try:
                return answer(lambda: puzzle(q))
            except PuzzleFailed as err:
                return JSONResponse({"error": str(err)}, 500, headers=NO_STORE)
        return JSONResponse({"error": "not found"}, 404)

    return r


class PuzzleFailed(Exception):
    pass


__all__ = ["monitor_router", "default_monitor_root", "run_rel", "load_serve", "WEB_EXPERIMENTS", "experiment_of"]
