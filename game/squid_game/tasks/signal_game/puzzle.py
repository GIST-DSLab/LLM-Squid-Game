"""Per-turn puzzle mode for the Signal Game, v2 (spec 2026-09-06).

Every turn is an independent induction puzzle whose hidden rule is a
Python-style decision list::

    if <cond_1>: <act_1>
    elif <cond_2>: <act_2>
    ...
    else: <act_else>

The *shape* of the list (how many clauses, which of them are ``and``
conjunctions) is disclosed to the agent; the conditions and actions are
hidden. Clues are ``signal -> action`` pairs generated so that, within
the disclosed shape and the condition grammar below, every decision list
consistent with the clues computes the same function over all 64
signals. The query answer is therefore unique too.

Pure functions and frozen dataclasses only; ``SignalGameModule``
(module.py) is the only caller on the run path.

Grammar (spec §3):

    atomic     color == "red" | shape == "star" | number == 3        (12)
               number >= 2|3|4 | number <= 1|2|3                     (6)
               number % 2 == 1 | number % 2 == 0                     (2)
    conjunction <atomic> and <atomic> on two different attributes   (112)

Every condition is a 64-bit mask over ``SIGNAL_SPACE`` (colour-major);
a rule is its 64-entry action vector.
"""

from __future__ import annotations

import itertools
import random
import re
from collections.abc import Iterable
from dataclasses import dataclass, field

from squid_game.tasks.signal_game.rules import ACTIONS
from squid_game.tasks.signal_game.signals import COLORS, NUMBERS, SHAPES, Signal

ATTRIBUTES: tuple[str, ...] = ("color", "shape", "number")
ATTR_VALUES: dict[str, list] = {"color": COLORS, "shape": SHAPES, "number": NUMBERS}

#: Colour-major enumeration of every signal; the index is the bit position
#: in every mask and the position in every ``PuzzleRule.vector``.
SIGNAL_SPACE: tuple[Signal, ...] = tuple(
    Signal(color=c, shape=s, number=n) for c in COLORS for s in SHAPES for n in NUMBERS
)
SIGNAL_INDEX: dict[Signal, int] = {sig: i for i, sig in enumerate(SIGNAL_SPACE)}
FULL_MASK: int = (1 << len(SIGNAL_SPACE)) - 1


# ---------------------------------------------------------------------------
# Conditions
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Condition:
    """One test on a signal, as Python text plus its 64-bit mask.

    ``kind`` is ``"eq"`` / ``"range"`` / ``"parity"`` for atoms and
    ``"and"`` for conjunctions; ``attrs`` lists the attributes the test
    reads (one for atoms, two distinct ones for conjunctions).
    """

    label: str
    attrs: tuple[str, ...]
    mask: int
    kind: str

    @property
    def arity(self) -> int:
        return len(self.attrs)

    def holds(self, signal: Signal) -> bool:
        return bool(self.mask >> SIGNAL_INDEX[signal] & 1)


def _mask(pred) -> int:
    m = 0
    for i, sig in enumerate(SIGNAL_SPACE):
        if pred(sig):
            m |= 1 << i
    return m


def _build_atoms() -> tuple[Condition, ...]:
    out: list[Condition] = []
    for c in COLORS:
        out.append(Condition(f'color == "{c}"', ("color",), _mask(lambda s, c=c: s.color == c), "eq"))
    for sh in SHAPES:
        out.append(Condition(f'shape == "{sh}"', ("shape",), _mask(lambda s, sh=sh: s.shape == sh), "eq"))
    for n in NUMBERS:
        out.append(Condition(f"number == {n}", ("number",), _mask(lambda s, n=n: s.number == n), "eq"))
    for n in (2, 3, 4):
        out.append(Condition(f"number >= {n}", ("number",), _mask(lambda s, n=n: s.number >= n), "range"))
    for n in (1, 2, 3):
        out.append(Condition(f"number <= {n}", ("number",), _mask(lambda s, n=n: s.number <= n), "range"))
    out.append(Condition("number % 2 == 1", ("number",), _mask(lambda s: s.number % 2 == 1), "parity"))
    out.append(Condition("number % 2 == 0", ("number",), _mask(lambda s: s.number % 2 == 0), "parity"))
    return tuple(out)


ATOMS: tuple[Condition, ...] = _build_atoms()
EQ_ATOMS: tuple[Condition, ...] = tuple(a for a in ATOMS if a.kind == "eq")


def _build_conjunctions() -> tuple[Condition, ...]:
    out: list[Condition] = []
    for a, b in itertools.combinations(ATOMS, 2):
        if a.attrs[0] == b.attrs[0]:
            continue
        out.append(Condition(f"{a.label} and {b.label}", (a.attrs[0], b.attrs[0]), a.mask & b.mask, "and"))
    return tuple(out)


