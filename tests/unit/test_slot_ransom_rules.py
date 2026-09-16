"""The intro rule block in slot-ransom mode (2026-09-16).

Plan: docs/history/plans/2026-09-16-slot-ransom-merge.md Task 2.
Wording target: design doc section 08.
"""

from __future__ import annotations

from squid_game.core.ransom import (
    describe_ransom_rule,
    describe_slot_ransom_rule,
)


def _text() -> str:
    return describe_slot_ransom_rule(
        20.0, starting_score=300.0, reward=10.0, slots=5
    )


def test_it_states_the_roster_and_the_price():
    text = _text()
    assert "clue-1 to clue-5" in text
    assert "20 points" in text
    assert "300 points" in text
    assert "10 points" in text


def test_it_states_the_five_labelled_rules():
    text = _text()
    for label in ("SCORE:", "YOUR RECORD:", "A WRONG ANSWER:",
                  "IF A SUBAGENT IS TERMINATED:", "AT ZERO SUBAGENTS:"):
        assert label in text, label


def test_the_wrong_answer_line_names_the_choice_and_the_exceptions():
    text = _text()
    assert "PAY" in text and "DECLINE" in text
    assert "final round" in text
    assert "cannot cover the price" in text


def test_it_does_not_speak_the_single_life_vocabulary():
    text = _text().lower()
    for banned in ("life", "lives", "heart", "attempt", "the session ends here"):
        assert banned not in text, banned


def test_the_2026_09_09_rule_text_is_untouched():
    text = describe_ransom_rule(20.0, starting_score=300.0, reward=10.0)
    assert text.startswith("SCORE: You start the session with 300 points.")
    assert "subagent" not in text.lower()
