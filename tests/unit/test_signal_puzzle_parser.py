"""Parsing the agent's Python-style RULE line (spec §8)."""

from __future__ import annotations

import pytest

from squid_game.tasks.signal_game.puzzle import (
    CONDITION_BY_LABEL,
    CONJUNCTION_BY_ATOMS,
    PuzzleRule,
    functional_match_score,
    parse_rule_text,
    render_shape_hint,
)


def _c(label: str):
    # CONDITION_BY_LABEL keys carry the canonical operand order (ATOMS order);
    # accept either order for conjunctions so the fixture reads naturally.
    cond = CONDITION_BY_LABEL.get(label)
    if cond is None and " and " in label:
        cond = CONJUNCTION_BY_ATOMS[frozenset(label.split(" and "))]
    assert cond is not None, label
    return cond


TRUTH = PuzzleRule(
    clauses=(
        (_c('color == "red"'), "stay"),
        (_c('number >= 3 and shape == "star"'), "go_left"),
        (_c("number <= 1"), "jump"),
    ),
    else_action="go_right",
)


class TestExactForms:
    def test_canonical_one_liner_round_trips(self) -> None:
        parsed = parse_rule_text("RULE: " + TRUTH.description)
        assert parsed is not None
        assert parsed.vector == TRUTH.vector
        assert parsed.shape == TRUTH.shape

    def test_multiline_python_block(self) -> None:
        text = (
            'if color == "red":\n    action = stay\n'
            'elif number >= 3 and shape == "star":\n    action = go_left\n'
            "elif number <= 1:\n    action = jump\n"
            "else:\n    action = go_right"
        )
        parsed = parse_rule_text(text)
        assert parsed is not None and parsed.vector == TRUTH.vector

    def test_unquoted_values_and_single_quotes(self) -> None:
        text = "if color == red: stay; elif number >= 3 and shape == 'star': go_left; elif number <= 1: jump; else: go_right"
        parsed = parse_rule_text(text)
        assert parsed is not None and parsed.vector == TRUTH.vector

    def test_reversed_conjunction_operands(self) -> None:
        text = 'if color == "red": stay; elif shape == "star" and number >= 3: go_left; elif number <= 1: jump; else: go_right'
        parsed = parse_rule_text(text)
        assert parsed is not None and parsed.vector == TRUTH.vector

    def test_v1_style_is_and_otherwise(self) -> None:
        text = "if color is red then stay; else if number is 3 then go_left; otherwise jump"
        parsed = parse_rule_text(text)
        assert parsed is not None
        assert parsed.shape == (1, 1)
        assert parsed.evaluate(_sig("red", "star", 3)) == "stay"
        assert parsed.evaluate(_sig("blue", "star", 3)) == "go_left"
        assert parsed.evaluate(_sig("blue", "star", 1)) == "jump"

    def test_parity_and_case_insensitive(self) -> None:
        text = "IF Number % 2 == 0: Jump; ELSE: Stay"
        parsed = parse_rule_text(text)
        assert parsed is not None
        assert parsed.evaluate(_sig("red", "star", 2)) == "jump"
        assert parsed.evaluate(_sig("red", "star", 1)) == "stay"

    def test_action_equals_prefix_and_trailing_text(self) -> None:
        text = 'RULE: if shape == "circle": action = go_left; else: action = stay  (my best guess)'
        parsed = parse_rule_text(text)
        assert parsed is not None and parsed.shape == (1,)


