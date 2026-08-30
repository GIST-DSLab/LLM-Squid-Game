#!/usr/bin/env python3
"""Thin shim. The canonical entry point is ``uv run squid-game``.

This script used to carry its own argparse, which had drifted: it lacked
``--resume``, so an interrupted experiment could not be continued from
here. Delegating to ``squid_game.runner.main`` closes that gap and removes
the second copy of the CLI.

Usage::

    uv run squid-game --config configs/experiment/v6_signal_game.yaml
    python scripts/run_experiment.py --config configs/experiment/v6_signal_game.yaml
"""

from squid_game.runner import main

if __name__ == "__main__":
    main()
