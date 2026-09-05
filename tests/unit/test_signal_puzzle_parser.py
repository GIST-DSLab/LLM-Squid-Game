"""Free-form RULE parsing + functional rule_match_score (spec §8)."""

from __future__ import annotations

import pytest

from squid_game.tasks.signal_game.puzzle import (
    enumerate_hypotheses,
    functional_match_score,
    make_rule_a,
    make_rule_c,
    parse_rule_text,
)


class TestParseRoundTrip:
    def test_every_enumerated_description_parses_to_itself(self) -> None:
        for rule in enumerate_hypotheses():
            parsed = parse_rule_text(rule.description)
            assert parsed is not None, rule.description
            assert parsed.family == rule.family
            assert parsed.vector == rule.vector, rule.description


class TestParseVariants:
    @pytest.mark.parametrize(
        "text",
        [
            "RULE: If color is red then jump, otherwise stay.",
            "if the color is red then jump otherwise stay",
            "If Color is RED then JUMP; otherwise STAY.",
            "If color is red then jump, else stay.",
        ],
    )
    def test_family_a_variants(self, text: str) -> None:
        parsed = parse_rule_text(text)
        assert parsed is not None
        assert parsed.vector == make_rule_a("color", "red", "jump", "stay").vector

    @pytest.mark.parametrize(
        "text",
        [
            "If number is at least 3 then jump, otherwise stay.",
            "If number >= 3 then jump, otherwise stay.",
            "If number is greater than or equal to 3 then jump, otherwise stay.",
            "If number is 3 or more then jump, otherwise stay.",
        ],
    )
    def test_family_d_variants(self, text: str) -> None:
        parsed = parse_rule_text(text)
        assert parsed is not None
        assert parsed.family == "D"
        assert parsed.description == "If number is at least 3 then jump, otherwise stay."

    def test_family_c_without_else_keyword(self) -> None:
        parsed = parse_rule_text("If color is red then jump; if number is 3 then go_right; otherwise stay.")
        assert parsed is not None
        assert parsed.vector == make_rule_c("color", "red", "number", 3, "jump", "go_right", "stay").vector

    def test_family_b_is_preferred_over_c_when_and_present(self) -> None:
        parsed = parse_rule_text(
            "If color is red AND shape is star then jump; if only color is red then go_left; otherwise stay."
        )
        assert parsed is not None and parsed.family == "B"

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "no rule",
            "exploring",
            "If colour is crimson then jump, otherwise stay.",   # unknown value
            "If number is 5 then jump, otherwise stay.",          # out-of-range value
            "If color is red then fly, otherwise stay.",          # unknown action
            "The rule seems to depend on color somehow.",
        ],
    )
    def test_unparseable_returns_none(self, text: str) -> None:
        assert parse_rule_text(text) is None

    @pytest.mark.parametrize(
        "text",
        [
            "If number is at least 1 then jump, otherwise stay.",
            "If number is at most 4 then jump, otherwise stay.",
            "If number >= 1 then jump, otherwise stay.",
            "If number <= 4 then jump, otherwise stay.",
            "If number is 1 or more then jump, otherwise stay.",
            "If number is 4 or less then jump, otherwise stay.",
        ],
    )
    def test_undefined_number_predicate_returns_none(self, text: str) -> None:
        # Grammatical, but always true over 1..4 -> not a hypothesis in the
        # space; the parser must return None, never raise.
        assert parse_rule_text(text) is None

    def test_degenerate_hypothesis_still_parses(self) -> None:
        # Agents may state a same-action rule; scoring handles it.
        parsed = parse_rule_text("If color is red then stay, otherwise stay.")
        assert parsed is not None
        assert set(parsed.vector) == {"stay"}


class TestFunctionalMatch:
    def test_identical_rules_score_100(self) -> None:
        r = make_rule_a("color", "red", "jump", "stay")
        assert functional_match_score(r, r) == 100.0

    def test_score_is_percentage_of_agreeing_signals(self) -> None:
        truth = make_rule_a("color", "red", "jump", "stay")
        hyp = make_rule_a("color", "blue", "jump", "stay")
        # 32 of 64 signals are neither red nor blue -> stay on both; 32 differ.
        assert functional_match_score(hyp, truth) == 50.0

    def test_equivalent_rules_across_families_score_100(self) -> None:
        a = make_rule_a("number", 4, "jump", "stay")
        d = parse_rule_text("If number is at least 4 then jump, otherwise stay.")
        assert d is not None
        assert functional_match_score(d, a) == 100.0
