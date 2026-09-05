"""Hypothesis space for the per-turn puzzle mode (spec §4)."""

from __future__ import annotations

import pytest

from squid_game.tasks.signal_game.puzzle import (
    ATTR_VALUES,
    FAMILIES,
    SIGNAL_INDEX,
    SIGNAL_SPACE,
    PuzzleRule,
    count_distinct_functions,
    enumerate_hypotheses,
    make_rule_a,
    make_rule_b,
    make_rule_c,
    make_rule_d,
)
from squid_game.tasks.signal_game.rules import ACTIONS
from squid_game.tasks.signal_game.signals import Signal


class TestSignalSpace:
    def test_sixty_four_distinct_signals(self) -> None:
        assert len(SIGNAL_SPACE) == 64
        assert len(set(SIGNAL_SPACE)) == 64

    def test_index_round_trips(self) -> None:
        for i, sig in enumerate(SIGNAL_SPACE):
            assert SIGNAL_INDEX[sig] == i


class TestConstructors:
    def test_family_a_vector(self) -> None:
        rule = make_rule_a("color", "red", "jump", "stay")
        assert rule.family == "A"
        assert rule.description == "If color is red then jump, otherwise stay."
        assert rule.evaluate(Signal("red", "circle", 1)) == "jump"
        assert rule.evaluate(Signal("blue", "circle", 1)) == "stay"
        assert len(rule.vector) == 64

    def test_family_b_partial_branch(self) -> None:
        rule = make_rule_b("color", "red", "shape", "star", "jump", "go_left", "stay")
        assert rule.family == "B"
        assert rule.evaluate(Signal("red", "star", 1)) == "jump"
        assert rule.evaluate(Signal("red", "circle", 1)) == "go_left"
        assert rule.evaluate(Signal("blue", "star", 1)) == "stay"
        assert rule.description == (
            "If color is red AND shape is star then jump; "
            "if only color is red then go_left; otherwise stay."
        )

    def test_family_c_first_clause_wins(self) -> None:
        rule = make_rule_c("color", "red", "number", 3, "jump", "go_right", "stay")
        assert rule.family == "C"
        # both clauses hold -> first clause decides
        assert rule.evaluate(Signal("red", "circle", 3)) == "jump"
        assert rule.evaluate(Signal("blue", "circle", 3)) == "go_right"
        assert rule.evaluate(Signal("blue", "circle", 1)) == "stay"
        assert rule.description == (
            "If color is red then jump; else if number is 3 then go_right; "
            "otherwise stay."
        )

    def test_family_c_same_attribute_different_values(self) -> None:
        rule = make_rule_c("color", "red", "color", "blue", "jump", "go_right", "stay")
        assert rule.evaluate(Signal("red", "circle", 1)) == "jump"
        assert rule.evaluate(Signal("blue", "circle", 1)) == "go_right"
        assert rule.evaluate(Signal("green", "circle", 1)) == "stay"

    @pytest.mark.parametrize(
        "label, hits",
        [
            ("at least 3", {3, 4}),
            ("at most 2", {1, 2}),
            ("odd", {1, 3}),
            ("even", {2, 4}),
        ],
    )
    def test_family_d_predicates(self, label: str, hits: set[int]) -> None:
        rule = make_rule_d(label, "jump", "stay")
        assert rule.family == "D"
        for n in (1, 2, 3, 4):
            expected = "jump" if n in hits else "stay"
            assert rule.evaluate(Signal("red", "circle", n)) == expected
        assert rule.description == f"If number is {label} then jump, otherwise stay."

    def test_unknown_predicate_label_raises(self) -> None:
        with pytest.raises(ValueError):
            make_rule_d("prime", "jump", "stay")


class TestEnumeration:
    def test_family_counts_match_spec(self) -> None:
        rules = enumerate_hypotheses()
        by_family = {f: sum(r.family == f for r in rules) for f in FAMILIES}
        assert by_family == {"A": 144, "B": 2304, "C": 3168, "D": 96}
        assert len(rules) == 5712

    def test_enumeration_is_cached_and_frozen(self) -> None:
        assert enumerate_hypotheses() is enumerate_hypotheses()
        assert isinstance(enumerate_hypotheses(), tuple)

    def test_every_rule_uses_distinct_actions(self) -> None:
        for rule in enumerate_hypotheses():
            used = set(rule.vector)
            assert used <= set(ACTIONS)
            # a rule that maps every signal to one action is degenerate
            assert len(used) >= 2, rule.description

    def test_family_b_never_pairs_an_attribute_with_itself(self) -> None:
        for rule in enumerate_hypotheses():
            if rule.family == "B":
                assert " AND " in rule.description
                a1 = rule.description.split()[1]
                a2 = rule.description.split(" AND ")[1].split()[0]
                assert a1 != a2

    def test_distinct_functions_fewer_than_rules(self) -> None:
        rules = enumerate_hypotheses()
        n_fn = count_distinct_functions(rules)
        # family A "number is 4" == family D "at least 4", etc.
        assert n_fn < len(rules)
        assert n_fn > 5000

    def test_vectors_are_64_long(self) -> None:
        assert all(len(r.vector) == 64 for r in enumerate_hypotheses())
