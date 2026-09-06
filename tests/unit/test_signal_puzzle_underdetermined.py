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


from squid_game.tasks.signal_game.puzzle import generate_underdetermined_puzzle

#: One rung from each of the two scheduled blocks, plus the extremes of
#: what block A and B can ask for.
_UD_SPECS = [
    PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
               overlap_query=False, extra_clues=2, underdetermined=True,
               n_candidate_actions=2),
    PuzzleSpec(turn=3, clauses=2, conjunctions=0, predicates=False,
               overlap_query=False, extra_clues=1, underdetermined=True,
               n_candidate_actions=2),
    PuzzleSpec(turn=5, clauses=3, conjunctions=0, predicates=True,
               overlap_query=True, extra_clues=0, underdetermined=True,
               n_candidate_actions=2),
    PuzzleSpec(turn=6, clauses=3, conjunctions=1, predicates=True,
               overlap_query=True, extra_clues=0, underdetermined=True,
               n_candidate_actions=2),
]


class TestGenerateUnderdetermined:
    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_query_splits_exactly_two_ways(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        cands = candidate_actions(puzzle.shape, puzzle.clues, puzzle.query)
        assert len(cands) == 2
        assert puzzle.candidate_actions == cands
        assert puzzle.n_candidate_actions == 2

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_truth_is_among_the_candidates(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        assert puzzle.correct_action in puzzle.candidate_actions

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_dropped_clue_was_load_bearing_and_is_not_shown(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        assert puzzle.dropped_clue is not None
        assert puzzle.dropped_clue.signal not in {c.signal for c in puzzle.clues}
        # Putting it back must restore a single answer.
        restored = list(puzzle.clues) + [puzzle.dropped_clue]
        assert len(candidate_actions(puzzle.shape, restored, puzzle.query)) == 1

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_every_shown_clue_is_truthful(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        for clue in puzzle.clues:
            assert puzzle.rule.evaluate(clue.signal) == clue.action
        assert puzzle.query not in {c.signal for c in puzzle.clues}

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_clue_count_matches_the_unique_twin_when_padded(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        if puzzle.clue_count_padded:
            # The twin is the determined puzzle this one was carved from, which
            # is NOT generate_puzzle(puzzle_rng(42, turn), spec): the generator
            # resamples a fresh base whenever no single load-bearing drop splits
            # the query n_candidate_actions ways, and each base has its own
            # minimal-set size. A determined puzzle of any rung shows exactly
            # n_minimal + extra_clues clues, and padding restores that count
            # (one load-bearing clue out, one redundant clue in), so this is the
            # invariant the twin comparison was reaching for.
            assert len(puzzle.clues) == puzzle.n_minimal_clues + 1 + spec.extra_clues

    def test_unique_puzzle_reports_one_candidate(self) -> None:
        spec = PuzzleSpec(turn=5, clauses=3, conjunctions=0, predicates=True,
                          overlap_query=True, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(42, 5), spec)
        assert puzzle.candidate_actions == (puzzle.correct_action,)
        assert puzzle.n_candidate_actions == 1
        assert puzzle.dropped_clue is None
        assert puzzle.clue_count_padded is False

    def test_minimal_clue_signals_are_recorded(self) -> None:
        spec = PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=2)
        puzzle = generate_puzzle(puzzle_rng(42, 1), spec)
        assert len(puzzle.minimal_clue_signals) == puzzle.n_minimal_clues
        assert puzzle.minimal_clue_signals <= {c.signal for c in puzzle.clues}


class TestCachedPuzzleBranch:
    def test_spec_flag_separates_the_two_versions(self) -> None:
        unique = PuzzleSpec(turn=2, clauses=1, conjunctions=0, predicates=True,
                            overlap_query=False, extra_clues=1)
        under = PuzzleSpec(turn=2, clauses=1, conjunctions=0, predicates=True,
                           overlap_query=False, extra_clues=1,
                           underdetermined=True, n_candidate_actions=2)
        a = cached_puzzle(42, 2, unique)
        b = cached_puzzle(42, 2, under)
        assert a.n_candidate_actions == 1
        assert b.n_candidate_actions == 2
        assert cached_puzzle(42, 2, under) is b        # memoised

    def test_generation_is_deterministic(self) -> None:
        spec = PuzzleSpec(turn=3, clauses=2, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=1,
                          underdetermined=True, n_candidate_actions=2)
        first = generate_underdetermined_puzzle(puzzle_rng(99, 3), spec)
        second = generate_underdetermined_puzzle(puzzle_rng(99, 3), spec)
        assert first.rule.description == second.rule.description
        assert first.query == second.query
        assert [str(c) for c in first.clues] == [str(c) for c in second.clues]
