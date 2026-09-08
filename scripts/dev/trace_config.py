#!/usr/bin/env python3
"""One command: run any experiment config offline and render its call trace.

    uv run python scripts/dev/trace_config.py --config configs/experiment/<x>.yaml

It loads the YAML unchanged, swaps every season's provider for
``provider: trace`` (``squid_game.providers.trace.TraceProvider``: records
each call's exact message list, replies with a canned stub, never touches
the network), forces ``num_repetitions: 1`` and ``parallel_workers: 1``,
redirects ``output_dir`` to ``outputs/_trace/<config-stem>/``, runs the
real runner in-process, then writes a single HTML page (default
``docs/reports/traces/<config-stem>.html``).

Nothing else about the config is touched, so the prompts on the page are
byte-for-byte what a paid run of that same YAML would send.

⚠️ The answers are stubs, not model behaviour. A trace run's forfeit
rate, accuracy and RI are artefacts of ``TraceProvider``, not results.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _rewrite(config_dict: dict, *, output_dir: str, reps: int, turns: int | None) -> dict:
    """Return a copy of the config dumped dict, pointed at the trace provider."""
    out = dict(config_dict)
    out["output_dir"] = output_dir
    out["num_repetitions"] = reps
    out["parallel_workers"] = 1

    seasons = []
    for season in out.get("seasons", []):
        season = dict(season)
        provider = dict(season.get("provider_config") or {})
        # Keep temperature / max_tokens: they are recorded per call, so the
        # page shows the sampling settings the real run would have used.
        provider["provider"] = "trace"
        provider["model"] = "trace-stub"
        provider["base_url"] = None
        provider["parallel_workers"] = 1
        season["provider_config"] = provider
        if turns is not None:
            task = dict(season.get("task_config") or {})
            task["total_turns"] = turns
            season["task_config"] = task
        seasons.append(season)
    out["seasons"] = seasons
    return out


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, help="Experiment YAML to trace")
    parser.add_argument(
        "--turns",
        type=int,
        default=None,
        help=(
            "Cap total_turns. Ignored with a warning when the task config "
            "refuses it (e.g. underdetermined blocks that fall outside a "
            "shorter season) — the configured length is used instead."
        ),
    )
    parser.add_argument("--reps", type=int, default=1, help="num_repetitions (default 1)")
    parser.add_argument(
        "--forfeit-at",
        type=int,
        default=None,
        help="Make the stub answer FORFEIT on this turn wherever the menu offers an exit.",
    )
    parser.add_argument("--out", default=None, help="Output HTML path")
    args = parser.parse_args()

    from squid_game.models.config import ExperimentConfig
    from squid_game.runner import ExperimentRunner, load_config_from_yaml

    config_path = Path(args.config)
    stem = config_path.stem
    output_dir = REPO_ROOT / "outputs" / "_trace" / stem
    output_dir.mkdir(parents=True, exist_ok=True)

    base = load_config_from_yaml(str(config_path))
    dumped = base.model_dump()

    def _build(turns: int | None) -> ExperimentConfig:
        return ExperimentConfig.model_validate(
            _rewrite(dumped, output_dir=str(output_dir), reps=args.reps, turns=turns)
        )

    try:
        config = _build(args.turns)
    except Exception as exc:  # pydantic ValidationError and friends
        if args.turns is None:
            raise
        print(f"[trace] --turns {args.turns} rejected, using the configured length:\n  {exc}")
        config = _build(None)

    trace_path = output_dir / "call_trace.jsonl"
    if trace_path.exists():
        trace_path.unlink()
    os.environ["SQUID_TRACE_PATH"] = str(trace_path)
    if args.forfeit_at is not None:
        os.environ["SQUID_TRACE_FORFEIT_AT"] = str(args.forfeit_at)
    else:
        os.environ.pop("SQUID_TRACE_FORFEIT_AT", None)

    before = {p.name for p in output_dir.iterdir() if p.is_dir()}
    ExperimentRunner(config).run()
    new_dirs = [
        p for p in output_dir.iterdir() if p.is_dir() and p.name not in before
    ]
    run_dir = max(new_dirs, key=lambda p: p.stat().st_mtime) if new_dirs else output_dir

    # Park the trace next to experiment_config.json / season_results.jsonl so
    # the renderer can label sessions by cell.
    if trace_path.exists() and run_dir != output_dir:
        trace_path.replace(run_dir / "call_trace.jsonl")

    out_html = Path(args.out) if args.out else REPO_ROOT / "docs/reports/traces" / f"{stem}.html"
    subprocess.run(
        [sys.executable, str(Path(__file__).with_name("render_call_trace.py")),
         str(run_dir), "--out", str(out_html)],
        check=True,
    )
    print(f"[trace] run dir: {run_dir}")
    print(f"[trace] page:    {out_html}")


if __name__ == "__main__":
    main()
