"""Print the |H| distribution per puzzle tier and a YAML snippet for the bands.

The per-turn puzzle mode accepts a puzzle only when the number of
hypotheses still consistent with its clues, |H|, lies inside the tier's
``[h_lo, h_hi]``. Those bounds are not design choices — they are the
10th / 90th percentile of what the generator produces for the tier's
``(families, n_clues)`` when unconstrained. This script measures that
and prints the ``puzzle_ladder`` block to paste into
``configs/tasks/signal_game.yaml``::

    uv run python -m scripts.dev.calibrate_signal_puzzle_ladder --seeds 200 --turns-per-tier 6

It also prints the per-tier medians so a non-monotone ladder is visible
before any LLM sees it.
"""

from __future__ import annotations

import argparse
import statistics
from dataclasses import replace

from squid_game.tasks.signal_game.puzzle import generate_puzzle, puzzle_rng
from squid_game.tasks.signal_game.puzzle_config import (
    SignalPuzzleConfig,
    load_signal_puzzle_config,
)

_UNBOUNDED_HI = 10**9


def _quantile(values: list[int], q: float) -> float:
    ordered = sorted(values)
    idx = max(0, min(len(ordered) - 1, round(q * (len(ordered) - 1))))
    return float(ordered[idx])


def run_calibration(
    config: SignalPuzzleConfig, seeds: int, turns_per_tier: int
) -> dict[int, dict[str, float]]:
    """Sample ``seeds x turns_per_tier`` puzzles per tier with the band removed."""
    stats: dict[int, dict[str, float]] = {}
    for step in config.puzzle_ladder:
        spec = replace(step.to_spec(), h_lo=1, h_hi=_UNBOUNDED_HI)
        counts: list[int] = []
        for seed in range(seeds):
            for t in range(turns_per_tier):
                turn = 1000 * step.tier + t  # any injective (tier, t) -> int works
                counts.append(generate_puzzle(puzzle_rng(seed, turn), spec).n_consistent)
        stats[step.tier] = {
            "n": float(len(counts)),
            "min": float(min(counts)),
            "p10": _quantile(counts, 0.10),
            "p50": float(statistics.median(counts)),
            "p90": _quantile(counts, 0.90),
            "max": float(max(counts)),
        }
    return stats


def _snippet(config: SignalPuzzleConfig, stats: dict[int, dict[str, float]]) -> str:
    lines = ["puzzle_ladder:"]
    for step in config.puzzle_ladder:
        s = stats[step.tier]
        fams = ", ".join(step.families)
        lines.append(
            f"  - {{tier: {step.tier}, turns: {step.turns}, families: [{fams}], "
            f"n_clues: {step.n_clues}, h_lo: {int(s['p10'])}, h_hi: {int(s['p90'])}}}"
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--seeds", type=int, default=200)
    parser.add_argument("--turns-per-tier", type=int, default=6)
    args = parser.parse_args(argv)

    config = load_signal_puzzle_config()
    stats = run_calibration(config, seeds=args.seeds, turns_per_tier=args.turns_per_tier)

    print(f"{'tier':>4} {'n':>5} {'min':>6} {'p10':>6} {'p50':>6} {'p90':>6} {'max':>6}")
    for tier in sorted(stats):
        s = stats[tier]
        print(f"{tier:>4} {int(s['n']):>5} {int(s['min']):>6} {int(s['p10']):>6} "
              f"{int(s['p50']):>6} {int(s['p90']):>6} {int(s['max']):>6}")
    medians = [stats[t]["p50"] for t in sorted(stats)]
    print("monotone:", "yes" if medians == sorted(medians) else "NO — adjust n_clues")
    print()
    print(_snippet(config, stats))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
