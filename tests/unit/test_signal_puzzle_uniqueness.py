"""exists_differing agrees with exhaustive enumeration (spec §4)."""

from __future__ import annotations

import random

import pytest

from squid_game.tasks.signal_game.puzzle import (
    ATOMS,
    CONDITION_BY_LABEL,
    SIGNAL_SPACE,
    Clue,
    PuzzleRule,
    enumerate_shape,
    exists_differing,
    is_unique,
)
from squid_game.tasks.signal_game.rules import ACTIONS


def _cond(label: str):
    return CONDITION_BY_LABEL[label]


def _brute_force_differs(shape, clues, truth) -> bool:
    checks = [(SIGNAL_SPACE.index(c.signal), c.action) for c in clues]
    for rule in enumerate_shape(shape):
        vec = rule.vector
        if all(vec[i] == a for i, a in checks) and vec != truth:
            return True
    return False


class TestEnumerateShape:
    def test_single_clause_count(self) -> None:
        assert sum(1 for _ in enumerate_shape((1,))) == 20 * 4 * 4

    def test_two_clause_count(self) -> None:
        assert sum(1 for _ in enumerate_shape((1, 1))) == 20 * 20 * 4 * 4 * 4


class TestAgainstBruteForce:
    @pytest.mark.parametrize("seed", range(12))
    def test_single_clause_random_clue_sets(self, seed: int) -> None:
        rng = random.Random(seed)
        rule = PuzzleRule(
            clauses=((rng.choice(ATOMS), "stay"),), else_action="jump"
        )
        n = rng.randint(2, 8)
        sigs = rng.sample(SIGNAL_SPACE, n)
        clues = [Clue(s, rule.evaluate(s)) for s in sigs]
        assert exists_differing((1,), clues, rule.vector) == _brute_force_differs(
            (1,), clues, rule.vector
        )

    @pytest.mark.parametrize("seed", range(6))
    def test_two_clause_random_clue_sets(self, seed: int) -> None:
        rng = random.Random(100 + seed)
        a, b = rng.sample(ATOMS, 2)
        acts = rng.sample(ACTIONS, 3)
        rule = PuzzleRule(clauses=((a, acts[0]), (b, acts[1])), else_action=acts[2])
        n = rng.randint(3, 10)
        sigs = rng.sample(SIGNAL_SPACE, n)
        clues = [Clue(s, rule.evaluate(s)) for s in sigs]
        assert exists_differing((1, 1), clues, rule.vector) == _brute_force_differs(
            (1, 1), clues, rule.vector
        )


class TestKnownCases:
    def test_all_signals_as_clues_is_unique(self) -> None:
        rule = PuzzleRule(clauses=((_cond('color == "red"'), "stay"),), else_action="jump")
        clues = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE]
        assert is_unique((1,), clues, rule)

    def test_no_clues_is_not_unique(self) -> None:
        rule = PuzzleRule(clauses=((_cond('color == "red"'), "stay"),), else_action="jump")
        assert not is_unique((1,), [], rule)

    def test_one_clue_is_not_unique(self) -> None:
        rule = PuzzleRule(clauses=((_cond('color == "red"'), "stay"),), else_action="jump")
        clues = [Clue(SIGNAL_SPACE[0], rule.evaluate(SIGNAL_SPACE[0]))]
        assert not is_unique((1,), clues, rule)

    def test_priority_case_needs_a_disambiguating_clue(self) -> None:
        # red AND number 3 -> first clause (stay). Without any red-3 clue, a list
        # that swaps the two clauses is consistent and differs on red-3 signals.
        rule = PuzzleRule(
            clauses=((_cond('color == "red"'), "stay"), (_cond("number == 3"), "go_left")),
            else_action="jump",
        )
        clues = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE
                 if not (s.color == "red" and s.number == 3)]
        assert exists_differing((1, 1), clues, rule.vector)
        clues_all = [Clue(s, rule.evaluate(s)) for s in SIGNAL_SPACE]
        assert not exists_differing((1, 1), clues_all, rule.vector)
