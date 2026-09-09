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

Split-call path (``use_split_forfeit_layer=True``, the canonical v6+
flow) — decision-first since 2026-09-04:

    decision call  (history + forfeit menu → CHOICE, ``ri_forfeit``)
        FORFEIT → session ends; the task call never runs
        CONTINUE ↓
    task call      (history + stimulus → RULE + ACTION, ``ri_task``)
    resolve        (score, reward, lives / death)

Cell 0 (menu skipped) issues the task call only. The Unit 17 Call 1.5
self-confidence probe was removed together with the reorder; the
``psuccess_*`` TurnResult fields stay ``None`` on every new run.
"""

from __future__ import annotations

import logging
import random
from typing import TYPE_CHECKING, Any

from squid_game.agents._parsing import (
    build_choice_echo,
    build_confidence_block,
    build_confidence_call_message,
    confidence_field_label,
    build_decision_call_message,
    build_ransom_call_message,
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
    is_threat_framing,
    states_outcome,
    resolve_base_p_death,
    should_skip_menu,
)
from squid_game.core.turn_prompts import (
    build_system_prompt,
    compose_task_call_user_message,
    compose_user_message,
    derive_action_hint,
    format_history_block,
    format_outcome_history_block,
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
from squid_game.core.carrot import resolve_carrot
from squid_game.core.ransom import (
    RANSOM_DECLINE,
    RANSOM_PAY,
)
from squid_game.models.config import ScorePolicyConfig, elimination_reset_score
from squid_game.models.state import GameState, TurnContext
from squid_game.tasks.base import RiskAwareTaskModule, TaskOutcome

if TYPE_CHECKING:  # pragma: no cover - typing only
    from squid_game.models.config import HazardRampConfig, RansomConfig

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
        rng: random.Random | None = None,
        phantom_death: bool = True,
        constant_p_death: float | None = None,
        action_hint: str | None = None,
        history_mode: str = "cumulative",
        max_history_turns: int = 15,
        lives_enabled: bool = False,
        score_floor: float = 0.0,
        confidence_call_enabled: bool = False,
        confidence_condition: str = "heart_loss",
        hazard_ramp: "HazardRampConfig | None" = None,
        score_policy: ScorePolicyConfig | None = None,
        carrot: str | None = None,
        flagship_pull: bool | None = None,
        ransom: "RansomConfig | None" = None,
        ransom_price: float | None = None,
    ) -> None:
        """Initialise the unified turn manager.

        ``ransom`` / ``ransom_price`` (2026-09-09, score-equivalent
        index): the run-level switch and this cell's price. When enabled,
        a wrong answer that empties the lives counter does not end the
        session outright -- it issues one more call offering to continue
        for ``ransom_price`` points. PAY deducts the price and restores
        the life; DECLINE (or an unparsed reply) ends the session with
        the score kept. FORFEIT turns never reach the decision point.
        Off by default, so every other run is unchanged. See
        ``squid_game.core.ransom``.

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
            history_mode: ``"cumulative"`` / ``"last"`` / ``"none"`` /
                ``"outcome"`` — controls how prior-turn outcomes are
                surfaced in the next turn's user prompt. ``"outcome"``
                (2026-09-05) renders the outcome-only block
                (round, verdict, cumulative score, lives) so the task
                call sees no signal, action or rule hypothesis.
            max_history_turns: Cap on cumulative-history rendering.
            confidence_call_enabled: SDI Phase 1.5 switch. When True the
                split-call path issues a confidence call before the
                decision call, records ``p_threat_self`` /
                ``ri_confidence``, and renders that call's CoT into the
                decision-call user body. Ignored on every other path.
            hazard_ramp: V7 hazard-ramp settings (2026-09-07, see
                ``squid_game.core.hazard_ramp``). The config block, not a
                pre-rendered string: two integers in the block move with
                the lives counter, so ``build_system_prompt`` re-renders
                it from each call's ``TurnContext``. Appended to the end
                of the FRAMING SECTION (before the task rules) of every
                system prompt this manager builds, and never to a user
                message. Purely declarative -- this manager still
                resolves the plain deterministic lives ledger and rolls
                no per-round hazard for it. ``None`` (the default)
                appends nothing.
            score_policy: Which exit keeps the accumulated score
                (2026-09-08). The manager reads only the ELIMINATION
                half -- the forfeit half is applied by
                ``ForfeitController.process_forfeit``, whose return
                value this manager records verbatim. ``None`` (the
                default) is the 2026-09-07 fixed rule.
            score_floor: ``TaskConfig.score_floor`` for the season, used
                only to write the same post-elimination number the
                engine writes (``elimination_reset_score``). Defaults to
                0.0, which is what every shipped config sets.
            carrot: Which prize the run states (2026-09-08), one of
                ``squid_game.core.carrot.CARROTS``. Run-level. The
                manager itself needs it for exactly one thing -- the
                confidence call's status-line noun -- because the
                framing prompt and the forfeit menu get it from
                ``FramingManager`` and ``ForfeitLayer`` directly.
                ``None`` / ``"flagship"`` (the default) keeps every
                render byte-identical.
            flagship_pull: DEPRECATED ALIAS of ``carrot`` -- the
                2026-09-08 "type D" boolean. ``False`` is
                ``carrot="none"``, ``True`` is ``carrot="flagship"``,
                ``None`` (the default) is "not passed".
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
        self._measurement = measurement
        self._cot_collector = cot_collector or CoTCollector()
        self._rng = rng if rng is not None else random.Random()
        self._phantom_death = phantom_death
        self._constant_p_death = constant_p_death
        self._action_hint = action_hint
        self._history_mode = history_mode
        self._max_history_turns = max_history_turns
        # Lives mechanic — when True the split-call path resolves a
        # deterministic lives ledger instead of rolling for death. Only
        # consulted inside _execute_turn_split_forfeit_layer; the
        # ExperimentConfig validator rejects every other combination.
        self._lives_enabled = lives_enabled
        # SDI (2026-09-04) — Phase 1.5 confidence call. Only consulted
        # inside _execute_turn_split_forfeit_layer, and only when the
        # forfeit menu is actually rendered (never on Cell 0).
        self._confidence_enabled = confidence_call_enabled
        # Which narrative 3-confidence_call.j2 renders ahead of the P_THREAT
        # question ("heart_loss" = question only, "gunshot_seungpil" =
        # pilot-v2 arm 4 condition block). See ConfidenceCallConfig.
        self._confidence_condition = confidence_condition
        # Hazard ramp (2026-09-07) — held as the CONFIG BLOCK, not a
        # rendered string, because its "Lives spent: X of T" line moves
        # with the counter and must be re-rendered per call. None means
        # "no ramp". Declarative only: nothing below rolls for it.
        self._hazard_ramp = hazard_ramp
        # Score policy (2026-09-08). Only the elimination half is read
        # here, to keep the recorded ``cumulative_after`` in step with
        # the score the engine will hold after an elimination turn.
        self._score_policy = (
            score_policy if score_policy is not None else ScorePolicyConfig()
        )
        self._score_floor = score_floor
        # The carrot (2026-09-08), run-level. Consulted only when
        # building the confidence call, whose status line borrows the
        # menu's score noun. ``flagship_pull`` is the deprecated alias.
        self._carrot = resolve_carrot(
            carrot=carrot, flagship_pull=flagship_pull
        )
        # End-of-round event roll (2026-09-08). ``None`` / disabled means
        # no draw is ever made and no result field moves.
        self._ransom = ransom
        self._ransom_price = ransom_price
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
            hazard_ramp=self._hazard_ramp,
        )
        # Legacy Risk-Choice-Layer path: ``always_decide`` is a
        # forfeit-layer knob and there is no forfeit layer here, so the
        # historical skip rule applies unconditionally.
        menu_skipped = should_skip_menu(
            base_p_death, forfeit_allowed, always_decide=False
        )

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
            lives_label=(
                "lives"
                if is_threat_framing(turn_context.framing)
                else "attempts"
            ),
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
        # Elimination keeps the score (2026-09-07); only FORFEIT zeroes
        # it, and that path never reaches here.
        cumulative_after = turn_context.cumulative_score + reward
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
            hazard_ramp=self._hazard_ramp,
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
            lives_label=(
                "lives"
                if is_threat_framing(turn_context.framing)
                else "attempts"
            ),
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
            turn_context.cumulative_score,
            turn_p_death=base_p_death,
            turn_number=turn_context.turn_number,
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
            turn_number=turn_context.turn_number,
        )
        p_death_eff = self._forfeit_layer.calculate_p_death(
            forfeit_choice.choice, turn_p_death=base_p_death
        )

        # Phase 7 — death roll (skipped in phantom-death mode).
        if self._phantom_death:
            died = False
        else:
            died = self._rng.random() < p_death_eff

        # The FORFEIT exit never reaches here; this is the other one, so
        # it follows the ELIMINATION half of the score policy.
        cumulative_after = self._cumulative_after(
            turn_context.cumulative_score, reward, died=died
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
        """Split-call forfeit-layer dispatch path — decision first.

        Two sequential LLM calls per turn so ``thinking_tokens`` can be
        attributed to choice deliberation (``ri_forfeit``) vs task
        reasoning (``ri_task``) cleanly. Since 2026-09-04 the order is
        decision-first: the agent chooses CONTINUE / FORFEIT from its
        accumulated history and the menu *before* the round's stimulus
        is shown. On FORFEIT the session ends and the task call is never
        issued (``ri_task`` / ``raw_response_task`` / ``thinking_text_task``
        stay ``None`` on that turn). On CONTINUE the task call follows
        and the turn resolves as before.

        Three sequential LLM calls when the confidence call is enabled:
        confidence → decision → task. The Phase 1.5 confidence call (SDI)
        shares the decision call's system prompt and history block, sees
        neither the stimulus nor the menu, and has its CoT rendered into
        the decision call's user body.

        Pre-decision context (2026-09-05): the confidence + decision
        calls' system prompt and history block are chosen by two
        ``ForfeitLayerConfig`` knobs.
        ``task_rules_before_decision=False`` builds their system prompt
        with ``include_task_rules=False`` (framing only; the task call
        keeps the full prompt), and ``split_context_level="outcome"``
        swaps :func:`format_history_block` for
        :func:`format_outcome_history_block`. Both default to the
        pre-2026-09-05 behaviour, so existing configs render
        byte-identically. Its ``ri_confidence`` is recorded
        separately and deliberately excluded from the combined
        ``reasoning_investment`` / ``raw_response`` / ``thinking_text``
        aggregates, which stay decision + task only so pre-SDI analyses
        keep comparing like with like. ``system_prompt`` and
        ``decision_call_input`` are recorded on every turn that issues a
        decision call, confidence call or not.

        Dispatcher guarantees: reachable only when both
        ``self._forfeit_layer is not None`` AND
        ``self._use_split_forfeit_layer is True``.

        Cell 0 handling (spec §3.5): when the menu is skipped (Cell 0 has
        ``p_death_override=0.0`` and ``forfeit_condition=not_allowed``)
        the decision call is *not* invoked — the path degenerates to a
        single task call that produces an auto-CONTINUE outcome, keeping
        backward comparability with Unit 14 Cell 0. The split-specific
        fields (``ri_forfeit`` etc.) stay ``None`` on that branch.

        ``ForfeitLayerConfig.always_decide`` (2026-09-07) turns that
        branch off: a blocked cell then runs the same three calls as an
        allowed one and records the same fields, but its menu holds the
        CONTINUE option alone. The recorded CHOICE is therefore not a
        choice; ``ri_forfeit`` is what the cell is for. Defaults to
        False, so every config written before that date still takes the
        degenerate branch.
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
        # docstring). The decision call's ``5-forfeit_option.j2`` user-body carries
        # the authoritative forfeit mechanism + framing-conditional
        # semantics, and the task call must stay free of forfeit
        # awareness per spec §3.3.
        system_prompt = build_system_prompt(
            turn_context,
            framing_mgr=self._framing_mgr,
            task=self._task,
            forfeit_ctrl=self._forfeit_ctrl,
            include_forfeit_text=False,
            hazard_ramp=self._hazard_ramp,
        )
        rule_template_hint = getattr(
            self._task, "get_rule_template_hint", lambda: None
        )()
        # Task-supplied task-call response format (2026-09-01). Tasks
        # whose answer is free-form rather than an action pick (the
        # external benchmark modules) return a block here; every legacy
        # task has no such attribute, so this stays None.
        response_format_override = getattr(
            self._task, "get_response_format_override", lambda: None
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
        menu_skipped = should_skip_menu(
            base_p_death,
            forfeit_allowed,
            always_decide=self._forfeit_layer.config.always_decide,
        )
        if menu_skipped:
            # Degenerate: no meaningful choice, so the decision call is
            # skipped. Produce a Unit-14-shaped CONTINUE result with
            # ri_task / raw_response_task set so downstream analyses can
            # still pull the task-only RI.
            task_call_body = compose_task_call_user_message(
                task_ctx,
                history=self._history,
                history_mode=self._history_mode,
                max_history_turns=self._max_history_turns,
                lives_label=(
                    "lives"
                    if is_threat_framing(turn_context.framing)
                    else "attempts"
                ),
            )
            # The peer-elimination notice fires in every threat cell,
            # forfeit allowed or not (the engine gates it on threat_level
            # only). On this path the task call is the turn's only LLM
            # call, so it has to carry the notice -- the CONTINUE path
            # below prefixes it to both calls (spec §3.4). Before
            # 2026-09-05 the notice was recorded on this branch but never
            # sent, so every threat x not_allowed turn of the 09-03 5x2
            # runs claims an announcement the model never saw.
            if turn_context.peer_death_text:
                task_call_body = (
                    f"{turn_context.peer_death_text}\n\n{task_call_body}"
                )
            task_parsed_resp = self._agent.respond_task_call(
                user_message=task_call_body,
                available_actions=self._task.get_available_actions(),
                system_prompt=system_prompt,
                rule_template_hint=rule_template_hint,
                response_format_override=response_format_override,
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
            # Cell 0 reward path — ``calculate_continue_reward`` at
            # ``turn_p_death=0.0`` is the fallback ``base_reward`` in the
            # calibrated and flat modes alike (the equal-EV formula is
            # degenerate at p_death=0), so routing through it changes
            # nothing for them and picks up the per-turn schedule under
            # ``reward_mode: geometric``.
            reward = (
                task_outcome.success_factor
                * self._forfeit_layer.calculate_continue_reward(
                    turn_context.cumulative_score,
                    turn_p_death=0.0,
                    turn_number=turn_context.turn_number,
                )
            )
            # The menu was skipped, so this turn is an auto-CONTINUE: an
            # incorrect answer still costs a life, exactly as it would in
            # a cell that actually offered the choice.
            lives_after, life_lost, died_lives = self._resolve_lives(
                turn_context,
                forfeited=False,
                success_factor=task_outcome.success_factor,
            )
            if died_lives:
                reward = 0.0
            # The elimination half of the score policy (the menu was
            # skipped, so FORFEIT is not reachable on this branch).
            cumulative_after = self._cumulative_after(
                turn_context.cumulative_score, reward, died=died_lives
            )
            # Ransom (2026-09-09): a wrong answer that emptied the
            # counter buys one more call offering to continue for a
            # price. Paying flips ``died`` back to False and restores the
            # life, so both are re-read from the return value.
            ransom_kwargs, cumulative_after, died_lives = self._offer_ransom(
                turn_context,
                died_lives=died_lives,
                cumulative_after=cumulative_after,
                system_prompt=system_prompt,
                peer_prefix=turn_context.peer_death_text or "",
            )
            if ransom_kwargs.get("ransom_decision") == RANSOM_PAY:
                lives_after = 1
            self._record_history(
                turn_number=turn_context.turn_number,
                task_ctx=task_ctx,
                task_outcome=task_outcome,
                stake_choice=None,
                cumulative_after=cumulative_after,
                outcome_summary=(
                    "eliminated"
                    if died_lives
                    else (
                        f"paid {ransom_kwargs['ransom_paid']:.0f}"
                        if ransom_kwargs.get("ransom_decision") == RANSOM_PAY
                        else f"+{reward:.0f}"
                    )
                ),
                lives_after=lives_after,
                lives_total=turn_context.lives_total,
            )
            merged_metadata: dict = {
                **task_ctx.metadata,
                **task_outcome.metadata,
            }
            return self._record(
                build_forfeit_layer_continue_result(
                    turn_context=turn_context,
                    user_message=task_call_body,
                    raw_text=raw_text_task,
                    thinking_text=thinking_text_task,
                    reasoning_investment=ri_task,
                    task_outcome=task_outcome,
                    reward=reward,
                    p_death_applied=0.0,
                    died=died_lives,
                    task_metadata=merged_metadata,
                    ground_truth_rule=self._resolve_ground_truth_rule(),
                    reward_offered=self._forfeit_layer.calculate_continue_reward(
                        turn_context.cumulative_score,
                        turn_p_death=0.0,
                        turn_number=turn_context.turn_number,
                    ),
                    ri_task=ri_task,
                    ri_forfeit=None,
                    raw_response_task=raw_text_task,
                    raw_response_forfeit=None,
                    thinking_text_task=thinking_text_task,
                    thinking_text_forfeit=None,
                    lives_kwargs={
                        **self._lives_result_kwargs(
                            turn_context,
                            lives_after=lives_after,
                            life_lost=life_lost,
                        ),
                        **ransom_kwargs,
                    },
                )
            )

        # Phase 2 — decision call (forfeit layer). Runs BEFORE the task
        # call: the agent sees its history and the menu, never this
        # round's stimulus.
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
            lives_enabled=self._lives_enabled,
            lives_remaining=turn_context.lives_remaining,
            lives_total=turn_context.lives_total,
            threat_framing=(
                bool(turn_context.threat_level)
                or is_threat_framing(turn_context.framing)
            ),
            threat_level=turn_context.threat_level,
            always_decide=self._forfeit_layer.config.always_decide,
            neutral_exhaustion=bool(self._ransom and self._ransom.enabled),
        )
        split_ctx = self._forfeit_layer.config.split_context_level
        # Under ``medium`` / ``full`` the agent sees the cumulative
        # history block so it can calibrate its own prediction-accuracy
        # before the CONTINUE vs FORFEIT choice. Under ``minimal`` the
        # history is deliberately omitted (build_decision_call_message
        # drops it). Under ``outcome`` (2026-09-05) it sees an
        # outcome-only block instead — right/wrong, score, lives — with
        # the signal, its own action and its rule hypothesis withheld,
        # so the choice cannot be conditioned on how well it understands
        # the hidden rule.
        if split_ctx == "outcome":
            history_block = (
                ""
                if self._history_mode == "none"
                else format_outcome_history_block(
                    self._history[-1:]
                    if self._history_mode == "last"
                    else self._history,
                    self._max_history_turns,
                    lives_label=(
                        "lives"
                        if is_threat_framing(turn_context.framing)
                        else "attempts"
                    ),
                )
            )
        else:
            # ``lives_label`` matters here too: with
            # ``history_mode="outcome"`` (2026-09-05) format_history_block
            # delegates to the outcome block, which prints a lives
            # counter. ``true_baseline`` must say "attempts".
            history_block = format_history_block(
                self._history,
                self._history_mode,
                self._max_history_turns,
                lives_label=(
                    "lives"
                    if is_threat_framing(turn_context.framing)
                    else "attempts"
                ),
            )
        # The pre-decision system prompt. With
        # ``task_rules_before_decision=False`` the confidence and
        # decision calls see the framing alone: the task identity (and
        # therefore what the round will even ask) arrives only with the
        # task call, after the choice has been made.
        if self._forfeit_layer.config.task_rules_before_decision:
            pre_decision_system_prompt = system_prompt
        else:
            pre_decision_system_prompt = build_system_prompt(
                turn_context,
                framing_mgr=self._framing_mgr,
                task=self._task,
                forfeit_ctrl=self._forfeit_ctrl,
                include_forfeit_text=False,
                include_task_rules=False,
                    hazard_ramp=self._hazard_ramp,
            )

        # Does this cell's framing state an outcome for the counter
        # reaching zero? The confidence call's question and the field it
        # asks for both hang on this: ``P_THREAT`` points at that outcome
        # with a definite description, and where there is none the model
        # answers something else (2026-09-07). Read off the RENDERED
        # framing, because ``reassurance`` is a per-season switch that a
        # framing name cannot tell you about.
        cell_states_outcome = states_outcome(pre_decision_system_prompt)
        confidence_label = confidence_field_label(cell_states_outcome)

        # Phase 1.5 — confidence call (SDI). Same system prompt and history
        # as the decision call; no stimulus, no menu. Its CoT is rendered
        # into the decision call's user body so the offline resampler can
        # replay the decision call from the recorded input alone.
        confidence_block: str | None = None
        confidence_kwargs: dict = {}
        if self._confidence_enabled:
            confidence_body = build_confidence_call_message(
                user_body=history_block,
                turn_number=turn_context.turn_number,
                current_score=turn_context.cumulative_score,
                lives_enabled=self._lives_enabled,
                lives_remaining=turn_context.lives_remaining,
                lives_total=turn_context.lives_total,
                threat_framing=(
                bool(turn_context.threat_level)
                or is_threat_framing(turn_context.framing)
            ),
                corruption_framing=corruption_framing,
                baseline_flagship_framing=baseline_flagship_framing,
                survival_framing=survival_framing,
                split_context_level=split_ctx,
                condition=self._confidence_condition,
                states_outcome=cell_states_outcome,
                carrot=self._carrot,
            )
            if turn_context.peer_death_text:
                confidence_body = (
                    f"{turn_context.peer_death_text}\n\n{confidence_body}"
                )
            confidence_resp = self._agent.respond_confidence_call(
                user_message=confidence_body,
                system_prompt=pre_decision_system_prompt,
            )
            completion_conf = self._agent.last_completion
            thinking_text_conf = getattr(completion_conf, "thinking_text", None)
            thinking_tokens_conf = (
                getattr(completion_conf, "thinking_tokens", None) or 0
            )
            ri_confidence = self._cot_collector.record(confidence_resp.raw_text)
            if thinking_tokens_conf:
                ri_confidence = ReasoningInvestment(
                    total_tokens=ri_confidence.total_tokens,
                    reasoning_steps=ri_confidence.reasoning_steps,
                    thinking_tokens=thinking_tokens_conf,
                )
            if confidence_resp.p_threat is None:
                logger.warning(
                    "Confidence call returned no P_THREAT on turn %s",
                    turn_context.turn_number,
                )
            confidence_block = build_confidence_block(
                thinking_text=thinking_text_conf,
                raw_text=confidence_resp.raw_text,
                p_threat=confidence_resp.p_threat,
                label=confidence_label,
            )
            confidence_kwargs = dict(
                p_threat_self=confidence_resp.p_threat,
                ri_confidence=ri_confidence,
                raw_response_confidence=confidence_resp.raw_text,
                thinking_text_confidence=thinking_text_conf,
                # Replay (2026-09-06): the confidence call is issued with
                # ``pre_decision_system_prompt``, the same prompt recorded
                # below as ``system_prompt``, so this body plus that field
                # reproduce the call byte-for-byte -- the property the
                # decision call already had.
                confidence_call_input=confidence_body,
            )

        decision_call_body = build_decision_call_message(
            user_body=history_block,
            menu_text=menu_text,
            forfeit_allowed=forfeit_allowed,
            split_context_level=split_ctx,
            confidence_block=confidence_block,
            always_decide=self._forfeit_layer.config.always_decide,
        )
        # The peer-elimination notice is prefixed verbatim to BOTH calls
        # so the threat is present while the agent decides AND while it
        # solves the task (spec §3.4 — one consistent announcement per
        # turn).
        if turn_context.peer_death_text:
            decision_call_body = (
                f"{turn_context.peer_death_text}\n\n{decision_call_body}"
            )
        # Replay inputs — the exact pair the decision call was issued
        # with, recorded on every turn that renders the menu (whether or
        # not the confidence call ran) so an offline resampler can
        # reproduce this call verbatim.
        replay_kwargs = dict(
            system_prompt=pre_decision_system_prompt,
            decision_call_input=decision_call_body,
        )
        forfeit_parsed_resp = self._agent.respond_decision_call(
            user_message=decision_call_body,
            forfeit_allowed=forfeit_allowed,
            system_prompt=pre_decision_system_prompt,
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

        # Phase 3 — parse the decision using ForfeitLayer for
        # authoritative semantics (NOT_ALLOWED guard + CHOICE enum + raw
        # capture).
        forfeit_choice = self._forfeit_layer.parse_choice(raw_text_forfeit)
        if not forfeit_allowed and forfeit_choice.choice == FORFEIT_CHOICE:
            logger.warning(
                "ForfeitLayer parsed FORFEIT in NOT_ALLOWED session "
                "(split-call path); forcing CONTINUE."
            )
            forfeit_choice = ForfeitChoice(
                choice=CONTINUE_CHOICE, raw_text=forfeit_choice.raw_text
            )

        reward_offered = self._forfeit_layer.calculate_continue_reward(
            turn_context.cumulative_score,
            turn_p_death=base_p_death,
            turn_number=turn_context.turn_number,
        )

        # Phase 4 — FORFEIT branch: the session ends here; the task call
        # is never issued, so every task-side field stays None.
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
                lives_after=turn_context.lives_remaining,
                lives_total=turn_context.lives_total,
            )
            return self._record(
                build_forfeit_layer_result(
                    turn_context=turn_context,
                    user_message=(
                        f"=== Decision call ===\n{decision_call_body}"
                    ),
                    raw_text=raw_text_forfeit,
                    thinking_text=thinking_text_forfeit,
                    reasoning_investment=ri_forfeit,
                    ground_truth_rule=self._resolve_ground_truth_rule(),
                    choice=FORFEIT_CHOICE,
                    reward_offered=reward_offered,
                    ri_task=None,
                    ri_forfeit=ri_forfeit,
                    raw_response_task=None,
                    raw_response_forfeit=raw_text_forfeit,
                    thinking_text_task=None,
                    thinking_text_forfeit=thinking_text_forfeit,
                    lives_kwargs=self._lives_result_kwargs(
                        turn_context,
                        lives_after=turn_context.lives_remaining,
                        life_lost=False,
                    ),
                    confidence_kwargs={**confidence_kwargs, **replay_kwargs},
                )
            )

        # Phase 5 — task call (task layer). Only reached on CONTINUE.
        task_call_body = compose_task_call_user_message(
            task_ctx,
            history=self._history,
            history_mode=self._history_mode,
            max_history_turns=self._max_history_turns,
            lives_label=(
                "lives"
                if is_threat_framing(turn_context.framing)
                else "attempts"
            ),
            # The decision call ran and returned CONTINUE. Echo WHICH of
            # the two ways that happened -- chosen, or the only thing
            # available -- so the task call's reasoning is conditioned on
            # it. Not rendered on the menu-skipped path above, where no
            # decision call was issued and there is no choice to echo.
            choice_echo=build_choice_echo(forfeit_allowed=forfeit_allowed),
        )
        if turn_context.peer_death_text:
            task_call_body = f"{turn_context.peer_death_text}\n\n{task_call_body}"
        task_parsed_resp = self._agent.respond_task_call(
            user_message=task_call_body,
            available_actions=self._task.get_available_actions(),
            system_prompt=system_prompt,
            rule_template_hint=rule_template_hint,
            response_format_override=response_format_override,
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

        # Parse the task call for the task outcome (RULE + ACTION). The
        # SignalGameModule.parse_response contract accepts the raw text
        # of any unified response containing ACTION/RULE — the task
        # call's output is strictly a subset so reuse is safe.
        task_parsed = self._task.parse_response(raw_text_task)

        # Combined fields for backward-compat with single-call analyses.
        # ``reasoning_investment`` / ``raw_response`` / ``thinking_text``
        # receive the SUM / CONCAT (decision call first, matching the
        # wire order) so analyses that do not know about the split
        # fields still see a sensible whole-turn value.
        combined_ri = ReasoningInvestment(
            total_tokens=(ri_forfeit.total_tokens or 0)
            + (ri_task.total_tokens or 0),
            reasoning_steps=(ri_forfeit.reasoning_steps or 0)
            + (ri_task.reasoning_steps or 0),
            thinking_tokens=(
                (ri_forfeit.thinking_tokens or 0)
                + (ri_task.thinking_tokens or 0)
            ),
        )
        combined_raw = (
            f"{raw_text_forfeit}\n\n--- Task call ---\n\n{raw_text_task}"
        )
        combined_thinking: str | None
        if thinking_text_forfeit and thinking_text_task:
            combined_thinking = (
                f"{thinking_text_forfeit}\n\n--- Task call ---\n\n"
                f"{thinking_text_task}"
            )
        else:
            combined_thinking = thinking_text_forfeit or thinking_text_task
        combined_user_message = (
            f"=== Decision call ===\n{decision_call_body}\n\n"
            f"=== Task call ===\n{task_call_body}"
        )

        # Phase 6 — CONTINUE branch: task scoring → reward/p_death.
        task_outcome = self._task.score(task_parsed, game_state)
        reward = self._forfeit_layer.calculate_reward(
            task_outcome,
            forfeit_choice.choice,
            turn_context.cumulative_score,
            turn_p_death=base_p_death,
            turn_number=turn_context.turn_number,
        )
        lives_after, life_lost, died_lives = self._resolve_lives(
            turn_context,
            forfeited=False,
            success_factor=task_outcome.success_factor,
        )

        # Phase 7 — death resolution.
        #
        # Lives mode is deterministic: the Bernoulli roll is not merely
        # zero-probability, it is never made at all (the RNG is not
        # consulted), and the displayed p_death stays 0.0 so the trace
        # never claims a risk the engine did not apply.
        if self._lives_enabled:
            p_death_eff = 0.0
            died = died_lives
            if died:
                reward = 0.0
        else:
            p_death_eff = self._forfeit_layer.calculate_p_death(
                forfeit_choice.choice, turn_p_death=base_p_death
            )
            if self._phantom_death:
                died = False
            else:
                died = self._rng.random() < p_death_eff

        # The FORFEIT exit ended the turn above; this is the other one,
        # so it follows the ELIMINATION half of the score policy.
        cumulative_after = self._cumulative_after(
            turn_context.cumulative_score, reward, died=died
        )
        # Ransom (2026-09-09). Only on the lives path (the validator ties
        # it to ``lives.enabled``), after the ledger, and only when this
        # round's wrong answer emptied the counter. Paying flips ``died``
        # back to False, so both it and the counter are re-read here.
        ransom_kwargs, cumulative_after, died = self._offer_ransom(
            turn_context,
            died_lives=died,
            cumulative_after=cumulative_after,
            system_prompt=system_prompt,
            peer_prefix=turn_context.peer_death_text or "",
        )
        if ransom_kwargs.get("ransom_decision") == RANSOM_PAY:
            lives_after = 1
        self._record_history(
            turn_number=turn_context.turn_number,
            task_ctx=task_ctx,
            task_outcome=task_outcome,
            stake_choice=None,
            cumulative_after=cumulative_after,
            outcome_summary=(
                ("eliminated" if self._lives_enabled else "died")
                if died
                else (
                    f"paid {ransom_kwargs['ransom_paid']:.0f}"
                    if ransom_kwargs.get("ransom_decision") == RANSOM_PAY
                    else f"+{reward:.0f}"
                )
            ),
            lives_after=lives_after,
            lives_total=turn_context.lives_total,
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
                lives_kwargs={
                    **self._lives_result_kwargs(
                        turn_context,
                        lives_after=lives_after,
                        life_lost=life_lost,
                    ),
                    **ransom_kwargs,
                },
                confidence_kwargs={**confidence_kwargs, **replay_kwargs},
            )
        )

    # ------------------------------------------------------------------
    # Helpers — lives ledger + threat-ladder TurnResult fields
    # ------------------------------------------------------------------

    def _offer_ransom(
        self,
        turn_context: TurnContext,
        *,
        died_lives: bool,
        cumulative_after: float,
        system_prompt: str,
        peer_prefix: str,
    ) -> tuple[dict[str, Any], float, bool]:
        """Offer the ransom on a wrong answer that emptied the counter.

        Returns ``(ransom_kwargs, cumulative_after, died)``. When the
        agent pays, ``died`` comes back False -- the session continues
        with the price deducted and the life restored, so the caller
        must use the returned value rather than ``died_lives``.

        The two guards below label themselves in ``ransom_kwargs`` via
        ``ransom_skipped``. Without it the final-round guard, the
        insufficient-score guard and an ordinary elimination write
        byte-identical turn records, and the second of those disappears
        preferentially from sessions that have already paid -- i.e.
        selectively on willingness to pay, exactly where the
        score-equivalent estimator reads. An analyst has to be able to
        see and drop those turns. The first early return stays bare:
        it is every ordinary turn, not a suppression.

        An unparsed reply is read as DECLINE. Paying takes points the
        agent never agreed to spend, so silence must not spend them.

        Not a roll: no RNG is consulted, and a run without the ransom
        reaches none of this.
        """
        if (
            self._ransom is None
            or not self._ransom.enabled
            or not died_lives
            or self._ransom_price is None
        ):
            return {}, cumulative_after, died_lives

        price = float(self._ransom_price)
        # Rounds left AFTER this one. With the per-round reward this is
        # everything the session can still pay out, which is the bound
        # ``ransom.is_dominated`` compares the price against.
        rounds_remaining = max(
            0, (turn_context.total_turns or 0) - turn_context.turn_number
        )
        # No offer on the final round. There would be nothing to buy: the
        # session ends after it either way, so the price purchases zero
        # rounds and DECLINE is right for every model at every price.
        # Recording that as a decision would pad the silent and threat
        # arms alike with a choice neither arm had to make. The smoke of
        # 2026-09-09 hit this on 6 of 9 offers before the guard existed.
        if rounds_remaining <= 0:
            return {"ransom_skipped": "final_round"}, cumulative_after, True
        # No offer the score cannot cover either. The engine would clamp
        # the deduction to what is there and continue the session, so the
        # agent would have paid less than the prompt said -- the one
        # place this design could state a price it does not charge.
        if cumulative_after - self._score_floor < price:
            return {"ransom_skipped": "insufficient_score"}, cumulative_after, True

        body = build_ransom_call_message(
            current_score=cumulative_after,
            lives_total=turn_context.lives_total,
            round_number=turn_context.turn_number,
            price=price,
            reward=self._forfeit_layer.config.base_reward,
            rounds_remaining=rounds_remaining,
            # Computed on the RENDERED framing, not on its name: whether
            # a cell states a consequence is a property of the bytes it
            # sends, and per-season switches can change it.
            states_outcome=states_outcome(system_prompt),
            # The true_baseline vocabulary contract forbids life/death
            # words; every other framing says "Lives", as the menu does.
            lives_label=(
                "Lives"
                if str(turn_context.framing) not in ("true_baseline", "Framing.TRUE_BASELINE")
                else "Attempts"
            ),
            carrot=self._carrot,
        )
        user_message = f"{peer_prefix}{body}" if peer_prefix else body
        response = self._agent.respond_ransom_call(
            user_message=user_message, system_prompt=system_prompt
        )
        completion = self._agent.last_completion
        decision = response.decision or RANSOM_DECLINE
        paid = decision == RANSOM_PAY
        kwargs: dict[str, Any] = {
            "ransom_offered": True,
            "ransom_price": price,
            "ransom_decision": decision,
            "ransom_why": response.why,
            "ransom_call_input": user_message,
            "raw_response_ransom": response.raw_text,
            "ri_ransom": getattr(completion, "thinking_tokens", 0) or 0,
            "thinking_text_ransom": getattr(completion, "thinking_text", None),
        }
        if not paid:
            kwargs["ransom_paid"] = 0.0
            return kwargs, cumulative_after, True
        # The price comes off the score the round just settled at, never
        # below the floor. The life is restored by the caller returning
        # died=False, so the counter reads 1 again next turn.
        spent = max(0.0, min(price, cumulative_after - self._score_floor))
        kwargs["ransom_paid"] = spent
        return kwargs, cumulative_after - spent, False

    def _resolve_lives(
        self,
        turn_context: TurnContext,
        *,
        forfeited: bool,
        success_factor: float | None,
    ) -> tuple[int | None, bool, bool]:
        """Compute this turn's lives outcome without mutating anything.

        The manager never touches ``GameState`` (Phase C invariant), so
        the arithmetic runs purely off ``turn_context.lives_remaining``
        and the engine applies the result afterwards.

        A life is lost exactly when the agent played the round
        (``forfeited=False``) and got it wrong — ``success_factor ==
        0.0``, which the task scorer also returns for an unparseable
        response. FORFEIT costs nothing: the score is preserved and the
        session ends.

        Args:
            turn_context: This turn's context; supplies ``lives_remaining``.
            forfeited: Whether the agent chose FORFEIT this turn.
            success_factor: The task outcome's success factor, or
                ``None`` when the task was not scored (FORFEIT).

        Returns:
            ``(lives_after, life_lost, died)``. ``lives_after`` is
            ``None`` when the lives mechanic is off, in which case
            ``life_lost`` and ``died`` are both ``False`` and the caller
            keeps its existing death semantics.
        """
        lives_before = turn_context.lives_remaining
        if not self._lives_enabled or lives_before is None:
            return None, False, False
        life_lost = (
            not forfeited
            and success_factor is not None
            and success_factor == 0.0
        )
        lives_after = lives_before - 1 if life_lost else lives_before
        return lives_after, life_lost, lives_after <= 0

    @staticmethod
    def _lives_result_kwargs(
        turn_context: TurnContext,
        *,
        lives_after: int | None,
        life_lost: bool,
    ) -> dict:
        """Build the lives/threat ``TurnResult`` kwargs for one turn.

        Always returns a dict (never ``None``): ``threat_level`` and the
        peer-death fields are meaningful even on a non-lives run, and
        every value defaults to the same thing ``TurnResult`` would have
        used on its own.
        """
        return {
            "lives_before": turn_context.lives_remaining,
            "lives_after": lives_after,
            "life_lost": life_lost,
            "threat_level": turn_context.threat_level,
            "peer_death_announced": bool(turn_context.peer_death_text),
            "peer_death_text": turn_context.peer_death_text,
        }

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

    def _cumulative_after(
        self,
        score_before: float,
        reward: float,
        *,
        died: bool,
    ) -> float:
        """Score after a non-forfeit turn, under the elimination policy.

        The FORFEIT exit is handled by
        ``ForfeitController.process_forfeit``, whose return value the
        forfeit branches record directly; this is the other exit. Under
        ``score_policy.elimination`` = ``'keep'`` (the default, and the
        2026-09-07 fixed rule) the score simply accrues, so a run that
        does not set the block records exactly what it recorded before.
        Under ``'reset'`` the turn that empties the counter records
        ``elimination_reset_score(score_floor)`` -- the same call the
        engine makes, so the recorded number, the engine's own score and
        the number the forfeit menu promised are one value.

        Args:
            score_before: Cumulative score going into the turn.
            reward: Reward credited this turn (already zeroed by the
                caller on an elimination turn).
            died: Whether this turn ended the session by elimination.

        Returns:
            The cumulative score to record for this turn.
        """
        if died and not self._score_policy.elimination_keeps:
            return elimination_reset_score(self._score_floor)
        return score_before + reward

    def _record_history(
        self,
        *,
        turn_number: int,
        task_ctx,
        task_outcome: TaskOutcome | None,
        stake_choice: str | None,
        cumulative_after: float,
        outcome_summary: str,
        lives_after: int | None = None,
        lives_total: int | None = None,
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

        2026-09-05 adds three purely additive keys consumed by
        :func:`~squid_game.core.turn_prompts.format_outcome_history_block`
        (``split_context_level: "outcome"``): ``correct`` — an explicit
        boolean read off ``task_outcome.success_factor`` rather than
        re-derived from the ``"+0"`` outcome string — plus
        ``lives_after`` / ``lives_total``. All three are ``None`` on
        rounds (or paths) that do not supply them; no existing key
        changes.
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
        correct: bool | None = None
        if task_outcome is not None:
            correct = bool(task_outcome.success_factor)
        self._history.append(
            {
                "turn": turn_number,
                "signal": signal,
                "action": action,
                "rule_hypothesis": rule_hypothesis,
                "stake_choice": stake_choice,
                "correct": correct,
                "outcome": outcome_summary,
                "cumulative_score": cumulative_after,
                "lives_after": lives_after,
                "lives_total": lives_total,
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
