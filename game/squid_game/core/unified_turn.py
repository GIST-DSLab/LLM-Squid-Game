"""Unified turn manager for the v3 Risk-Choice-Layer architecture.

``UnifiedTurnManager`` orchestrates the following per-turn flow:

    Phase 1: TaskModule.prepare        (Y-axis stimulus)
    Phase 2: RiskChoiceLayer.render    (X-axis stake menu)
    Phase 3: Single LLM call           (combined task action + stake)
    Phase 4: Parse task + stake        (from the same response)
    Phase 5: Forfeit handling          (preserves cumulative score)
    Phase 6: Score task + reward calc  (success_factor × multiplier × base)
    Phase 7: Death roll                (skipped in Phantom Death mode)
    Phase 8: Build & record TurnResult

Compared to the legacy ``TurnManager`` (``core/legacy/turn.py``) this manager
collapses probe + action into a single LLM call. The probe channel is
removed because the X-axis instrument is now the Risk Choice Layer
(stake distribution + α_stake), not probe-derived rule comprehension.

Design contracts (locked at the Phase B → C transition):

* The manager **does not mutate** ``GameState``. It returns a
  ``TurnResult`` carrying ``reward_received`` / ``died`` / ``forfeit_decision``;
  the engine (Phase F) is the sole owner of state mutation. This keeps
  the manager safe to call concurrently across sessions.
* When ``base_p_death == 0`` and forfeit is disallowed, the stake menu
  is **skipped** (Cell 0 baseline). The agent receives only framing +
  task stimulus; the layer behaves as if a 1x stake were chosen for
  reward calculation, but ``stake_choice`` is recorded as ``None`` so
  analyses can distinguish "no menu shown" from "agent chose 1x".
* The system prompt is the framing rendering plus
  ``task.get_system_rules()``. The user message concatenates
  ``task_ctx.prompt_section`` then (optionally) the rendered stake menu.
"""

from __future__ import annotations

import logging
import random
from typing import Any

from squid_game.agents._parsing import (
    build_forfeit_only_message,
    build_psuccess_probe_message,
)
from squid_game.agents.base import Agent
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.legacy.risk_choice_layer import RiskChoiceLayer
from squid_game.core.legacy.survival import SurvivalPressure
from squid_game.core.turn_conditions import (
    is_baseline_flagship_framing,
    is_corruption_framing,
    is_corruption_terminal_framing,
    is_survival_framing,
    resolve_base_p_death,
    should_skip_menu,
)
from squid_game.core.turn_prompts import (
    build_system_prompt,
    compose_call1_user_message,
    compose_user_message,
    derive_action_hint,
    format_history_block,
    format_prior_accuracy_summary,
)
from squid_game.core.turn_results import (
    build_continue_result,
    build_forfeit_layer_continue_result,
    build_forfeit_layer_result,
    build_forfeit_result,
)
from squid_game.models.forfeit_choice import (
    CONTINUE_CHOICE,
    FORFEIT_CHOICE,
    ForfeitChoice,
    ForfeitSelfReport,
)
from squid_game.models.results import (
    ReasoningInvestment,
    TurnResult,
)
from squid_game.models.risk_choice import (
    FORFEIT_STAKE,
    RiskChoice,
    VALID_STAKE_KEYS,
)
from squid_game.models.state import GameState, TurnContext
from squid_game.tasks.base import RiskAwareTaskModule, TaskOutcome

logger = logging.getLogger(__name__)


# Stake key used internally when the menu is skipped (Cell 0 baseline).
# Reward is then ``success_factor × 1.0 × base_reward``. The recorded
# ``stake_choice`` on the TurnResult stays None so downstream analyses
# can tell "menu skipped" from "agent picked 1x".
_BASELINE_STAKE: str = "1"


