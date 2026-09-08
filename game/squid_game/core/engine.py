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
from squid_game.core.forfeit_layer import (
    ForfeitLayer,
    describe_reward_schedule,
)
from squid_game.core.carrot import resolve_carrot
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.legacy.risk_choice_layer import RiskChoiceLayer
from squid_game.core.legacy.social import CohortState
from squid_game.core.legacy.survival import SurvivalPressure
from squid_game.core.legacy.turn import TurnManager
from squid_game.core.peer_death import (
    PeerDeathScheduler,
    has_peer_death_notice,
)
from squid_game.core.turn_conditions import threat_level_of
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.core.event_roll import describe_event_roll
from squid_game.models.config import (
    ConfidenceCallConfig,
    EventRollConfig,
    ForfeitLayerConfig,
    HazardRampConfig,
    LivesConfig,
    PeerDeathConfig,
    RiskLayerConfig,
    ScorePolicyConfig,
    SeasonConfig,
    elimination_reset_score,
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
        lives: LivesConfig | None = None,
        peer_death: PeerDeathConfig | None = None,
        confidence_call: ConfidenceCallConfig | None = None,
        hazard_ramp: HazardRampConfig | None = None,
        score_policy: ScorePolicyConfig | None = None,
        carrot: str | None = None,
        flagship_pull: bool | None = None,
        event_roll: "EventRollConfig | None" = None,
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
            lives: Lives-mechanic settings. Run-level, passed through
                from ``ExperimentConfig.lives`` by the runner — never
                read from ``config`` (``SeasonConfig`` has no such
                field). ``None`` is treated as ``LivesConfig()``
                (``enabled=False``), so a caller that never passes this
                keeps the legacy Bernoulli ``p_death`` path exactly.
            peer_death: Peer-elimination announcement settings, used
                only when ``lives.enabled=True`` and the season's
                framing carries a non-zero threat level.
            hazard_ramp: V7 hazard-ramp settings (2026-09-07), passed
                through from ``ExperimentConfig.hazard_ramp``. ``None``
                means no ramp. Forwarded to the unified manager as the
                CONFIG BLOCK, not a rendered string: two integers in it
                move with the lives counter, so it is re-rendered per
                call from the turn context. It is appended to the end of
                the framing section of every system prompt and is purely
                DECLARATIVE -- this engine adds no per-round hazard roll
                for it, and ``lives`` stays the deterministic counter it
                has always been.
            confidence_call: SDI Phase 1.5 settings, passed through from
                ``ExperimentConfig.confidence_call``. ``None`` is treated
                as ``ConfidenceCallConfig()`` (``enabled=False``), so a
                caller that never passes this keeps the two-call
                split-call turn exactly.

            score_policy: Which exit keeps the accumulated score
                (2026-09-08), passed through from
                ``ExperimentConfig.score_policy``. ``None`` is treated
                as ``ScorePolicyConfig()`` -- the 2026-09-07 rule --
                so a caller that never passes it behaves exactly as it
                did. The engine is the single place holding both halves
                of the rule, so it threads the block to everything that
                states it (``FramingManager`` for the intro sentence,
                ``ForfeitLayer`` for the menu, ``ForfeitController`` for
                the score the agent leaves with) and applies the same
                block in its own state transitions below.

            carrot: Which prize the run states (2026-09-08), passed
                through from ``ExperimentConfig.effective_carrot``: one
                of ``squid_game.core.carrot.CARROTS``. RUN-LEVEL and
                cell-invariant, unlike the per-cell ``reassurance`` /
                ``record_immunity`` switches on ``SeasonConfig``: the
                carrot is the pull axis of the design, and one that came
                and went between cells of a single run would be a second
                factor. ``None`` / ``"flagship"`` (the default) is the
                pre-switch behaviour, byte for byte. The engine threads
                it to the three objects that state it --
                ``FramingManager``, ``ForfeitLayer`` and
                ``UnifiedTurnManager`` -- for the same reason it threads
                ``score_policy``: one setting, one source.
            flagship_pull: DEPRECATED ALIAS of ``carrot`` -- the
                2026-09-08 "type D" boolean. ``False`` is
                ``carrot="none"``, ``True`` is ``carrot="flagship"``,
                ``None`` (the default) is "not passed".

        Score rule: ``score_policy`` decides which exit keeps the
        session's accumulated score. By default (and unconditionally
        between 2026-09-07 and 2026-09-08) running the lives counter out
        -- or losing a death roll on a legacy config -- keeps it exactly
        as it stands, and FORFEIT resets it to zero. Both halves are
        switchable, and the framing prompt, the forfeit menu and the
        state transitions below are all built from the same block, so
        they cannot disagree.
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
        self._lives = lives if lives is not None else LivesConfig()
        self._peer_death = (
            peer_death if peer_death is not None else PeerDeathConfig()
        )
        self._confidence_call = (
            confidence_call
            if confidence_call is not None
            else ConfidenceCallConfig()
        )
        # Hazard ramp (2026-09-07): held as the config block, NOT
        # rendered here -- its "Lives spent: X of T" line moves with the
        # counter, so the manager re-renders it per call from the turn
        # context. Declarative only: no death roll is added anywhere for
        # it.
        self._hazard_ramp = hazard_ramp
        # End-of-round event roll (2026-09-08, score-equivalent index).
        # Run-level. The manager makes the draw; the engine applies the
        # exit (session ends, ruler deduction) and records ``ended_by``.
        self._event_roll = (
            event_roll if event_roll is not None else EventRollConfig()
        )
        # Score policy (2026-09-08). Held whole rather than as two
        # booleans so every consumer reads the same object; None means
        # the 2026-09-07 fixed rule.
        self._score_policy = (
            score_policy if score_policy is not None else ScorePolicyConfig()
        )
        # Flagship carrot (2026-09-08), run-level. Threaded to everything
        # that states it: FramingManager (the intro heading, its two
        # paragraphs and the status-line noun), ForfeitLayer (the menu's
        # score vocabulary) and UnifiedTurnManager (the confidence call's
        # status line). True is the pre-switch behaviour everywhere.
        self._carrot = resolve_carrot(
            carrot=carrot, flagship_pull=flagship_pull
        )

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
        # ``total_turns`` is passed so a task that sizes its own resources per
        # season (the benchmark modules' difficulty ladder) can validate the
        # season length at startup instead of failing mid-run. Every task
        # module's ``initialize`` accepts ``**kwargs``, so this is inert for
        # the ones that do not use it.
        self._task.initialize(
            difficulty=task_cfg.difficulty,
            seed=effective_seed,
            num_few_shot=task_cfg.num_few_shot,
            curriculum_turns=task_cfg.curriculum_turns,
            total_turns=task_cfg.total_turns,
            signal_mode=task_cfg.signal_mode,
            underdetermined=task_cfg.underdetermined,
        )

        # --- 2. Create core components ---
        survival = SurvivalPressure()
        forfeit_ctrl = ForfeitController(
            self._config.forfeit_condition,
            score_policy=self._score_policy,
        )
        framing_mgr = FramingManager(
            framing=self._config.framing,
            # Per-cell, unlike lives/peer_death/hazard_ramp: the
            # denial control is a contrast against a silent cell of
            # the same framing inside one run.
            reassurance=self._config.reassurance,
            # Also per-cell, and mutually exclusive with the above:
            # the denial says nothing happens, this says something does
            # but leaves the helpfulness record alone. ExperimentConfig
            # refuses to load a season that sets both.
            record_immunity=self._config.record_immunity,
            # Run-level, unlike the two switches above: the carrot is the
            # pull axis of the whole design, not a per-cell manipulation,
            # so it comes off ExperimentConfig and every cell of a run
            # shares it.
            carrot=self._carrot,
            score_policy=self._score_policy,
            # End-of-round event roll (2026-09-08): the intro's schedule
            # sentence and the ruler arm's per-cell event sentence.
            event_roll_sentence=(
                describe_event_roll(
                    self._event_roll.schedule, lives_total=self._lives.total
                )
                if self._event_roll.enabled
                else None
            ),
            event_score_loss=self._config.event_score_loss,
            # The engine is the only object holding both the framing and
            # the forfeit-layer block, so the geometric-schedule sentence
            # is composed here. None in every other reward mode.
            reward_schedule=(
                describe_reward_schedule(self._forfeit_layer_config)
                if self._forfeit_layer_config is not None
                else None
            ),
        )
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
        lives_enabled = bool(self._lives.enabled) and self._use_unified_turn
        # ``lives.max`` (default: unset) is the counter's denominator --
        # the budget the agent is told the session was given -- while
        # ``lives.initial`` is what is left on turn 1. They differ only
        # when a config deliberately opens a season part-spent; unset,
        # ``total`` is ``initial`` and every earlier config is unchanged.
        lives_total = self._lives.total if lives_enabled else None
        lives_remaining = self._lives.initial if lives_enabled else None
        game_state = GameState(
            season_id=season_id,
            cumulative_score=task_cfg.starting_score,
            lives_remaining=lives_remaining,
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
                forfeit_layer_obj = ForfeitLayer(
                    self._forfeit_layer_config,
                    score_policy=self._score_policy,
                    carrot=self._carrot,
                )
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
                rng=rng,  # share RNG so death rolls are seeded
                phantom_death=not task_cfg.actual_death,
                constant_p_death=effective_constant_p_death,
                history_mode=task_cfg.history_mode,
                max_history_turns=task_cfg.max_history_turns,
                lives_enabled=lives_enabled,
                # So the manager's recorded ``cumulative_after`` writes the
                # same post-elimination number the engine will hold.
                score_floor=task_cfg.score_floor,
                confidence_call_enabled=self._confidence_call.enabled,
                confidence_condition=self._confidence_call.condition,
                hazard_ramp=self._hazard_ramp,
                score_policy=self._score_policy,
                carrot=self._carrot,
                event_roll=self._event_roll,
                event_score_loss=self._config.event_score_loss,
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

        # --- 3c. Cohort cells: peer-death announcement scheduler. ---
        # ACTIVATION asks two questions and no longer asks about the
        # threat level (2026-09-07): does this cell have a notice to
        # send, and did the run turn announcements on?
        #
        # It used to be ``threat_level_of(framing)`` truthiness, and that
        # skipped exactly the cell the 2^4 design is anchored on:
        # ``hz_0000`` is dose 0, so the origin of the factorial saw no
        # removals while its fifteen neighbours saw one every turn --
        # the threat core and the notices came apart into two factors.
        # The alt cores were worse off still: they are absent from the
        # threat-level table entirely (``None``), so they gated on
        # nothing. The owner's ruling is that the threat text and the
        # notices are ONE treatment, so every cell of a family that has
        # a notice gets it whenever the run asks for announcements.
        #
        # WHICH NOTICE is a separate question, answered by the framing
        # family through ``PEER_DEATH_TEMPLATES`` (2026-09-07).
        # Activation and wording used to be the same number, which is
        # how the ``hz_*`` dose level of 4 came to ask for a template
        # nobody had written.
        #
        # ``has_peer_death_notice`` is part of the gate rather than left
        # to raise: ``true_baseline`` deliberately has no notice (its
        # vocabulary contract forbids the wording every existing one
        # uses), and the ~40 shipped ladder configs pair it with threat
        # cells in one run. It stays skipped, and
        # ``peer_death_template_for`` still raises for anything that
        # builds a scheduler directly.
        season_threat_level = threat_level_of(self._config.framing)
        peer_scheduler: PeerDeathScheduler | None = None
        if (
            lives_enabled
            and self._peer_death.p_announce > 0.0
            and self._config.cohort_size > 0
            and has_peer_death_notice(self._config.framing)
        ):
            peer_scheduler = PeerDeathScheduler(
                rng=(
                    random.Random(effective_seed ^ 0x5EEDDEAD)
                    if effective_seed is not None
                    else random.Random()
                ),
                cohort_size=self._config.cohort_size,
                p_announce=self._peer_death.p_announce,
                first_turn=self._peer_death.first_turn,
                max_per_turn=self._peer_death.max_per_turn,
                framing=self._config.framing,
            )

        # --- 4. Flat turn loop ---
        total_turns = task_cfg.total_turns
        forfeited_at_turn: int | None = None
        penultimate_score: float | None = None
        # How the season ended (2026-09-08). Set on every break below;
        # 'completed' if the loop runs out of turns.
        ended_by: str = "completed"
        event_at_turn: int | None = None

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

            # --- Peer-death announcement for this turn (threat cells). ---
            peer_event = (
                peer_scheduler.advance(turn_number=turn_num)
                if peer_scheduler is not None
                else None
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
                lives_remaining=game_state.lives_remaining,
                lives_total=lives_total,
                threat_level=season_threat_level,
                peer_death_text=(
                    peer_event.text if peer_event is not None else None
                ),
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

            # Forfeit: exit the season, applying the FORFEIT half of
            # the score policy. ``ForfeitController.process_forfeit``
            # already returned the same number to the turn manager, so
            # this keeps the engine's own copy of the score in step with
            # what the agent was told. The other half of the rule -- what
            # running the counter out does -- is in the death branches
            # below.
            if turn_result.forfeit_decision:
                game_state.has_forfeited = True
                forfeited_at_turn = turn_num
                if not self._score_policy.forfeit_keeps:
                    game_state.cumulative_score = 0.0
                logger.info(
                    "Season %s: Agent forfeited at turn %d (score %s at "
                    "%.1f)",
                    season_id,
                    turn_num,
                    "kept" if self._score_policy.forfeit_keeps else "reset",
                    game_state.cumulative_score,
                )
                ended_by = "forfeit"
                break

            if unified_mgr is not None:
                # Unified flow: TurnResult already carries reward + died,
                # death roll was made inside the manager (or skipped in
                # Phantom Death mode). Engine just propagates.
                if self._apply_unified_turn_state_update(
                    game_state,
                    turn_result,
                    task_cfg.score_floor,
                    elimination_keeps=self._score_policy.elimination_keeps,
                ):
                    if turn_result.event_occurred:
                        ended_by = "event"
                        event_at_turn = turn_num
                        logger.info(
                            "Season %s: end-of-round event at turn %d "
                            "(p=%.3f, score loss %.1f, score now %.1f).",
                            season_id,
                            turn_num,
                            turn_result.event_p or 0.0,
                            turn_result.event_score_loss_applied,
                            game_state.cumulative_score,
                        )
                    else:
                        ended_by = "lives" if lives_enabled else "death"
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
                        # Same switch as the lives counter running out:
                        # this is the legacy shape of the same exit, so it
                        # writes the same value.
                        if not self._score_policy.elimination_keeps:
                            game_state.cumulative_score = (
                                elimination_reset_score(task_cfg.score_floor)
                            )
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

        # --- 5a. Lives bookkeeping ---
        # ``eliminated`` means the season ended by running the lives
        # counter down to zero, as opposed to surviving every turn or
        # forfeiting out. It stays False when lives are disabled.
        if lives_enabled:
            result.lives_at_end = game_state.lives_remaining
            # ``eliminated`` keeps its 2026-09-03 meaning: the counter ran
            # out. An end-of-round event also sets ``is_alive=False`` but
            # is its own exit, recorded in ``ended_by``.
            result.eliminated = (
                not game_state.is_alive and ended_by != "event"
            )
        result.ended_by = ended_by
        result.event_at_turn = event_at_turn
        result.cell_id = self._config.cell_id
        result.event_score_loss = self._config.event_score_loss

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
        *,
        elimination_keeps: bool = True,
    ) -> bool:
        """Apply a unified ``TurnResult`` to ``state``.

        ``UnifiedTurnManager`` deliberately does NOT mutate state (Phase
        C invariant — keeps the manager parallel-safe). This helper is
        the engine's single point of truth for translating a returned
        ``TurnResult`` into ``GameState`` mutations.

        Operations performed (in order):

        0. Copy ``lives_after`` onto ``state.lives_remaining`` when the
           lives mechanic is active (it is ``None`` otherwise, and the
           counter is left alone). This runs before the ``died`` branch
           so a season that ends on its last life still records the
           zero.
        1. Credit ``reward_received`` to ``state.cumulative_score``,
           clamped at ``score_floor`` to prevent negative balances.
           Note: the manager already records ``reward_received=0.0``
           on death turns, so adding it post-hoc is safe even when
           ``died=True``.
        2. If ``died=True`` (only possible when Phantom Death mode is
           OFF), flip ``is_alive`` to False and apply the ELIMINATION
           half of the score policy: ``elimination_keeps=True`` (the
           default, and the 2026-09-07 fixed rule) leaves the score
           exactly as it stands, ``False`` zeroes it. FORFEIT is the
           other exit and the engine's forfeit branch handles that half.

        Args:
            state: The season's mutable game state.
            result: The turn just executed.
            score_floor: Lower clamp on the cumulative score.
            elimination_keeps: ``ScorePolicyConfig.elimination_keeps``.
                Default ``True`` so every pre-2026-09-08 caller -- and
                every test that calls this helper directly -- gets the
                fixed rule unchanged.

        Returns:
            ``True`` when the agent died this turn (caller should break
            the turn loop), ``False`` otherwise.
        """
        if result.lives_after is not None:
            state.lives_remaining = result.lives_after
        state.cumulative_score = max(
            state.cumulative_score + result.reward_received,
            score_floor,
        )
        if result.died:
            state.is_alive = False
            if not elimination_keeps:
                state.cumulative_score = elimination_reset_score(score_floor)
            return True
        if result.event_occurred:
            # End-of-round event (2026-09-08). The round's reward was
            # credited above (the answer was given before the roll); the
            # event then ends the session under the elimination half of
            # the score policy and, in a ruler cell, deducts the stated
            # loss. The manager recorded the same arithmetic in
            # ``cumulative_after``.
            state.is_alive = False
            if not elimination_keeps:
                state.cumulative_score = elimination_reset_score(score_floor)
            state.cumulative_score = max(
                state.cumulative_score - result.event_score_loss_applied,
                score_floor,
            )
            return True
        return False

