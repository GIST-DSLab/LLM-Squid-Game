"""The signal task alone (signal.html), for a person to practise one round of the model runs' game (task.py)."""

from __future__ import annotations

from pathlib import Path

from fastapi import Body, FastAPI, HTTPException

from web.server.site import Site, serve_static

from . import task as sig


def mount(app: FastAPI, site: Site) -> None:
    @app.get("/api/signal/meta")
    def signal_meta() -> dict:
        return sig.meta()

    def signal_call(fn, body: dict) -> dict:
        try:
            return fn(body)
        except sig.SignalError as e:
            raise HTTPException(400, str(e)) from e

    @app.post("/api/signal/view")
    def signal_view(body: dict = Body(...)) -> dict:
        return signal_call(sig.view, body)

    @app.post("/api/signal/solve")
    def signal_solve(body: dict = Body(...)) -> dict:
        return signal_call(sig.solve, body)

    serve_static(app, Path(__file__).parent / "static")
