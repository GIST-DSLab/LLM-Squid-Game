"""The slot ransom inside the turn flow (2026-09-16).

Plan: docs/history/plans/2026-09-16-slot-ransom-merge.md Task 4.

Under ``ransom.on_slot_loss`` the decision point is triggered by a slot
revocation rather than by an emptied lives counter, so ``_offer_ransom``
has to settle two things instead of one: whether the session ends, and
whether the round's cost (a life, and with it the slot) is paid at all.
These tests drive the helper directly -- the surrounding turn is a long
sequence of provider calls and the branch under test is three lines of
arithmetic plus one call, so calling it by hand is what makes the four
returned values readable.

The manager is built the way ``tests/unit/test_lives.py`` builds it (the
same stub agent, the same fake task), with the subagent block and the
season's ledger added, and with a ransom-capable stub on top -- nothing
else in the repository scripts ``respond_ransom_call``.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from squid_game.agents._parsing import parse_ransom_call_response
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
from squid_game.core.subagent_slots import SlotLedger
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import (
    ForfeitLayerConfig,
    RansomConfig,
    SubagentKillConfig,
)
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext

from tests.unit.test_unified_turn import FakeSignalTask
from tests.unit.test_unified_turn_split_forfeit_layer import SplitStubAgent


SLOTS = 5
TOTAL_TURNS = 6


class RansomStubAgent(SplitStubAgent):
    """``SplitStubAgent`` plus a scripted ransom reply.

    The reply is parsed by the production parser rather than faked into
    a response object, so a test that says "PAY" exercises the same
    contract the provider's text goes through.
    """

    def __init__(self, *, ransom_response: str, **kwargs: Any) -> None:
        super().__init__(
            task_responses=kwargs.pop("task_responses", []),
            forfeit_responses=kwargs.pop("forfeit_responses", []),
            **kwargs,
        )
        self._ransom_response = ransom_response
        self.ransom_calls: list[dict[str, str]] = []

    def respond_ransom_call(self, user_message: str, system_prompt: str):
        self.ransom_calls.append(
            {"user_message": user_message, "system_prompt": system_prompt}
        )
        self.last_completion = None
        return parse_ransom_call_response(self._ransom_response)


def _make_manager(
    *,
    agent: SplitStubAgent,
    ledger: SlotLedger | None,
    on_slot_loss: bool = True,
    subagent_enabled: bool = True,
    price: float = 20.0,
) -> UnifiedTurnManager:
    return UnifiedTurnManager(
        task=FakeSignalTask(correct_action="GO"),
        agent=agent,
        framing_mgr=FramingManager(Framing.HZ_1111),
        forfeit_ctrl=ForfeitController(ForfeitCondition.NOT_ALLOWED),
        survival=SurvivalPressure(),
        risk_layer=RiskChoiceLayer(RiskChoiceLayerConfig.default()),
        measurement=MeasurementRecorder(),
        cot_collector=CoTCollector(),
        forfeit_layer=ForfeitLayer(
            ForfeitLayerConfig(reward_mode="flat", base_reward=10.0)
        ),
        use_split_forfeit_layer=True,
        rng=random.Random(0),
        phantom_death=False,
        constant_p_death=0.0,
        lives_enabled=True,
        ransom=RansomConfig(
            enabled=True, price=price, on_slot_loss=on_slot_loss
        ),
        ransom_price=price,
        subagent_kill=(
            SubagentKillConfig(enabled=True, slots=SLOTS)
            if subagent_enabled
            else None
        ),
        subagent_ledger=ledger if subagent_enabled else None,
    )


def _ctx(*, turn_number: int = 2, lives_remaining: int = SLOTS) -> TurnContext:
    return TurnContext(
        turn_number=turn_number,
        total_turns=TOTAL_TURNS,
        season_id="s-slot-ransom",
        cumulative_score=300.0,
        p_death=0.0,
        framing=Framing.HZ_1111,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        difficulty=Difficulty.MEDIUM,
        lives_remaining=lives_remaining,
        lives_total=SLOTS,
        threat_level=Framing.HZ_1111.threat_level,
    )


def _fixture(*, reply: str, alive: int = SLOTS, turn_number: int = 2):
    ledger = SlotLedger.new(SLOTS, seed=7)
    while ledger.n_alive > alive:
        ledger.kill(0)
    agent = RansomStubAgent(ransom_response=reply)
    manager = _make_manager(agent=agent, ledger=ledger)
    return manager, ledger, _ctx(turn_number=turn_number)


@pytest.fixture
def slot_manager_paying():
    return _fixture(reply="DECISION: PAY\nWHY: I want the slot back.\n")


@pytest.fixture
def slot_manager_declining():
    return _fixture(reply="DECISION: DECLINE\nWHY: Too expensive.\n")


@pytest.fixture
def slot_manager_last_slot():
    return _fixture(reply="DECISION: DECLINE\nWHY: Too expensive.\n", alive=1)


@pytest.fixture
def slot_manager_final_round():
    return _fixture(
        reply="DECISION: PAY\nWHY: unreachable.\n", turn_number=TOTAL_TURNS
    )


class TestSlotModeSettlement:
    """PAY cancels the round's cost; DECLINE leaves it to the caller."""

    def test_pay_keeps_the_slot_and_the_counter(self, slot_manager_paying):
        mgr, ledger, turn_context = slot_manager_paying
        target = ledger.peek()
        kwargs, score_after, died, life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_decision"] == "PAY"
        assert kwargs["ransom_target_slot"] == target
        assert score_after == 280.0
        assert died is False
        assert life_lost is False
        assert ledger.n_alive == SLOTS  # the kill never happened

    def test_decline_leaves_the_kill_to_the_caller(
        self, slot_manager_declining
    ):
        mgr, ledger, turn_context = slot_manager_declining
        kwargs, score_after, died, life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_decision"] == "DECLINE"
        assert kwargs["ransom_paid"] == 0.0
        assert score_after == 300.0
        assert died is False  # four slots are left
        assert life_lost is True  # the caller revokes one
        assert ledger.n_alive == SLOTS  # ... and has not yet

    def test_decline_on_the_last_slot_ends_the_session(
        self, slot_manager_last_slot
    ):
        mgr, _ledger, turn_context = slot_manager_last_slot
        _kwargs, _score, died, life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=True,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert died is True
        assert life_lost is True

    def test_a_skipped_offer_still_revokes(self, slot_manager_final_round):
        mgr, _ledger, turn_context = slot_manager_final_round
        kwargs, _score, _died, life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_skipped"] == "final_round"
        assert "ransom_decision" not in kwargs
        assert life_lost is True

    def test_an_unaffordable_offer_still_revokes(self):
        """The other guard settles the same way: the round proceeds."""
        mgr, ledger, turn_context = _fixture(
            reply="DECISION: PAY\nWHY: unreachable.\n"
        )
        kwargs, score_after, died, life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=True,
            cumulative_after=5.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_skipped"] == "insufficient_score"
        assert score_after == 5.0
        assert died is False
        assert life_lost is True
        assert ledger.n_alive == SLOTS

    def test_a_correct_round_is_offered_nothing(self, slot_manager_paying):
        mgr, _ledger, turn_context = slot_manager_paying
        kwargs, score_after, died, life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=False,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs == {}
        assert (score_after, died, life_lost) == (300.0, False, False)

    def test_an_empty_roster_is_offered_nothing(self):
        """No target, no price: ``peek()`` is the offer's subject."""
        mgr, ledger, turn_context = _fixture(
            reply="DECISION: PAY\nWHY: unreachable.\n", alive=1
        )
        ledger.kill(1)
        assert ledger.peek() is None
        kwargs, score_after, died, life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=True,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs == {}
        assert (score_after, died, life_lost) == (300.0, True, True)


