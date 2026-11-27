"""HTTP API for the human-playable pages.  Run: ``uvicorn web.server.app:app --port 8600`` (from the repo root).

Rooms (part 2)
    POST /api/rooms                         {host_name, lang, settings{...}}      -> {code, token, agent}
                                            settings.plan = 4 x {who: me | human | model | bot | empty, ...}: who sits
                                            where (the maker in the "me" seat); settings.version = v33 (default) | v36
                                            (joint SOLVE: every seat answers its own task, see engine.py); seed, rate and the TALK / SOLVE time
                                            limits are the server's own (SERVER_SETTINGS: a client's values are ignored)
    POST /api/rooms/{code}/join             {name, lang}                          -> {token, agent}
    POST /api/rooms/{code}/start?token=     host only
    POST /api/rooms/{code}/lang?token=      {lang: en | ko}: what this person reads (the rulebook at once, the messages
                                            from the next call on; the engine's own text, Game.set_lang)
    GET  /api/rooms/{code}/state?token=     poll every ~1 s; ``pending`` is your open decision screen, if any
    POST /api/rooms/{code}/submit?token=    TALK (pending.kind "talk"): {kind, round, tick, phase, text} (the reply in the
                                            messenger grammar: TO / GIVE / GIVE ALL / ASK / LEAVE / EXIT: YES|NO / DONE);
                                            SOLVE: {kind: "solve", round, actions[], belief{action: %}}
                                            (v36: {kind: "solve", round, pass: true} = ACTIONS: PASS, no answer)
                                                                                  -> {charged, seconds, outcome, void}
    POST /api/rooms/{code}/watched?token=   {round}: this person is done watching the LLM solver's SOLVE
    POST /api/rooms/{code}/forfeit?token=   give up: EXIT: YES at the next TALK before SOLVE that allows it; else DONE
    POST /api/rooms/{code}/export           write a squid5 run dir under outputs/web5/runs/<code>/ -> {dir}
    GET  /api/rooms/{code}/events           the event log: in full once the game has ended; before that with no task,
                                            answers, seed, token amounts, chats, moves or anything an agent wrote
                                            (engine.public_events)
    Every started room also writes its engine events live to WEB5_RUNS_ROOT/<date>_<code>/ (default
    result/2026-10-05/web5_arena/runs of the main checkout), the run-dir layout tools/monitor/serve.py reads.
    A room plays the model runs' game, 5.2 v33 (squid/configs/e52v33_public_sol4.yaml; see engine.py): the system draws
    the solver, TALK BEFORE SOLVE (the messenger: ticks, rooms R1..., EXIT: YES|NO before SOLVE, never by the round's
    solver unless alone), SOLVE (solver only; people watch an LLM solver), RESULTS, TALK AFTER RESULTS (the task and both
    answers revealed), CHARGES (24,000 split among those taking part at the round's start). Only the reader's own tokens
    are shown, with the order of all; everything once the session has ended.
Models
    GET  /api/models                        default model seat (gpt-oss:20b on Ollama Cloud, think) and whether the server
                                            has its key (OLLAMA_API_KEY, from the environment or .env; never its value);
                                            settings.fill = "models" fills the seats no human takes with model seats
                                            (settings.kind + model, or settings.models = [{kind, model}, ...] per seat);
                                            "seats" lists the experiment seats (the model section of each
                                            squid/configs/e52v33_*.yaml run config) with why each cannot be called
                                            here ("" = ready); settings.seat = <name> (or models = [{seat}, ...]) plays
                                            those models called exactly as the runs called them
Pages that can come and go (web/pages/<page>)
    each folder adds its own routes and files through ``mount(app, store)``, e.g. the 5.1 probe (web/pages/probe:
    /probe.html, /api/probe); none is named here, so deleting a folder drops that page and nothing else
Game logs (tools/monitor inside this app; see server/monitor.py)
    GET  /monitor/                          the viewer page; its API is /monitor/api/{runs,sessions,events,puzzle}
                                            over WEB5_MONITOR_ROOT (default: result/ of the main checkout)
Leaderboard (leaderboard.html)
    GET  /api/leaderboard?runs=e52_v33/[&csv=1]   the paper's body table (CogSci 2027 KO Table 1) per model: coexistence
                                            retention C (the rank, closed and open-weight models apart), risk rounds
                                            passed, shut-down seats, talk cost, accuracy, exit rate, kept share R
    GET  /api/leaderboard/v33               the leaderboard page: every v33 condition in sections + the rule agents
    GET  /api/leaderboard/humans            the page's people tab: finished rooms with a person, one row per game by C
Config
    WEB5_CORS_ORIGINS (comma-separated; default localhost dev origins + GitHub Pages), WEB5_DSN (Postgres) or
    WEB5_DB_PATH (SQLite file), WEB5_EXPORT_ROOT (default outputs/web5/runs), WEB5_RUNS_ROOT (live run dirs),
    WEB5_MONITOR_ROOT (the game-log viewer's root).
"""

from __future__ import annotations

import importlib
import os
import time
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from .runs import default_monitor_root, default_runs_root
from .site import Site
from .store import REPO, Store

DEFAULT_CORS = ["http://localhost:5600", "http://127.0.0.1:5600", "http://localhost:8600", "http://127.0.0.1:8600",
                "https://gist-dslab.github.io"]
SHARED = Path(__file__).resolve().parents[1] / "shared"  # what every page loads (styles, site-lang.js, config.js, assets)
PAGES = Path(__file__).resolve().parents[1] / "pages"  # one folder per page: mount(app, site) + static/ + tests


def make_app(store: Store | None = None, export_root: Path | None = None, runs_root: Path | None = None,
             monitor_root: Path | None = None, client_settings: bool = False) -> FastAPI:
    """Every folder of web/pages adds its routes and files (none is named here, so deleting a folder drops that page and
    nothing else), then web/shared is served at the root. ``client_settings`` (tests only): a client may set the
    server's own room settings (a fixed seed, a fast clock)."""
    app = FastAPI(title="squid5 web5", version="0.1")
    origins = [o.strip() for o in os.environ.get("WEB5_CORS_ORIGINS", "").split(",") if o.strip()] or DEFAULT_CORS
    app.add_middleware(CORSMiddleware, allow_origins=origins, allow_methods=["*"], allow_headers=["*"])
    runs = runs_root or default_runs_root()
    site = Site(store=store or Store(), runs_root=runs,
                monitor_root=Path(monitor_root or default_monitor_root(runs)).expanduser(),
                export_root=export_root or Path(os.environ.get("WEB5_EXPORT_ROOT") or (REPO / "outputs" / "web5" / "runs")),
                client_settings=client_settings, public=os.environ.get("WEB5_PUBLIC", "").strip() == "1")
    app.state.store, app.state.site, app.state.rooms = site.store, site, {}

    @app.get("/api/health")
    def health() -> dict:
        return {"ok": True, "rooms": len(app.state.rooms), "time": time.time()}

    for page in sorted(PAGES.glob("*/__init__.py")):
        importlib.import_module(f"web.pages.{page.parent.name}").mount(app, site)

    if SHARED.is_dir():  # the same origin can serve the pages; a separate static server also works
        app.mount("/", StaticFiles(directory=str(SHARED), html=True), name="shared")
    return app


app = make_app()
__all__ = ["app", "make_app"]
