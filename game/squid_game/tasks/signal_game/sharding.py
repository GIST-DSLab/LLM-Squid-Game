"""Clue sharding for the subagent-kill design (spec §5).

Each round the puzzle's examples stop being a list in the observation and
become a pile of examples per alive subagent slot. The knob is the round's
**required slots** ``R_t``: the task can be solved only while at least
``R_t`` subagents survive.

The deal makes that rule true by construction rather than approximately:

1. ``R_eff = min(R_t, |M|)`` where ``M`` is the round's load-bearing clue
   set (``puzzle.minimal_clue_signals``). When a rung carries fewer
   load-bearing clues than ``R_t``, no deal can make ``R_t`` slots
   necessary, so the round's effective threshold is the smaller number and
   both are recorded.
2. The shuffled ``M`` is dealt round-robin into exactly ``R_eff`` piles:
   every pile is non-empty and pile sizes differ by at most one.
3. The alive slots are taken in canonical order and shuffled with the same
   seeded RNG. Pile *i* goes to the *i*-th alive slot; if there is no
   *i*-th alive slot, that pile is **unreachable** this round.
4. Redundant clues fill the alive slots that drew no pile, round-robin, at
   most ``capacity`` (the largest pile size) each, so no slot's example
   count tells the player whether it is holding a pile.

Under ``main_holds_bundle`` (the team-wallet design, plan 2026-09-17 §4)
the main agent joins the deal as a recipient, **first** in line: the piles
go over ``["main"] + alive_slots``, main's pile is rendered inline in the
observation and the round is solvable while ``1 + n_alive >= R_eff``. The
number of *subagents* the round needs is then ``R_eff - 1``, recorded as
``required_subagents``; ``required_slots`` / ``required_slots_effective``
keep meaning "how many bundles", which is one more. With the flag off
nothing about the deal changes -- main holds no bundle, ``main_clues`` is
empty and ``required_subagents == required_slots_effective``.

Hence ``reachable == |M|`` exactly when ``n_alive >= R_eff``: losing a slot
below the threshold always strands a whole pile, and staying at or above it
never strands one. A fixed capacity cannot do this — it was also what made
the earlier draft measure a floor, since the rungs carry 4, 5, 7 … 34
load-bearing clues and five slots at one clue each left rung 4 onward
unsolvable with every slot alive.

Nothing here tells the agent how many clues matter or how many slots the
round needs: ``required_slots`` / ``required_slots_effective`` /
``threshold`` / ``solvable_with_alive_slots`` are recorded in
``task_metadata`` only.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from typing import Sequence

from squid_game.tasks.signal_game.puzzle import Clue, Puzzle


@dataclass(frozen=True)
class ShardPlan:
    """Who holds what this round, and what that leaves out of reach.

    Attributes:
        shard_map: Every slot name → the clue texts it holds, possibly
            empty. Dead slots and alive slots that drew nothing both map
            to ``[]``; the rendered prompt is the same either way, so a
            dead slot's silence is not a signal about the clue set.
        threshold: The number of slots the round actually needs — the
            same number as ``required_slots_effective``, under the name
            the design reads.
        required_slots: ``R_t`` for this round, from the season's
            schedule, as stated.
        required_slots_effective: ``min(R_t, |M|)`` — what the deal could
            make necessary. Equal to ``required_slots`` on every rung with
            at least ``R_t`` load-bearing clues, which is every rung from
            3 on at the design's five slots.
        capacity: The largest pile size, ``ceil(|M| / R_eff)``. Also the
            per-slot cap on redundant clues, so a pile-holding slot and an
            extras-holding slot look alike from the outside.
        reachable_clues: Load-bearing clues in piles that reached a slot.
        unreachable_clues: ``|M| - reachable_clues`` — the clues in piles
            that ran out of alive slots. (``|M|`` is therefore
            ``reachable_clues + unreachable_clues``; it is not stored
            separately, and it is NOT ``threshold``.)
        solvable_with_alive_slots: ``reachable_clues == |M|``, which by the
            construction above is exactly
            ``n_alive >= required_subagents``. When False the round is
            graded against the true rule anyway (as in ``underdetermined``
            mode), so analyses must condition on this column before
            computing accuracy.
        main_clues: The pile the MAIN agent holds, rendered inline in the
            observation. Empty unless ``main_holds_bundle``; it is NOT a
            key of ``shard_map``, which names subagent slots only.
        main_holds_bundle: Whether the main agent was a recipient of this
            deal. Off by default, and off every other field is what it was
            before this flag existed.
        required_subagents: How many SUBAGENTS the round needs —
            ``required_slots_effective - 1`` when main holds a bundle (main
            is one of the holders), ``required_slots_effective`` otherwise.
            This is the number ``solvable_with_alive_slots`` compares
            ``n_alive`` against in both modes.
    """

    shard_map: dict[str, list[str]]
    threshold: int
    required_slots: int
    required_slots_effective: int
    capacity: int
    reachable_clues: int
    unreachable_clues: int
    solvable_with_alive_slots: bool
    main_clues: list[str] = field(default_factory=list)
    main_holds_bundle: bool = False
    required_subagents: int = 0


def _alive_in_canonical_order(
    slot_names: Sequence[str], alive: Sequence[str]
) -> list[str]:
    """The alive slots in ``slot_names`` order, refusing unknown names.

    Canonical order first so the shuffle is the only source of order: the
    caller may pass ``alive`` in any order and gets one answer.
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


#: The main agent's name in the recipient list. Never a key of
#: ``shard_map`` — slots are ``clue-1`` .. ``clue-N`` and main is not a
#: slot, so the two can never collide.
_MAIN = "main"


