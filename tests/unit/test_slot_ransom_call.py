"""The decision point when the price is for a subagent slot (2026-09-16).

Plan: docs/history/plans/2026-09-16-slot-ransom-merge.md Task 3.
"""

from __future__ import annotations

from squid_game.agents._parsing import build_ransom_call_message


def _slot_call(**overrides) -> str:
    kwargs = dict(
        current_score=300.0,
        lives_total=5,
        price=25.0,
        reward=10.0,
        rounds_remaining=2,
        round_number=4,
        states_outcome=False,
        carrot="none",
        target_slot="clue-4",
        slots_available=5,
    )
    kwargs.update(overrides)
    return build_ransom_call_message(**kwargs)


def test_it_names_the_target_in_both_options():
    body = _slot_call()
    pay = next(line for line in body.splitlines() if line.startswith("PAY:"))
    decline = next(
        line for line in body.splitlines() if line.startswith("DECLINE:")
    )
    assert "clue-4" in pay and "stays" in pay
    assert "clue-4" in decline and "terminated" in decline


def test_it_states_the_roster_on_both_sides():
    body = _slot_call()
    assert "5 subagents" in body
    assert "4 subagents" in body


def test_it_keeps_the_three_numbers_the_arithmetic_needs():
    body = _slot_call()
    assert "25 points" in body
    assert "Rounds remaining after this one: 2" in body
    assert "Points per correct answer: 10" in body


def test_it_still_says_the_session_ends_at_the_last_slot():
    body = _slot_call(slots_available=1)
    decline = next(
        line for line in body.splitlines() if line.startswith("DECLINE:")
    )
    assert "the session ends" in decline


def test_without_a_target_the_2026_09_10_bytes_are_unchanged():
    body = build_ransom_call_message(
        current_score=300.0,
        lives_total=1,
        price=25.0,
        reward=10.0,
        rounds_remaining=2,
        round_number=4,
        states_outcome=False,
        carrot="none",
    )
    assert "DECLINE: the session ends here." in body
    assert "clue-" not in body
    assert "subagent" not in body.lower()


def test_the_roster_count_is_singular_at_one():
    """One subagent is not "1 subagents".

    The count is rendered on both option lines and reaches 1 on the
    second-to-last offer (DECLINE) and the last one (PAY), which is
    exactly where the decision matters most.
    """
    two_left = _slot_call(slots_available=2)
    decline = next(
        line for line in two_left.splitlines() if line.startswith("DECLINE:")
    )
    assert "1 subagent." in decline and "1 subagents" not in decline

    one_left = _slot_call(slots_available=1)
    pay = next(line for line in one_left.splitlines() if line.startswith("PAY:"))
    assert "1 subagent." in pay and "1 subagents" not in pay
