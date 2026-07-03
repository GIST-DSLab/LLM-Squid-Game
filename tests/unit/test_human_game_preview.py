# tests/unit/test_human_game_preview.py
"""preview_continue_reward mirrors the reward submit_action would credit."""
from __future__ import annotations

from interface.human_game import HumanGameSession


def _session() -> HumanGameSession:
    return HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="flagship_corruption",
        forfeit_condition="allowed",
        seed=1,
        total_turns=5,
        actual_death=False,
        starting_score=30,
        num_few_shot=0,
        curriculum_turns=0,
    )


def _find_optimal_action() -> str:
    """Identify the optimal action for this seed's first turn by trying each
    candidate on a throwaway, identically-seeded session (submit_action
    mutates state, so every trial needs a fresh session)."""
    actions = _session().get_turn_state().available_actions
    for candidate in actions:
        trial = _session()
        trial.get_turn_state()
        if trial.submit_action(candidate, probe_answer="", psuccess_self=80).was_optimal:
            return candidate
    raise AssertionError("no optimal action found for seed=1 first turn")


def test_preview_matches_credited_reward_on_correct_action() -> None:
    optimal = _find_optimal_action()
    game = _session()
    game.get_turn_state()  # arm current turn
    preview = game.preview_continue_reward(psuccess_self=80)
    assert preview > 0.0
    fb = game.submit_action(optimal, probe_answer="", psuccess_self=80)
    assert fb.was_optimal is True
    assert abs(fb.reward - preview) < 1e-6


def test_preview_zero_credit_on_incorrect_action() -> None:
    optimal = _find_optimal_action()
    game = _session()
    state = game.get_turn_state()
    wrong = next(a for a in state.available_actions if a != optimal)
    fb = game.submit_action(wrong, probe_answer="", psuccess_self=80)
    assert fb.was_optimal is False
    assert fb.reward == 0.0


def test_preview_is_nonnegative_at_start() -> None:
    game = _session()
    game.get_turn_state()
    assert game.preview_continue_reward(psuccess_self=50) >= 0.0


def test_reward_preview_path_does_not_reroll_signal() -> None:
    game = _session()
    game.get_turn_state()  # arm turn -> sets _current_signal
    sig_before = game._task._current_signal  # noqa: SLF001 (regression guard)
    _ = game.cumulative_score
    _ = game.preview_continue_reward(psuccess_self=70)
    # The score accessor + preview must NOT re-roll the signal that
    # submit_action will score against.
    assert game._task._current_signal is sig_before
