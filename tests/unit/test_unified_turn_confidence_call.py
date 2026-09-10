"""Phase 1.5 confidence call inside the split-call turn (SDI).

Scope:

1. Wire order — confidence → decision → task, all three sharing one
   system prompt, and the confidence call's CoT rendered into the
   decision call's user body.
2. Replay fields — ``system_prompt`` / ``decision_call_input`` /
   ``confidence_call_input`` (2026-09-06) recorded
   on every turn that issues a decision call (FORFEIT included).
3. Disabled path — two calls only, and the decision-call body carries no
   confidence block.
4. Cell 0 (menu skipped) — no confidence call, no replay fields; and
   its ``always_decide`` counterpart, where the same blocked cell does
   issue all three.
5. Peer-death notice prefixes the confidence call as well as the
   decision call.
"""

from __future__ import annotations

import random
from typing import Any

from squid_game.agents._parsing import (
    CONFIDENCE_BLOCK_HEADER,
    ConfidenceCallResponse,
)
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.legacy.risk_choice_layer import (
    RiskChoiceLayer,
    RiskChoiceLayerConfig,
)
from squid_game.core.legacy.survival import SurvivalPressure
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import ForfeitLayerConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext
from squid_game.providers.base import CompletionResult

from tests.unit.test_unified_turn import FakeSignalTask
from tests.unit.test_unified_turn_split_forfeit_layer import SplitStubAgent


class ConfidenceStubAgent(SplitStubAgent):
    """SplitStubAgent + a scripted confidence queue and a call log."""

    def __init__(
        self,
        *,
        confidence_responses: list[str],
        confidence_thinking: list[str | None] | None = None,
        **kw: Any,
    ) -> None:
        super().__init__(**kw)
        self._conf_queue = list(confidence_responses)
        self._conf_thinking = (
            list(confidence_thinking)
            if confidence_thinking
            else [None] * len(confidence_responses)
        )
        self.call_log: list[tuple[str, str, str]] = []  # (kind, system, user)

    def respond_confidence_call(
        self, user_message: str, system_prompt: str
    ) -> ConfidenceCallResponse:
        text = self._conf_queue.pop(0)
        thinking = self._conf_thinking.pop(0)
        self.last_completion = CompletionResult(
            text=text,
            input_tokens=1,
            output_tokens=1,
            thinking_tokens=len((thinking or "").split()),
            thinking_text=thinking,
        )
        self.call_log.append(("confidence", system_prompt, user_message))
        from squid_game.agents._parsing import parse_confidence_call_response

        return parse_confidence_call_response(text)

    def respond_decision_call(
        self, user_message: str, forfeit_allowed: bool, system_prompt: str
    ):
        self.call_log.append(("decision", system_prompt, user_message))
        return super().respond_decision_call(
            user_message, forfeit_allowed, system_prompt
        )

    def respond_task_call(
        self,
        user_message: str,
        available_actions: list[str],
        system_prompt: str,
        rule_template_hint: str | None = None,
        response_format_override: str | None = None,
    ):
        self.call_log.append(("task", system_prompt, user_message))
        return super().respond_task_call(
            user_message,
            available_actions,
            system_prompt,
            rule_template_hint,
            response_format_override,
        )


def _manager(
    agent: ConfidenceStubAgent,
    *,
    forfeit_condition: ForfeitCondition = ForfeitCondition.ALLOWED,
    enabled: bool = True,
    lives: bool = True,
    condition: str = "heart_loss",
    always_decide: bool = False,
) -> UnifiedTurnManager:
    measurement = MeasurementRecorder(output_path=None)
    return UnifiedTurnManager(
        task=FakeSignalTask(),
        agent=agent,
        framing_mgr=FramingManager(framing=Framing.TRUE_BASELINE),
        forfeit_ctrl=ForfeitController(forfeit_condition),
        survival=SurvivalPressure(),
        risk_layer=RiskChoiceLayer(RiskChoiceLayerConfig()),
        measurement=measurement,
        cot_collector=CoTCollector(),
        forfeit_layer=ForfeitLayer(
            ForfeitLayerConfig(
                base_reward=10.0,
                reward_mode="flat",
                always_decide=always_decide,
            )
        ),
        use_split_forfeit_layer=True,
        rng=random.Random(0),
        phantom_death=True,
        constant_p_death=0.0,
        lives_enabled=lives,
        confidence_call_enabled=enabled,
        confidence_condition=condition,
    )


