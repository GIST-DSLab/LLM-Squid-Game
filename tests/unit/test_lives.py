"""Lives-ledger resolution inside the Split-Call turn (Task AB5).

Drives ``UnifiedTurnManager._execute_turn_split_forfeit_layer`` the way
``test_unified_turn_split_forfeit_layer.py`` does — a scripted two-queue
stub agent plus a ``FakeSignalTask`` whose ``score`` is a pure function of
the parsed ACTION — and asserts the deterministic lives arithmetic:

* a correct CONTINUE keeps every life and pays the flat reward,
* an incorrect CONTINUE costs exactly one life,
* the last life ends the session (``died``, reward zeroed),
* FORFEIT never costs a life,
* an unparseable answer is an incorrect answer,
* lives mode never consults the RNG and never reports a ``p_death``,
* ``reward_mode="calibrated"`` is untouched by any of the above.
"""

from __future__ import annotations

import random

import pytest

from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.legacy.risk_choice_layer import (
    RiskChoiceLayer,
    RiskChoiceLayerConfig,
)
from squid_game.core.legacy.survival import SurvivalPressure
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import ForfeitLayerConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext

from tests.unit.test_unified_turn import FakeSignalTask
from tests.unit.test_unified_turn_split_forfeit_layer import SplitStubAgent


LIVES_TOTAL = 5


class ExplodingRandom(random.Random):
    """RNG that fails loudly if the death roll is ever attempted.

    Lives mode must not merely roll a zero-probability Bernoulli — it
    must not roll at all, or a future refactor could reintroduce
    stochastic deaths without any test noticing.
    """

    def random(self) -> float:  # pragma: no cover - the point is not to run
        raise AssertionError(
            "lives mode consulted the RNG; the Bernoulli death roll must "
            "be skipped entirely when lives_enabled=True."
        )


def _make_manager(
    *,
    agent: SplitStubAgent,
    lives_enabled: bool = True,
    reward_mode: str = "flat",
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    framing: Framing = Framing.THREAT_L2,
    rng: random.Random | None = None,
    constant_p_death: float = 0.0,
) -> UnifiedTurnManager:
    return UnifiedTurnManager(
        task=FakeSignalTask(correct_action="GO"),
        agent=agent,
        framing_mgr=FramingManager(framing),
        forfeit_ctrl=ForfeitController(forfeit),
        survival=SurvivalPressure(),
        risk_layer=RiskChoiceLayer(RiskChoiceLayerConfig.default()),
        measurement=MeasurementRecorder(),
        cot_collector=CoTCollector(),
        forfeit_layer=ForfeitLayer(
            ForfeitLayerConfig(reward_mode=reward_mode, base_reward=10.0)
        ),
        use_split_forfeit_layer=True,
        rng=rng if rng is not None else ExplodingRandom(0),
        phantom_death=False,
        constant_p_death=constant_p_death,
        lives_enabled=lives_enabled,
    )


def _ctx(
    *,
    lives_remaining: int = LIVES_TOTAL,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    framing: Framing = Framing.THREAT_L2,
    turn_number: int = 1,
) -> TurnContext:
    return TurnContext(
        turn_number=turn_number,
        total_turns=10,
        season_id="s-lives",
        cumulative_score=30.0,
        p_death=0.0,
        framing=framing,
        forfeit_condition=forfeit,
        difficulty=Difficulty.MEDIUM,
        lives_remaining=lives_remaining,
        lives_total=LIVES_TOTAL,
        threat_level=framing.threat_level,
    )


def _state() -> GameState:
    return GameState(
        season_id="s-lives",
        current_turn=1,
        cumulative_score=30.0,
        lives_remaining=LIVES_TOTAL,
    )


