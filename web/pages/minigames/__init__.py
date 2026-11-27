"""The mini games page (minigames.html): one card per game of the arena (a picture and a name); a card opens that game's
description (the pictures are web/shared/assets/games, which the arena's game picker shows too). Nothing is played here
and there is no API: the games themselves run in the arena's rooms
(web/server/game.py GAME_LIST, web/pages/arena)."""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI

from web.server.site import Site, serve_static


def mount(app: FastAPI, site: Site) -> None:
    serve_static(app, Path(__file__).parent / "static")
