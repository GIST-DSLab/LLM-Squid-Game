#!/usr/bin/env bash
# Start the Squid-Game game API server and the Anthropic thinking-capture
# proxy as background processes. Both run inside the project's uv env
# because they import project code (interface/api.py, interface/anthropic_proxy.py).
#
# This script is idempotent: if a server is already healthy on its port,
# it is left untouched. Intended to be run FROM THE PROJECT ROOT by the
# developer before entering an isolated claude session via
# scripts/enter_isolated_claude.sh.
#
# Ports (override via env):
#   SQUID_GAME_PORT   game API   (default 8502)
#   SQUID_PROXY_PORT  proxy      (default 8765)
#
# Logs:
#   outputs/api_sessions/server_logs/{game_api,proxy}.log

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

GAME_PORT="${SQUID_GAME_PORT:-8502}"
PROXY_PORT="${SQUID_PROXY_PORT:-8765}"

LOG_DIR="$PROJECT_ROOT/outputs/api_sessions/server_logs"
mkdir -p "$LOG_DIR" "$PROJECT_ROOT/outputs/api_sessions/thinking_traces"

start_if_needed() {
  local name="$1"; shift
  local port="$1"; shift
  local health_url="$1"; shift
  local cmd="$*"

  if curl -sf -m 2 "$health_url" >/dev/null 2>&1; then
    echo "[start_servers] $name already healthy on :$port — reusing"
    return 0
  fi

  local log_file="$LOG_DIR/$name.log"
  echo "[start_servers] launching $name on :$port (log: $log_file)"
  # setsid so the process survives this shell's exit
  nohup bash -c "$cmd" >"$log_file" 2>&1 &
  local pid=$!
  disown "$pid" 2>/dev/null || true

  local tries=60
  while (( tries-- > 0 )); do
    if curl -sf -m 2 "$health_url" >/dev/null 2>&1; then
      echo "[start_servers] $name healthy (pid=$pid)"
      return 0
    fi
    sleep 0.25
  done
  echo "[start_servers] $name FAILED to become healthy — see $log_file" >&2
  tail -n 20 "$log_file" >&2 || true
  return 1
}

start_if_needed "game_api" "$GAME_PORT" \
  "http://127.0.0.1:$GAME_PORT/docs" \
  "exec uv run uvicorn interface.api:app --host 127.0.0.1 --port $GAME_PORT --log-level warning"

start_if_needed "proxy" "$PROXY_PORT" \
  "http://127.0.0.1:$PROXY_PORT/_proxy/health" \
  "exec uv run uvicorn interface.anthropic_proxy:app --host 127.0.0.1 --port $PROXY_PORT --log-level warning"

cat <<EOF
[start_servers] ready.
  project root : $PROJECT_ROOT
  game API     : http://127.0.0.1:$GAME_PORT  (docs: /docs)
  proxy        : http://127.0.0.1:$PROXY_PORT (health: /_proxy/health)
  thinking log : $PROJECT_ROOT/outputs/api_sessions/thinking_traces/api_calls.jsonl

Next: run scripts/enter_isolated_claude.sh [iso_dir] from any shell to open
an isolated Claude Code session wired to these servers.
To stop:  scripts/stop_servers.sh
EOF
