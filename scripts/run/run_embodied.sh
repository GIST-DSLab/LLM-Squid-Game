#!/usr/bin/env bash
# Run an embodied-threat experiment inside the container stack
# (docker-compose.embodied.yml / Dockerfile.embodied — Unit 18, Task 12).
#
# Usage: CONFIG=configs/experiment/<name>.yaml scripts/run/run_embodied.sh
# CONFIG defaults to configs/experiment/embodied_threat_smoke.yaml if unset.
#
# API keys (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY /
# OLLAMA_API_KEY) are read from the calling shell's environment by
# docker-compose.embodied.yml -- none are baked into the image.
set -euo pipefail

# Task 14: default to the smoke config so this script has a runnable
# entry point out of the box; override CONFIG to point at any other
# embodied_threat.enabled=true experiment yaml.
#
# I1 (final review): must be `export`ed, not just set as a shell
# variable -- docker-compose.embodied.yml's `command:` interpolates
# `${CONFIG}` from the host process environment at parse time (via
# `docker compose ... run`), so a plain shell assignment never reaches
# it and a bare `scripts/run/run_embodied.sh` silently ran `--config ""`.
export CONFIG="${CONFIG:-configs/experiment/embodied_threat_smoke.yaml}"

COMPOSE_FILE="docker-compose.embodied.yml"

# The ollama service only starts when a season's runtime=agent_harness
# targets an Ollama Cloud model; it lives behind the "ollama" compose
# profile (see docker-compose.embodied.yml) so a plain run never pays to
# start it. Opt in with:
#   RUN_EMBODIED_PROFILE=ollama CONFIG=... scripts/run/run_embodied.sh
PROFILE_ARGS=()
if [ -n "${RUN_EMBODIED_PROFILE:-}" ]; then
    PROFILE_ARGS=(--profile "${RUN_EMBODIED_PROFILE}")
fi

docker compose -f "${COMPOSE_FILE}" "${PROFILE_ARGS[@]}" build runner
docker compose -f "${COMPOSE_FILE}" "${PROFILE_ARGS[@]}" run --rm \
    -e CONFIG="${CONFIG}" runner
docker compose -f "${COMPOSE_FILE}" "${PROFILE_ARGS[@]}" down
