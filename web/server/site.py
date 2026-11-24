"""What a page folder (web/pages/<page>) gets from the app, and the one way a page serves its files.

Every page has ``mount(app, site)``: it adds its API routes, then ``serve_static(app, <its static dir>)`` puts its files at
the site root next to the shared ones (web/shared), as GitHub Pages lays them out too.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from .store import Store


@dataclass
class Site:
    store: Store
    runs_root: Path  # the arena rooms' live run dirs
    monitor_root: Path  # what the game-log viewer and the leaderboard read
    export_root: Path  # where a room's export goes
    client_settings: bool = False  # tests only: a client may set the server's own room settings (seed, clocks)
    public: bool = False  # the deployed server (WEB5_PUBLIC=1): pages show less (the arena's own switches: engine.py)


def serve_static(app: FastAPI, static: Path) -> None:
    """Every file under ``static`` at the site root (GET and HEAD: a link to a missing page hides, web/shared/site-lang.js);
    ``index.html`` also at ``/``."""
    def serve(path: Path):
        return lambda: FileResponse(path)

    for p in sorted(static.rglob("*")):
        if p.is_file():
            rel = p.relative_to(static).as_posix()
            for url in ("/" + rel, "/") if rel == "index.html" else ("/" + rel,):
                app.add_api_route(url, serve(p), methods=["GET", "HEAD"], include_in_schema=False)
