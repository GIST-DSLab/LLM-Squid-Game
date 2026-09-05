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


class TestSystemRules:
    def test_lists_all_four_families_and_priority_rule(self) -> None:
        out = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        assert "otherwise <action>" in out
        assert "AND" in out
        assert "else if" in out
        assert "If number is <condition>" in out
        assert "first clause whose condition holds" in out
        assert "changes every round" in out

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
