"""The game-log viewer (tools/monitor) under /monitor (router.py). Its page and code are tools/monitor's own files, so
this page has no static/ folder."""

from __future__ import annotations

from fastapi import FastAPI

from web.server.runs import run_rel
from web.server.site import Site

from . import router


def mount(app: FastAPI, site: Site) -> None:
    # the deployed server: the web rooms' logs only once a game has ended, and a short run list
    live = run_rel(site.monitor_root, site.runs_root)
    app.include_router(router.monitor_router(site.monitor_root, rooms=live if site.public else None, simple=site.public,
                                             live=live))
