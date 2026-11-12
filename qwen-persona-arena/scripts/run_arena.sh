#!/usr/bin/env bash
# One arm of the arena: assumes the steering server is already up (uv run python -m persona_arena.server).
#   bash scripts/run_arena.sh community_spirit [extra squid5 args, e.g. --reps 1]
set -euo pipefail
ARM="$1"; shift
HERE="$(cd "$(dirname "$0")/.." && pwd)"
ENGINE="$HOME/wt/squid5-e52"
PY="$ENGINE/.venv/bin/python"; [ -x "$PY" ] || PY="$HOME/.venvs/squid-game/bin/python"
curl -sf http://127.0.0.1:8610/v1/models >/dev/null || { echo "steering server is not running on :8610"; exit 1; }
cd "$ENGINE" && QWEN_STEER_KEY=local PYTHONPATH=. "$PY" -m squid5 run "$HERE/configs/e52v35_qwen8b_${ARM}.yaml" "$@"
