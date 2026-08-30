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