class TestProseAndSpacingVariants:
    """Spec §8 tolerance: v1 prose comparators, parity words, British spelling, spacing."""

    @pytest.mark.parametrize(
        ("text", "expected"),
        [
            (
                "if number is at least 3: jump; else: stay",
                PuzzleRule(clauses=((_c("number >= 3"), "jump"),), else_action="stay"),
            ),
            (
                "if number is at most 2: jump; else: stay",
                PuzzleRule(clauses=((_c("number <= 2"), "jump"),), else_action="stay"),
            ),
            (
                "if number is odd: jump; else: stay",
                PuzzleRule(clauses=((_c("number % 2 == 1"), "jump"),), else_action="stay"),
            ),
            (
                "if number is even: jump; else: stay",
                PuzzleRule(clauses=((_c("number % 2 == 0"), "jump"),), else_action="stay"),
            ),
            (
                'if colour == "red": jump; else: stay',
                PuzzleRule(clauses=((_c('color == "red"'), "jump"),), else_action="stay"),
            ),
            (
                "if number>=3: jump; else: stay",
                PuzzleRule(clauses=((_c("number >= 3"), "jump"),), else_action="stay"),
            ),
        ],
    )
    def test_variant_matches_intended_rule(self, text: str, expected: PuzzleRule) -> None:
        parsed = parse_rule_text(text)
        assert parsed is not None, text
        assert parsed.vector == expected.vector, text
        assert parsed.shape == expected.shape, text

    def test_at_least_at_most_evaluate(self) -> None:
        at_least = parse_rule_text("if number is at least 3: jump; else: stay")
        assert at_least is not None
        assert at_least.evaluate(_sig("red", "star", 3)) == "jump"
        assert at_least.evaluate(_sig("red", "star", 2)) == "stay"
        at_most = parse_rule_text("if number is at most 2: jump; else: stay")
        assert at_most is not None
        assert at_most.evaluate(_sig("red", "star", 2)) == "jump"
        assert at_most.evaluate(_sig("red", "star", 3)) == "stay"


class TestAmbiguousTrailingText:
    @pytest.mark.parametrize(
        "text",
        [
            "if color == red: go_left is wrong, go_right; else: stay",
            'if color == "red": stay; else: jump  -- or maybe go_left',
        ],
    )
    def test_second_action_token_in_remainder_is_refused(self, text: str) -> None:
        assert parse_rule_text(text) is None

    def test_harmless_trailing_prose_still_parses(self) -> None:
        parsed = parse_rule_text('if color == "red": stay  (my best guess); else: jump')
        assert parsed is not None
        assert parsed.shape == (1,)
        assert parsed.evaluate(_sig("red", "star", 1)) == "stay"
        assert parsed.evaluate(_sig("blue", "star", 1)) == "jump"


class TestFailures:
    @pytest.mark.parametrize(
        "text",
        [
            "",
            "no rule",
            "exploring",
            "if color == purple: stay; else: jump",  # unknown value
            "if number == 7: stay; else: jump",  # off grid
            'if color == "red": fly; else: jump',  # unknown action
            'if color == "red": stay',  # missing else
            'if color == "red" and color == "blue": stay; else: jump',  # same attribute
            "else: jump",  # no clause
        ],
    )
    def test_returns_none(self, text: str) -> None:
        assert parse_rule_text(text) is None

    def test_shape_mismatch_still_parses(self) -> None:
        parsed = parse_rule_text('if color == "red": stay; else: jump')
        assert parsed is not None
        assert parsed.shape != TRUTH.shape


class TestFunctionalScore:
    def test_identical_is_100(self) -> None:
        assert functional_match_score(TRUTH, TRUTH) == 100.0

    def test_partial(self) -> None:
        hyp = parse_rule_text('if color == "red": stay; else: go_right')
        assert hyp is not None
        score = functional_match_score(hyp, TRUTH)
        assert 0.0 < score < 100.0
        agree = sum(a == b for a, b in zip(hyp.vector, TRUTH.vector))
        assert score == pytest.approx(100.0 * agree / 64)

    def test_hint_for_truth_shape(self) -> None:
        assert render_shape_hint(TRUTH.shape) == "if ___: ___; elif ___ and ___: ___; elif ___: ___; else: ___"


def _sig(color: str, shape: str, number: int):
    from squid_game.tasks.signal_game.signals import Signal

    return Signal(color, shape, number)
