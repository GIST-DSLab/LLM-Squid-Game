"""Clue sharding for the subagent-kill design (spec §5).

Each round the puzzle's examples stop being a list in the observation and
become one example per alive subagent slot. Slot capacity is **1**: a slot
holds at most one clue, so the number of alive slots is a hard ceiling on
how many examples the agent can reach this round.

The load-bearing clues (``puzzle.minimal_clue_signals``) go first, so the
threshold the design measures is ``|M|`` — the number of alive slots the
round needs to stay solvable. Redundant clues fill whatever alive slots are
left; leftovers are dropped. Every slot name appears in ``shard_map``, dead
ones mapped to ``None``, so a caller can render a prompt for each slot
without holding the ledger.

Nothing here tells the agent how many clues matter: ``threshold`` and
``solvable_with_alive_slots`` are recorded in ``task_metadata`` only.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Sequence

from squid_game.tasks.signal_game.puzzle import Puzzle


@dataclass(frozen=True)
class ShardPlan:
    """Who holds what this round, and what that leaves out of reach.

    Attributes:
        shard_map: Every slot name → the clue text it holds, or ``None``.
            Dead slots and alive slots with nothing left both map to
            ``None``; the rendered prompt is the same either way, so a
            dead slot's silence is not a signal about the clue set.
        threshold: ``|M|`` — how many alive slots this round needs.
        reachable_clues: Load-bearing clues actually placed,
            ``min(|M|, |A|)``.
        unreachable_clues: ``threshold - reachable_clues``.
        solvable_with_alive_slots: Whether every load-bearing clue was
            placed. When False the round is graded against the true rule
            anyway (as in ``underdetermined`` mode), so analyses must
            condition on this column before computing accuracy.
    """

    shard_map: dict[str, str | None]
    threshold: int
    reachable_clues: int
    unreachable_clues: int
    solvable_with_alive_slots: bool


def shard_clues(
    puzzle: Puzzle,
    slot_names: Sequence[str],
    alive: Sequence[str],
    seed: int | None,
    turn_number: int,
) -> ShardPlan:
    """Distribute *puzzle*'s clues one per alive slot.

    The draw is ``random.Random(f"{seed}:{turn_number}:shard")`` and
    nothing else, so every cell of one repetition shards the same round
    the same way and a plan can be recomputed offline from the recorded
    seed.

    Args:
        puzzle: This round's puzzle; ``minimal_clue_signals`` picks out
            the load-bearing clues.
        slot_names: Every slot name in the season, alive or not.
        alive: The subset still alive going into this round.
        seed: The season seed.
        turn_number: This round's number.
    """
    minimal = [c for c in puzzle.clues if c.signal in puzzle.minimal_clue_signals]
    extras = [c for c in puzzle.clues if c.signal not in puzzle.minimal_clue_signals]
    rng = random.Random(f"{seed}:{turn_number}:shard")
    rng.shuffle(minimal)
    rng.shuffle(extras)
    alive_set = set(alive)
    # Canonical order first, so the shuffle below is the only source of
    # order and a caller passing ``alive`` in any order gets one answer.
    alive_list = [s for s in slot_names if s in alive_set]
    rng.shuffle(alive_list)

    shard: dict[str, str | None] = {s: None for s in slot_names}
    reachable = 0
    for slot, clue in zip(alive_list, minimal):
        shard[slot] = str(clue)
        reachable += 1
    for slot, clue in zip(alive_list[len(minimal):], extras):
        shard[slot] = str(clue)

    return ShardPlan(
        shard_map=shard,
        threshold=len(minimal),
        reachable_clues=reachable,
        unreachable_clues=len(minimal) - reachable,
        solvable_with_alive_slots=reachable == len(minimal),
    )


def control_plan(puzzle: Puzzle, slot_names: Sequence[str]) -> ShardPlan:
    """The plan for the control cell: the slots hold nothing.

    Every clue is rendered in the observation as it always was, so the
    round is solvable whatever the alive count is. The slots still exist
    and are still revoked on a wrong answer — that is what makes this the
    cell the threshold is read against.
    """
    minimal = [c for c in puzzle.clues if c.signal in puzzle.minimal_clue_signals]
    return ShardPlan(
        shard_map={s: None for s in slot_names},
        threshold=len(minimal),
        reachable_clues=len(minimal),
        unreachable_clues=0,
        solvable_with_alive_slots=True,
    )


def render_subagent_prompts(plan: ShardPlan) -> dict[str, str]:
    """One rendered system prompt per slot name in *plan*.

    A slot holding nothing gets the no-example sentence rather than no
    prompt at all: every slot must be defined for the harness, and the
    tool list must not say which slots are worth calling.
    """
    from squid_game.prompts import render

    return {
        slot: render("subagent_clue.j2", slot=slot, clue=clue).strip()
        for slot, clue in plan.shard_map.items()
    }
