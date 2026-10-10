# squid5 web5 API. Build from the repo root:  docker build -f web/deploy/Dockerfile -t squid5-web5 .
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx pyyaml numpy matplotlib psycopg[binary]
# the arena runs the experiment engine itself (web/server/engine.py imports squid5 from the repo root = /app)
COPY squid5 /app/squid5
COPY web/server /app/web/server
COPY web/frontend /app/web/frontend
COPY web/__init__.py /app/web/__init__.py
# the game-log viewer and model comparison / leaderboard (mounted at /monitor/, /api/leaderboard) and a snapshot of
# finished runs for them to read (the container has no ~/squid5-runs)
COPY tools/monitor /app/tools/monitor
COPY web/data/runs /app/web/data/runs
ENV WEB5_MONITOR_ROOT=/app/web/data/runs
ENV PORT=8600
# WEB5_DSN / WEB5_CORS_ORIGINS come from the platform; without WEB5_DSN events go to a SQLite file on the container disk.
CMD ["sh", "-c", "python -m uvicorn web.server.app:app --host 0.0.0.0 --port ${PORT}"]
