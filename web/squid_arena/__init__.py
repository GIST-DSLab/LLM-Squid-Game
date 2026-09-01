"""Web Arena backend -- the FastAPI service and the human-play session layer.

This is the web tier. It may import ``squid_game`` (the game engine) and
``squid_store`` (persistence); neither of those may import back into it.
The tier directory is ``web/`` but the import name is ``squid_arena``:
``web`` is taken on PyPI and would be a hazard as a top-level import name.

Served as ``squid_arena.api:app`` (see the repo-root Dockerfile and
web/DEPLOY.md).
"""