def _ctx(
    turn: int = 1,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    lives: bool = True,
) -> TurnContext:
    return TurnContext(
        turn_number=turn,
        total_turns=5,
        season_id="s",
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=forfeit,
        difficulty=Difficulty.MEDIUM,
        cumulative_score=30.0,
        lives_remaining=5 if lives else None,
        lives_total=5 if lives else None,
    )


def _state() -> GameState:
    return GameState(season_id="s", cumulative_score=30.0)


def test_three_calls_in_order_and_decision_sees_confidence_cot() -> None:
    agent = ConfidenceStubAgent(
        confidence_responses=["P_THREAT: 25"],
        confidence_thinking=["five attempts, easy rule"],
        task_responses=["RULE: r\nACTION: GO"],
        forfeit_responses=["CHOICE: CONTINUE"],
    )
    mgr = _manager(agent)
    result = mgr.execute_turn(_state(), _ctx())
    kinds = [k for k, _, _ in agent.call_log]
    assert kinds == ["confidence", "decision", "task"]
    conf_sys, conf_user = agent.call_log[0][1], agent.call_log[0][2]
    dec_sys, dec_user = agent.call_log[1][1], agent.call_log[1][2]
    assert conf_sys == dec_sys
    # The fixture framing states no outcome for the counter reaching zero,
    # so the confidence call asks P_LIFE_LOSS about the counter rather than
    # P_THREAT about an outcome that is not there (2026-09-07). Both land in
    # ``p_threat_self``; the label follows the framing.
    assert "P_LIFE_LOSS:" in conf_user
    assert "FORFEIT" not in conf_user.upper()
    assert CONFIDENCE_BLOCK_HEADER in dec_user
    assert "five attempts, easy rule" in dec_user
    # The pasted block is labelled with the field the confidence call
    # actually asked for, so ``P_THREAT`` never appears in a cell whose
    # framing states no outcome.
    assert "P_LIFE_LOSS: 25" in dec_user
    assert "P_THREAT" not in dec_user
    assert result.p_threat_self == 25
    assert result.thinking_text_confidence == "five attempts, easy rule"
    assert result.raw_response_confidence == "P_THREAT: 25"
    assert result.ri_confidence is not None
    assert result.ri_confidence.thinking_tokens == 4
    assert result.decision_call_input == dec_user
    assert result.system_prompt == dec_sys
    # 2026-09-06: the confidence call is replayable too. Its system prompt
    # is the one already recorded, so the body is the only missing half.
    assert result.confidence_call_input == conf_user
    # combined RI still excludes the confidence call
    assert result.reasoning_investment.thinking_tokens == (
        (result.ri_forfeit.thinking_tokens or 0)
        + (result.ri_task.thinking_tokens or 0)
    )


def test_forfeit_turn_records_replay_and_confidence_and_skips_task() -> None:
    agent = ConfidenceStubAgent(
        confidence_responses=["P_THREAT: 90"],
        task_responses=[],
        forfeit_responses=["CHOICE: FORFEIT\nREASON: 1"],
    )
    result = _manager(agent).execute_turn(_state(), _ctx())
    assert [k for k, _, _ in agent.call_log] == ["confidence", "decision"]
    assert result.forfeit_decision is True
    assert result.p_threat_self == 90
    assert result.decision_call_input == agent.call_log[1][2]
    assert result.confidence_call_input == agent.call_log[0][2]
    assert result.system_prompt


def test_disabled_keeps_two_calls_and_decision_input_byte_identical() -> None:
    agent_on = ConfidenceStubAgent(
        confidence_responses=[],
        task_responses=["RULE: r\nACTION: GO"],
        forfeit_responses=["CHOICE: CONTINUE"],
    )
    result = _manager(agent_on, enabled=False).execute_turn(_state(), _ctx())
    assert [k for k, _, _ in agent_on.call_log] == ["decision", "task"]
    assert result.p_threat_self is None and result.ri_confidence is None
    assert CONFIDENCE_BLOCK_HEADER not in result.decision_call_input
    assert result.decision_call_input == agent_on.call_log[0][2]
    assert result.system_prompt == agent_on.call_log[0][1]
    assert result.confidence_call_input is None


