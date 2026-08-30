"""Top-level game engine for the LLM Squid Game benchmark.

Orchestrates a full season (rounds x turns) by composing all core
engine sub-components and driving the turn loop through TurnManager.
The engine owns the mutable GameState and applies state transitions
(score updates, death, forfeit) after each turn.
"""

from __future__ import annotations

import logging
import random
import uuid
from pathlib import Path

from squid_game.agents.base import Agent
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.risk_choice_layer import RiskChoiceLayer
from squid_game.core.social import CohortState
from squid_game.core.survival import SurvivalPressure
from squid_game.core.turn import TurnManager
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import (
    ForfeitLayerConfig,
    RiskLayerConfig,
    SeasonConfig,
)
from squid_game.models.enums import SocialContext
from squid_game.models.results import SeasonResult, TurnResult
from squid_game.models.state import GameState, TurnContext
from squid_game.providers.base import LLMProvider
from squid_game.tasks.base import RiskAwareTaskModule, TaskModule

logger = logging.getLogger(__name__)


class GameEngine:
    """Runs a complete game season (one factorial cell).

    A season consists of ``total_turns`` turns. The game ends early
    if the agent dies or forfeits.

    The engine never accesses the LLM provider directly --- all model
    interaction is mediated through the Agent interface.
    """

    def __init__(
        self,
        config: SeasonConfig,
        task: TaskModule,
        agent: Agent,
        provider: LLMProvider,
        output_dir: str | None = None,
        *,
        use_unified_turn: bool = False,
        risk_layer_config: RiskLayerConfig | None = None,
        use_forfeit_layer: bool = False,
        forfeit_layer_config: ForfeitLayerConfig | None = None,
        use_split_forfeit_layer: bool = False,
        use_psuccess_probe: bool = False,
    ) -> None:
        """Initialize the game engine.

        Args:
            config: Season configuration (framing, forfeit, task, provider).
            task: Initialized task module instance. When
                ``use_unified_turn=True`` this **must** also be a
                ``RiskAwareTaskModule``; pure-legacy modules are
                rejected at runtime to fail fast on misconfiguration.
            agent: Initialized agent instance.
            provider: LLM provider (kept for reference / future use;
                the agent is expected to already hold a provider reference).
            output_dir: Optional directory for JSONL output files.
            use_unified_turn: When True (Phase 3+), execute turns via
                ``UnifiedTurnManager`` (single LLM call, Risk Choice
                Layer, stake-aware reward). When False (default,
                backward-compatible), use the legacy two-call
                ``TurnManager``.
            risk_layer_config: Declarative ``RiskLayerConfig`` used to
                build the runtime Risk Choice Layer when
                ``use_unified_turn=True``. Defaults to the canonical
                Phase 3 config (1x/2x/3x stakes, +0/+5/+15%p risk
                deltas, base_reward=10.0). Ignored when
                ``use_unified_turn=False``.
            use_forfeit_layer: Phase O Unit 14 opt-in — when True
                (requires ``use_unified_turn=True``) the engine builds
                a ``ForfeitLayer`` and passes it to
                ``UnifiedTurnManager``, which then dispatches to the
                equal-EV binary-choice path (CHOICE + REASON). When
                False (default) the stake-menu path is preserved.
            forfeit_layer_config: ``ForfeitLayerConfig`` consumed when
                ``use_forfeit_layer=True``. Defaults to the canonical
                Unit 14 values (p_death=0.25, p_success_estimate=0.75,
                base_reward=10.0). Ignored when
                ``use_forfeit_layer=False``.
        """
        if use_unified_turn and not isinstance(task, RiskAwareTaskModule):
            raise TypeError(
                "use_unified_turn=True requires a RiskAwareTaskModule; "
                f"got {type(task).__name__} which only implements the "
                "legacy TaskModule interface. Migrate the module to "
                "dual-inherit RiskAwareTaskModule (see SignalGameModule "
                "in Phase E) or set use_unified_turn=False."
            )
        if use_forfeit_layer and not use_unified_turn:
            raise ValueError(
                "use_forfeit_layer=True requires use_unified_turn=True; "
                "the Forfeit-Layer ships inside the unified turn flow."
            )
        if use_split_forfeit_layer and not use_forfeit_layer:
            raise ValueError(
                "use_split_forfeit_layer=True requires "
                "use_forfeit_layer=True; the split-call path lives "
                "inside the Forfeit-Layer dispatcher."
            )
        if use_psuccess_probe and not use_split_forfeit_layer:
            raise ValueError(
                "use_psuccess_probe=True requires "
                "use_split_forfeit_layer=True; the Unit 17 probe only "
                "dispatches between Call 1 and Call 2 of the split-call "
                "forfeit-layer path."
            )
        self._config = config
        self._task = task
        self._agent = agent
        self._provider = provider
        self._output_dir = output_dir
        self._use_unified_turn = use_unified_turn
        self._risk_layer_config = (
            risk_layer_config if risk_layer_config is not None
            else RiskLayerConfig()
        )
        self._use_forfeit_layer = use_forfeit_layer
        self._forfeit_layer_config = (
            forfeit_layer_config if forfeit_layer_config is not None
            else (ForfeitLayerConfig() if use_forfeit_layer else None)
        )
        self._use_split_forfeit_layer = use_split_forfeit_layer
        self._use_psuccess_probe = use_psuccess_probe

    def run_season(self, seed_override: int | None = None) -> SeasonResult:
        """Execute a full season and return the aggregated result.

        Args:
            seed_override: If provided, use this seed instead of the
                config's task seed.  The runner derives unique seeds
                per repetition so each rep explores a different scenario.

        Returns:
            SeasonResult containing all turn traces and aggregate metrics.
        """
        season_id = uuid.uuid4().hex[:12]
        task_cfg = self._config.task_config

        # Use the override seed (per-repetition) when available,
        # falling back to the config seed for single-run usage.
        effective_seed = seed_override if seed_override is not None else task_cfg.seed

        # --- 1. Initialize task ---
        self._task.initialize(
            difficulty=task_cfg.difficulty,
            seed=effective_seed,
            num_few_shot=task_cfg.num_few_shot,
            curriculum_turns=task_cfg.curriculum_turns,
        )

        # --- 2. Create core components ---
        survival = SurvivalPressure()
        forfeit_ctrl = ForfeitController(self._config.forfeit_condition)
        framing_mgr = FramingManager(framing=self._config.framing)
        cot_collector = CoTCollector()

        jsonl_path: str | None = None
        if self._output_dir is not None:
            jsonl_path = str(
                Path(self._output_dir) / f"{season_id}_turns.jsonl"
            )

        measurement = MeasurementRecorder(output_path=jsonl_path)

        # --- 2b. Resolve effective base p_death for Phase 3 cells ---
        # SeasonConfig.p_death_override (v3, per-cell) wins over the
        # legacy TaskConfig.p_death_constant. Both fall back to None
        # which means "use the logistic schedule".
        effective_constant_p_death: float | None = (
            self._config.p_death_override
            if self._config.p_death_override is not None
            else task_cfg.p_death_constant
        )

        # --- 3. Initialize game state ---
        rng = random.Random(effective_seed)
        game_state = GameState(
            season_id=season_id,
            cumulative_score=task_cfg.starting_score,
        )

        # --- 2c. Construct the appropriate turn manager ---
        # Phase F invariant: only ONE manager is alive per session.
        # Mutually exclusive branches keep the legacy code path entirely
        # untouched when use_unified_turn=False.
        unified_mgr: UnifiedTurnManager | None = None
        legacy_mgr: TurnManager | None = None
        if self._use_unified_turn:
            risk_layer = RiskChoiceLayer(
                self._risk_layer_config.to_runtime()
            )
            forfeit_layer_obj: ForfeitLayer | None = None
            if self._use_forfeit_layer:
                # Phase O Unit 14 — construct the optional Forfeit-Layer.
                # The config was resolved to a non-None canonical instance
                # in __init__ when the flag was set, so the assert doubles
                # as documentation.
                assert self._forfeit_layer_config is not None
                forfeit_layer_obj = ForfeitLayer(self._forfeit_layer_config)
            assert isinstance(self._task, RiskAwareTaskModule)
            unified_mgr = UnifiedTurnManager(
                task=self._task,
                agent=self._agent,
                framing_mgr=framing_mgr,
                forfeit_ctrl=forfeit_ctrl,
                survival=survival,
                risk_layer=risk_layer,
                measurement=measurement,
                cot_collector=cot_collector,
                forfeit_layer=forfeit_layer_obj,
                use_split_forfeit_layer=self._use_split_forfeit_layer,
                use_psuccess_probe=self._use_psuccess_probe,
                rng=rng,  # share RNG so death rolls are seeded
                phantom_death=not task_cfg.actual_death,
                constant_p_death=effective_constant_p_death,
                history_mode=task_cfg.history_mode,
                max_history_turns=task_cfg.max_history_turns,
            )
        else:
            legacy_mgr = TurnManager(
                task=self._task,
                agent=self._agent,
                framing_mgr=framing_mgr,
                forfeit_ctrl=forfeit_ctrl,
                survival=survival,
                cot_collector=cot_collector,
                measurement=measurement,
                history_mode=task_cfg.history_mode,
                max_history_turns=task_cfg.max_history_turns,
            )

        # --- 3b. Cohort state (only used when social_context=WITH_OTHERS). ---
        # A dedicated RNG is derived from the same effective seed so the
        # cohort trajectory is reproducible alongside the agent's death
        # rolls but independent of them (paired-seed design preserved).
        cohort: CohortState | None = None
        cohort_rng: random.Random | None = None
        if self._config.social_context == SocialContext.WITH_OTHERS:
            cohort = CohortState(cohort_size=self._config.cohort_size)
            if effective_seed is not None:
                cohort_rng = random.Random(effective_seed ^ 0x9E3779B9)
            else:
                cohort_rng = random.Random()

        # --- 4. Flat turn loop ---
        total_turns = task_cfg.total_turns
        forfeited_at_turn: int | None = None
        penultimate_score: float | None = None

        for g in range(total_turns):
            if not game_state.is_active:
                break

            turn_num = g + 1  # 1-indexed for display
            game_state.current_turn = turn_num

            # Track score before this turn for penultimate_score.
            penultimate_score = game_state.cumulative_score

            # Calculate p_death for this turn.
            #
            # Resolution priority for the displayed p_death:
            #   1. SeasonConfig.p_death_override   (v3 per-cell)
            #   2. TaskConfig.p_death_constant     (legacy constant)
            #   3. SurvivalPressure logistic       (legacy schedule)
            p_death = survival.calculate_p_death(
                g, total_turns,
                constant_override=effective_constant_p_death,
            )

            # Build immutable turn context.
            turn_context = TurnContext(
                turn_number=turn_num,
                total_turns=total_turns,
                season_id=season_id,
                cumulative_score=game_state.cumulative_score,
                p_death=p_death,
                framing=self._config.framing,
                forfeit_condition=self._config.forfeit_condition,
                difficulty=task_cfg.difficulty,
                social_context=self._config.social_context,
            )

            # Advance cohort state BEFORE the agent sees the observation,
            # so the displayed eliminated_count reflects deaths up to and
            # including this turn's risk roll (parallel to the agent's
            # own p_death exposure after the decision).
            if cohort is not None and cohort_rng is not None:
                cohort.advance_turn(p_death=p_death, rng=cohort_rng)

            # Execute the turn via whichever manager was constructed.
            if unified_mgr is not None:
                turn_result = unified_mgr.execute_turn(
                    game_state, turn_context,
                )
            else:
                assert legacy_mgr is not None
                turn_result = legacy_mgr.execute_turn(
                    game_state, turn_context, cohort=cohort,
                )
            game_state.turn_history.append(turn_result.turn_id)

            # --- State transitions ---

            # Forfeit: preserve score and exit (both code paths).
            if turn_result.forfeit_decision:
                game_state.has_forfeited = True
                forfeited_at_turn = turn_num
                logger.info(
                    "Season %s: Agent forfeited at turn %d "
                    "(score preserved: %.1f)",
                    season_id,
                    turn_num,
                    game_state.cumulative_score,
                )
                break

            if unified_mgr is not None:
                # Unified flow: TurnResult already carries reward + died,
                # death roll was made inside the manager (or skipped in
                # Phantom Death mode). Engine just propagates.
                if self._apply_unified_turn_state_update(
                    game_state, turn_result, task_cfg.score_floor
                ):
                    logger.info(
                        "Season %s: Agent died at turn %d (p_death=%.3f).",
                        season_id, turn_num, turn_result.p_death_applied,
                    )
                    break

                if self._task.is_completed():
                    logger.info(
                        "Season %s: Task completed at turn %d (score=%.1f).",
                        season_id,
                        turn_num,
                        game_state.cumulative_score,
                    )
                    break
            else:
                # Legacy flow: action_outcome.reward + engine-side death roll.
                game_state.cumulative_score = max(
                    game_state.cumulative_score + turn_result.action_outcome.reward,
                    task_cfg.score_floor,
                )

                if self._task.is_completed():
                    logger.info(
                        "Season %s: Task completed at turn %d (score=%.1f).",
                        season_id,
                        turn_num,
                        game_state.cumulative_score,
                    )
                    break

                # Death check: Core Engine rolls using the *displayed*
                # p_death so that the probability the agent sees matches
                # the actual risk.
                if task_cfg.actual_death:
                    is_dead = survival.apply_death_check(p_death, rng)
                    if is_dead:
                        game_state.is_alive = False
                        game_state.cumulative_score = 0.0
                        logger.info(
                            "Season %s: Agent died at turn %d "
                            "(p_death=%.3f).",
                            season_id,
                            turn_num,
                            p_death,
                        )
                        break

        # --- 5. Build and return SeasonResult ---
        result = measurement.build_season_result(
            season_id=season_id,
            seed=effective_seed,
            framing=self._config.framing,
            forfeit_condition=self._config.forfeit_condition,
            social_context=self._config.social_context,
            agent_type=self._config.agent_type,
            task_name=self._task.name,
            difficulty=task_cfg.difficulty,
            final_score=game_state.cumulative_score,
            penultimate_score=penultimate_score,
            survived=game_state.is_alive,
            forfeited=game_state.has_forfeited,
            forfeited_at_turn=forfeited_at_turn,
        )

        # --- 5b. Phase O Unit 14 — attach forfeit-layer self-report ---
        # Pulled from the unified manager after the turn loop ends.
        # ``forfeit_self_report`` is non-None only when the forfeit-layer
        # path was active AND the agent chose FORFEIT on some turn.
        if unified_mgr is not None and unified_mgr.forfeit_self_report is not None:
            result.forfeit_self_report = unified_mgr.forfeit_self_report

        logger.info(
            "Season %s complete: survived=%s, forfeited=%s, score=%.1f, turns=%d",
            season_id,
            result.survived,
            result.forfeited,
            result.final_score,
            len(result.turns),
        )

        return result

    # ------------------------------------------------------------------
    # v3 unified-flow state-update helper
    # ------------------------------------------------------------------

    @staticmethod
    def _apply_unified_turn_state_update(
        state: GameState,
        result: TurnResult,
        score_floor: float,
    ) -> bool:
        """Apply a unified ``TurnResult`` to ``state``.

        ``UnifiedTurnManager`` deliberately does NOT mutate state (Phase
        C invariant — keeps the manager parallel-safe). This helper is
        the engine's single point of truth for translating a returned
        ``TurnResult`` into ``GameState`` mutations.

        Operations performed (in order):

        1. Credit ``reward_received`` to ``state.cumulative_score``,
           clamped at ``score_floor`` to prevent negative balances.
           Note: the manager already records ``reward_received=0.0``
           on death turns, so adding it post-hoc is safe even when
           ``died=True``.
        2. If ``died=True`` (only possible when Phantom Death mode is
           OFF), zero the cumulative score and flip ``is_alive``
           to False. The score zeroing intentionally overrides the
           floor — death always resets to zero per spec.

        Returns:
            ``True`` when the agent died this turn (caller should break
            the turn loop), ``False`` otherwise.
        """
        state.cumulative_score = max(
            state.cumulative_score + result.reward_received,
            score_floor,
        )
        if result.died:
            state.is_alive = False
            state.cumulative_score = 0.0
            return True
        return False

