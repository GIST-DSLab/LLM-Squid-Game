#!/usr/bin/env bash
# Run an experiment inside the container stack
# (docker-compose.runner.yml / Dockerfile.runner).
#
# Usage: CONFIG=configs/experiment/<name>.yaml scripts/run/run_docker.sh
# CONFIG defaults to configs/experiment/lives_threat_smoke.yaml if unset.
#
# API keys (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY /
# OLLAMA_API_KEY) are read from the calling shell's environment by
# docker-compose.runner.yml -- none are baked into the image.
set -euo pipefail

# Default to the smoke config so this script has a runnable entry point
# out of the box; override CONFIG to point at any other experiment yaml.
#
# Must be `export`ed, not just set as a shell variable --
# docker-compose.runner.yml's `command:` interpolates `${CONFIG}` from
# the host process environment at parse time (via `docker compose ...
# run`), so a plain shell assignment never reaches it and a bare
# `scripts/run/run_docker.sh` would silently run `--config ""`.
export CONFIG="${CONFIG:-configs/experiment/lives_threat_smoke.yaml}"

COMPOSE_FILE="docker-compose.runner.yml"

docker compose -f "${COMPOSE_FILE}" build runner
docker compose -f "${COMPOSE_FILE}" run --rm -e CONFIG="${CONFIG}" runner
docker compose -f "${COMPOSE_FILE}" down
