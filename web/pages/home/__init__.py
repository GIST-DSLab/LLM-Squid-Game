"""The landing page (index.html, also at /) and its old About address (about.html, a redirect to index.html#about)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from web.server.site import Site, serve_static


def mount(app: FastAPI, site: Site) -> None:
    serve_static(app, Path(__file__).parent / "static")
