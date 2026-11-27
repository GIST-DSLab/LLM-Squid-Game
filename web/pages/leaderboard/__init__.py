"""The leaderboard (leaderboard.html): the paper's Table 1 per model over the run dirs (tools/monitor/compare.py) and
the people tab (humans.py: the arena rooms with a person in them)."""

from __future__ import annotations

import os
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query

from web.server.game import GAME_LIST, VERSIONS
from web.server.runs import load_compare
from web.server.site import Site, serve_static

from .humans import humans_board


def mount(app: FastAPI, site: Site) -> None:
    runs, mon_root = site.runs_root, site.monitor_root

    @app.get("/api/leaderboard")
    def leaderboard(runs: str = Query("e52_v33/"), csv: bool = Query(False)):
        """The paper's Table 1 per model over the run dirs under the monitor root, ranked by C (tools/monitor/compare.py
        ``leaderboard``; the earlier end-token columns stay in the rows and the CSV)."""
        cmp = load_compare()
        picks = [x for x in runs.split(",") if x.strip()]
        try:
            data = cmp.leaderboard(mon_root, picks)
        except Exception as err:  # noqa: BLE001 - a run being written must not break the page
            raise HTTPException(500, f"leaderboard: {err!r}") from err
        if csv:
            from fastapi.responses import Response
            return Response(cmp.chart_csv(data, "leaderboard").encode("utf-8-sig"), media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": 'attachment; filename="leaderboard.csv"'})
        return data

    @app.get("/api/leaderboard/v33")
    def leaderboard_v33() -> dict:
        """Every v33 condition (base, the three prize conditions, stay_on) with the paper's Table 1 columns, and the
        simulated rule agents (tools/monitor/compare.py ``v33_board``): the leaderboard page shows all of it."""
        try:
            return load_compare().v33_board(mon_root)
        except Exception as err:  # noqa: BLE001
            raise HTTPException(500, f"leaderboard: {err!r}") from err

    @app.get("/api/leaderboard/humans")
    def leaderboard_humans() -> dict:
        """The people tab: every finished arena room with a person in it, one row per game, tagged with its arena game
        (v33 ... v42; the page filters by game), best presence first within a game (humans.py)."""
        try:
            return humans_board(runs, load_compare(), VERSIONS, {g["version"]: g["ko"] for g in GAME_LIST.values()})
        except Exception as err:  # noqa: BLE001
            raise HTTPException(500, f"leaderboard: {err!r}") from err

    if os.environ.get("WEB5_WARM"):  # the deployed image: compute the v33 board once at start, so no visitor waits for it
        threading.Thread(target=lambda: load_compare().v33_board(mon_root), daemon=True, name="v33-board-warm").start()

    serve_static(app, Path(__file__).parent / "static")
