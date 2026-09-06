"""Conditions, decision-list evaluation and shape rendering (spec §3, §7)."""

from __future__ import annotations

import pytest

from squid_game.tasks.signal_game.puzzle import (
    ATOMS,
    CONDITION_BY_LABEL,
    CONDITIONS_BY_ARITY,
    CONJUNCTION_BY_ATOMS,
    CONJUNCTIONS,
    EQ_ATOMS,
    FULL_MASK,
    SIGNAL_INDEX,
    SIGNAL_SPACE,
    PuzzleRule,
    render_shape_block,
    render_shape_hint,
    shape_label,
)
from squid_game.tasks.signal_game.rules import ACTIONS
from squid_game.tasks.signal_game.signals import Signal


def _cond(label: str):
    return CONDITION_BY_LABEL[label]


class TestConditions:
    def test_counts(self) -> None:
        assert len(ATOMS) == 20
        assert len(EQ_ATOMS) == 12
        assert len(CONJUNCTIONS) == 112
        assert len(CONDITIONS_BY_ARITY[1]) == 20
        assert len(CONDITIONS_BY_ARITY[2]) == 112

    def test_no_condition_is_constant(self) -> None:
        for c in ATOMS + CONJUNCTIONS:
            assert 0 < c.mask < FULL_MASK, c.label

    def test_masks_match_definitions(self) -> None:
        red = _cond('color == "red"')
        for i, sig in enumerate(SIGNAL_SPACE):
            assert bool(red.mask >> i & 1) == (sig.color == "red")
        ge3 = _cond("number >= 3")
        for i, sig in enumerate(SIGNAL_SPACE):
            assert bool(ge3.mask >> i & 1) == (sig.number >= 3)
        odd = _cond("number % 2 == 1")
        for i, sig in enumerate(SIGNAL_SPACE):
            assert bool(odd.mask >> i & 1) == (sig.number % 2 == 1)

    def test_conjunctions_pair_different_attributes(self) -> None:
        for c in CONJUNCTIONS:
            assert c.arity == 2
            assert len(set(c.attrs)) == 2
        assert all(a.arity == 1 for a in ATOMS)

    def test_conjunction_lookup_by_atom_labels(self) -> None:
        c = CONJUNCTION_BY_ATOMS[frozenset({'color == "red"', "number >= 3"})]
        assert c.mask == _cond('color == "red"').mask & _cond("number >= 3").mask
        assert c.label == 'color == "red" and number >= 3'

    def test_signal_index_round_trip(self) -> None:
        for i, sig in enumerate(SIGNAL_SPACE):
            assert SIGNAL_INDEX[sig] == i


class TestPuzzleRule:
    def _rule(self) -> PuzzleRule:
        return PuzzleRule(
            clauses=(
                (_cond('color == "red"'), "stay"),
                (_cond("number == 3"), "go_left"),
            ),
            else_action="jump",
        )

    def test_first_matching_clause_wins(self) -> None:
        rule = self._rule()
        # red AND number 3: both clauses hold, the first decides.
        assert rule.evaluate(Signal("red", "star", 3)) == "stay"
        assert rule.evaluate(Signal("blue", "star", 3)) == "go_left"
        assert rule.evaluate(Signal("blue", "star", 1)) == "jump"

    def test_vector_matches_evaluate(self) -> None:
        rule = self._rule()
        assert len(rule.vector) == 64
        for i, sig in enumerate(SIGNAL_SPACE):
            assert rule.vector[i] == rule.evaluate(sig)

    def test_shape_and_description(self) -> None:
        rule = self._rule()
        assert rule.shape == (1, 1)
        assert rule.description == (
            'if color == "red": stay; elif number == 3: go_left; else: jump'
        )

    def test_overlap_count(self) -> None:
        rule = self._rule()
        assert rule.overlap_count(Signal("red", "star", 3)) == 2
        assert rule.overlap_count(Signal("red", "star", 1)) == 1
        assert rule.overlap_count(Signal("blue", "star", 1)) == 0

    def test_region_masks_partition_the_grid(self) -> None:
        rule = self._rule()
        regions = rule.region_masks()
        assert len(regions) == 3  # two clauses + else
        union = 0
        for r in regions:
            assert union & r == 0
            union |= r
        assert union == FULL_MASK

    def test_actions_must_be_valid(self) -> None:
        with pytest.raises(ValueError):
            PuzzleRule(clauses=((_cond('color == "red"'), "fly"),), else_action="jump")
        with pytest.raises(ValueError):
            PuzzleRule(clauses=(), else_action="jump")


class TestRendering:
    def test_shape_label(self) -> None:
        assert shape_label((1, 2, 1)) == "1,2,1"

    def test_shape_block(self) -> None:
        out = render_shape_block((1, 2, 1))
        assert out == (
            "if ___:\n"
            "    action = ___\n"
            "elif ___ and ___:\n"
            "    action = ___\n"
            "elif ___:\n"
            "    action = ___\n"
            "else:\n"
            "    action = ___"
        )

    def test_shape_block_single_clause(self) -> None:
        assert render_shape_block((1,)) == (
            "if ___:\n    action = ___\nelse:\n    action = ___"
        )

    def test_shape_hint_one_line(self) -> None:
        assert render_shape_hint((1, 2)) == "if ___: ___; elif ___ and ___: ___; else: ___"
        assert "\n" not in render_shape_hint((2, 1, 1))