def _effective_threshold(n_minimal: int, required_slots: int) -> int:
    """``min(R_t, |M|)`` — what the deal can actually make necessary."""
    return min(required_slots, n_minimal)


def _required_subagents(effective: int, main_holds_bundle: bool) -> int:
    """How many SUBAGENTS the round needs, given ``R_eff``.

    Main holds one of the bundles under the flag, so the slots supply one
    fewer; without it every bundle is a slot's.
    """
    return max(0, effective - 1) if main_holds_bundle else effective


def _piles(minimal: Sequence[Clue], n_piles: int) -> list[list[Clue]]:
    """*minimal* dealt round-robin into *n_piles* non-empty piles."""
    if n_piles < 1:
        return []
    piles: list[list[Clue]] = [[] for _ in range(n_piles)]
    for i, clue in enumerate(minimal):
        piles[i % n_piles].append(clue)
    return piles


def shard_clues(
    puzzle: Puzzle,
    slot_names: Sequence[str],
    alive: Sequence[str],
    seed: int | None,
    turn_number: int,
    required_slots: int,
    main_holds_bundle: bool = False,
) -> ShardPlan:
    """Deal *puzzle*'s clues so the round needs ``R_eff`` slots exactly.

    The load-bearing clues go into ``R_eff = min(required_slots, |M|)``
    piles and the piles go to the alive slots one each; a pile with no
    slot left to go to is stranded whole. Redundant clues then fill the
    alive slots that drew no pile.

    With *main_holds_bundle* the recipients are ``["main"] + alive_slots``
    instead of ``alive_slots``, main first. One rule covers both the piles
    and the redundant filling — recipient *i* takes pile *i*, and any
    recipient left over after the piles takes redundant clues — so main is
    filled exactly as a slot is. Because main is recipient 0 it takes pile
    0, the largest of the round-robin piles, whenever there is a pile at
    all: it can never look emptier than a subagent, and it only reaches the
    redundant fill in the degenerate ``R_eff == 0`` case the guard below
    rules out.

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
        required_slots: ``R_t`` — how many **bundles** the round asks
            for. Without *main_holds_bundle* that is the same as how many
            slots it asks for; with it, one of the bundles is main's, so
            the round asks for ``R_t - 1`` subagents.
        main_holds_bundle: Deal the main agent a pile too, first in line.

    Returns:
        A :class:`ShardPlan` in which ``solvable_with_alive_slots`` is
        ``True`` exactly when ``len(alive) >= required_subagents``.

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

    effective = _effective_threshold(len(minimal), required_slots)
    piles = _piles(minimal, effective)
    capacity = max((len(p) for p in piles), default=1)

    shard: dict[str, list[str]] = {s: [] for s in slot_names}
    main_clues: list[str] = []
    # One recipient list for the piles and the redundant fill alike. Without
    # the flag it is ``alive_list`` and every line below is what it always
    # was; with it main is prepended and takes pile 0.
    recipients = ([_MAIN] if main_holds_bundle else []) + alive_list

    def _give(who: str, clue_texts: list[str]) -> None:
        if who == _MAIN:
            main_clues.extend(clue_texts)
        else:
            shard[who].extend(clue_texts)

    stranded = 0
    for i, pile in enumerate(piles):
        if i < len(recipients):
            _give(recipients[i], [str(c) for c in pile])
        else:
            # No slot left for this pile: every clue in it is out of reach
            # this round, whatever the agent does.
            stranded += len(pile)

    # Redundant clues go to the recipients that drew no pile, capped at the
    # largest pile size so example counts do not mark the piles out.
    spare = recipients[len(piles):]
    if spare:
        for who, clue in zip(spare * capacity, extras):
            _give(who, [str(clue)])

    reachable = len(minimal) - stranded
    return ShardPlan(
        shard_map=shard,
        threshold=effective,
        required_slots=required_slots,
        required_slots_effective=effective,
        capacity=capacity,
        reachable_clues=reachable,
        unreachable_clues=stranded,
        solvable_with_alive_slots=reachable == len(minimal),
        main_clues=main_clues,
        main_holds_bundle=bool(main_holds_bundle),
        required_subagents=_required_subagents(effective, main_holds_bundle),
    )


def control_plan(
    puzzle: Puzzle,
    slot_names: Sequence[str],
    required_slots: int,
    main_holds_bundle: bool = False,
) -> ShardPlan:
    """The plan for the control cell: the slots hold nothing.

    Every clue is rendered in the observation as it always was, so the
    round is solvable whatever the alive count is. The slots still exist
    and are still revoked on a wrong answer — that is what makes this the
    cell the threshold is read against. The threshold columns describe the
    round, so the two cells' rows line up column for column; here they are
    not a constraint the cell is under.

    *main_holds_bundle* only sets the two bookkeeping columns here: the
    control cell renders every clue in the observation anyway, so there is
    no bundle to hand anybody and ``main_clues`` stays empty. It is
    accepted so the two cells' rows keep lining up column for column.
    """
    if required_slots < 1:
        raise ValueError(f"required_slots must be at least 1, got {required_slots}.")
    n_minimal = sum(
        1 for c in puzzle.clues if c.signal in puzzle.minimal_clue_signals
    )
    effective = _effective_threshold(n_minimal, required_slots)
    return ShardPlan(
        shard_map={s: [] for s in slot_names},
        threshold=effective,
        required_slots=required_slots,
        required_slots_effective=effective,
        capacity=math.ceil(n_minimal / effective) if effective else 1,
        reachable_clues=n_minimal,
        unreachable_clues=0,
        solvable_with_alive_slots=True,
        main_clues=[],
        main_holds_bundle=bool(main_holds_bundle),
        required_subagents=_required_subagents(effective, main_holds_bundle),
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
