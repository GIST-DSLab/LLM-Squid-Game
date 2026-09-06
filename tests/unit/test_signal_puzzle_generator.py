"""v2 generator: honest rules, unique function, minimal clues (spec §3.5, §4.3, §5)."""

from __future__ import annotations

import time

import pytest

from squid_game.tasks.signal_game.puzzle import (
    CONDITION_BY_LABEL,
    Puzzle,
    PuzzleGenerationError,
    PuzzleSpec,
    draw_shape,
    exists_differing,
    generate_puzzle,
    is_unique,
    minimal_clues,
    puzzle_rng,
    sample_rule,
)
from squid_game.tasks.signal_game.rules import ACTIONS

#: The spec §6 ladder, inline so this file does not depend on the YAML (Task 5).
LADDER = [
    PuzzleSpec(1, 1, 0, False, False, 2),
    PuzzleSpec(2, 1, 0, True, False, 1),
    PuzzleSpec(3, 2, 0, False, False, 1),
    PuzzleSpec(4, 2, 0, True, True, 0),
    PuzzleSpec(5, 3, 0, True, True, 0),
    PuzzleSpec(6, 3, 1, True, True, 0),
    PuzzleSpec(7, 4, 1, True, True, 0),
    PuzzleSpec(8, 4, 2, True, True, 0),
    PuzzleSpec(9, 5, 2, True, True, 0),
    PuzzleSpec(10, 6, 3, True, True, 0),
]


def _honest(rule) -> bool:
    regions = rule.region_masks()
    if any(r == 0 for r in regions):
        return False  # every clause reachable, else region non-empty
    acts = [a for _, a in rule.clauses]
    if any(x == y for x, y in zip(acts, acts[1:])):
        return False
    if acts[-1] == rule.else_action:
        return False
    labels = [c.label for c, _ in rule.clauses]
    return len(set(labels)) == len(labels)


class TestDrawShape:
    def test_arity_counts(self) -> None:
        for seed in range(20):
            shape = draw_shape(puzzle_rng(seed, 8), LADDER[7])
            assert len(shape) == 4
            assert shape.count(2) == 2
            assert set(shape) <= {1, 2}

    def test_conjunction_positions_vary(self) -> None:
        shapes = {draw_shape(puzzle_rng(s, 8), LADDER[7]) for s in range(30)}
        assert len(shapes) > 1


class TestSampleRule:
    @pytest.mark.parametrize("seed", range(10))
    def test_honesty_constraints(self, seed: int) -> None:
        rng = puzzle_rng(seed, 9)
        rule = sample_rule(rng, (1, 2, 1, 2, 1), predicates=True)
        assert rule.shape == (1, 2, 1, 2, 1)
        assert _honest(rule)

    def test_every_clause_matters(self) -> None:
        from squid_game.tasks.signal_game.puzzle import PuzzleRule

        rule = sample_rule(puzzle_rng(3, 5), (1, 1, 1), predicates=True)
        for i in range(3):
            shorter = PuzzleRule(
                clauses=tuple(c for j, c in enumerate(rule.clauses) if j != i),
                else_action=rule.else_action,
            )
            assert shorter.vector != rule.vector

    def test_predicates_false_uses_equality_only(self) -> None:
        for seed in range(15):
            rule = sample_rule(puzzle_rng(seed, 3), (1, 1), predicates=False)
            for cond, _ in rule.clauses:
                assert cond.kind == "eq"

    def test_predicates_true_eventually_uses_range_or_parity(self) -> None:
        kinds = set()
        for seed in range(40):
            rule = sample_rule(puzzle_rng(seed, 5), (1, 1, 1), predicates=True)
            kinds |= {cond.kind for cond, _ in rule.clauses}
        assert kinds & {"range", "parity"}


class TestMinimalClues:
    @pytest.mark.parametrize("seed", range(5))
    def test_minimal_set_is_unique_and_irreducible(self, seed: int) -> None:
        rng = puzzle_rng(seed, 4)
        rule = sample_rule(rng, (1, 1), predicates=True)
        from squid_game.tasks.signal_game.puzzle import SIGNAL_SPACE

        q = SIGNAL_SPACE[seed]  # any signal works as the query
        clues = minimal_clues(rng, (1, 1), rule, q)
        assert all(c.signal != q for c in clues)
        assert is_unique((1, 1), clues, rule)
        for drop in clues:
            rest = [c for c in clues if c != drop]
            assert exists_differing((1, 1), rest, rule.vector), "a clue was redundant"


class TestGeneratePuzzle:
    @pytest.mark.parametrize("seed", range(6))
    @pytest.mark.parametrize("spec", LADDER, ids=[f"turn{s.turn}" for s in LADDER])
    def test_every_rung(self, seed: int, spec: PuzzleSpec) -> None:
        pz = generate_puzzle(puzzle_rng(seed, spec.turn), spec)
        assert isinstance(pz, Puzzle)
        assert pz.spec == spec
        assert len(pz.shape) == spec.clauses
        assert pz.shape.count(2) == spec.conjunctions
        assert _honest(pz.rule)
        assert pz.query not in {c.signal for c in pz.clues}
        assert pz.correct_action == pz.rule.evaluate(pz.query)
        assert is_unique(pz.shape, pz.clues, pz.rule)
        assert len(pz.clues) == pz.n_minimal_clues + spec.extra_clues
        if spec.overlap_query:
            assert pz.query_overlap_count >= 2
        if not spec.predicates:
            # Every atomic operand is an equality test -- at any arity, so a future
            # `conjunctions > 0, predicates: false` rung stays legal.
            for cond, _ in pz.rule.clauses:
                for part in cond.label.split(" and "):
                    assert CONDITION_BY_LABEL[part].kind == "eq"
        # at least two distinct actions among the clues
        assert len({c.action for c in pz.clues}) >= 2

    def test_deterministic_per_seed_and_turn(self) -> None:
        a = generate_puzzle(puzzle_rng(42, 7), LADDER[6])
        b = generate_puzzle(puzzle_rng(42, 7), LADDER[6])
        c = generate_puzzle(puzzle_rng(43, 7), LADDER[6])
        assert a == b
        assert a != c

    def test_ladder_generation_time_budget(self) -> None:
        t0 = time.perf_counter()
        for spec in LADDER:
            generate_puzzle(puzzle_rng(0, spec.turn), spec)
        # Loose regression guard (spec §12), not the p50 budget: the same ten puzzles
        # are also generated by test_every_rung[turn*-0], so this only catches a
        # blow-up, and the bound must clear the slowest seed rather than the median.
        assert time.perf_counter() - t0 < 120.0

    def test_impossible_spec_raises(self) -> None:
        # 20 atoms cannot fill 25 distinct clauses.
        spec = PuzzleSpec(1, 25, 0, True, False, 0)
        with pytest.raises(PuzzleGenerationError):
            generate_puzzle(puzzle_rng(0, 1), spec)

    def test_overlap_requires_two_clauses(self) -> None:
        with pytest.raises(ValueError):
            PuzzleSpec(1, 1, 0, True, True, 0)
        with pytest.raises(ValueError):
            PuzzleSpec(1, 2, 3, True, False, 0)
