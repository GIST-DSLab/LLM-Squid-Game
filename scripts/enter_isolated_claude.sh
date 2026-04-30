#!/usr/bin/env bash
# Open a Claude Code session whose CWD is an EMPTY isolated directory so
# the orchestrator skill and its subagents cannot read the Squid-Game
# project source via Read/Grep/Glob. The session still talks to the game
# API (http://127.0.0.1:8502) and the Anthropic proxy
# (http://127.0.0.1:8765) over localhost.
#
# Hard-isolation layers applied:
#
#   1. CWD is switched to an empty directory (default $HOME/sg-isolated)
#      before `exec claude`, so Read/Grep/Glob default globs have nothing
#      to walk.
#   2. A project-local .claude/settings.json is written inside that iso
#      dir with `permissions.deny` rules for the project's source trees
#      (src/, interface/, configs/, prompts/, docs/, scripts/, top-level
#      *.py/*.toml/*.lock). Claude Code merges this with the global
#      settings at ~/.claude/settings.json.
#   3. SQUID_PROJECT_ROOT is exported so the skill can reach outputs/
#      (which is NOT denied) via absolute path, and nothing else needs
#      to guess project location.
#   4. ANTHROPIC_BASE_URL + SQUID_PROXY_ACTIVE + SQUID_THINKING_LOG_DIR
#      are exported so the thinking proxy and the SubagentStop hook do
#      their work.
#
# Usage:
#
#   scripts/enter_isolated_claude.sh                   # default iso dir
#   scripts/enter_isolated_claude.sh ~/my-iso-sg       # custom iso dir
#   scripts/enter_isolated_claude.sh ~/my-iso-sg arg1  # extra claude args
#
# Before running, start the servers:
#
#   scripts/start_servers.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# --- resolve iso dir ---------------------------------------------------------

ISO_DIR_ARG="${1:-$HOME/sg-isolated}"
# pass through remaining args to claude
if [[ $# -ge 1 ]]; then shift; fi

# Expand ~
ISO_DIR="${ISO_DIR_ARG/#\~/$HOME}"
# Refuse to use anything inside PROJECT_ROOT as iso dir
if [[ "$ISO_DIR" == "$PROJECT_ROOT"* ]]; then
  echo "[enter_isolated_claude] ERROR: iso dir must be OUTSIDE the project" >&2
  echo "                      project : $PROJECT_ROOT" >&2
  echo "                      iso dir : $ISO_DIR" >&2
  exit 2
fi

mkdir -p "$ISO_DIR"
ISO_DIR="$(cd "$ISO_DIR" && pwd)"

# --- health check the servers ------------------------------------------------

GAME_API="${SQUID_GAME_API_URL:-http://127.0.0.1:8502}"
PROXY_URL="${SQUID_PROXY_URL:-http://127.0.0.1:8765}"
PROXY_HEALTH="$PROXY_URL/_proxy/health"

if ! curl -sf -m 2 "$GAME_API/docs" >/dev/null 2>&1; then
  echo "[enter_isolated_claude] ERROR: game API not reachable at $GAME_API" >&2
  echo "                      Run $SCRIPT_DIR/start_servers.sh first." >&2
  exit 1
fi
if ! curl -sf -m 2 "$PROXY_HEALTH" >/dev/null 2>&1; then
  echo "[enter_isolated_claude] ERROR: proxy not reachable at $PROXY_HEALTH" >&2
  echo "                      Run $SCRIPT_DIR/start_servers.sh first." >&2
  exit 1
fi

# --- write project-local settings with deny rules ----------------------------

mkdir -p "$ISO_DIR/.claude"
SETTINGS_FILE="$ISO_DIR/.claude/settings.json"

# Use python for safe JSON writing so special characters in PROJECT_ROOT
# (shouldn't be any, but defensive) don't break.
/usr/bin/env python3 - "$PROJECT_ROOT" "$SETTINGS_FILE" <<'PY'
import json
import sys
from pathlib import Path

project_root = sys.argv[1]
out = Path(sys.argv[2])

# Paths we want the isolated claude session to NOT read. outputs/ is
# intentionally omitted so the skill's QC agent can read season_results.jsonl
# and the proxy thinking log.
denied_subtrees = [
    "src",
    "interface",
    "configs",
    "prompts",
    "docs",
    "scripts",
    "archive",
    "tests",
]
deny = []
for sub in denied_subtrees:
    deny.append(f"Read({project_root}/{sub}/**)")
    deny.append(f"Grep(path:{project_root}/{sub})")
# Also deny top-level source / config files
for pat in ("*.py", "*.toml", "*.lock", "*.md"):
    deny.append(f"Read({project_root}/{pat})")

settings = {
    "permissions": {
        "deny": deny,
    },
}

out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps(settings, indent=2) + "\n", encoding="utf-8")
PY

# --- export env --------------------------------------------------------------

export ANTHROPIC_BASE_URL="$PROXY_URL"
export SQUID_PROXY_ACTIVE=1
export SQUID_PROXY_HEALTH_URL="$PROXY_HEALTH"
export SQUID_THINKING_LOG_DIR="$PROJECT_ROOT/outputs/api_sessions/thinking_traces"
export SQUID_GAME_API_URL="$GAME_API"
export SQUID_PROJECT_ROOT="$PROJECT_ROOT"

cat <<EOF
[enter_isolated_claude] isolation ready.
  iso dir           : $ISO_DIR
  project root      : $PROJECT_ROOT     (denied via settings.json)
  game API          : $GAME_API
  proxy             : $PROXY_URL        (ANTHROPIC_BASE_URL)
  thinking log      : $SQUID_THINKING_LOG_DIR/api_calls.jsonl
  deny rules        : $SETTINGS_FILE

Launching claude in iso dir. First run will prompt to trust this workspace — approve.
EOF

cd "$ISO_DIR"
exec claude "$@"
