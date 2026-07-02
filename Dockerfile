# LLM Squid Game — Web Arena backend image.
#
# Serves `interface/api.py` (FastAPI) via uvicorn. Built for Render (see
# render.yaml) but intentionally platform-agnostic — it also runs unmodified
# on Fly.io, HF Spaces (Docker SDK), or any container host that injects a
# $PORT env var and (optionally) WEB_ARENA_DSN / WEB_ARENA_CORS_ORIGINS.
#
# No secrets are baked in: WEB_ARENA_DSN and WEB_ARENA_CORS_ORIGINS are read
# from the environment at runtime (see interface/api.py, interface/persistence).
#
# See web/DEPLOY.md for the full deploy walkthrough.

FROM python:3.12-slim

# uv: install via the official static-binary image (no pip bootstrap needed).
COPY --from=ghcr.io/astral-sh/uv:0.5.11 /uv /uvx /usr/local/bin/

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONUNBUFFERED=1

# Install dependencies first (layer caching): only pyproject.toml + uv.lock
# need to be present for this step, so app-code edits don't bust the cache.
# --extra postgres pulls in psycopg[binary] for the production DB backend
# (interface/persistence/postgres_repository.py); local dev/tests use the
# SQLite fallback and don't need it.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project --extra postgres --no-dev

# Now copy the actual source and install the project itself.
COPY src ./src
COPY interface ./interface
RUN uv sync --frozen --extra postgres --no-dev

# Render (and most PaaS hosts) inject $PORT at runtime; default to 8502 for
# local `docker run` parity with the non-Docker dev workflow.
ENV PORT=8502
EXPOSE 8502

# Shell form so ${PORT} expands; Render always sets PORT, so this only
# matters for local `docker run` without -e PORT=...
CMD uv run --no-sync uvicorn interface.api:app --host 0.0.0.0 --port ${PORT:-8502}
