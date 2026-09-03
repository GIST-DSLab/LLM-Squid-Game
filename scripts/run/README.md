# scripts/run/

The canonical way to run an experiment is `uv run squid-game --config <path>`.
`run_experiment.py` and `resume_experiment.py` here are legacy-compatible
shims and battery-guarded sequencing around that same entry point — not a
second implementation of it.

- `run_experiment.py` — thin CLI shim delegating to `squid_game.runner.main`.
- `resume_experiment.py` — resumes an interrupted run via `--resume`.
- `start_servers.sh` / `enter_isolated_claude.sh` — dev-loop helpers that
  start the Web Arena API + proxy and open an isolated Claude Code session
  against them; not part of the experiment pipeline itself.
- `run_pipeline.sh` — one-off battery-guarded sequential pipeline script for
  a specific historical run, kept for reference.
- `run_docker.sh` — builds and runs the containerised experiment stack
  (`Dockerfile.runner` / `docker-compose.runner.yml` at the repo root),
  defaulting to `configs/experiment/lives_threat_smoke.yaml`.

## Running in Docker

`Dockerfile.runner` has two build targets and `docker-compose.runner.yml`
one service per target:

| service | target | extras | bind mounts | size (linux/arm64) |
|---|---|---|---|---|
| `runner` | `runner` | none (`--no-dev`) | `./outputs` | ~0.9 GB |
| `analysis` | `analysis` | `--extra analysis --extra probe` | `./outputs`, `./results`, `hf-cache` | ~2.8 GB |

Neither image contains an API key. Compose forwards
`ANTHROPIC_API_KEY` / `OPENAI_API_KEY` / `GEMINI_API_KEY` /
`OLLAMA_API_KEY` from the calling shell's environment; `run_docker.sh`
fills in any that are unset from the repo-root `.env`.

⚠️ `.env` here contains lines shaped `KEY= value # comment`. Neither
`source .env` nor `export $(grep -E '^OLLAMA_API_KEY=' .env)` works on
it — the latter word-splits and `export` rejects the key value as "not
an identifier". Let `run_docker.sh` do it, or strip by hand:

```bash
export OLLAMA_API_KEY="$(grep -E '^OLLAMA_API_KEY=' .env | head -1 \
  | sed -e 's/^OLLAMA_API_KEY=[[:space:]]*//' -e 's/[[:space:]]*#.*$//')"
```

### (a) A run

```bash
# via the wrapper (builds, runs, then `compose down`)
CONFIG=configs/experiment/lives_threat_docker_smoke.yaml scripts/run/run_docker.sh
CONFIG=configs/experiment/lives_threat_docker_smoke.yaml scripts/run/run_docker.sh --dry-run

# or directly
docker compose -f docker-compose.runner.yml build runner
CONFIG=configs/experiment/lives_threat_docker_smoke.yaml \
  docker compose -f docker-compose.runner.yml run --rm runner
```

Extra arguments given to `run_docker.sh` are forwarded to `main.py`
after `--config`, so `--dry-run`, `--parallel N`, `--output-dir <dir>`
and `--resume <dir>` all work through it.

⚠️ `configs/` is COPYed into the image. A config file added or edited on
the host after the last build is invisible inside the container until
the image is rebuilt (`run_docker.sh` rebuilds on every invocation).

### (b) The analysis service

```bash
docker compose -f docker-compose.runner.yml build analysis

RUN=outputs/lives_threat_docker_smoke/<ts>_gpt-oss-120b-cloud_signal-game

docker compose -f docker-compose.runner.yml run --rm analysis \
  uv run --no-sync python -m scripts.analysis.probe_threat_motive \
    --runs "$RUN" --n-permutations 20 --out results/threat_probe/docker_smoke

docker compose -f docker-compose.runner.yml run --rm analysis \
  uv run --no-sync python -m scripts.analysis.probe_reasoning_embeddings \
    --root outputs/lives_threat_docker_smoke --target threat_level \
    --channel task --channel forfeit --n-permutations 20 --n-splits 3 \
    --min-rows 5 --out results/threat_probe/docker_smoke

docker compose -f docker-compose.runner.yml run --rm analysis \
  uv run --no-sync python scripts/analysis/analyze_threat_effort.py \
    outputs/lives_threat_docker_smoke/ --out results/threat_effort_docker_smoke
```

`./results` is bind-mounted, so the artefacts land on the host. The
SentenceBERT probe downloads its model on first use into the named
`hf-cache` volume, so later runs are offline for that step.

```bash
docker compose -f docker-compose.runner.yml down   # when finished
```
