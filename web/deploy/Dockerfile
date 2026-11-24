# squid5 web5 API. Build from the repo root:  docker build -f web/deploy/Dockerfile -t squid5-web5 .
FROM python:3.12-slim
WORKDIR /app
RUN pip install --no-cache-dir fastapi "uvicorn[standard]" httpx pyyaml numpy matplotlib "psycopg[binary]" google-cloud-storage
# the researchers' experiment seats (WEB5_SEATS, behind WEB5_SEAT_CODE): Claude Code and Codex at the versions the
# experiment's CLI image pins (squid/docker/agent-cli.Dockerfile), node from the official image; the relay that drops the
# Claude CLI's own token note (the claude seats' base_url http://127.0.0.1:18781) runs beside the app
COPY --from=node:22-slim /usr/local/bin/node /usr/local/bin/node
COPY --from=node:22-slim /usr/local/lib/node_modules/npm /usr/local/lib/node_modules/npm
RUN ln -s ../lib/node_modules/npm/bin/npm-cli.js /usr/local/bin/npm \
 && npm install -g @anthropic-ai/claude-code@2.1.303 @openai/codex@0.162.1 && npm cache clean --force
COPY tools/relay.py /app/tools/relay.py
# the arena runs the experiment engine itself (web/server/engine.py imports squid from the repo root = /app)
COPY squid /app/squid
# web/server/signal.py reads the experiment configs (configs/squid5/e52v14*.yaml) at import time; without them the app
# does not start
COPY configs/squid5 /app/configs/squid5
COPY web/server /app/web/server
COPY web/frontend /app/web/frontend
COPY web/__init__.py /app/web/__init__.py
# the game-log viewer and model comparison / leaderboard (mounted at /monitor/, /api/leaderboard) and a snapshot of
# finished runs for them to read (the container has no checkout, so no result/)
COPY tools/monitor /app/tools/monitor
# 11-19 researcher: only the fixed v33 experiment (base, prize conditions, stay_on: the leaderboard's runs) and the games
# played here (web/, the rooms' run dirs on the VM disk, mounted by compose.yaml); no earlier version's runs
COPY web/data/runs/e52_v33 /app/monitor/e52_v33
COPY web/data/runs/e52_v33ab /app/monitor/e52_v33ab
COPY web/data/runs/e52_v33so /app/monitor/e52_v33so
# newer runs keep events.jsonl as events.jsonl.xz in git (web/tools/runs_snapshot.py); the viewer seeks in the plain file
COPY web/tools/runs_snapshot.py /app/web/tools/runs_snapshot.py
RUN python /app/web/tools/runs_snapshot.py unpack /app/monitor
ENV WEB5_MONITOR_ROOT=/app/monitor
# compute the leaderboard page's v33 board at start (web/server/app.py), so the first visitor does not wait for it
ENV WEB5_WARM=1
# rooms' live engine logs (outside the image there is no git checkout whose result/ they would default to)
ENV WEB5_RUNS_ROOT=/app/monitor/web
ENV PORT=8600
# the deployed server is public: model seats only from WEB5_MODELS, no client-chosen provider / address / key name
# (web/server/engine.py PUBLIC); the key itself (OLLAMA_API_KEY) comes from the platform's secret store
ENV WEB5_PUBLIC=1
ENV WEB5_MODELS=gpt-oss:120b
# WEB5_DSN / WEB5_CORS_ORIGINS come from the platform; without WEB5_DSN events go to a SQLite file on the container disk.
CMD ["sh", "-c", "python tools/relay.py 18781 & exec python -m uvicorn web.server.app:app --host 0.0.0.0 --port ${PORT}"]