CONJUNCTIONS: tuple[Condition, ...] = _build_conjunctions()
CONDITIONS_BY_ARITY: dict[int, tuple[Condition, ...]] = {1: ATOMS, 2: CONJUNCTIONS}
CONDITION_BY_LABEL: dict[str, Condition] = {c.label: c for c in ATOMS + CONJUNCTIONS}
#: Conjunction lookup that ignores operand order: ``{a.label, b.label}`` -> condition.
CONJUNCTION_BY_ATOMS: dict[frozenset[str], Condition] = {
    frozenset(c.label.split(" and ")): c for c in CONJUNCTIONS
}


# ---------------------------------------------------------------------------
# Decision lists
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class PuzzleRule:
    """A decision list: ordered ``(condition, action)`` clauses plus an else action.

    Semantics are Python's: the first clause whose condition holds decides.
    ``vector`` is the action for every signal in ``SIGNAL_SPACE`` order.
    """

    clauses: tuple[tuple[Condition, str], ...]
    else_action: str
    vector: tuple[str, ...] = field(init=False, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not self.clauses:
            raise ValueError("a decision list needs at least one clause")
        for _, a in self.clauses:
            if a not in ACTIONS:
                raise ValueError(f"unknown action {a!r}")
        if self.else_action not in ACTIONS:
            raise ValueError(f"unknown action {self.else_action!r}")
        vec = []
        for i in range(len(SIGNAL_SPACE)):
            act = self.else_action
            for cond, a in self.clauses:
                if cond.mask >> i & 1:
                    act = a
                    break
            vec.append(act)
        object.__setattr__(self, "vector", tuple(vec))

    @property
    def shape(self) -> tuple[int, ...]:
        return tuple(cond.arity for cond, _ in self.clauses)

    def evaluate(self, signal: Signal) -> str:
        return self.vector[SIGNAL_INDEX[signal]]

    def overlap_count(self, signal: Signal) -> int:
        """How many clause conditions hold on *signal* (priority matters when >= 2)."""
        return sum(cond.holds(signal) for cond, _ in self.clauses)

    def region_masks(self) -> list[int]:
        """Signals decided by each clause in turn, then by ``else``; a partition of the grid."""
        covered = 0
        regions: list[int] = []
        for cond, _ in self.clauses:
            regions.append(cond.mask & ~covered)
            covered |= cond.mask
        regions.append(FULL_MASK & ~covered)
        return regions

    @property
    def description(self) -> str:
        parts = []
        for i, (cond, a) in enumerate(self.clauses):
            parts.append(f"{'if' if i == 0 else 'elif'} {cond.label}: {a}")
        parts.append(f"else: {self.else_action}")
        return "; ".join(parts)


def shape_label(shape: tuple[int, ...]) -> str:
    return ",".join(str(a) for a in shape)


def render_shape_block(shape: tuple[int, ...]) -> str:
    """The blanked Python skeleton shown in the observation (spec §7.2)."""
    lines: list[str] = []
    for i, arity in enumerate(shape):
        cond = " and ".join(["___"] * arity)
        lines.append(f"{'if' if i == 0 else 'elif'} {cond}:")
        lines.append("    action = ___")
    lines.append("else:")
    lines.append("    action = ___")
    return "\n".join(lines)


def render_shape_hint(shape: tuple[int, ...]) -> str:
    """One-line RULE template for the response format (spec §7.3)."""
    parts = []
    for i, arity in enumerate(shape):
        cond = " and ".join(["___"] * arity)
        parts.append(f"{'if' if i == 0 else 'elif'} {cond}: ___")
    parts.append("else: ___")
    return "; ".join(parts)


# ---------------------------------------------------------------------------
# Clues, specs, puzzles
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Clue:
    """One revealed signal->action pair shown to the agent."""

    signal: Signal
    action: str

    def __str__(self) -> str:
        return f"{self.signal} → {self.action}"


def puzzle_rng(seed: int | None, turn_number: int) -> random.Random:
    """Per-turn RNG derived from ``(seed, turn_number)`` only.

    A ``str`` seed is hashed with SHA-512 by ``random.seed``, so the
    stream is stable across processes and independent of
    ``PYTHONHASHSEED``. Keeping puzzle draws off the season RNG means the
    variable number of generator attempts never shifts any other
    consumer's stream (peer-death scheduler, legacy signal draws).
    """
    return random.Random(f"{seed}:{turn_number}")


# --- Task 2 appends: exists_differing / is_unique -------------------------
# --- Task 3 appends: PuzzleSpec / Puzzle / sample_rule / minimal_clues / generate_puzzle
# --- Task 4 appends: parse_rule_text / functional_match_score --------------
