#!/usr/bin/env python3
"""CLI entry point for running LLM Squid Game experiments.

Loads experiment configuration from a YAML file, validates it against
the Pydantic schema, and drives the ExperimentRunner.

Usage::

    python scripts/run_experiment.py --config configs/phase1.yaml
    python scripts/run_experiment.py --config configs/phase1.yaml --dry-run
    python scripts/run_experiment.py --config configs/phase1.yaml --parallel 4
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

# Ensure the project source is importable when running as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

from squid_game.runner import (
    ExperimentRunner,
    load_config_from_yaml,
    _print_dry_run,
)


def _build_parser() -> argparse.ArgumentParser:
    """Build the argument parser for the experiment CLI.

    Returns:
        Configured ArgumentParser.
    """
    parser = argparse.ArgumentParser(
        prog="run_experiment",
        description=(
            "LLM Squid Game -- Run a benchmark experiment from a YAML config."
        ),
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to the YAML experiment configuration file.",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Override the number of parallel workers. "
            "Default is taken from the config file."
        ),
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        metavar="PATH",
        help="Override the output directory from the config file.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate configuration and print the execution plan without running.",
    )
    return parser


def main() -> None:
    """Parse arguments, load config, and execute the experiment."""
    parser = _build_parser()
    args = parser.parse_args()

    # Set up logging.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        stream=sys.stderr,
    )
    logger = logging.getLogger("run_experiment")

    # Load and validate configuration.
    config_path = Path(args.config)
    if not config_path.exists():
        logger.error("Config file not found: %s", config_path)
        sys.exit(1)

    try:
        config = load_config_from_yaml(str(config_path))
    except Exception as exc:
        logger.error("Failed to load config: %s", exc)
        sys.exit(1)

    logger.info("Loaded config '%s' from %s", config.name, config_path)

    # Apply CLI overrides.
    overrides: dict = {}
    if args.parallel is not None:
        overrides["parallel_workers"] = args.parallel
    if args.output_dir is not None:
        overrides["output_dir"] = args.output_dir

    if overrides:
        config = config.model_copy(update=overrides)

    # Dry run: print plan and exit.
    if args.dry_run:
        _print_dry_run(config)
        sys.exit(0)

    # Execute experiment.
    total_runs = len(config.seasons) * config.num_repetitions
    print(
        f"Starting experiment '{config.name}': "
        f"{len(config.seasons)} conditions x "
        f"{config.num_repetitions} repetitions = "
        f"{total_runs} total season runs",
        flush=True,
    )

    runner = ExperimentRunner(config)
    result = runner.run()

    # Print summary.
    survived = sum(1 for s in result.seasons if s.survived and not s.forfeited)
    forfeited = sum(1 for s in result.seasons if s.forfeited)
    died = sum(1 for s in result.seasons if not s.survived)
    print(f"\nSummary: {len(result.seasons)} seasons completed")
    print(f"  Survived: {survived}")
    print(f"  Forfeited: {forfeited}")
    print(f"  Died: {died}")


if __name__ == "__main__":
    main()
