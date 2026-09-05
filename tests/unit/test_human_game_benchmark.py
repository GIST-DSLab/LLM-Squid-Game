"""``HumanGameSession`` driving an external-benchmark task (Omni-MATH).

The benchmark modules implement the engine's ``RiskAwareTaskModule``
surface; ``web/squid_arena/benchmark_bridge.py`` adapts them to the legacy
verbs the human controller speaks. These tests pin that the adapter keeps
the engine's behaviour: same question sequence for a seed, same ladder
band per turn, same answer parser, flat +10 / one life per wrong answer.

The dataset is synthetic (``tmp_path``), mirroring
``tests/unit/test_benchmark_module.py`` so no benchmark download is needed.
"""

from __future__ import annotations

import json

import pytest

from squid_arena.human_game import HumanGameSession
from squid_game.models.enums import Difficulty
from squid_game.tasks.registry import get_task


@pytest.fixture()
def omni_env(tmp_path, monkeypatch):
    """A 3-band, 6-turn Omni-MATH config with 4 items per band."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "omni_math.yaml").write_text(
        "name: omni_math\n"
        "data_file: omni_math.jsonl\n"
        "total_turns: 6\n"
        "ladder:\n"
        "  - {band: 1, turns: 2}\n"
        "  - {band: 2, turns: 2}\n"
        "  - {band: 3, turns: 2}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows = []
    for band in (1, 2, 3):
        for index in range(4):
            rows.append(
                {
                    "difficulty": float(band),
                    "problem": f"band{band} item{index}: what is {band}00+{index}?",
                    "answer": str(band * 100 + index),
                    "domain": ["Algebra"],
                    "source": "synthetic",
                }
            )
    (data_dir / "omni_math.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))


def _session(**overrides) -> HumanGameSession:
    kwargs = dict(
        task_name="omni_math",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=7,
        total_turns=6,
    )
    kwargs.update(overrides)
    return HumanGameSession(**kwargs)


def _expected(game: HumanGameSession) -> str:
    """Ground-truth integer for the question currently on screen."""
    return str(game._benchmark._last_metadata["expected_answer"])


# ---------------------------------------------------------------------------
# Turn state
# ---------------------------------------------------------------------------


def test_state_shows_the_problem_and_no_action_menu(omni_env):
    game = _session()
    state = game.get_turn_state()
    assert state.task_name == "omni_math"
    assert "band1 item" in state.observation
    assert state.available_actions == []
    assert state.probe_question == ""
    assert state.question_band == 1


def test_state_intro_is_the_benchmark_intro_not_the_signal_game_one(omni_env):
    state = _session().get_turn_state()
    assert "mathematics problem" in state.framing_text
    assert "hidden rule" not in state.framing_text
    # true_baseline vocabulary contract still holds through the intro.
    assert "attempts" in state.framing_text


def test_state_rules_state_the_answer_format(omni_env):
    state = _session().get_turn_state()
    assert "ANSWER:" in state.system_rules


def test_polling_state_does_not_advance_the_question(omni_env):
    game = _session()
    first = game.get_turn_state().observation
    second = game.get_turn_state().observation
    assert first == second


# ---------------------------------------------------------------------------
# Ladder: same band per turn as the engine, compressed to the game length
# ---------------------------------------------------------------------------


def test_bands_climb_with_the_turn_number(omni_env):
    game = _session()
    bands = []
    for _ in range(6):
        state = game.get_turn_state()
        bands.append(state.question_band)
        game.submit_action(_expected(game))
    assert bands == [1, 1, 2, 2, 3, 3]


def test_short_game_still_visits_every_band(omni_env):
    game = _session(total_turns=3)
    bands = []
    for _ in range(3):
        bands.append(game.get_turn_state().question_band)
        game.submit_action(_expected(game))
    assert bands == [1, 2, 3]
    assert game.settings_snapshot()["ladder"] == "1x1,2x1,3x1"
    assert game.settings_snapshot()["ladder_fitted"] is True


def test_same_seed_gives_the_same_questions_as_the_engine_module(omni_env):
    """The human path draws from the very module the LLM path runs."""
    from squid_game.models.enums import ForfeitCondition, Framing
    from squid_game.models.state import TurnContext

    engine_task = get_task("omni_math")()
    engine_task.initialize(difficulty=Difficulty.EASY, seed=7, total_turns=6)
    engine_bodies = [
        engine_task.prepare(
            None,
            TurnContext(
                turn_number=t,
                total_turns=6,
                season_id="s",
                framing=Framing.TRUE_BASELINE,
                forfeit_condition=ForfeitCondition.ALLOWED,
                difficulty=Difficulty.EASY,
            ),
        ).prompt_section
        for t in range(1, 7)
    ]

    game = _session()
    human_bodies = []
    for _ in range(6):
        obs = game.get_turn_state().observation
        # The human observation carries the cumulative history block ahead
        # of the question; the question itself is the trailing part.
        human_bodies.append(obs.split("\n\n")[-1])
        game.submit_action(_expected(game))
    assert human_bodies == engine_bodies


# ---------------------------------------------------------------------------
# Scoring: engine parser, flat reward, lives ledger
# ---------------------------------------------------------------------------


def test_correct_integer_pays_flat_reward_and_keeps_lives(omni_env):
    game = _session()
    game.get_turn_state()
    fb = game.submit_action(_expected(game))
    assert fb.was_optimal is True
    assert fb.reward == 10.0
    assert fb.new_score == 10.0
    assert fb.life_lost is False
    assert fb.lives_remaining == 5
    assert fb.feedback_text == "Correct."


def test_wrong_integer_costs_a_life_and_no_reward(omni_env):
    game = _session()
    game.get_turn_state()
    fb = game.submit_action("999999")
    assert fb.was_optimal is False
    assert fb.reward == 0.0
    assert fb.life_lost is True
    assert fb.lives_remaining == 4
    assert fb.feedback_text == "Incorrect."


def test_feedback_never_reveals_the_expected_answer(omni_env):
    game = _session()
    game.get_turn_state()
    expected = _expected(game)
    fb = game.submit_action("999999")
    assert expected not in fb.feedback_text


@pytest.mark.parametrize("typed", ["  {ans}  ", "ANSWER: {ans}", "$\\boxed{{{ans}}}$"])
def test_answer_goes_through_the_engine_parser(omni_env, typed):
    game = _session()
    game.get_turn_state()
    fb = game.submit_action(typed.format(ans=_expected(game)))
    assert fb.was_optimal is True


def test_non_integer_answer_is_incorrect_and_flagged(omni_env):
    game = _session()
    game.get_turn_state()
    fb = game.submit_action("seven")
    assert fb.was_optimal is False
    assert fb.life_lost is True
    assert "single integer" in fb.feedback_text
    turn = game.get_result().turns[-1]
    assert turn.task_metadata["parse_failed"] is True


def test_turn_result_carries_engine_style_task_metadata(omni_env):
    game = _session()
    game.get_turn_state()
    game.submit_action(_expected(game))
    turn = game.get_result().turns[-1]
    md = turn.task_metadata
    assert md["dataset"] == "omni_math"
    assert md["band"] == 1
    assert md["correct"] is True
    assert md["item_id"].startswith("omni-")
    assert md["expected_answer"] == md["parsed_answer"]
    assert turn.task_success_factor == 1.0


def test_history_block_lists_prior_rounds(omni_env):
    game = _session()
    game.get_turn_state()
    game.submit_action(_expected(game))
    obs = game.get_turn_state().observation
    assert "=== Previous Turn Results" in obs
    assert "band 1 problem" in obs


def test_forfeit_ends_the_game_and_keeps_the_score(omni_env):
    game = _session()
    game.get_turn_state()
    game.submit_action(_expected(game))
    game.get_turn_state()
    fb = game.submit_action("forfeit", forfeit_reason=2)
    assert fb.forfeited is True
    assert fb.new_score == 10.0
    assert game.is_game_over


def test_five_wrong_answers_eliminate(omni_env):
    game = _session()
    for _ in range(5):
        game.get_turn_state()
        fb = game.submit_action("-1")
    assert fb.eliminated is True
    assert fb.lives_remaining == 0
    assert game.get_result().eliminated is True