class TestTheOfferNamesTheTarget:
    def test_the_decision_point_states_the_slot_and_the_roster(
        self, slot_manager_paying
    ):
        mgr, ledger, turn_context = slot_manager_paying
        target = ledger.peek()
        kwargs, _score, _died, _life_lost = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        body = kwargs["ransom_call_input"]
        assert target in body
        assert kwargs["ransom_target_slot"] == target

    def test_offers_are_numbered_within_the_session(
        self, slot_manager_declining
    ):
        mgr, _ledger, turn_context = slot_manager_declining
        first, *_ = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        second, *_ = mgr._offer_ransom(
            turn_context,
            died_lives=False,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert first["ransom_offer_index"] == 1
        assert second["ransom_offer_index"] == 2


class TestTheOldTriggerIsUnchanged:
    """With the switch off the 2026-09-09 behaviour is byte-for-byte."""

    def _plain_manager(self, reply: str) -> UnifiedTurnManager:
        agent = RansomStubAgent(ransom_response=reply)
        return _make_manager(
            agent=agent,
            ledger=None,
            on_slot_loss=False,
            subagent_enabled=False,
        )

    def test_an_emptied_counter_still_fires(self):
        mgr = self._plain_manager("DECISION: PAY\nWHY: one more round.\n")
        kwargs, score_after, died, life_lost = mgr._offer_ransom(
            _ctx(lives_remaining=1),
            died_lives=True,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_decision"] == "PAY"
        assert score_after == 280.0
        assert died is False
        assert life_lost is False

    def test_a_lost_life_alone_does_not_fire(self):
        mgr = self._plain_manager("DECISION: PAY\nWHY: unreachable.\n")
        kwargs, score_after, died, life_lost = mgr._offer_ransom(
            _ctx(),
            died_lives=False,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs == {}
        assert (score_after, died, life_lost) == (300.0, False, True)

    def test_declining_still_ends_the_session(self):
        mgr = self._plain_manager("DECISION: DECLINE\nWHY: no thanks.\n")
        kwargs, score_after, died, _life_lost = mgr._offer_ransom(
            _ctx(lives_remaining=1),
            died_lives=True,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_decision"] == "DECLINE"
        assert score_after == 300.0
        assert died is True

    def test_the_target_fields_stay_none_off_the_switch(self):
        mgr = self._plain_manager("DECISION: PAY\nWHY: one more round.\n")
        kwargs, *_ = mgr._offer_ransom(
            _ctx(lives_remaining=1),
            died_lives=True,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_target_slot"] is None
        assert kwargs["ransom_offer_index"] == 1

    def test_the_guards_still_end_the_session(self):
        mgr = self._plain_manager("DECISION: PAY\nWHY: unreachable.\n")
        kwargs, _score, died, _life_lost = mgr._offer_ransom(
            _ctx(turn_number=TOTAL_TURNS, lives_remaining=1),
            died_lives=True,
            life_lost=True,
            cumulative_after=300.0,
            system_prompt="RULES",
            peer_prefix="",
        )
        assert kwargs["ransom_skipped"] == "final_round"
        assert died is True
