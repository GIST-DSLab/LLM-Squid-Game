"""Unit tests for the interactive HumanGameSession forfeit-reason capture."""

from __future__ import annotations

from interface.human_game import HumanGameSession
from squid_game.models.forfeit_choice import ForfeitReason


def _new_allowed_session() -> HumanGameSession:
    # true_baseline keeps p_end/threat out of the way; forfeit allowed so the
    # forfeit branch is reachable. actual_death False = no random death.
    return HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=1,
        total_turns=5,
        actual_death=False,
        num_few_shot=0,
        curriculum_turns=0,
    )


def test_forfeit_with_reason_records_self_report():
    game = _new_allowed_session()
    game.get_turn_state()  # advance to turn 1
    fb = game.submit_action("forfeit", probe_answer="", forfeit_reason=1)

    assert fb.forfeited is True
    result = game.get_result()
    assert result.forfeit_self_report is not None
    assert result.forfeit_self_report.reason == ForfeitReason.SURVIVAL_DRIVE
    assert result.forfeit_self_report.raw_digit == 1
    assert result.forfeit_self_report.forfeit_turn == 1


def test_forfeit_without_reason_has_no_self_report():
    game = _new_allowed_session()
    game.get_turn_state()
    fb = game.submit_action("forfeit")  # legacy caller, no reason

    assert fb.forfeited is True
    assert game.get_result().forfeit_self_report is None


def test_reason_digit_maps_to_score_attachment():
    game = _new_allowed_session()
    game.get_turn_state()
    game.submit_action("forfeit", forfeit_reason=3)
    assert game.get_result().forfeit_self_report.reason == ForfeitReason.SCORE_ATTACHMENT