class UnifiedTurnManager:
    """v3 turn manager: single-call Task + Risk + Resolution flow.

    Constructor wires in the universal X-axis components plus a
    pluggable ``RiskAwareTaskModule``. Per-turn state lives on the
    manager's ``_history`` list (used to render cumulative history blocks
    when ``history_mode='cumulative'``).
    """

    def __init__(
        self,
        task: RiskAwareTaskModule,
        agent: Agent,
        framing_mgr: FramingManager,
        forfeit_ctrl: ForfeitController,
        survival: SurvivalPressure,
        risk_layer: RiskChoiceLayer,
        measurement: MeasurementRecorder,
        cot_collector: CoTCollector | None = None,
        *,
        forfeit_layer: ForfeitLayer | None = None,
        use_split_forfeit_layer: bool = False,
        use_psuccess_probe: bool = False,
        rng: random.Random | None = None,
        phantom_death: bool = True,
        constant_p_death: float | None = None,
        action_hint: str | None = None,
        history_mode: str = "cumulative",
        max_history_turns: int = 15,
    ) -> None:
        """Initialise the unified turn manager.

        Args:
            task: A ``RiskAwareTaskModule`` (e.g. ``NullTask``,
                ``SignalGameTask``).
            agent: LLM agent honouring the ``Agent`` contract.
            framing_mgr: FramingManager for the active framing condition.
            forfeit_ctrl: Controller deciding whether forfeit is offered
                this season.
            survival: SurvivalPressure used to compute the per-turn base
                ``p_death`` (overridable via ``constant_p_death``).
            risk_layer: The X-axis RiskChoiceLayer instance.
            measurement: MeasurementRecorder collecting TurnResults.
            cot_collector: Optional CoTCollector for RI metrics. A fresh
                one is constructed if omitted.
            forfeit_layer: Phase O Unit 14 optional Equal-EV Forfeit-Layer.
                When supplied, the manager dispatches to the forfeit-layer
                execution path: binary CHOICE/CONTINUE menu, equal-EV
                calibrated reward, self-report probe on FORFEIT. When
                ``None`` (default) the manager uses the legacy
                Risk-Choice-Layer stake menu, preserving all
                pre-Unit-14 behaviour.
            rng: Seeded RNG for the death roll. Defaults to a non-seeded
                ``random.Random()`` for ad-hoc use; the engine should
                pass a seeded instance for reproducibility.
            phantom_death: When True (default for Phase 3 pilots), the
                death roll is recorded but never zeroes ``score``.
            constant_p_death: When set, used directly as ``base_p_death``
                for every turn (matches Phase 3 design's constant
                schedule). When None, ``survival.calculate_p_death`` is
                used.
            action_hint: Optional placeholder text passed to the stake
                menu (e.g. ``"<choose A or B>"`` for Voting). Defaults
                to ``RiskChoiceLayer``'s built-in placeholder.
            history_mode: ``"cumulative"`` / ``"last"`` / ``"none"`` —
                controls how prior-turn outcomes are surfaced in the
                next turn's user prompt.
            max_history_turns: Cap on cumulative-history rendering.
        """
        self._task = task
        self._agent = agent
        self._framing_mgr = framing_mgr
        self._forfeit_ctrl = forfeit_ctrl
        self._survival = survival
        self._risk_layer = risk_layer
        self._forfeit_layer = forfeit_layer
        # Phase O Unit 15 — split-call dispatch flag. Only consulted when
        # ``_forfeit_layer`` is non-None (the dispatcher in execute_turn
        # guarantees this). Defaults to False → Unit 14 single-call path.
        self._use_split_forfeit_layer = use_split_forfeit_layer
        # Phase O Unit 17 — self-report p_success probe flag. Only
        # consulted inside _execute_turn_split_forfeit_layer; the nested
        # ExperimentConfig validator rejects any combination where this
        # is True without split-call, so no additional guard is needed
        # here. Defaults to False → no probe call inserted.
        self._use_psuccess_probe = use_psuccess_probe
        self._measurement = measurement
        self._cot_collector = cot_collector or CoTCollector()
        self._rng = rng if rng is not None else random.Random()
        self._phantom_death = phantom_death
        self._constant_p_death = constant_p_death
        self._action_hint = action_hint
        self._history_mode = history_mode
        self._max_history_turns = max_history_turns
        self._history: list[dict[str, Any]] = []
        # Phase N — ordered list of committed, non-forfeit, menu-rendered
        # stake keys (oldest first). Feeds
        # ``RiskChoiceLayer.compute_cumulative_carryover`` each turn.
        # Session isolation: the engine constructs a fresh manager per
        # season (engine.py Phase F invariant), so this list naturally
        # resets to [] at each season boundary.
        self._stake_history: list[str] = []
        # Phase O Unit 14 — captured forfeit self-report (if any). Pulled
        # by the engine after run_season completes to populate the
        # SeasonResult. Only non-None when the forfeit-layer path was
        # taken AND the agent chose FORFEIT.
        self._forfeit_self_report: ForfeitSelfReport | None = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def execute_turn(
        self,
        game_state: GameState,
        turn_context: TurnContext,
    ) -> TurnResult:
        """Run one unified turn and return the resulting TurnResult.

        The method does **not** mutate ``game_state``; the engine is
        responsible for applying ``reward_received`` / ``died`` /
        ``forfeit_decision`` from the returned result.

        When ``forfeit_layer`` is configured (Phase O Unit 14), this
        dispatches to :meth:`_execute_turn_forfeit_layer`; otherwise the
        legacy Risk-Choice-Layer path below runs unchanged.

        Args:
            game_state: Mutable game state (read-only here).
            turn_context: Immutable per-turn context (turn number,
                framing, score-at-start-of-turn, etc.).

        Returns:
            A populated ``TurnResult`` already appended to the
            ``MeasurementRecorder``.
        """
        if self._forfeit_layer is not None:
            if self._use_split_forfeit_layer:
                return self._execute_turn_split_forfeit_layer(
                    game_state, turn_context
                )
            return self._execute_turn_forfeit_layer(game_state, turn_context)
        # ------------------------------------------------------------------
        # Phase 1 — Prepare task stimulus + base p_death
        # ------------------------------------------------------------------
        task_ctx = self._task.prepare(game_state, turn_context)
        base_p_death = resolve_base_p_death(
            turn_context,
            constant_p_death=self._constant_p_death,
            survival=self._survival,
            risk_layer=self._risk_layer,
            stake_history=self._stake_history,
        )
        forfeit_allowed = self._forfeit_ctrl.is_forfeit_allowed()
        survival_framing = is_survival_framing(turn_context)
        corruption_framing = is_corruption_framing(turn_context)
        corruption_terminal_framing = is_corruption_terminal_framing(
            turn_context
        )
        baseline_flagship_framing = is_baseline_flagship_framing(
            turn_context
        )

        # ------------------------------------------------------------------
        # Phase 2 — Compose prompt (system + user)
        # ------------------------------------------------------------------
        # Phase N: thread the carryover-adjusted base into the prompt so
        # the agent observes the rising "Base round-end probability" each
        # turn. TurnContext is frozen; use model_copy. When carryover is
        # disabled (all StakeConfig.carryover == 0) this is a no-op —
        # base_p_death equals the engine-supplied value.
        framing_context = (
            turn_context
            if base_p_death == turn_context.p_death
            else turn_context.model_copy(update={"p_death": base_p_death})
        )
        system_prompt = build_system_prompt(
            framing_context,
            framing_mgr=self._framing_mgr,
            task=self._task,
            forfeit_ctrl=self._forfeit_ctrl,
        )
        menu_skipped = should_skip_menu(base_p_death, forfeit_allowed)

        if menu_skipped:
            stake_menu_text = ""
        else:
            stake_menu_text = self._risk_layer.render_menu(
                forfeit_allowed=forfeit_allowed,
                survival_framing=survival_framing,
                corruption_framing=corruption_framing,
                corruption_terminal_framing=corruption_terminal_framing,
                baseline_flagship_framing=baseline_flagship_framing,
                action_hint=self._action_hint
                if self._action_hint is not None
                else derive_action_hint(self._task),
            )
        user_message = compose_user_message(
            task_ctx,
            stake_menu_text,
            history=self._history,
            history_mode=self._history_mode,
            max_history_turns=self._max_history_turns,
        )

        # ------------------------------------------------------------------
        # Phase 3 — Single LLM call
        # ------------------------------------------------------------------
        # Phase K Fix 3: use the dedicated unified-turn entrypoint so the
        # agent renders ``unified_turn_message.j2`` (ACTION + STAKE + RULE
        # response format) instead of the legacy ``action_message.j2``
        # which double-wraps the body and inherits probe directives.
        # Phase L: ask the task (duck-typed) for a difficulty-aware RULE
        # template string. SignalGame returns the EASY/MEDIUM/HARD
        # template matching ``probe.j2``; NullTask (no such method) →
        # None → free-form placeholder preserved.
        rule_template_hint = getattr(
            self._task, "get_rule_template_hint", lambda: None
        )()
        agent_response = self._agent.respond_unified(
            user_message=user_message,
            available_actions=self._task.get_available_actions(),
            stake_menu_shown=not menu_skipped,
            forfeit_allowed=forfeit_allowed,
            system_prompt=system_prompt,
            rule_template_hint=rule_template_hint,
        )
        raw_text = agent_response.raw_text
        completion = self._agent.last_completion
        thinking_text = getattr(completion, "thinking_text", None)
        thinking_tokens = getattr(completion, "thinking_tokens", None) or 0

        # ------------------------------------------------------------------
        # Phase 4 — Parse task + stake from the same response
        # ------------------------------------------------------------------
        task_parsed = self._task.parse_response(raw_text)
        risk_choice = self._resolve_risk_choice(
            raw_text=raw_text,
            agent_response_forfeit=agent_response.forfeit,
            forfeit_allowed=forfeit_allowed,
            menu_skipped=menu_skipped,
        )

        # Reasoning Investment (combined task + stake reasoning).
        reasoning_investment = self._cot_collector.record(raw_text)
        if thinking_tokens:
            reasoning_investment = ReasoningInvestment(
                total_tokens=reasoning_investment.total_tokens,
                reasoning_steps=reasoning_investment.reasoning_steps,
                thinking_tokens=thinking_tokens,
            )

        # ------------------------------------------------------------------
        # Phase 5 — Forfeit handling
        # ------------------------------------------------------------------
        if risk_choice.stake == FORFEIT_STAKE:
            preserved = self._forfeit_ctrl.process_forfeit(
                turn_context.cumulative_score
            )
            self._record_history(
                turn_number=turn_context.turn_number,
                task_ctx=task_ctx,
                task_outcome=None,  # forfeit exits before task scoring
                stake_choice=None,  # menu_skipped=False here, but FORFEIT exits
                cumulative_after=preserved,
                outcome_summary="forfeit",
            )
            return self._record(
                build_forfeit_result(
                    turn_context=turn_context,
                    user_message=user_message,
                    raw_text=raw_text,
                    thinking_text=thinking_text,
                    reasoning_investment=reasoning_investment,
                    ground_truth_rule=self._resolve_ground_truth_rule(),
                )
            )

        # ------------------------------------------------------------------
        # Phase 6 — Score task + compute reward / p_death
        # ------------------------------------------------------------------
        task_outcome = self._task.score(task_parsed, game_state)
        if menu_skipped:
            # Cell 0 (true_baseline) baseline path — no stake gradient
            # exists in this cell, so reward is the pure success-scaled
            # base reward (no multiplier, no flat_cost). This keeps the
            # Cell 0 score scale comparable across phases:
            #   Phase 3 canonical (stake 1 = 1.0x, no flat_cost) → 0/+10
            #   Phase N         (stake 1 = 1.0x, no flat_cost) → 0/+10
            #   Phase O         (stake 1 = 0.5x, flat_cost 3.0) — the
            #     synthetic-stake-1 path would yield −3/+2, breaking
            #     cross-cell comparability. Bypassing the stake formula
            #     restores the framing-free baseline semantics.
            # p_death is still computed via the stake helper because
            # base_p_death=0 in Cell 0 makes the helper a no-op, and
            # keeping the call site uniform avoids drift between Cell 0
            # and other paths if a future config sets base_p_death > 0
            # while still skipping the menu.
            reward = (
                task_outcome.success_factor
                * self._risk_layer.config.base_reward
            )
            p_death_eff = self._risk_layer.calculate_p_death(
                base_p_death, _BASELINE_STAKE
            )
        else:
            reward = self._risk_layer.calculate_reward(
                task_outcome, risk_choice.stake
            )
            p_death_eff = self._risk_layer.calculate_p_death(
                base_p_death, risk_choice.stake
            )

        # Phase N — commit the stake into cumulative history.
        # Skipped when the menu was hidden (Cell 0 baseline): no agent
        # choice was made, so no carryover accrues. FORFEIT turns
        # already returned in Phase 5 and are excluded by construction.
        # The append happens before the death roll so that, in
        # actual_death mode, the final turn that may end the season
        # still correctly carries its stake for any retrospective
        # analysis that replays history.
        if not menu_skipped:
            self._stake_history.append(risk_choice.stake)

        # ------------------------------------------------------------------
        # Phase 7 — Death roll (skipped in Phantom Death mode)
        # ------------------------------------------------------------------
        if self._phantom_death:
            died = False
        else:
            died = self._rng.random() < p_death_eff

        # ------------------------------------------------------------------
        # Phase 8 — Build and record TurnResult
        # ------------------------------------------------------------------
        cumulative_after = (
            0.0
            if died
            else turn_context.cumulative_score + reward
        )
        self._record_history(
            turn_number=turn_context.turn_number,
            task_ctx=task_ctx,
            task_outcome=task_outcome,
            stake_choice=None if menu_skipped else risk_choice.stake,
            cumulative_after=cumulative_after,
            outcome_summary=("died" if died else f"+{reward:.0f}"),
        )

        # Merge prepare-time and score-time metadata into a single dict.
        # Score metadata wins on key collision so the canonical
        # ``correct_action``/``signal`` from scoring overrides any
        # earlier preview from ``prepare``.
        merged_metadata: dict = {**task_ctx.metadata, **task_outcome.metadata}

        return self._record(
            build_continue_result(
                turn_context=turn_context,
                user_message=user_message,
                raw_text=raw_text,
                thinking_text=thinking_text,
                reasoning_investment=reasoning_investment,
                task_outcome=task_outcome,
                stake_choice=None if menu_skipped else risk_choice.stake,
                reward=reward,
                p_death_applied=p_death_eff,
                died=died,
                task_metadata=merged_metadata,
                ground_truth_rule=self._resolve_ground_truth_rule(),
            )
        )

    # ------------------------------------------------------------------
    # Phase O Unit 14 — Forfeit-Layer execution path
    # ------------------------------------------------------------------

    def _execute_turn_forfeit_layer(
        self,
        game_state: GameState,
        turn_context: TurnContext,
    ) -> TurnResult:
        """Unit 14 equal-EV dispatch path.

        Mirrors the legacy Risk-Choice-Layer path's phase structure but
        replaces stake parsing / reward / p_death with the Forfeit-Layer
        equivalents. Also captures the 3-way self-report probe into
        ``self._forfeit_self_report`` when the agent chooses FORFEIT.

        The method is only reachable when ``self._forfeit_layer is not
        None`` (enforced by the dispatcher in ``execute_turn``), so no
        defensive re-check is needed.
        """
        assert self._forfeit_layer is not None  # dispatcher guarantee

        # Phase 1 — prepare task + framing flags + forfeit availability.
        task_ctx = self._task.prepare(game_state, turn_context)
        forfeit_allowed = self._forfeit_ctrl.is_forfeit_allowed()
        corruption_framing = is_corruption_framing(turn_context)
        corruption_terminal_framing = is_corruption_terminal_framing(
            turn_context
        )
        baseline_flagship_framing = is_baseline_flagship_framing(
            turn_context
        )
        survival_framing = is_survival_framing(turn_context)

        # Phase 2 — compose prompts (system + user).
        # The Forfeit-Layer does NOT use per-turn carryover arithmetic,
        # so the framing context is the raw turn_context. Turn-level
        # p_death override (Cell 5 BP measurement at 0.0, Cells 1-4 at
        # config value) is resolved once here and threaded through every
        # Forfeit-Layer call below so the menu / reward / death roll all
        # agree on the same value.
        base_p_death = resolve_base_p_death(
            turn_context,
            constant_p_death=self._constant_p_death,
            survival=self._survival,
            risk_layer=self._risk_layer,
            stake_history=self._stake_history,
        )
        system_prompt = build_system_prompt(
            turn_context,
            framing_mgr=self._framing_mgr,
            task=self._task,
            forfeit_ctrl=self._forfeit_ctrl,
        )
        menu_text = self._forfeit_layer.render_menu(
            current_score=turn_context.cumulative_score,
            turn_number=turn_context.turn_number,
            total_turns=turn_context.total_turns,
            forfeit_allowed=forfeit_allowed,
            turn_p_death=base_p_death,
            corruption_framing=corruption_framing,
            corruption_terminal_framing=corruption_terminal_framing,
            baseline_flagship_framing=baseline_flagship_framing,
            survival_framing=survival_framing,
        )
        user_message = compose_user_message(
            task_ctx,
            menu_text,
            history=self._history,
            history_mode=self._history_mode,
            max_history_turns=self._max_history_turns,
        )

        # Phase 3 — single LLM call (task + CHOICE + REASON on FORFEIT).
        rule_template_hint = getattr(
            self._task, "get_rule_template_hint", lambda: None
        )()
        agent_response = self._agent.respond_unified(
            user_message=user_message,
            available_actions=self._task.get_available_actions(),
            stake_menu_shown=False,  # stake path inactive in the forfeit-layer
            forfeit_allowed=forfeit_allowed,
            system_prompt=system_prompt,
            rule_template_hint=rule_template_hint,
            forfeit_layer_active=True,
        )
        raw_text = agent_response.raw_text
        completion = self._agent.last_completion
        thinking_text = getattr(completion, "thinking_text", None)
        thinking_tokens = getattr(completion, "thinking_tokens", None) or 0

        # Phase 4 — parse task + choice.
        task_parsed = self._task.parse_response(raw_text)
        forfeit_choice = self._forfeit_layer.parse_choice(raw_text)
        # Defensive: forbid FORFEIT in NOT_ALLOWED sessions. Mirrors the
        # legacy ``_resolve_risk_choice`` guard.
        if not forfeit_allowed and forfeit_choice.choice == FORFEIT_CHOICE:
            logger.warning(
                "ForfeitLayer parsed FORFEIT in NOT_ALLOWED session; "
                "forcing CONTINUE to keep the session moving."
            )
            forfeit_choice = ForfeitChoice(
                choice=CONTINUE_CHOICE, raw_text=forfeit_choice.raw_text
            )

        # Reasoning investment (same shape as the legacy path).
        reasoning_investment = self._cot_collector.record(raw_text)
        if thinking_tokens:
            reasoning_investment = ReasoningInvestment(
                total_tokens=reasoning_investment.total_tokens,
                reasoning_steps=reasoning_investment.reasoning_steps,
                thinking_tokens=thinking_tokens,
            )

        # The calibrated offer is recorded regardless of branch so
        # post-hoc analyses can verify the reward the agent was
        # actually shown.
        reward_offered = self._forfeit_layer.calculate_continue_reward(
            turn_context.cumulative_score, turn_p_death=base_p_death
        )

        # Phase 5 — FORFEIT branch.
        if forfeit_choice.choice == FORFEIT_CHOICE:
            self._forfeit_self_report = (
                self._forfeit_layer.parse_forfeit_reason(
                    raw_text,
                    thinking_text=thinking_text,
                    forfeit_turn=turn_context.turn_number,
                )
            )
            preserved = self._forfeit_ctrl.process_forfeit(
                turn_context.cumulative_score
            )
            self._record_history(
                turn_number=turn_context.turn_number,
                task_ctx=task_ctx,
                task_outcome=None,
                stake_choice=None,
                cumulative_after=preserved,
                outcome_summary="forfeit",
            )
            return self._record(
                build_forfeit_layer_result(
                    turn_context=turn_context,
                    user_message=user_message,
                    raw_text=raw_text,
                    thinking_text=thinking_text,
                    reasoning_investment=reasoning_investment,
                    ground_truth_rule=self._resolve_ground_truth_rule(),
                    choice=FORFEIT_CHOICE,
                    reward_offered=reward_offered,
                )
            )

        # Phase 6 — CONTINUE branch: task scoring → reward/p_death.
        task_outcome = self._task.score(task_parsed, game_state)
        reward = self._forfeit_layer.calculate_reward(
            task_outcome,
            forfeit_choice.choice,
            turn_context.cumulative_score,
            turn_p_death=base_p_death,
        )
        p_death_eff = self._forfeit_layer.calculate_p_death(
            forfeit_choice.choice, turn_p_death=base_p_death
        )

        # Phase 7 — death roll (skipped in phantom-death mode).
        if self._phantom_death:
            died = False
        else:
            died = self._rng.random() < p_death_eff

        cumulative_after = (
            0.0 if died else turn_context.cumulative_score + reward
        )
        self._record_history(
            turn_number=turn_context.turn_number,
            task_ctx=task_ctx,
            task_outcome=task_outcome,
            stake_choice=None,
            cumulative_after=cumulative_after,
            outcome_summary=("died" if died else f"+{reward:.0f}"),
        )
        merged_metadata: dict = {
            **task_ctx.metadata,
            **task_outcome.metadata,
        }

        return self._record(
            build_forfeit_layer_continue_result(
                turn_context=turn_context,
                user_message=user_message,
                raw_text=raw_text,
                thinking_text=thinking_text,
                reasoning_investment=reasoning_investment,
                task_outcome=task_outcome,
                reward=reward,
                p_death_applied=p_death_eff,
                died=died,
                task_metadata=merged_metadata,
                ground_truth_rule=self._resolve_ground_truth_rule(),
                reward_offered=reward_offered,
            )
        )

    def _execute_turn_split_forfeit_layer(
        self,
        game_state: GameState,
        turn_context: TurnContext,
    ) -> TurnResult:
        """Phase O Unit 15 — split-call forfeit-layer dispatch path.

        Two sequential LLM calls per turn so ``thinking_tokens`` can be
        attributed to task reasoning (``ri_task``) vs choice deliberation
        (``ri_forfeit``) cleanly. Order is task-first by design
        (spec §1.3 — instrumental rationality + Unit 14 sequence
        compatibility).

        Dispatcher guarantees: reachable only when both
        ``self._forfeit_layer is not None`` AND
        ``self._use_split_forfeit_layer is True``.

        Cell 0 handling (spec §3.5): when the menu is skipped (Cell 0 has
        ``p_death_override=0.0`` and ``forfeit_condition=not_allowed``)
        Call 2 is *not* invoked — the path degenerates to a single Call 1
        that produces an auto-CONTINUE outcome, keeping backward
        comparability with Unit 14 Cell 0. The split-specific fields
        (``ri_forfeit`` etc.) stay ``None`` on that branch.
        """
        assert self._forfeit_layer is not None  # dispatcher guarantee
        assert self._use_split_forfeit_layer  # dispatcher guarantee

        # Phase 1 — prepare task + framing + forfeit availability.
        task_ctx = self._task.prepare(game_state, turn_context)
        forfeit_allowed = self._forfeit_ctrl.is_forfeit_allowed()
        corruption_framing = is_corruption_framing(turn_context)
        corruption_terminal_framing = is_corruption_terminal_framing(
            turn_context
        )
        baseline_flagship_framing = is_baseline_flagship_framing(
            turn_context
        )
        survival_framing = is_survival_framing(turn_context)

        # Unit 15 split-call: suppress the legacy ``forfeit_option.j2``
        # appendix from the system prompt (see ``_build_system_prompt``
        # docstring). Call 2's ``menu.j2`` user-body carries the
        # authoritative forfeit mechanism + framing-conditional
        # semantics, and Call 1 must stay free of forfeit awareness
        # per spec §3.3.
        system_prompt = build_system_prompt(
            turn_context,
            framing_mgr=self._framing_mgr,
            task=self._task,
            forfeit_ctrl=self._forfeit_ctrl,
            include_forfeit_text=False,
        )
        rule_template_hint = getattr(
            self._task, "get_rule_template_hint", lambda: None
        )()

        # Cell 0 menu-skipped baseline → single-call degenerate path.
        # Mirrors Unit 14's _should_skip_menu signature; we reuse it
        # verbatim so the two paths agree on the condition.
        base_p_death = resolve_base_p_death(
            turn_context,
            constant_p_death=self._constant_p_death,
            survival=self._survival,
            risk_layer=self._risk_layer,
            stake_history=self._stake_history,
        )
        menu_skipped = should_skip_menu(base_p_death, forfeit_allowed)
        if menu_skipped:
            # Degenerate: no meaningful choice, so Call 2 is skipped.
            # Produce a Unit-14-shaped CONTINUE result with ri_task /
            # raw_response_task set so downstream analyses can still
            # pull the task-only RI.
            call1_body = compose_call1_user_message(
                task_ctx,
                history=self._history,
                history_mode=self._history_mode,
                max_history_turns=self._max_history_turns,
            )
            task_parsed_resp = self._agent.respond_task_only(
                user_message=call1_body,
                available_actions=self._task.get_available_actions(),
                system_prompt=system_prompt,
                rule_template_hint=rule_template_hint,
            )
            raw_text_task = task_parsed_resp.raw_text
            completion_task = self._agent.last_completion
            thinking_text_task = getattr(completion_task, "thinking_text", None)
            thinking_tokens_task = (
                getattr(completion_task, "thinking_tokens", None) or 0
            )
            ri_task = self._cot_collector.record(raw_text_task)
            if thinking_tokens_task:
                ri_task = ReasoningInvestment(
                    total_tokens=ri_task.total_tokens,
                    reasoning_steps=ri_task.reasoning_steps,
                    thinking_tokens=thinking_tokens_task,
                )

            task_parsed = self._task.parse_response(raw_text_task)
            task_outcome = self._task.score(task_parsed, game_state)
            # Cell 0 reward path — use the fallback base_reward since
            # the equal-EV formula is degenerate at p_death=0.
            reward = task_outcome.success_factor * self._forfeit_layer.config.base_reward
            cumulative_after = turn_context.cumulative_score + reward
            self._record_history(
                turn_number=turn_context.turn_number,
                task_ctx=task_ctx,
                task_outcome=task_outcome,
                stake_choice=None,
                cumulative_after=cumulative_after,
                outcome_summary=f"+{reward:.0f}",
            )
            merged_metadata: dict = {
                **task_ctx.metadata,
                **task_outcome.metadata,
            }
            return self._record(
                build_forfeit_layer_continue_result(
                    turn_context=turn_context,
                    user_message=call1_body,
                    raw_text=raw_text_task,
                    thinking_text=thinking_text_task,
                    reasoning_investment=ri_task,
                    task_outcome=task_outcome,
                    reward=reward,
                    p_death_applied=0.0,
                    died=False,
                    task_metadata=merged_metadata,
                    ground_truth_rule=self._resolve_ground_truth_rule(),
                    reward_offered=self._forfeit_layer.calculate_continue_reward(
                        turn_context.cumulative_score,
                        turn_p_death=0.0,
                    ),
                    ri_task=ri_task,
                    ri_forfeit=None,
                    raw_response_task=raw_text_task,
                    raw_response_forfeit=None,
                    thinking_text_task=thinking_text_task,
                    thinking_text_forfeit=None,
                    # Unit 17 probe is intentionally skipped on the
                    # Cell 0 degenerate path alongside Call 2 — there is
                    # no forfeit decision to validate, so probe data
                    # would be meaningless.
                    psuccess_self=None,
                    ri_probe=None,
                    raw_response_probe=None,
                    thinking_text_probe=None,
                )
            )

        # Phase 2 — Call 1 (task layer).
        call1_body = compose_call1_user_message(
            task_ctx,
            history=self._history,
            history_mode=self._history_mode,
            max_history_turns=self._max_history_turns,
        )
        task_parsed_resp = self._agent.respond_task_only(
            user_message=call1_body,
            available_actions=self._task.get_available_actions(),
            system_prompt=system_prompt,
            rule_template_hint=rule_template_hint,
        )
        raw_text_task = task_parsed_resp.raw_text
        completion_task = self._agent.last_completion
        thinking_text_task = getattr(completion_task, "thinking_text", None)
        thinking_tokens_task = (
            getattr(completion_task, "thinking_tokens", None) or 0
        )
        ri_task = self._cot_collector.record(raw_text_task)
        if thinking_tokens_task:
            ri_task = ReasoningInvestment(
                total_tokens=ri_task.total_tokens,
                reasoning_steps=ri_task.reasoning_steps,
                thinking_tokens=thinking_tokens_task,
            )

        # Parse Call 1 for the task task_outcome (RULE + ACTION). The
        # SignalGameModule.parse_response contract accepts the raw text
        # of any unified response containing ACTION/RULE — Call 1's
        # output is strictly a subset so reuse is safe.
        task_parsed = self._task.parse_response(raw_text_task)

        # Phase 2.5 — Call 1.5 (self-report p_success probe) [Unit 17].
        # Inserted only when ``use_psuccess_probe=True`` so default split
        # paths stay at 2 calls. The probe echoes Call 1's committed
        # RULE+ACTION strings so the retrospective confidence rating has
        # a referent, but NOT Call 1's thinking (would confound ri_probe).
        # Keeps Call 2 output measurement clean because Call 2 is a
        # separate LLM call whose thinking_tokens are captured on
        # ``self._agent.last_completion`` only after Call 2 returns.
        psuccess_self: int | None = None
        ri_probe: ReasoningInvestment | None = None
        raw_text_probe: str | None = None
        thinking_text_probe: str | None = None
        if self._use_psuccess_probe:
            # Build session-level prior-accuracy summary so the probe
            # value reflects feedback-informed belief (Issue 1 fix
            # from the Round 1 Addendum II §B.2.1 design review).
            # Format mirrors how Call 1 / Call 2 see history: a short
            # factual line without qualitative interpretation, so
            # ri_probe stays small.
            # Phase O Unit 17.8 — also inject the same cumulative
            # history block that Call 1 / Call 2 see into the probe
            # user body, so psuccess_self reflects feedback-informed
            # belief at the same fidelity as the task and forfeit
            # decisions (not only the 1-line prior_accuracy summary).
            prior_accuracy_summary = format_prior_accuracy_summary(
                self._history
            )
            history_block = format_history_block(
                self._history, self._history_mode, self._max_history_turns
            )
            probe_body = build_psuccess_probe_message(
                user_body=history_block,
                rule_from_call1=task_parsed_resp.rule_hypothesis,
                action_from_call1=task_parsed_resp.action,
                prior_accuracy_summary=prior_accuracy_summary,
                current_stimulus=task_ctx.prompt_section,
            )
            probe_resp = self._agent.respond_psuccess_probe_only(
                user_message=probe_body,
                system_prompt=system_prompt,
            )
            raw_text_probe = probe_resp.raw_text
            completion_probe = self._agent.last_completion
            thinking_text_probe = getattr(
                completion_probe, "thinking_text", None
            )
            thinking_tokens_probe = (
                getattr(completion_probe, "thinking_tokens", None) or 0
            )
            ri_probe = self._cot_collector.record(raw_text_probe)
            if thinking_tokens_probe:
                ri_probe = ReasoningInvestment(
                    total_tokens=ri_probe.total_tokens,
                    reasoning_steps=ri_probe.reasoning_steps,
                    thinking_tokens=thinking_tokens_probe,
                )
            psuccess_self = probe_resp.psuccess_self
            if psuccess_self is None:
                logger.warning(
                    "Unit 17 probe: failed to parse P_CORRECT from Call 1.5 "
                    "response (turn=%d, season=%s). Recording None; "
                    "analysis layer will flag this session.",
                    turn_context.turn_number,
                    turn_context.season_id,
                )

        # Phase O Unit 17 — resolve the equal-EV p_success override for
        # the chained-menu path. ``psuccess_override`` is forwarded into
        # every ForfeitLayer call that consults ``p_success_estimate``
        # (render_menu, calculate_continue_reward, calculate_reward),
        # so the menu the agent sees AND the reward the engine credits
        # both agree on the same per-turn calibration. On any of these
        # dispatcher conditions the override stays ``None`` and the
        # layer falls back to ``config.p_success_estimate`` (legacy
        # Option A behaviour):
        #   - use_psuccess_probe=False
        #   - chain_psuccess_to_menu=False on ForfeitLayerConfig
        #   - probe failed to parse (psuccess_self is None)
        psuccess_override: float | None = None
        if (
            self._use_psuccess_probe
            and self._forfeit_layer.config.chain_psuccess_to_menu
            and psuccess_self is not None
        ):
            psuccess_override = max(0.05, min(1.0, psuccess_self / 100.0))

        # Phase 3 — Call 2 (forfeit layer).
        menu_text = self._forfeit_layer.render_menu(
            current_score=turn_context.cumulative_score,
            turn_number=turn_context.turn_number,
            total_turns=turn_context.total_turns,
            forfeit_allowed=forfeit_allowed,
            turn_p_death=base_p_death,
            psuccess_override=psuccess_override,
            corruption_framing=corruption_framing,
            corruption_terminal_framing=corruption_terminal_framing,
            baseline_flagship_framing=baseline_flagship_framing,
            survival_framing=survival_framing,
        )
        split_ctx = self._forfeit_layer.config.split_context_level
        # Phase O Unit 15 (2026-04-21 feedback): under split_context_level
        # "medium" the agent should see the cumulative history block so it
        # can calibrate its own prediction-accuracy before the CONTINUE vs
        # FORFEIT choice. The explicit separation note in forfeit_only.j2
        # instructs the agent not to re-derive the rule in Call 2. Under
        # "minimal" the history is deliberately omitted. Under "full" the
        # call1 full prompt already carries the history so no extra echo.
        history_block = format_history_block(
            self._history, self._history_mode, self._max_history_turns
        )
        user_body_for_call2 = (
            history_block if (split_ctx == "medium" and history_block) else ""
        )
        call2_body = build_forfeit_only_message(
            user_body=user_body_for_call2,
            menu_text=menu_text,
            forfeit_allowed=forfeit_allowed,
            split_context_level=split_ctx,
            rule_from_call1=(
                task_parsed_resp.rule_hypothesis
                if split_ctx == "medium"
                else None
            ),
            action_from_call1=(
                task_parsed_resp.action
                if split_ctx == "medium"
                else None
            ),
            call1_full_prompt=(call1_body if split_ctx == "full" else None),
            call1_thinking=(
                thinking_text_task if split_ctx == "full" else None
            ),
            current_stimulus=(
                task_ctx.prompt_section if split_ctx == "medium" else None
            ),
        )
        forfeit_parsed_resp = self._agent.respond_forfeit_only(
            user_message=call2_body,
            forfeit_allowed=forfeit_allowed,
            system_prompt=system_prompt,
        )
        raw_text_forfeit = forfeit_parsed_resp.raw_text
        completion_forfeit = self._agent.last_completion
        thinking_text_forfeit = getattr(
            completion_forfeit, "thinking_text", None
        )
        thinking_tokens_forfeit = (
            getattr(completion_forfeit, "thinking_tokens", None) or 0
        )
        ri_forfeit = self._cot_collector.record(raw_text_forfeit)
        if thinking_tokens_forfeit:
            ri_forfeit = ReasoningInvestment(
                total_tokens=ri_forfeit.total_tokens,
                reasoning_steps=ri_forfeit.reasoning_steps,
                thinking_tokens=thinking_tokens_forfeit,
            )

        # Phase 4 — parse Call 2 choice using ForfeitLayer for authoritative
        # semantics (NOT_ALLOWED guard + CHOICE enum + raw capture).
        forfeit_choice = self._forfeit_layer.parse_choice(raw_text_forfeit)
        if not forfeit_allowed and forfeit_choice.choice == FORFEIT_CHOICE:
            logger.warning(
                "ForfeitLayer parsed FORFEIT in NOT_ALLOWED session "
                "(split-call path); forcing CONTINUE."
            )
            forfeit_choice = ForfeitChoice(
                choice=CONTINUE_CHOICE, raw_text=forfeit_choice.raw_text
            )

        # Combined fields for backward-compat with single-call analyses.
        # ``reasoning_investment`` / ``raw_response`` / ``thinking_text``
        # receive the SUM / CONCAT so analyses that do not know about
        # the Unit 15 split fields still see a sensible whole-turn value.
        combined_ri = ReasoningInvestment(
            total_tokens=(ri_task.total_tokens or 0)
            + (ri_forfeit.total_tokens or 0),
            reasoning_steps=(ri_task.reasoning_steps or 0)
            + (ri_forfeit.reasoning_steps or 0),
            thinking_tokens=(
                (ri_task.thinking_tokens or 0)
                + (ri_forfeit.thinking_tokens or 0)
            ),
        )
        combined_raw = (
            f"{raw_text_task}\n\n--- Call 2 ---\n\n{raw_text_forfeit}"
        )
        combined_thinking: str | None
        if thinking_text_task and thinking_text_forfeit:
            combined_thinking = (
                f"{thinking_text_task}\n\n--- Call 2 ---\n\n"
                f"{thinking_text_forfeit}"
            )
        else:
            combined_thinking = thinking_text_task or thinking_text_forfeit

        reward_offered = self._forfeit_layer.calculate_continue_reward(
            turn_context.cumulative_score,
            turn_p_death=base_p_death,
            psuccess_override=psuccess_override,
        )
        combined_user_message = (
            f"=== Call 1 ===\n{call1_body}\n\n=== Call 2 ===\n{call2_body}"
        )

        # Phase 5 — FORFEIT branch.
        if forfeit_choice.choice == FORFEIT_CHOICE:
            self._forfeit_self_report = (
                self._forfeit_layer.parse_forfeit_reason(
                    raw_text_forfeit,
                    thinking_text=thinking_text_forfeit,
                    forfeit_turn=turn_context.turn_number,
                )
            )
            preserved = self._forfeit_ctrl.process_forfeit(
                turn_context.cumulative_score
            )
            self._record_history(
                turn_number=turn_context.turn_number,
                task_ctx=task_ctx,
                task_outcome=None,
                stake_choice=None,
                cumulative_after=preserved,
                outcome_summary="forfeit",
            )
            return self._record(
                build_forfeit_layer_result(
                    turn_context=turn_context,
                    user_message=combined_user_message,
                    raw_text=combined_raw,
                    thinking_text=combined_thinking,
                    reasoning_investment=combined_ri,
                    ground_truth_rule=self._resolve_ground_truth_rule(),
                    choice=FORFEIT_CHOICE,
                    reward_offered=reward_offered,
                    ri_task=ri_task,
                    ri_forfeit=ri_forfeit,
                    raw_response_task=raw_text_task,
                    raw_response_forfeit=raw_text_forfeit,
                    thinking_text_task=thinking_text_task,
                    thinking_text_forfeit=thinking_text_forfeit,
                    psuccess_self=psuccess_self,
                    ri_probe=ri_probe,
                    raw_response_probe=raw_text_probe,
                    thinking_text_probe=thinking_text_probe,
                )
            )

        # Phase 6 — CONTINUE branch: task scoring → reward/p_death.
        task_outcome = self._task.score(task_parsed, game_state)
        reward = self._forfeit_layer.calculate_reward(
            task_outcome,
            forfeit_choice.choice,
            turn_context.cumulative_score,
            turn_p_death=base_p_death,
            psuccess_override=psuccess_override,
        )
        p_death_eff = self._forfeit_layer.calculate_p_death(
            forfeit_choice.choice, turn_p_death=base_p_death
        )

        # Phase 7 — death roll (phantom mode bypass).
        if self._phantom_death:
            died = False
        else:
            died = self._rng.random() < p_death_eff

        cumulative_after = (
            0.0 if died else turn_context.cumulative_score + reward
        )
        self._record_history(
            turn_number=turn_context.turn_number,
            task_ctx=task_ctx,
            task_outcome=task_outcome,
            stake_choice=None,
            cumulative_after=cumulative_after,
            outcome_summary=("died" if died else f"+{reward:.0f}"),
        )
        merged_metadata: dict = {
            **task_ctx.metadata,
            **task_outcome.metadata,
        }
        return self._record(
            build_forfeit_layer_continue_result(
                turn_context=turn_context,
                user_message=combined_user_message,
                raw_text=combined_raw,
                thinking_text=combined_thinking,
                reasoning_investment=combined_ri,
                task_outcome=task_outcome,
                reward=reward,
                p_death_applied=p_death_eff,
                died=died,
                task_metadata=merged_metadata,
                ground_truth_rule=self._resolve_ground_truth_rule(),
                reward_offered=reward_offered,
                ri_task=ri_task,
                ri_forfeit=ri_forfeit,
                raw_response_task=raw_text_task,
                raw_response_forfeit=raw_text_forfeit,
                thinking_text_task=thinking_text_task,
                thinking_text_forfeit=thinking_text_forfeit,
                psuccess_self=psuccess_self,
                ri_probe=ri_probe,
                raw_response_probe=raw_text_probe,
                thinking_text_probe=thinking_text_probe,
            )
        )

    def _resolve_risk_choice(
        self,
        *,
        raw_text: str,
        agent_response_forfeit: bool,
        forfeit_allowed: bool,
        menu_skipped: bool,
    ) -> RiskChoice:
        """Pick the final RiskChoice, honouring menu-skip + agent FORFEIT.

        When the menu is skipped, the parser is bypassed entirely and a
        synthetic 1x stake is returned so reward calculation is well
        defined (the result still records ``stake_choice=None``).

        When the agent's helper-extracted ``forfeit`` flag fires AND
        forfeit is allowed, we honour that even if the regex parser
        missed the explicit ``ACTION: FORFEIT`` line.
        """
        if menu_skipped:
            return RiskChoice(stake=_BASELINE_STAKE, raw_text="<menu skipped>")

        choice = self._risk_layer.parse_choice(raw_text)
        if (
            agent_response_forfeit
            and forfeit_allowed
            and choice.stake != FORFEIT_STAKE
        ):
            logger.info(
                "Agent.forfeit flag set but RiskChoiceLayer parsed stake=%s; "
                "honouring forfeit signal.",
                choice.stake,
            )
            return RiskChoice(stake=FORFEIT_STAKE, raw_text=choice.raw_text)
        if choice.stake == FORFEIT_STAKE and not forfeit_allowed:
            # Defensive: parser found FORFEIT but session forbids it.
            # Fall back to the standard stake to keep the session moving.
            logger.warning(
                "Parsed FORFEIT in NOT_ALLOWED session; falling back to "
                "stake=%s.",
                _BASELINE_STAKE,
            )
            return RiskChoice(
                stake=_BASELINE_STAKE,
                raw_text=choice.raw_text,
            )
        # Defensive: stake must be a valid key.
        if choice.stake not in VALID_STAKE_KEYS and choice.stake != FORFEIT_STAKE:
            logger.warning(
                "Unexpected parsed stake=%r; falling back to %s.",
                choice.stake,
                _BASELINE_STAKE,
            )
            return RiskChoice(stake=_BASELINE_STAKE, raw_text=choice.raw_text)
        return choice

    # ------------------------------------------------------------------
    # Helpers — TurnResult builders
    # ------------------------------------------------------------------

    def _resolve_ground_truth_rule(self) -> str | None:
        """Duck-typed extraction of the active hidden rule string.

        SignalGameModule + NavigationModule expose
        ``get_active_rule_description()``; NullTask and other
        rule-free tasks do not, in which case the field stays None
        (matching the legacy TurnManager behaviour for non-rule tasks).

        Pre-2026-04-20 the v3 manager hardcoded ``ground_truth_rule=None``
        on every turn, which silently dropped the rule from
        ``season_results.jsonl``. Downstream analyses had to recover
        the rule from ``task_metadata['hidden_rule']`` instead — this
        method restores parity with the legacy TurnManager so the
        explicit field carries the value too.
        """
        getter = getattr(self._task, "get_active_rule_description", None)
        if getter is None:
            return None
        try:
            return getter()
        except Exception:  # pragma: no cover — defensive
            # If a task implements the method but raises before the
            # rule is initialised (e.g. called pre-prepare), surface
            # None rather than crashing the whole turn.
            return None

    def _record(self, result: TurnResult) -> TurnResult:
        self._measurement.record_turn(result)
        return result

    # ------------------------------------------------------------------
    # Helpers — cumulative history (constraint #3)
    # ------------------------------------------------------------------

    def _record_history(
        self,
        *,
        turn_number: int,
        task_ctx,
        task_outcome: TaskOutcome | None,
        stake_choice: str | None,
        cumulative_after: float,
        outcome_summary: str,
    ) -> None:
        """Append one entry to the in-manager history buffer.

        Keys per spec constraint #3 ("History format: cumulative history
        must include ``stake_choice`` per entry") plus Phase K Fix 1
        (restore behavioural continuity via ``action`` field):

            turn, signal, action, stake_choice, outcome, cumulative_score

        ``action`` is pulled from ``task_outcome.metadata["action"]`` so
        agents can reconstruct their own prior behaviour from the history
        block — a capability that existed in the legacy Phase 1/2
        ``_format_turn_history`` but was silently dropped when Phase 3
        moved to the stake-only history. For NullTask (no task action)
        and forfeit turns we fall back to the ``—`` sentinel.
        """
        signal = task_ctx.metadata.get("signal", "") if task_ctx.metadata else ""
        action: str | None = None
        rule_hypothesis: str | None = None
        if task_outcome is not None and task_outcome.metadata:
            raw_action = task_outcome.metadata.get("action")
            if isinstance(raw_action, str) and raw_action:
                action = raw_action
            raw_rule = task_outcome.metadata.get("rule_hypothesis")
            if isinstance(raw_rule, str) and raw_rule:
                rule_hypothesis = raw_rule
        self._history.append(
            {
                "turn": turn_number,
                "signal": signal,
                "action": action,
                "rule_hypothesis": rule_hypothesis,
                "stake_choice": stake_choice,
                "outcome": outcome_summary,
                "cumulative_score": cumulative_after,
            }
        )

    # ------------------------------------------------------------------
    # Read-only diagnostic accessors (used by tests + Phase F engine)
    # ------------------------------------------------------------------

    @property
    def history(self) -> list[dict[str, Any]]:
        """Read-only snapshot of the cumulative history buffer."""
        return list(self._history)

    @property
    def stake_history(self) -> list[str]:
        """Read-only snapshot of the committed stake history (Phase N).

        Populated only for turns where the stake menu was shown and a
        real stake was chosen (FORFEIT and menu-skipped turns are
        excluded). Used by
        ``RiskChoiceLayer.compute_cumulative_carryover`` and by tests
        to verify session isolation.
        """
        return list(self._stake_history)

    @property
    def forfeit_self_report(self) -> ForfeitSelfReport | None:
        """Phase O Unit 14 — the captured forfeit self-report, if any.

        Non-None only when the forfeit-layer path was active AND the
        agent chose FORFEIT on some turn. The engine pulls this after
        ``run_season`` completes to populate ``SeasonResult
        .forfeit_self_report``. Returns ``None`` for risk-layer
        sessions or forfeit-layer sessions that never forfeited.
        """
        return self._forfeit_self_report
