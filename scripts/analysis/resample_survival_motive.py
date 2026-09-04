"""Resample the recorded decision call N times per turn → ``smi_turns.csv``.

Usage
-----
    uv run python -m scripts.analysis.resample_survival_motive outputs/<run_dir> --n 10
    uv run python -m scripts.analysis.resample_survival_motive outputs/<run_dir> --dry-run

The provider is rebuilt from ``<run_dir>/experiment_config.json`` (first
season's ``provider_config``); temperature / max_tokens come from there too
unless overridden.
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


def _provider_config(run_dir: Path) -> ProviderConfig:
    raw = json.loads((run_dir / "experiment_config.json").read_text())
    return ProviderConfig(**raw["seasons"][0]["provider_config"])


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument("--n", type=int, default=10)
    parser.add_argument("--workers", type=int, default=1)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=None)
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    pcfg = _provider_config(args.run_dir)
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
