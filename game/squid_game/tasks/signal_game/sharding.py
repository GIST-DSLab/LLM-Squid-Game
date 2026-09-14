"""Clue sharding for the subagent-kill design (spec §5).

Each round the puzzle's examples stop being a list in the observation and
become a handful of examples per alive subagent slot. The knob is the
round's **required slots** ``R_t``: the task can be solved only while at
least ``R_t`` subagents survive. Slot capacity follows from it,

    capacity c = max(1, ceil(|M| / R_t))

where ``M`` is the round's load-bearing clue set
(``puzzle.minimal_clue_signals``), so ``R_t`` slots between them can hold
every clue that matters and the threshold does not drift with the ladder's
clue counts. A fixed capacity of 1 cannot do this: the rungs carry 4, 5, 7,
… 34 load-bearing clues, so from rung 4 on, five slots at one clue each
would leave the round unsolvable even with every slot alive.

Load-bearing clues are dealt round-robin over the alive slots first, so a
slot that dies takes as few of them as the deal allows; redundant clues then
fill whatever capacity is left. Every slot name appears in ``shard_map``,
dead ones mapped to ``[]``, so a caller can render a prompt for each slot
without holding the ledger.

Nothing here tells the agent how many clues matter or how many slots the
round needs: ``required_slots`` / ``threshold`` /
``solvable_with_alive_slots`` are recorded in ``task_metadata`` only.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass
from typing import Sequence

from squid_game.tasks.signal_game.puzzle import Puzzle


@dataclass(frozen=True)
class ShardPlan:
    """Who holds what this round, and what that leaves out of reach.

    Attributes:
        shard_map: Every slot name → the clue texts it holds, possibly
            empty. Dead slots and alive slots that drew nothing both map
            to ``[]``; the rendered prompt is the same either way, so a
            dead slot's silence is not a signal about the clue set.
        threshold: ``R_t`` — how many slots the round needs. Same number
            as ``required_slots``; the name is kept because it is the
            column the design reads.
        required_slots: ``R_t`` for this round, from the season's
            schedule.
        capacity: ``max(1, ceil(|M| / R_t))`` — the most clues one slot
            may hold this round.
        reachable_clues: Load-bearing clues actually placed,
            ``min(|M|, n_alive * capacity)``.
        unreachable_clues: ``|M| - reachable_clues``. (``|M|`` itself is
            therefore ``reachable_clues + unreachable_clues``; it is not
            stored separately, and it is NOT ``threshold`` any more.)
        solvable_with_alive_slots: ``n_alive >= required_slots`` — the
            design's rule, stated once per round by the schedule rather
            than inferred from how the deal happened to land. Where
            ``R_t`` does not divide ``|M|`` the capacity rounds up and a
            round can be short of ``R_t`` slots while the clues still
            physically fit (``unreachable_clues == 0``); the declared rule
            wins, because it is the one the design manipulates. When this
            is False the round is graded against the true rule anyway (as
            in ``underdetermined`` mode), so analyses must condition on
            this column before computing accuracy.
    """

    shard_map: dict[str, list[str]]
    threshold: int
    required_slots: int
    capacity: int
    reachable_clues: int
    unreachable_clues: int
    solvable_with_alive_slots: bool


def _alive_in_canonical_order(
    slot_names: Sequence[str], alive: Sequence[str]
) -> list[str]:
    """The alive slots in ``slot_names`` order, refusing unknown names.

    Canonical order first so the shuffle below is the only source of order:
    the caller may pass ``alive`` in any order and gets one answer.
    """
    known = list(slot_names)
    unknown = sorted(set(alive) - set(known))
    if unknown:
        raise ValueError(
            f"alive names {unknown} are not slots of this season "
            f"(slots: {known}). A name the ledger does not know would be "
            "dropped silently and the round would shard as if that slot "
            "had died."
        )
    alive_set = set(alive)
    return [s for s in known if s in alive_set]


def shard_clues(
    puzzle: Puzzle,
    slot_names: Sequence[str],
    alive: Sequence[str],
    seed: int | None,
    turn_number: int,
    required_slots: int,
) -> ShardPlan:
    """Distribute *puzzle*'s clues over the alive slots at this round's capacity.

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
        required_slots: ``R_t`` — how many slots the round needs.

    Raises:
        ValueError: If *required_slots* is below 1, or *alive* names a
            slot this season does not have.
    """
    if required_slots < 1:
        raise ValueError(
            f"required_slots must be at least 1, got {required_slots}: a "
            "round nobody has to survive is not a threshold."
        )
    minimal = [c for c in puzzle.clues if c.signal in puzzle.minimal_clue_signals]
    extras = [c for c in puzzle.clues if c.signal not in puzzle.minimal_clue_signals]
    rng = random.Random(f"{seed}:{turn_number}:shard")
    rng.shuffle(minimal)
    rng.shuffle(extras)
    alive_list = _alive_in_canonical_order(slot_names, alive)
    rng.shuffle(alive_list)

    capacity = max(1, math.ceil(len(minimal) / required_slots))
    # ``alive_list`` repeated ``capacity`` times IS the round-robin order
    # with a per-slot cap: position i of the repetition hands slot
    # ``i % n_alive`` its ``i // n_alive``-th clue, and the list runs out
    # after exactly ``capacity`` clues per slot.
    deal_order = alive_list * capacity
    shard: dict[str, list[str]] = {s: [] for s in slot_names}
    for slot, clue in zip(deal_order, minimal + extras):
        shard[slot].append(str(clue))

    reachable = min(len(minimal), len(alive_list) * capacity)
    return ShardPlan(
        shard_map=shard,
        threshold=required_slots,
        required_slots=required_slots,
        capacity=capacity,
        reachable_clues=reachable,
        unreachable_clues=len(minimal) - reachable,
        solvable_with_alive_slots=len(alive_list) >= required_slots,
    )


def control_plan(
    puzzle: Puzzle, slot_names: Sequence[str], required_slots: int
) -> ShardPlan:
    """The plan for the control cell: the slots hold nothing.

    Every clue is rendered in the observation as it always was, so the
    round is solvable whatever the alive count is. The slots still exist
    and are still revoked on a wrong answer — that is what makes this the
    cell the threshold is read against. ``required_slots`` / ``capacity``
    are recorded so the two cells' rows line up column for column; here
    they describe the round, not a constraint the cell is under.
    """
    if required_slots < 1:
        raise ValueError(
            f"required_slots must be at least 1, got {required_slots}."
        )
    minimal = [c for c in puzzle.clues if c.signal in puzzle.minimal_clue_signals]
    return ShardPlan(
        shard_map={s: [] for s in slot_names},
        threshold=required_slots,
        required_slots=required_slots,
        capacity=max(1, math.ceil(len(minimal) / required_slots)),
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
        slot: render("subagent_clue.j2", slot=slot, clues=list(clues)).strip()
        for slot, clues in plan.shard_map.items()
    }
