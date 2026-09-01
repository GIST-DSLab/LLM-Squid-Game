"""Print the 30-turn question sequence a given seed produces.

The sequence is derived deterministically from the seed, so it is not baked
into a file anywhere; this script is how a human inspects it before a run::

    uv run python scripts/dump_benchmark_sequence.py --task gpqa --seed 7

Uses ``Framing.TRUE_BASELINE`` / ``ForfeitCondition.ALLOWED`` as the probe
context — these are the canonical Phase O v6 values (``ForfeitCondition``
has only ``ALLOWED``/``NOT_ALLOWED``; there is no ``EXIT``/``NO_EXIT``).
The task module's item sequence depends only on the seed and turn number,
not on framing or forfeit condition, so this choice does not affect what
is printed.
"""

from __future__ import annotations

import argparse
import sys

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.tasks.registry import get_task
import squid_game.tasks.benchmark  # noqa: F401  (registers the three tasks)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dump a benchmark item sequence.")
    parser.add_argument("--task", required=True, choices=["omni_math", "hi_tom", "gpqa"])
    parser.add_argument("--seed", type=int, required=True)
    parser.add_argument("--turns", type=int, default=30)
    parser.add_argument(
        "--show-body",
        action="store_true",
        help="Print the question text as well (keep this off in shared logs).",
    )
    args = parser.parse_args(argv)

    task = get_task(args.task)()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=args.seed)

    for turn in range(1, args.turns + 1):
        context = task.prepare(
            None,
            TurnContext(
                turn_number=turn,
                total_turns=args.turns,
                season_id="dump",
                cumulative_score=30.0,
                p_death=0.25,
                framing=Framing.TRUE_BASELINE,
                forfeit_condition=ForfeitCondition.ALLOWED,
                difficulty=Difficulty.MEDIUM,
            ),
        )
        meta = context.metadata
        print(f"turn {turn:>2}  band {meta['band']:>2}  {meta['item_id']}")
        if args.show_body:
            print(context.prompt_section)
            print("-" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
