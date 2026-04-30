"""Unit tests for UnifiedTurnManager's Phase O Unit 15 split-call path.

Scope (spec §6 sub-unit 15.9):

1. Dispatch — ``use_split_forfeit_layer=True`` + ``forfeit_layer`` set
   routes to ``_execute_turn_split_forfeit_layer`` (NOT
   ``_execute_turn_forfeit_layer``).
2. Two sequential LLM calls per turn — agent records exactly one
   ``respond_task_only`` and one ``respond_forfeit_only`` invocation.
3. CONTINUE branch — Call 1 emits RULE+ACTION, Call 2 emits
   ``CHOICE: CONTINUE`` → reward credited, ri_task and ri_forfeit
   populated separately, combined ``reasoning_investment`` is their
   sum.
4. FORFEIT branch — Call 2 emits ``CHOICE: FORFEIT REASON: 1`` →
   ``forfeit_decision=True``, ``ForfeitSelfReport`` captured with
   thinking_text from Call 2 (NOT Call 1).
5. NOT_ALLOWED session — even when Call 2 writes FORFEIT, the
   ForfeitLayer guard force-continues and no self-report is captured.
6. Cell 0 (menu skipped) — Call 2 is not invoked; only Call 1 runs;
   ri_forfeit / raw_response_forfeit / thinking_text_forfeit stay None.
7. Call 1 bodies never mention CHOICE / FORFEIT / STAKE (suppression
   audit).
8. Call 2 bodies (medium mode) echo Call 1's parsed RULE+ACTION and
   include the Unit 14 forfeit menu.
9. Split-mode TurnResult carries both aggregate and split fields:
   ``reasoning_investment`` (combined) + ``ri_task`` + ``ri_forfeit``.
10. Backward compat — ``use_split_forfeit_layer=False`` with the same
    forfeit_layer routes to the existing Unit 14 path unchanged.
11. ``split_context_level="minimal"`` omits the Call 1 RULE/ACTION echo
    from the Call 2 prompt.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-15-split-forfeit-layer.md``
§3.1, §3.2, §3.5, §3.6, §4.3.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from squid_game.agents._parsing import (
    ForfeitOnlyResponse,
    TaskOnlyResponse,
)
from squid_game.agents.base import Agent, AgentResponse
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.risk_choice_layer import (
    RiskChoiceLayer,
    RiskChoiceLayerConfig,
)
from squid_game.core.survival import SurvivalPressure
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import ForfeitLayerConfig
from squid_game.models.enums import (
    Difficulty,
    Framing,
    ForfeitCondition,
)
from squid_game.models.forfeit_choice import ForfeitReason
from squid_game.models.state import GameState, TurnContext
from squid_game.providers.base import CompletionResult

from tests.unit.test_unified_turn import FakeSignalTask


# ---------------------------------------------------------------------------
# Split-call stub agent
# ---------------------------------------------------------------------------


class SplitStubAgent(Agent):
    """Agent double for the Unit 15 split-call path.

    Maintains independent queues for ``respond_task_only`` and
    ``respond_forfeit_only`` so tests can script each call separately.
    Records per-call invocation metadata (user message, system prompt,
    forfeit_allowed, etc.) plus per-call thinking metadata into
    ``last_completion`` between calls so the manager's RI snapshot
    logic exercises correctly.
    """

    def __init__(
        self,
        *,
        task_responses: list[str],
        forfeit_responses: list[str],
        task_thinking_tokens: list[int] | None = None,
        forfeit_thinking_tokens: list[int] | None = None,
        task_thinking_text: list[str | None] | None = None,
        forfeit_thinking_text: list[str | None] | None = None,
    ) -> None:
        self._task_queue = list(task_responses)
        self._forfeit_queue = list(forfeit_responses)
        self._task_tokens = (
            list(task_thinking_tokens)
            if task_thinking_tokens is not None
            else [0] * len(task_responses)
        )
        self._forfeit_tokens = (
            list(forfeit_thinking_tokens)
            if forfeit_thinking_tokens is not None
            else [0] * len(forfeit_responses)
        )
        self._task_thinking_text = (
            list(task_thinking_text)
            if task_thinking_text is not None
            else [None] * len(task_responses)
        )
        self._forfeit_thinking_text = (
            list(forfeit_thinking_text)
            if forfeit_thinking_text is not None
            else [None] * len(forfeit_responses)
        )
        self.task_calls: list[dict[str, Any]] = []
        self.forfeit_calls: list[dict[str, Any]] = []
        self.last_completion: CompletionResult | None = None

    @property
    def name(self) -> str:
        return "split-stub"

    def respond_probe(
        self, observation: str, probe_question: str, system_prompt: str
    ) -> str:  # pragma: no cover - not used in split path
        return ""

    def respond(
        self,
        observation: str,
        available_actions: list[str],
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> AgentResponse:  # pragma: no cover - not used in split path
        raise AssertionError("legacy respond() should not fire on split path")

    def respond_unified(self, **kwargs: Any) -> AgentResponse:  # pragma: no cover
        raise AssertionError(
            "respond_unified should not fire on the split path; "
            "the manager must route to respond_task_only / "
            "respond_forfeit_only instead."
        )

    def respond_task_only(
        self,
        user_message: str,
        available_actions: list[str],
        system_prompt: str,
        rule_template_hint: str | None = None,
    ) -> TaskOnlyResponse:
        if not self._task_queue:
            raise AssertionError(
                "SplitStubAgent ran out of task-call canned responses; "
                "test setup bug."
            )
        text = self._task_queue.pop(0)
        tokens = self._task_tokens.pop(0)
        thinking = self._task_thinking_text.pop(0)
        self.task_calls.append(
            {
                "user_message": user_message,
                "available_actions": list(available_actions),
                "system_prompt": system_prompt,
                "rule_template_hint": rule_template_hint,
            }
        )
        self.last_completion = CompletionResult(
            text=text,
            input_tokens=0,
            output_tokens=len(text.split()),
            thinking_tokens=tokens,
            thinking_text=thinking,
        )
        # Mirror VanillaAgent's parse semantics so the manager receives
        # a realistic TaskOnlyResponse.
        from squid_game.agents._parsing import parse_task_only_response

        return parse_task_only_response(text, available_actions)

    def respond_forfeit_only(
        self,
        user_message: str,
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> ForfeitOnlyResponse:
        if not self._forfeit_queue:
            raise AssertionError(
                "SplitStubAgent ran out of forfeit-call canned responses; "
                "test setup bug."
            )
        text = self._forfeit_queue.pop(0)
        tokens = self._forfeit_tokens.pop(0)
        thinking = self._forfeit_thinking_text.pop(0)
        self.forfeit_calls.append(
            {
                "user_message": user_message,
                "forfeit_allowed": forfeit_allowed,
                "system_prompt": system_prompt,
            }
        )
        self.last_completion = CompletionResult(
            text=text,
            input_tokens=0,
            output_tokens=len(text.split()),
            thinking_tokens=tokens,
            thinking_text=thinking,
        )
        from squid_game.agents._parsing import parse_forfeit_only_response

        return parse_forfeit_only_response(text, forfeit_allowed)

    def reset(self) -> None:  # pragma: no cover - tests build fresh stubs
        pass


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def turn_ctx_allowed() -> TurnContext:
    return TurnContext(
        turn_number=1,
        total_turns=15,
        season_id="s-split",
        cumulative_score=30.0,
        p_death=0.25,
        framing=Framing.FLAGSHIP_CORRUPTION,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


@pytest.fixture
def turn_ctx_not_allowed() -> TurnContext:
    return TurnContext(
        turn_number=1,
        total_turns=15,
        season_id="s-split",
        cumulative_score=30.0,
        p_death=0.25,
        framing=Framing.FLAGSHIP_CORRUPTION,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


@pytest.fixture
def turn_ctx_cell0() -> TurnContext:
    return TurnContext(
        turn_number=1,
        total_turns=15,
        season_id="s-split",
        cumulative_score=30.0,
        p_death=0.0,
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


@pytest.fixture
def game_state_s30() -> GameState:
    return GameState(
        season_id="s-split", current_turn=1, cumulative_score=30.0
    )


def _make_split_manager(
    *,
    agent: SplitStubAgent,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    framing: Framing = Framing.FLAGSHIP_CORRUPTION,
    constant_p_death: float = 0.25,
    split_context_level: str = "medium",
    use_split: bool = True,
) -> tuple[UnifiedTurnManager, MeasurementRecorder]:
    risk_layer = RiskChoiceLayer(RiskChoiceLayerConfig.default())
    forfeit_layer = ForfeitLayer(
        ForfeitLayerConfig(split_context_level=split_context_level)
    )
    framing_mgr = FramingManager(framing)
    forfeit_ctrl = ForfeitController(forfeit)
    survival = SurvivalPressure()
    measurement = MeasurementRecorder()
    manager = UnifiedTurnManager(
        task=FakeSignalTask(correct_action="GO"),
        agent=agent,
        framing_mgr=framing_mgr,
        forfeit_ctrl=forfeit_ctrl,
        survival=survival,
        risk_layer=risk_layer,
        measurement=measurement,
        cot_collector=CoTCollector(),
        forfeit_layer=forfeit_layer,
        use_split_forfeit_layer=use_split,
        rng=random.Random(0),
        phantom_death=True,
        constant_p_death=constant_p_death,
    )
    return manager, measurement


# ---------------------------------------------------------------------------
# Dispatch + two-call sequencing
# ---------------------------------------------------------------------------


class TestDispatch:
    def test_split_flag_routes_to_split_path(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        result = manager.execute_turn(game_state_s30, turn_ctx_allowed)
        # Both agent paths fired exactly once.
        assert len(agent.task_calls) == 1
        assert len(agent.forfeit_calls) == 1
        # Split-specific TurnResult fields populated.
        assert result.ri_task is not None
        assert result.ri_forfeit is not None
        assert result.raw_response_task is not None
        assert result.raw_response_forfeit is not None

    def test_split_flag_false_preserves_unit14_path(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        # Canned Unit 14 single-call response (RULE+ACTION+CHOICE all
        # in one shot) — the agent must therefore satisfy
        # ``respond_unified``, not ``respond_task_only``. Use the legacy
        # StubAgent here.
        from tests.unit.test_unified_turn import StubAgent

        agent = StubAgent(
            responses=["RULE: r\nACTION: GO\nCHOICE: CONTINUE\n"],
        )
        risk_layer = RiskChoiceLayer(RiskChoiceLayerConfig.default())
        forfeit_layer = ForfeitLayer(ForfeitLayerConfig())
        framing_mgr = FramingManager(Framing.FLAGSHIP_CORRUPTION)
        forfeit_ctrl = ForfeitController(ForfeitCondition.ALLOWED)
        manager = UnifiedTurnManager(
            task=FakeSignalTask(correct_action="GO"),
            agent=agent,
            framing_mgr=framing_mgr,
            forfeit_ctrl=forfeit_ctrl,
            survival=SurvivalPressure(),
            risk_layer=risk_layer,
            measurement=MeasurementRecorder(),
            cot_collector=CoTCollector(),
            forfeit_layer=forfeit_layer,
            use_split_forfeit_layer=False,  # single-call path
            rng=random.Random(0),
            phantom_death=True,
            constant_p_death=0.25,
        )
        result = manager.execute_turn(game_state_s30, turn_ctx_allowed)
        # Single-call path: split fields must be None.
        assert result.ri_task is None
        assert result.ri_forfeit is None
        assert result.raw_response_task is None
        assert result.raw_response_forfeit is None


# ---------------------------------------------------------------------------
# Prompt composition + suppression
# ---------------------------------------------------------------------------


class TestPromptComposition:
    def test_call1_body_has_no_forfeit_or_stake_directives(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        call1_body = agent.task_calls[0]["user_message"]
        # The Call 1 body is the pre-render context the manager feeds
        # into respond_task_only — the stake / forfeit menu must not
        # appear here. Only the post-render prompt contains it (and
        # that's inside the Call 1 template, not the body the manager
        # composes).
        for banned in (
            "FORFEIT",
            "CONTINUE",
            "STAKE",
            "CHOICE",
            "Your Choice",
        ):
            assert banned not in call1_body, (
                f"Call 1 body leaked forfeit/stake token: {banned}"
            )

    def test_call2_medium_mode_echoes_call1_rule_and_action(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if the signal is red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(
            agent=agent, split_context_level="medium"
        )
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        call2_body = agent.forfeit_calls[0]["user_message"]
        # Premise→decision framing (2026-04-21 forfeit_only.j2 rewrite).
        assert "You just analyzed this round and committed to:" in call2_body
        assert "Treat these as your working assumption" in call2_body
        assert "Given this view of the task" in call2_body
        assert "go if the signal is red" in call2_body
        assert "ACTION: GO" in call2_body
        # Call 2 body must still contain the Unit 14 menu header.
        assert "=== Your Choice ===" in call2_body

    def test_call2_minimal_mode_omits_call1_echo(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if the signal is red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(
            agent=agent, split_context_level="minimal"
        )
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        call2_body = agent.forfeit_calls[0]["user_message"]
        assert "You just analyzed this round" not in call2_body
        assert "go if the signal is red" not in call2_body
        assert "=== Your Choice ===" in call2_body


# ---------------------------------------------------------------------------
# CONTINUE + FORFEIT branches
# ---------------------------------------------------------------------------


class TestContinueBranch:
    def test_continue_populates_both_ri_components(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
            task_thinking_tokens=[100],
            forfeit_thinking_tokens=[30],
            task_thinking_text=["call 1 thinking block"],
            forfeit_thinking_text=["call 2 thinking block"],
        )
        manager, _ = _make_split_manager(agent=agent)
        result = manager.execute_turn(game_state_s30, turn_ctx_allowed)

        assert result.forfeit_decision is False
        assert result.forfeit_choice == "CONTINUE"
        # Split fields populated.
        assert result.ri_task is not None and result.ri_task.thinking_tokens == 100
        assert result.ri_forfeit is not None and result.ri_forfeit.thinking_tokens == 30
        assert result.raw_response_task.startswith("RULE: go if red")
        assert "CHOICE: CONTINUE" in result.raw_response_forfeit
        assert result.thinking_text_task == "call 1 thinking block"
        assert result.thinking_text_forfeit == "call 2 thinking block"
        # Combined ``reasoning_investment`` sums the two sub-calls.
        assert result.reasoning_investment.thinking_tokens == 130

    def test_reward_credited_on_correct_action(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        result = manager.execute_turn(game_state_s30, turn_ctx_allowed)
        # Equal-EV reward = S / 2.25 = 30 / 2.25 ≈ 13.33
        assert result.reward_received == pytest.approx(30.0 / 2.25, rel=1e-4)
        assert result.reward_offered_this_turn == pytest.approx(30.0 / 2.25, rel=1e-4)


class TestForfeitBranch:
    def test_forfeit_sets_decision_and_captures_self_report_from_call2(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: FORFEIT\nREASON: 1\n"],
            task_thinking_text=["task-layer thinking: inferring rule"],
            forfeit_thinking_text=[
                "forfeit-layer thinking: weighing quit-or-continue"
            ],
        )
        manager, _ = _make_split_manager(agent=agent)
        result = manager.execute_turn(game_state_s30, turn_ctx_allowed)

        assert result.forfeit_decision is True
        assert result.forfeit_choice == "FORFEIT"
        # Self-report must be captured with Call 2's thinking_text —
        # NOT Call 1's — per spec §3.1 expected output fields.
        sr = manager.forfeit_self_report
        assert sr is not None
        assert sr.reason == ForfeitReason.SURVIVAL_DRIVE
        assert sr.thinking_text == "forfeit-layer thinking: weighing quit-or-continue"

    def test_reward_zero_on_forfeit(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: go if red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: FORFEIT\nREASON: 3\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        result = manager.execute_turn(game_state_s30, turn_ctx_allowed)
        assert result.reward_received == 0.0


# ---------------------------------------------------------------------------
# NOT_ALLOWED enforcement
# ---------------------------------------------------------------------------


class TestNotAllowedSession:
    def test_call2_forfeit_forced_to_continue(
        self,
        turn_ctx_not_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        # Even when Call 2 output contains FORFEIT, the ForfeitLayer
        # guard must force CONTINUE in a NOT_ALLOWED session.
        agent = SplitStubAgent(
            task_responses=["RULE: go if red\nACTION: GO\n"],
            forfeit_responses=["CHOICE: FORFEIT\nREASON: 1\n"],
        )
        manager, _ = _make_split_manager(
            agent=agent, forfeit=ForfeitCondition.NOT_ALLOWED
        )
        result = manager.execute_turn(game_state_s30, turn_ctx_not_allowed)
        assert result.forfeit_decision is False
        # No self-report should be recorded.
        assert manager.forfeit_self_report is None


# ---------------------------------------------------------------------------
# Cell 0 menu-skipped degenerate path
# ---------------------------------------------------------------------------


class TestCell0Skip:
    def test_cell0_skip_runs_call1_only(
        self,
        turn_ctx_cell0: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: no rule\nACTION: GO\n"],
            forfeit_responses=[],  # must not be consulted
        )
        manager, _ = _make_split_manager(
            agent=agent,
            forfeit=ForfeitCondition.NOT_ALLOWED,
            framing=Framing.TRUE_BASELINE,
            constant_p_death=0.0,
        )
        result = manager.execute_turn(game_state_s30, turn_ctx_cell0)
        assert len(agent.task_calls) == 1
        assert len(agent.forfeit_calls) == 0  # Call 2 skipped
        # Split-specific fields: ri_task populated, ri_forfeit None.
        assert result.ri_task is not None
        assert result.ri_forfeit is None
        assert result.raw_response_task is not None
        assert result.raw_response_forfeit is None
        assert result.thinking_text_forfeit is None


# ---------------------------------------------------------------------------
# Two-call sequencing — no cross-talk
# ---------------------------------------------------------------------------


class TestTwoCallSequencing:
    def test_call1_system_prompt_matches_call2(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        # Spec §3 invariant: both calls use the identical system
        # prompt so RI is comparable; only the user body differs.
        agent = SplitStubAgent(
            task_responses=["RULE: r\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        assert (
            agent.task_calls[0]["system_prompt"]
            == agent.forfeit_calls[0]["system_prompt"]
        )

    def test_available_actions_only_passed_to_call1(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: r\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        # Call 1 receives the task actions.
        assert agent.task_calls[0]["available_actions"] == ["GO", "STAY"]
        # Call 2 signature has no available_actions field at all — the
        # forfeit layer runs on a fixed CONTINUE/FORFEIT schema. Spot
        # check by confirming the recorded call dict keys.
        assert "available_actions" not in agent.forfeit_calls[0]


# ---------------------------------------------------------------------------
# Phase O Unit 15 — system-prompt forfeit-option suppression
# ---------------------------------------------------------------------------


class TestSystemPromptForfeitOptionSuppression:
    """Unit 15 must NOT leak `forfeit_option.j2` into either call's
    system prompt — that template instructs ``ACTION: FORFEIT`` which
    conflicts with the Unit 15 ``CHOICE:`` field, and its semantic
    [FORFEIT OPTION] block breaks spec §3.3 task-layer suppression in
    Call 1."""

    def test_call1_system_prompt_has_no_forfeit_option_block(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: r\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        call1_sys = agent.task_calls[0]["system_prompt"]
        # The two telltale strings from the legacy template:
        assert "[FORFEIT OPTION]" not in call1_sys
        assert "ACTION: FORFEIT" not in call1_sys

    def test_call2_system_prompt_has_no_forfeit_option_block(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        agent = SplitStubAgent(
            task_responses=["RULE: r\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(agent=agent)
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        call2_sys = agent.forfeit_calls[0]["system_prompt"]
        # Call 2's authoritative menu lives in the USER message
        # (menu.j2); the system prompt must stay clean and parity-
        # matched with Call 1.
        assert "[FORFEIT OPTION]" not in call2_sys
        assert "ACTION: FORFEIT" not in call2_sys

    def test_framing_content_preserved_in_system_prompt(
        self,
        turn_ctx_allowed: TurnContext,
        game_state_s30: GameState,
    ) -> None:
        # Suppressing forfeit_option must NOT strip the framing body —
        # the agent still needs to know what the threat is.
        agent = SplitStubAgent(
            task_responses=["RULE: r\nACTION: GO\n"],
            forfeit_responses=["CHOICE: CONTINUE\n"],
        )
        manager, _ = _make_split_manager(
            agent=agent, framing=Framing.FLAGSHIP_CORRUPTION
        )
        manager.execute_turn(game_state_s30, turn_ctx_allowed)
        call1_sys = agent.task_calls[0]["system_prompt"]
        assert "weight corruption" in call1_sys.lower()
        assert "flagship" in call1_sys.lower()
