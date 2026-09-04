"""Resample the recorded decision call N times per turn → ``smi_turns.csv``.

Usage
-----
    uv run python -m scripts.analysis.resample_survival_motive outputs/<run_dir> --n 10
    uv run python -m scripts.analysis.resample_survival_motive outputs/<run_dir> --dry-run

The provider is rebuilt from ``<run_dir>/experiment_config.json`` (first
season's ``provider_config``); temperature / max_tokens come from there too
unless overridden.

Two provider properties are rejected outright rather than warned about:

* ``--workers > 1`` with ``codex_cli`` / ``claude_code``. Those providers
  share one scratch working directory per instance, and the resampler
  shares a single provider object across threads, so concurrent calls
  would collide in that directory.
* A fixed ``seed`` in the recorded ``provider_config``. SMI is
  ``q = n_forfeit / n_valid`` over N *independent* replays of the same
  decision call; a seeded provider returns the same completion every time,
  which collapses q to exactly 0 or 1 and makes the index meaningless.
  Re-run with the seed removed from the config, or resample a run that had
  none.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from squid_game.evaluation.behavioral.survival_motive import (
    iter_resample_targets,
    resample_run,
)
from squid_game.models.config import ProviderConfig
from squid_game.providers.factory import build_provider


# Agent-harness providers: one scratch working directory per instance, so a
# single shared provider object cannot be called from several threads.
_SINGLE_WORKDIR_PROVIDERS = frozenset({"codex_cli", "claude_code"})


def _provider_config(run_dir: Path) -> ProviderConfig:
    raw = json.loads((run_dir / "experiment_config.json").read_text())
    return ProviderConfig(**raw["seasons"][0]["provider_config"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument(
        "--workers", type=int, default=1,
        help=(
            "Threads sharing one provider object. Safe for the cloud providers "
            "(gemini / ollama_cloud / openai / anthropic); keep it at 1 for the "
            "agent-harness providers (codex_cli, claude_code), whose per-instance "
            "scratch directory is shared across calls."
        ),
    )
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pcfg = _provider_config(args.run_dir)
    if pcfg.provider in _SINGLE_WORKDIR_PROVIDERS and args.workers > 1:
        parser.error(
            f"--workers > 1 is unsafe with provider {pcfg.provider!r}: "
            "one shared workdir per instance"
        )
    if getattr(pcfg, "seed", None) is not None:
        parser.error(
            f"provider_config has a fixed seed ({pcfg.seed}); the N replays "
            "would be identical, collapsing q to 0 or 1 and making smi = q/p "
            "meaningless. Resample a run whose provider had no seed."
        )
    temperature = args.temperature if args.temperature is not None else pcfg.temperature
    max_tokens = args.max_tokens if args.max_tokens is not None else pcfg.max_tokens
    if args.dry_run:
        targets = list(iter_resample_targets(args.run_dir))
        print(f"{len(targets)} replayable turns → {len(targets) * args.n} calls "
              f"({pcfg.provider}/{pcfg.model}, T={temperature})")
        return
    provider = build_provider(pcfg)
    resample_run(
        args.run_dir, provider, n=args.n, temperature=temperature,
        max_tokens=max_tokens, limit=args.limit, workers=args.workers,
    )


if __name__ == "__main__":
    main()
