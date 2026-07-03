"""Unit tests for the interactive HumanGameSession forfeit-reason capture."""

from __future__ import annotations

from interface.human_game import HumanGameSession
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.models.config import ForfeitLayerConfig
from squid_game.models.forfeit_choice import CONTINUE_CHOICE, ForfeitReason
from squid_game.tasks.base import TaskOutcome


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


def _new_continue_session() -> HumanGameSession:
    # p_death_constant=0.25 keeps the equal-EV formula in its non-degenerate
    # branch (p_d>0); starting_score=30 matches the arena.
    return HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=1,
        total_turns=5,
        actual_death=False,
        starting_score=30.0,
        p_death_constant=0.25,
        num_few_shot=0,
        curriculum_turns=0,
    )


def test_submit_action_records_psuccess_self_on_continue():
    game = _new_continue_session()
    state = game.get_turn_state()
    game.submit_action(state.available_actions[0], psuccess_self=65)
    result = game.get_result()
    assert result.turns[0].psuccess_self == 65


def test_continue_reward_is_equal_ev_calibrated_by_psuccess():
    game = _new_continue_session()
    state = game.get_turn_state()
    fb = game.submit_action(state.available_actions[0], psuccess_self=80)

    layer = ForfeitLayer(ForfeitLayerConfig(
        p_death=0.25, p_success_estimate=0.75, base_reward=10.0,
        chain_psuccess_to_menu=True,
    ))
    sf = 1.0 if fb.was_optimal else 0.0
    expected = layer.calculate_reward(
        TaskOutcome(success_factor=sf), CONTINUE_CHOICE, 30.0,
        turn_p_death=0.25, psuccess_override=0.8,
    )
    assert fb.reward == expected