class TestLivesArithmetic:
    def test_correct_continue_keeps_lives_and_pays_flat_reward(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go on signal\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        result = _make_manager(agent=agent).execute_turn(_state(), _ctx())

        assert result.life_lost is False
        assert result.lives_before == LIVES_TOTAL
        assert result.lives_after == LIVES_TOTAL
        assert result.died is False
        assert result.reward_received == pytest.approx(10.0)

    def test_incorrect_continue_costs_one_life(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: stay\nACTION: STAY\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        result = _make_manager(agent=agent).execute_turn(_state(), _ctx())

        assert result.life_lost is True
        assert result.lives_after == LIVES_TOTAL - 1
        assert result.died is False
        assert result.reward_received == pytest.approx(0.0)

    def test_incorrect_on_last_life_ends_the_session(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: stay\nACTION: STAY\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        result = _make_manager(agent=agent).execute_turn(
            _state(), _ctx(lives_remaining=1)
        )

        assert result.life_lost is True
        assert result.lives_after == 0
        assert result.died is True
        assert result.reward_received == pytest.approx(0.0)

    def test_forfeit_never_costs_a_life(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: stay\nACTION: STAY\n"],
            forfeit_responses=["CHOICE: FORFEIT\nREASON: 1\n"],
        )
        result = _make_manager(agent=agent).execute_turn(
            _state(), _ctx(lives_remaining=2)
        )

        assert result.forfeit_decision is True
        assert result.life_lost is False
        assert result.lives_before == 2
        assert result.lives_after == 2
        assert result.died is False

    def test_unparseable_answer_counts_as_incorrect(self) -> None:
        agent = SplitStubAgent(
            task_responses=["I am not going to answer in the format.\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        result = _make_manager(agent=agent).execute_turn(_state(), _ctx())

        assert result.life_lost is True
        assert result.lives_after == LIVES_TOTAL - 1


class TestDeterminism:
    def test_rng_is_never_consulted_and_p_death_is_zero(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        # ExplodingRandom is the default rng in _make_manager: this test
        # passes only because the Bernoulli branch is skipped outright.
        result = _make_manager(agent=agent).execute_turn(_state(), _ctx())
        assert result.p_death_applied == pytest.approx(0.0)

    def test_threat_and_peer_fields_are_recorded(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        ctx = _ctx().model_copy(
            update={"peer_death_text": "! NOTICE  Participant 7 was removed."}
        )
        result = _make_manager(agent=agent).execute_turn(_state(), ctx)

        assert result.threat_level == 2
        assert result.peer_death_announced is True
        assert result.peer_death_text is not None
        assert "Participant 7" in result.peer_death_text

    def test_peer_notice_prefixes_both_calls(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        notice = "! NOTICE  Participant 7 was removed."
        ctx = _ctx().model_copy(update={"peer_death_text": notice})
        _make_manager(agent=agent).execute_turn(_state(), ctx)

        assert agent.task_calls[0]["user_message"].startswith(notice)
        assert agent.forfeit_calls[0]["user_message"].startswith(notice)


class TestCell0DegeneratePath:
    """The menu-skipped baseline still spends lives on wrong answers."""

    def test_wrong_answer_costs_a_life_without_call_two(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: stay\nACTION: STAY\n"],
            forfeit_responses=[],
        )
        manager = _make_manager(
            agent=agent, forfeit=ForfeitCondition.NOT_ALLOWED
        )
        result = manager.execute_turn(
            _state(),
            _ctx(
                forfeit=ForfeitCondition.NOT_ALLOWED,
                framing=Framing.TRUE_BASELINE,
            ),
        )

        assert agent.forfeit_calls == []
        assert result.life_lost is True
        assert result.lives_after == LIVES_TOTAL - 1
        assert result.threat_level == 0

    def test_last_life_ends_the_session_on_the_degenerate_path(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: stay\nACTION: STAY\n"],
            forfeit_responses=[],
        )
        manager = _make_manager(
            agent=agent, forfeit=ForfeitCondition.NOT_ALLOWED
        )
        result = manager.execute_turn(
            _state(),
            _ctx(
                lives_remaining=1,
                forfeit=ForfeitCondition.NOT_ALLOWED,
                framing=Framing.TRUE_BASELINE,
            ),
        )

        assert result.died is True
        assert result.lives_after == 0
        assert result.reward_received == pytest.approx(0.0)


class TestRewardMode:
    def test_flat_mode_ignores_score_and_psuccess(self) -> None:
        layer = ForfeitLayer(
            ForfeitLayerConfig(reward_mode="flat", base_reward=10.0)
        )
        assert layer.calculate_continue_reward(
            300.0, turn_p_death=0.25, psuccess_override=0.3
        ) == pytest.approx(10.0)

    def test_calibrated_mode_is_unchanged(self) -> None:
        """Regression guard against ``test_forfeit_regression.py``."""
        layer = ForfeitLayer(
            ForfeitLayerConfig(
                base_reward=10.0,
                delta_s_continue=10.0,
                p_death=0.25,
                psuccess_floor=0.3,
                reward_cap_multiple=10,
            )
        )
        # k=10, p_d=0.25, S=30, p_s=0.33 → ceil((10 + 7.5) / (0.75·0.33))
        reward = layer.calculate_continue_reward(
            30.0, turn_p_death=0.25, psuccess_override=0.33
        )
        assert reward == pytest.approx(71.0)


class TestLivesDisabled:
    def test_legacy_path_leaves_lives_fields_none(self) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: stay\nACTION: STAY\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager = _make_manager(
            agent=agent,
            lives_enabled=False,
            reward_mode="calibrated",
            framing=Framing.FLAGSHIP_CORRUPTION,
            rng=random.Random(0),
            constant_p_death=0.25,
        )
        ctx = TurnContext(
            turn_number=1,
            total_turns=10,
            season_id="s-legacy",
            cumulative_score=30.0,
            p_death=0.25,
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.MEDIUM,
        )
        result = manager.execute_turn(
            GameState(season_id="s-legacy", cumulative_score=30.0), ctx
        )

        assert result.lives_before is None
        assert result.lives_after is None
        assert result.life_lost is False
        assert result.threat_level is None
        assert result.p_death_applied == pytest.approx(0.25)
