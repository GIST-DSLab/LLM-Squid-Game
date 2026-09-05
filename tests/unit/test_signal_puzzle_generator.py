"""Unique-answer puzzle generation (spec §5)."""

from __future__ import annotations

import random

import pytest

from squid_game.tasks.signal_game.puzzle import (
    Clue,
    Puzzle,
    PuzzleGenerationError,
    TierSpec,
    consistent_hypotheses,
    enumerate_hypotheses,
    generate_puzzle,
    make_rule_a,
    puzzle_rng,
)
from squid_game.tasks.signal_game.signals import Signal

WIDE = TierSpec(tier=1, families=("A",), n_clues=3, h_lo=1, h_hi=10**6)
MIXED = TierSpec(tier=5, families=("A", "B", "C", "D"), n_clues=3, h_lo=1, h_hi=10**6)


def _brute_force_unique(puzzle: Puzzle) -> bool:
    truth = puzzle.correct_action
    for h in enumerate_hypotheses():
        if all(h.evaluate(c.signal) == c.action for c in puzzle.clues):
            if h.evaluate(puzzle.query) != truth:
                return False
    return True


class TestClue:
    def test_str_uses_arrow(self) -> None:
        assert str(Clue(Signal("red", "circle", 2), "jump")) == (
            "red circle with number 2 → jump"
        )


class TestConsistentHypotheses:
    def test_single_clue_keeps_only_agreeing_rules(self) -> None:
        clue = Clue(Signal("red", "circle", 1), "jump")
        hs = consistent_hypotheses((clue,))
        assert hs
        assert all(h.evaluate(clue.signal) == "jump" for h in hs)

    def test_result_is_deduplicated_by_function(self) -> None:
        clue = Clue(Signal("red", "circle", 4), "jump")
        hs = consistent_hypotheses((clue,))
        assert len({h.vector for h in hs}) == len(hs)

    def test_explicit_hypothesis_pool(self) -> None:
        pool = [make_rule_a("color", "red", "jump", "stay"), make_rule_a("shape", "star", "jump", "stay")]
        hs = consistent_hypotheses((Clue(Signal("red", "circle", 1), "jump"),), hypotheses=pool)
        assert [h.description for h in hs] == ["If color is red then jump, otherwise stay."]


class TestGeneratePuzzle:
    def test_shape(self) -> None:
        p = generate_puzzle(random.Random(0), WIDE)
        assert isinstance(p, Puzzle)
        assert p.tier == 1
        assert p.rule.family == "A"
        assert len(p.clues) == 3
        assert p.query not in {c.signal for c in p.clues}
        assert len({c.signal for c in p.clues}) == 3
        assert p.correct_action == p.rule.evaluate(p.query)
        assert p.n_consistent >= 1

    def test_clues_are_not_all_the_same_action(self) -> None:
        for seed in range(30):
            p = generate_puzzle(random.Random(seed), MIXED)
            assert len({c.action for c in p.clues}) >= 2

    @pytest.mark.parametrize("spec", [WIDE, MIXED])
    def test_query_answer_is_unique_brute_force(self, spec: TierSpec) -> None:
        for seed in range(40):
            p = generate_puzzle(random.Random(seed), spec)
            assert _brute_force_unique(p), (seed, p.rule.description, p.clues, p.query)

    def test_n_consistent_matches_brute_force(self) -> None:
        p = generate_puzzle(random.Random(3), MIXED)
        n = len({h.vector for h in enumerate_hypotheses()
                 if all(h.evaluate(c.signal) == c.action for c in p.clues)})
        assert p.n_consistent == n

    def test_respects_h_band(self) -> None:
        spec = TierSpec(tier=2, families=("A",), n_clues=2, h_lo=3, h_hi=10**6)
        for seed in range(20):
            p = generate_puzzle(random.Random(seed), spec)
            assert p.n_consistent >= 3

    def test_relaxes_clue_count_when_spec_is_impossible(self) -> None:
        # One clue can never show two distinct actions, so the first pass
        # must fail and the generator must add clues. Two clues never pin
        # the query answer either (0 hits in 3,000 sampled family-A draws),
        # so the relax loop has to climb past 2 before it can return.
        spec = TierSpec(tier=1, families=("A",), n_clues=1, h_lo=1, h_hi=10**6)
        p = generate_puzzle(random.Random(0), spec)
        assert len(p.clues) > spec.n_clues
        assert _brute_force_unique(p)

    def test_raises_when_hopeless(self) -> None:
        # h_hi=0 can never be satisfied; every pass (3..6 clues) must fail.
        spec = TierSpec(tier=1, families=("A",), n_clues=3, h_lo=1, h_hi=0)
        with pytest.raises(PuzzleGenerationError):
            generate_puzzle(random.Random(0), spec)

    def test_only_requested_families_are_sampled(self) -> None:
        spec = TierSpec(tier=3, families=("B",), n_clues=4, h_lo=1, h_hi=10**6)
        for seed in range(10):
            assert generate_puzzle(random.Random(seed), spec).rule.family == "B"


class TestPuzzleRng:
    def test_same_seed_and_turn_same_puzzle(self) -> None:
        a = generate_puzzle(puzzle_rng(42, 7), MIXED)
        b = generate_puzzle(puzzle_rng(42, 7), MIXED)
        assert a == b

    def test_turn_changes_puzzle(self) -> None:
        a = generate_puzzle(puzzle_rng(42, 7), MIXED)
        b = generate_puzzle(puzzle_rng(42, 8), MIXED)
        assert a != b

    def test_seed_changes_puzzle(self) -> None:
        a = generate_puzzle(puzzle_rng(42, 7), MIXED)
        b = generate_puzzle(puzzle_rng(43, 7), MIXED)
        assert a != b

    def test_none_seed_is_deterministic(self) -> None:
        assert generate_puzzle(puzzle_rng(None, 1), MIXED) == generate_puzzle(puzzle_rng(None, 1), MIXED)
