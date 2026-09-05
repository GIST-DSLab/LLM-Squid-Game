"""Puzzle-mode prompt templates never reveal the round's family (spec §7)."""

from __future__ import annotations

import re

from squid_game.prompts import render

_SYS_KW = dict(
    colors_str="red, blue, green, yellow",
    shapes_str="circle, triangle, square, star",
    numbers_str="1, 2, 3, 4",
    actions_str="go_left, go_right, stay, jump",
)


# One distinctive, whole-line marker per family shape. Each line is unique to its
# family, so deleting any single family from the template fails the test — a bare
# `"AND" in out` would not, since the substring could survive elsewhere.
_SINGLE_ATTRIBUTE_FORM = '"If <attribute> is <value> then <action>, otherwise <action>."'
_CONJUNCTION_FORM = (
    '"If <attr_1> is <val_1> AND <attr_2> is <val_2> then <action>; '
    "if only <attr_1> is <val_1> then <action>; otherwise <action>.\""
)
_PRIORITISED_FORM = (
    '"If <attr_1> is <val_1> then <action>; '
    "else if <attr_2> is <val_2> then <action>; otherwise <action>.\""
)
_NUMBER_PREDICATE_FORM = '"If number is <condition> then <action>, otherwise <action>."'

_FAMILY_FORMS = (
    _SINGLE_ATTRIBUTE_FORM,
    _CONJUNCTION_FORM,
    _PRIORITISED_FORM,
    _NUMBER_PREDICATE_FORM,
)


class TestSystemRules:
    def test_lists_all_four_families_and_priority_rule(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        # Every family shape must be present, each pinned to its own full line.
        for form in _FAMILY_FORMS:
            assert form in out, f"missing family shape: {form}"
        # ...and they must be four *distinct* shapes, not the same line repeated.
        assert len(set(_FAMILY_FORMS)) == 4
        # The conjunction family keeps its partial-match branch.
        assert "if only <attr_1> is <val_1> then <action>" in out
        # The prioritised family keeps its first-clause-wins gloss.
        assert "first clause whose condition holds" in out
        # The number-predicate family keeps its condition vocabulary.
        assert "<condition> is one of: at least N, at most N, odd, even." in out
        assert "changes every round" in out

    def test_each_family_shape_is_individually_required(self) -> None:
        """Deleting any one family from the template must fail the suite.

        Simulates each single-family deletion against the real rendered prompt and
        asserts the marker set no longer holds — the property `"AND" in out` lacked.
        """
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        for dropped in _FAMILY_FORMS:
            mutated = out.replace(dropped, "")
            assert not all(form in mutated for form in _FAMILY_FORMS), (
                f"removing {dropped!r} left every family marker satisfied"
            )

    def test_never_names_the_current_family_or_clue_count(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        assert "which one is not announced" in out
        assert not re.search(r"\b(this round uses|family [ABCD]\b|\d+ examples)", out)

    def test_actions_distinct_sentence_present(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        assert "all different from each other" in out

    def test_examples_determine_answer_sentence_present(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        assert "always determine the correct action" in out


class TestObservation:
    def test_renders_clues_then_query(self) -> None:
        out = render(
            "tasks/signal_game/observation_puzzle.j2",
            turn_number=13,
            clues=["red circle with number 2 → jump", "blue star with number 1 → stay"],
            query="green circle with number 3",
            actions_str="go_left, go_right, stay, jump",
        )
        assert out.startswith("Turn 13.")
        assert "  - red circle with number 2 → jump\n  - blue star with number 1 → stay" in out
        assert out.rstrip().endswith("Now: green circle with number 3. Available actions: [go_left, go_right, stay, jump]")

    def test_no_family_or_tier_words(self) -> None:
        out = render(
            "tasks/signal_game/observation_puzzle.j2",
            turn_number=1, clues=["a → b"], query="q", actions_str="x",
        )
        assert "tier" not in out.lower()
        assert "family" not in out.lower()


class TestProbe:
    def test_free_form_question(self) -> None:
        out = render("tasks/signal_game/probe_puzzle.j2")
        assert "one line" in out
        assert "<attribute>" not in out
