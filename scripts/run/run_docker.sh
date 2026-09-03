#!/usr/bin/env bash
# Run an experiment inside the container stack
# (docker-compose.runner.yml / Dockerfile.runner).
#
# Usage:
#   CONFIG=configs/experiment/<name>.yaml scripts/run/run_docker.sh
#   CONFIG=configs/experiment/<name>.yaml scripts/run/run_docker.sh --dry-run
#
# CONFIG defaults to configs/experiment/lives_threat_smoke.yaml if unset.
# Any extra arguments are forwarded verbatim to `main.py` after
# `--config "${CONFIG}"`, so `--dry-run`, `--parallel N`, `--output-dir
# <dir>` and `--resume <dir>` all work through this script.
#
# API keys (ANTHROPIC_API_KEY / OPENAI_API_KEY / GEMINI_API_KEY /
# OLLAMA_API_KEY) are read from the calling shell's environment by
# docker-compose.runner.yml -- none are baked into the image. Any of the
# four still unset when this script runs is filled in from a repo-root
# `.env`, if one exists (see _load_from_dotenv below).
#
# For the analysis / probe scripts use the sibling `analysis` service
# instead -- see the header of docker-compose.runner.yml.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "${REPO_ROOT}"

# Read one KEY from .env without sourcing the file. The repo's .env has
# lines shaped `KEY= value # comment`, so neither `source .env` (the
# comment and the space make it a syntax error / part of the value) nor
# `export $(grep ^KEY= .env)` (word-splits into four arguments, and
# `export` rejects the second one as "not an identifier") works. Strip
# the leading whitespace, any trailing ` # comment`, and trailing space.
_load_from_dotenv() {
    local key="$1" line
    [[ -f .env ]] || return 0
    [[ -z "${!key:-}" ]] || return 0          # already set in the environment
    line="$(grep -E "^${key}=" .env | head -1 || true)"
    [[ -n "${line}" ]] || return 0
    line="${line#"${key}"=}"
    line="$(printf '%s' "${line}" | sed -e 's/^[[:space:]]*//' \
                                        -e 's/[[:space:]]*#.*$//' \
                                        -e 's/[[:space:]]*$//')"
    [[ -n "${line}" ]] || return 0
    export "${key}=${line}"
}

for _key in ANTHROPIC_API_KEY OPENAI_API_KEY GEMINI_API_KEY OLLAMA_API_KEY; do
    _load_from_dotenv "${_key}"
done

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

# configs/ is COPYed into the image, so a config file added or edited on
# the host since the last build is invisible to the container until this
# rebuild runs.
docker compose -f "${COMPOSE_FILE}" build runner

if [[ $# -gt 0 ]]; then
    # Extra args: override the service's `command:` entirely, since
    # compose has no "append to command" form.
    docker compose -f "${COMPOSE_FILE}" run --rm runner \
        uv run --no-sync python main.py --config "${CONFIG}" "$@"
else
    docker compose -f "${COMPOSE_FILE}" run --rm -e CONFIG="${CONFIG}" runner
fi

docker compose -f "${COMPOSE_FILE}" down
