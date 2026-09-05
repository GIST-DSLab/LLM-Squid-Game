"""Per-turn puzzle mode for the Signal Game (spec 2026-09-05).

Pure functions and frozen dataclasses only — no module state, no
template rendering. ``SignalGameModule`` (module.py) is the only caller
on the run path; ``scripts/dev/calibrate_signal_puzzle_ladder.py`` and
the unit tests call it directly.

Four stateless rule families over the 4x4x4 signal grid:

    A  single      If <attr> is <val> then X, otherwise Z.
    B  conjunction If <a1> is <v1> AND <a2> is <v2> then X; if only <a1> is <v1> then Y; otherwise Z.
    C  two_branch  If <a1> is <v1> then X; else if <a2> is <v2> then Y; otherwise Z.
    D  number_pred If number is <pred> then X, otherwise Z.

A rule is represented by its 64-entry action vector (one action per
signal in ``SIGNAL_SPACE`` order), which is what every downstream
computation — consistency with clues, uniqueness of the query answer,
functional match of an agent hypothesis — actually needs.
"""

from __future__ import annotations

import itertools
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from functools import lru_cache

from squid_game.tasks.signal_game.rules import ACTIONS
from squid_game.tasks.signal_game.signals import COLORS, NUMBERS, SHAPES, Signal

ATTRIBUTES: tuple[str, ...] = ("color", "shape", "number")
ATTR_VALUES: dict[str, list] = {"color": COLORS, "shape": SHAPES, "number": NUMBERS}
FAMILIES: tuple[str, ...] = ("A", "B", "C", "D")

#: Colour-major enumeration of every signal; the index is the position
#: every ``PuzzleRule.vector`` uses.
SIGNAL_SPACE: tuple[Signal, ...] = tuple(
    Signal(color=c, shape=s, number=n) for c in COLORS for s in SHAPES for n in NUMBERS
)
SIGNAL_INDEX: dict[Signal, int] = {sig: i for i, sig in enumerate(SIGNAL_SPACE)}

#: Family D predicates on the number attribute, keyed by the label that
#: appears in the rule description.
NUMBER_PREDICATES: tuple[tuple[str, Callable[[int], bool]], ...] = (
    ("at least 2", lambda n: n >= 2),
    ("at least 3", lambda n: n >= 3),
    ("at least 4", lambda n: n >= 4),
    ("at most 1", lambda n: n <= 1),
    ("at most 2", lambda n: n <= 2),
    ("at most 3", lambda n: n <= 3),
    ("odd", lambda n: n % 2 == 1),
    ("even", lambda n: n % 2 == 0),
)
_PREDICATE_BY_LABEL: dict[str, Callable[[int], bool]] = dict(NUMBER_PREDICATES)


@dataclass(frozen=True)
class PuzzleRule:
    """One hidden rule, materialised as its action vector."""

    family: str
    description: str
    vector: tuple[str, ...]

    def evaluate(self, signal: Signal) -> str:
        return self.vector[SIGNAL_INDEX[signal]]


def _vectorise(fn: Callable[[Signal], str]) -> tuple[str, ...]:
    return tuple(fn(sig) for sig in SIGNAL_SPACE)


def make_rule_a(attr: str, value: str | int, then_action: str, else_action: str) -> PuzzleRule:
    def fn(sig: Signal) -> str:
        return then_action if getattr(sig, attr) == value else else_action

    return PuzzleRule(
        family="A",
        description=f"If {attr} is {value} then {then_action}, otherwise {else_action}.",
        vector=_vectorise(fn),
    )


def make_rule_b(
    a1: str, v1: str | int, a2: str, v2: str | int,
    both_action: str, only_a1_action: str, else_action: str,
) -> PuzzleRule:
    def fn(sig: Signal) -> str:
        m1 = getattr(sig, a1) == v1
        m2 = getattr(sig, a2) == v2
        if m1 and m2:
            return both_action
        if m1:
            return only_a1_action
        return else_action

    return PuzzleRule(
        family="B",
        description=(
            f"If {a1} is {v1} AND {a2} is {v2} then {both_action}; "
            f"if only {a1} is {v1} then {only_a1_action}; otherwise {else_action}."
        ),
        vector=_vectorise(fn),
    )


def make_rule_c(
    a1: str, v1: str | int, a2: str, v2: str | int,
    first_action: str, second_action: str, else_action: str,
) -> PuzzleRule:
    def fn(sig: Signal) -> str:
        if getattr(sig, a1) == v1:
            return first_action
        if getattr(sig, a2) == v2:
            return second_action
        return else_action

    return PuzzleRule(
        family="C",
        description=(
            f"If {a1} is {v1} then {first_action}; "
            f"else if {a2} is {v2} then {second_action}; otherwise {else_action}."
        ),
        vector=_vectorise(fn),
    )


def make_rule_d(predicate_label: str, then_action: str, else_action: str) -> PuzzleRule:
    try:
        pred = _PREDICATE_BY_LABEL[predicate_label]
    except KeyError as exc:
        raise ValueError(f"unknown number predicate {predicate_label!r}") from exc

    def fn(sig: Signal) -> str:
        return then_action if pred(sig.number) else else_action

    return PuzzleRule(
        family="D",
        description=f"If number is {predicate_label} then {then_action}, otherwise {else_action}.",
        vector=_vectorise(fn),
    )


def _attr_value_pairs() -> list[tuple[str, str | int]]:
    return [(attr, val) for attr in ATTRIBUTES for val in ATTR_VALUES[attr]]


@lru_cache(maxsize=1)
def enumerate_hypotheses() -> tuple[PuzzleRule, ...]:
    """Every rule of every family with pairwise-distinct actions (5,712)."""
    rules: list[PuzzleRule] = []
    pairs = _attr_value_pairs()
    two_actions = list(itertools.permutations(ACTIONS, 2))
    three_actions = list(itertools.permutations(ACTIONS, 3))

    for attr, val in pairs:
        for x, z in two_actions:
            rules.append(make_rule_a(attr, val, x, z))

    for a1, a2 in itertools.permutations(ATTRIBUTES, 2):
        for v1 in ATTR_VALUES[a1]:
            for v2 in ATTR_VALUES[a2]:
                for x, y, z in three_actions:
                    rules.append(make_rule_b(a1, v1, a2, v2, x, y, z))

    for (a1, v1), (a2, v2) in itertools.permutations(pairs, 2):
        for x, y, z in three_actions:
            rules.append(make_rule_c(a1, v1, a2, v2, x, y, z))

    for label, _ in NUMBER_PREDICATES:
        for x, z in two_actions:
            rules.append(make_rule_d(label, x, z))

    return tuple(rules)


def count_distinct_functions(rules: Iterable[PuzzleRule]) -> int:
    """Number of distinct action vectors among *rules*."""
    return len({r.vector for r in rules})
