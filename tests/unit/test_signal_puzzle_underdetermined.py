"""Underdetermined turns: reachability primitive and query candidate actions.

Spec: docs/history/specs/2026-09-06-signal-puzzle-underdetermined-turns-design.md
"""

from __future__ import annotations

import pytest

from squid_game.tasks.signal_game.puzzle import (
    SIGNAL_SPACE,
    Clue,
    PuzzleSpec,
    candidate_actions,
    cached_puzzle,
    enumerate_shape,
    exists_consistent,
    generate_puzzle,
    puzzle_rng,
)
from squid_game.tasks.signal_game.rules import ACTIONS
from squid_game.tasks.signal_game.signals import Signal


def _brute_consistent(shape, clues):
    """Every decision list of *shape* agreeing with *clues* (test oracle)."""
    for rule in enumerate_shape(shape):
        if all(rule.evaluate(c.signal) == c.action for c in clues):
            yield rule


class TestExistsConsistent:
    def test_single_clue_is_satisfiable(self) -> None:
        clues = [Clue(Signal(color="red", shape="star", number=3), "jump")]
        assert exists_consistent((1,), clues) is True

    def test_agrees_with_brute_force_on_random_clue_sets(self) -> None:
        rng = __import__("random").Random(7)
        for _ in range(40):
            shape = (1,)
            signals = rng.sample(SIGNAL_SPACE, 3)
            clues = [Clue(s, rng.choice(ACTIONS)) for s in signals]
            expected = any(True for _ in _brute_consistent(shape, clues))
            assert exists_consistent(shape, clues) is expected, clues

    def test_unsatisfiable_clue_set(self) -> None:
        # Shape (1,) can split the grid two ways at most; three clues that
        # demand three different actions cannot be served by one clause + else.
        clues = [
            Clue(Signal(color="red", shape="star", number=1), "jump"),
            Clue(Signal(color="blue", shape="circle", number=2), "stay"),
            Clue(Signal(color="green", shape="square", number=4), "go_left"),
        ]
        assert exists_consistent((1,), clues) is False

    def test_contradictory_clues_on_one_signal(self) -> None:
        sig = Signal(color="red", shape="star", number=3)
        assert exists_consistent((1,), [Clue(sig, "jump"), Clue(sig, "stay")]) is False


class TestCandidateActions:
    def test_unique_puzzle_has_exactly_one_candidate(self) -> None:
        spec = PuzzleSpec(turn=3, clauses=2, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=1)
        puzzle = generate_puzzle(puzzle_rng(11, 3), spec)
        cands = candidate_actions(puzzle.shape, puzzle.clues, puzzle.query)
        assert cands == (puzzle.correct_action,)

    def test_agrees_with_brute_force(self) -> None:
        spec = PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(5, 1), spec)
        shown = list(puzzle.clues)[:-1]          # drop one clue -> may split
        expected = tuple(
            a for a in ACTIONS
            if any(r.evaluate(puzzle.query) == a for r in _brute_consistent(puzzle.shape, shown))
        )
        assert candidate_actions(puzzle.shape, shown, puzzle.query) == expected

    def test_truth_action_is_always_a_candidate(self) -> None:
        spec = PuzzleSpec(turn=4, clauses=2, conjunctions=0, predicates=True,
                          overlap_query=True, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(23, 4), spec)
        for i in range(len(puzzle.clues)):
            shown = [c for j, c in enumerate(puzzle.clues) if j != i]
            assert puzzle.correct_action in candidate_actions(
                puzzle.shape, shown, puzzle.query
            )

    def test_returns_actions_in_canonical_order(self) -> None:
        spec = PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(5, 1), spec)
        cands = candidate_actions(puzzle.shape, list(puzzle.clues)[:1], puzzle.query)
        assert list(cands) == [a for a in ACTIONS if a in cands]