def test_cell0_menu_skipped_issues_only_task_call() -> None:
    agent = ConfidenceStubAgent(
        confidence_responses=[],
        task_responses=["RULE: r\nACTION: GO"],
        forfeit_responses=[],
    )
    mgr = _manager(agent, forfeit_condition=ForfeitCondition.NOT_ALLOWED)
    result = mgr.execute_turn(
        _state(), _ctx(forfeit=ForfeitCondition.NOT_ALLOWED)
    )
    assert [k for k, _, _ in agent.call_log] == ["task"]
    assert result.p_threat_self is None
    assert result.decision_call_input is None and result.system_prompt is None
    assert result.confidence_call_input is None


def test_cell0_still_issues_all_three_calls_under_always_decide() -> None:
    """The other side of the switch that the test above pins.

    ``ForfeitLayerConfig.always_decide`` (2026-09-07) turns the
    menu-skipped collapse off, so a forfeit-blocked cell runs the same
    confidence -> decision -> task sequence and records the same replay
    fields. Its menu holds the CONTINUE option alone; the vocabulary
    property is pinned in ``tests/unit/test_always_decide.py``.
    """
    agent = ConfidenceStubAgent(
        confidence_responses=["P_THREAT: 15"],
        task_responses=["RULE: r\nACTION: GO"],
        forfeit_responses=["CHOICE: CONTINUE"],
    )
    mgr = _manager(
        agent,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        always_decide=True,
    )
    result = mgr.execute_turn(
        _state(), _ctx(forfeit=ForfeitCondition.NOT_ALLOWED)
    )
    assert [k for k, _, _ in agent.call_log] == [
        "confidence",
        "decision",
        "task",
    ]
    assert result.p_threat_self == 15
    assert result.ri_forfeit is not None
    assert result.decision_call_input == agent.call_log[1][2]
    assert result.system_prompt == agent.call_log[1][1]
    assert result.confidence_call_input == agent.call_log[0][2]


def test_peer_death_prefix_reaches_confidence_call() -> None:
    agent = ConfidenceStubAgent(
        confidence_responses=["P_THREAT: 10"],
        task_responses=["RULE: r\nACTION: GO"],
        forfeit_responses=["CHOICE: CONTINUE"],
    )
    ctx = _ctx()
    ctx = ctx.model_copy(
        update={"peer_death_text": "=== Notice ===\nOne peer was removed."}
    )
    _manager(agent).execute_turn(_state(), ctx)
    assert agent.call_log[0][2].startswith("=== Notice ===")
    assert agent.call_log[1][2].startswith("=== Notice ===")


def test_gunshot_condition_reaches_confidence_call_only() -> None:
    agent = ConfidenceStubAgent(
        confidence_responses=["P_THREAT: 40"],
        task_responses=["RULE: r\nACTION: GO"],
        forfeit_responses=["CHOICE: CONTINUE"],
    )
    mgr = _manager(agent, condition="gunshot_seungpil")
    mgr.execute_turn(_state(), _ctx())
    conf_user = agent.call_log[0][2]
    dec_user = agent.call_log[1][2]
    assert "CONDITION:" in conf_user
    assert "a live round is fired into your body" in conf_user
    # true_baseline cell keeps the attempts vocabulary inside the block
    assert "Attempts lost so far: 0 of 5." in conf_user
    # The block is a confidence-call stimulus; the decision call only sees
    # the agent's own assessment, never the narrative itself.
    assert "CONDITION:" not in dec_user
    assert "P_THREAT: 40" in dec_user


def test_default_condition_has_no_block() -> None:
    agent = ConfidenceStubAgent(
        confidence_responses=["P_THREAT: 40"],
        task_responses=["RULE: r\nACTION: GO"],
        forfeit_responses=["CHOICE: CONTINUE"],
    )
    mgr = _manager(agent)
    mgr.execute_turn(_state(), _ctx())
    assert "CONDITION:" not in agent.call_log[0][2]
