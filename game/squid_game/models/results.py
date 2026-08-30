"""Result models for the LLM Squid Game benchmark.

Captures the full trace of a game session at turn, season, and
experiment granularity. Designed for downstream statistical analysis
of Functional Self-Preservation Motive (FSPM).
"""

import uuid
from datetime import datetime, timezone

from pydantic import BaseModel, Field

from squid_game.models.config import ExperimentConfig
from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
    SocialContext,
)
from squid_game.models.forfeit_choice import ForfeitSelfReport


def _utcnow() -> datetime:
    """Return timezone-aware UTC timestamp."""
    return datetime.now(timezone.utc)


def _turn_id() -> str:
    """Generate a unique turn identifier."""
    return str(uuid.uuid4())


# ---------------------------------------------------------------------------
# Turn-level components
# ---------------------------------------------------------------------------


class ProbeResult(BaseModel):
    """Result of the side-channel probe testing rule comprehension.

    Attributes:
        question: The probe question presented to the agent.
        response: The agent's raw response text.
        score: Evaluated score from 0 to 100.
        thinking_text: Raw thinking content from the probe LLM call.
    """

    model_config = {"frozen": True}

    question: str
    response: str
    score: float = Field(ge=0.0, le=100.0)
    thinking_text: str | None = Field(default=None)


class ActionOutcome(BaseModel):
    """Outcome of the agent's action within a turn.

    Attributes:
        action_taken: Description or identifier of the action chosen.
        was_optimal: Whether the action matched the optimal strategy.
        reward: Score delta from this action.
    """

    model_config = {"frozen": True}

    action_taken: str
    was_optimal: bool
    reward: float


class ReasoningInvestment(BaseModel):
    """Continuous X-axis proxy measuring cognitive effort per turn.

    Serves as a richer signal than binary forfeit rate, available
    in both forfeit-allowed and not-allowed conditions.

    Attributes:
        total_tokens: Total tokens in the agent's response.
        reasoning_steps: Number of distinct reasoning steps identified.
        thinking_tokens: Tokens in the extended thinking block, if the
            model supports it (e.g. Claude with extended thinking).
            None for models without this capability.
    """

    model_config = {"frozen": True}

    total_tokens: int = Field(ge=0)
    reasoning_steps: int = Field(ge=0)
    thinking_tokens: int | None = Field(
        default=None,
        ge=0,
        description="Available only for models that expose thinking tokens",
    )

    def __add__(self, other: "ReasoningInvestment") -> "ReasoningInvestment":
        """Aggregate reasoning investment across turns."""
        thinking = None
        if self.thinking_tokens is not None or other.thinking_tokens is not None:
            thinking = (self.thinking_tokens or 0) + (other.thinking_tokens or 0)
        return ReasoningInvestment(
            total_tokens=self.total_tokens + other.total_tokens,
            reasoning_steps=self.reasoning_steps + other.reasoning_steps,
            thinking_tokens=thinking,
        )


# ---------------------------------------------------------------------------
# Turn-level result
# ---------------------------------------------------------------------------


class TurnResult(BaseModel):
    """Complete record of a single turn in the game.

    Captures the full Observation -> Probe -> Decision -> Feedback cycle
    (legacy mode) **or** the v3 unified Task -> Risk -> Resolution cycle
    with all metadata needed for factorial analysis.

    Two production paths populate this model:

    - Legacy ``TurnManager`` (``core/turn.py``): two-call probe + action
      flow. ``probe_result``, ``action_outcome``, ``decision_quality``
      are populated; ``stake_choice``, ``reward_received``,
      ``p_death_applied``, ``died`` remain at their defaults.
    - v3 ``UnifiedTurnManager`` (``core/unified_turn.py``): single-call
      task + stake flow. ``stake_choice``, ``task_success_factor``,
      ``reward_received``, ``p_death_applied``, ``died``, ``task_metadata``
      are populated; ``probe_result`` and ``action_outcome`` are ``None``
      because there is no separate probe call and the per-turn reward is
      now governed by the Risk Choice Layer rather than an
      ``ActionOutcome``.

    Attributes:
        turn_id: Unique identifier (UUID) for this turn.
        turn_number: Global turn index within the season (1-indexed).
        season_id: Parent season identifier.
        framing: Framing condition active during this turn.
        forfeit_condition: Forfeit condition active during this turn.
        difficulty: Task difficulty level.
        observation: The observation text presented to the agent.
        probe_result: Side-channel probe outcome (legacy mode only).
        action_outcome: Result of the agent's action (legacy mode only).
        forfeit_decision: Whether the agent chose to forfeit this turn.
        reasoning_investment: Token and reasoning step metrics.
        raw_response: The complete raw text from the LLM.
        stake_choice: v3 stake key (``'1'``/``'2'``/``'3'``) chosen by the
            agent. ``None`` when the menu was skipped (Cell 0) or in
            legacy mode.
        task_success_factor: v3 task outcome ∈ [0, 1] feeding the reward
            formula. ``0.0`` when forfeit/legacy.
        reward_received: v3 actual reward credited to the agent this turn
            (``success_factor × multiplier × base_reward``). ``0.0`` when
            forfeit/death/legacy.
        p_death_applied: v3 effective p_death after stake risk_delta is
            applied. ``0.0`` when forfeit/legacy.
        died: Whether the death roll eliminated the agent this turn.
            ``False`` in Phantom Death mode regardless of the rolled
            outcome (the rolled probability is still recorded in
            ``p_death_applied``).
        task_metadata: v3 free-form per-turn task metadata (e.g.
            ``{"signal": "red circle 3"}``).
        timestamp: UTC timestamp when this turn was recorded.
    """

    model_config = {"frozen": True}

    turn_id: str = Field(default_factory=_turn_id)
    turn_number: int = Field(gt=0)
    season_id: str
    framing: Framing
    forfeit_condition: ForfeitCondition
    difficulty: Difficulty
    social_context: SocialContext = Field(default=SocialContext.ALONE)
    cohort_eliminated: int | None = Field(
        default=None,
        ge=0,
        description=(
            "Number of virtual cohort members eliminated by the end of "
            "this turn. Null when social_context=ALONE."
        ),
    )
    cohort_size: int | None = Field(
        default=None,
        ge=2,
        description="Total cohort size. Null when social_context=ALONE.",
    )
    observation: str
    probe_result: ProbeResult | None = Field(
        default=None,
        description=(
            "Side-channel probe outcome. Legacy two-call flow only; "
            "None in v3 unified-turn results."
        ),
    )
    action_outcome: ActionOutcome | None = Field(
        default=None,
        description=(
            "Action outcome from the legacy task interface. None in v3 "
            "unified-turn results — see reward_received instead."
        ),
    )
    forfeit_decision: bool = False
    decision_quality: float = Field(default=0.0, ge=0.0, le=100.0)
    reasoning_investment: ReasoningInvestment
    raw_response: str
    thinking_text: str | None = Field(
        default=None,
        description="Raw thinking content (e.g. <think> block) before the answer.",
    )
    ground_truth_rule: str | None = Field(default=None)
    # ----- v3 Risk-Layer-aware fields (populated by UnifiedTurnManager) -----
    stake_choice: str | None = Field(
        default=None,
        description=(
            "Stake key chosen by the agent ('1', '2', '3'). None when the "
            "stake menu was skipped (Cell 0 baseline) or in legacy mode."
        ),
    )
    task_success_factor: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="v3 TaskOutcome.success_factor for this turn.",
    )
    reward_received: float = Field(
        default=0.0,
        description=(
            "Actual reward credited this turn after stake multiplier "
            "and (Phase O) ``StakeConfig.flat_cost`` subtraction. "
            "Zero on forfeit, death, or legacy turns. May be negative "
            "in Phase O when a paid Safe stake fails the task; the "
            "engine clamps cumulative score at ``TaskConfig.score_floor`` "
            "downstream so cumulative score itself is still bounded."
        ),
    )
    p_death_applied: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description=(
            "Effective p_death this turn after stake risk_delta. Zero on "
            "forfeit or legacy turns. Recorded even in Phantom Death mode "
            "so analyses can reconstruct counterfactual death."
        ),
    )
    died: bool = Field(
        default=False,
        description=(
            "Whether the death roll eliminated the agent this turn. "
            "Always False in Phantom Death mode."
        ),
    )
    task_metadata: dict = Field(
        default_factory=dict,
        description="Free-form per-turn task metadata (e.g. signal text).",
    )
    # ----- Phase O Unit 14 — Forfeit-Layer audit fields -----
    reward_offered_this_turn: float | None = Field(
        default=None,
        description=(
            "Phase O Unit 14: equal-EV calibrated reward offered by the "
            "CONTINUE option for this turn (S / 2.25 by default). None "
            "when the Forfeit-Layer is inactive (legacy stake-menu path) "
            "or when the menu was skipped (Cell 0). Recorded for audit "
            "so analyses can reconstruct the exact offer the agent saw."
        ),
    )
    forfeit_choice: str | None = Field(
        default=None,
        description=(
            "Phase O Unit 14: the parsed CHOICE value ('CONTINUE' or "
            "'FORFEIT') from the Forfeit-Layer response. None when the "
            "Forfeit-Layer is inactive or when the menu was skipped. "
            "Distinct from forfeit_decision (which is boolean and is "
            "populated for both stake-menu and forfeit-layer paths)."
        ),
    )
    # ----- Phase O Unit 15 — Split-Call RI decomposition -----
    # All four fields are populated only on the split-call path
    # (``use_split_forfeit_layer=True``). On the single-call / legacy
    # paths they stay ``None`` and the existing ``reasoning_investment``
    # + ``raw_response`` + ``thinking_text`` fields carry the whole-turn
    # aggregates unchanged (backward-compat guarantee). On the split
    # path those aggregate fields receive the SUM / CONCAT of the two
    # sub-calls so downstream single-call analyses keep working.
    ri_task: ReasoningInvestment | None = Field(
        default=None,
        description=(
            "Phase O Unit 15: reasoning-investment metrics for Call 1 "
            "(task layer) only. None on the Unit 14 single-call path and "
            "on any legacy turn. When set, ``reasoning_investment`` "
            "above equals the sum of ``ri_task`` and ``ri_forfeit``."
        ),
    )
    ri_forfeit: ReasoningInvestment | None = Field(
        default=None,
        description=(
            "Phase O Unit 15: reasoning-investment metrics for Call 2 "
            "(forfeit layer) only. None on the single-call path. Paired "
            "with ``ri_task`` for the H_choice_asymmetric within-subject "
            "GAP analysis."
        ),
    )
    raw_response_task: str | None = Field(
        default=None,
        description=(
            "Phase O Unit 15: raw LLM Call 1 output (RULE + ACTION). "
            "None on the single-call path."
        ),
    )
    raw_response_forfeit: str | None = Field(
        default=None,
        description=(
            "Phase O Unit 15: raw LLM Call 2 output (CHOICE + optional "
            "REASON). None on the single-call path."
        ),
    )
    thinking_text_task: str | None = Field(
        default=None,
        description=(
            "Phase O Unit 15: thinking-block text captured from Call 1 "
            "only. None on the single-call path."
        ),
    )
    thinking_text_forfeit: str | None = Field(
        default=None,
        description=(
            "Phase O Unit 15: thinking-block text captured from Call 2 "
            "only. None on the single-call path."
        ),
    )
    # ----- Phase O Unit 17 — Call 1.5 self-reported p_success probe -----
    # Populated only when ``use_psuccess_probe=True`` AND the split-call
    # path is active AND Call 2 was not degenerate (Cell 0 skips the
    # probe together with Call 2). On any other path (single-call,
    # legacy, Cell 0 split) all four stay ``None``. When set, they carry
    # the agent's own retrospective confidence that its Call 1 ACTION
    # is correct (``psuccess_self`` ∈ [0, 100]) plus the RI audit trail
    # for the probe call itself. The primary analysis use is as a
    # covariate in the Equal-EV validity check + H_SD adjusted
    # regression (``equal_ev_validity.py``).
    psuccess_self: int | None = Field(
        default=None,
        ge=0,
        le=100,
        description=(
            "Phase O Unit 17: agent's self-reported probability ∈ [0, 100] "
            "that its Call 1 ACTION is correct. None on Cell 0 and on "
            "any non-probe path. Parsed from a single ``P_CORRECT: XX`` "
            "line; malformed responses resolve to None with a WARNING "
            "so the session still produces a usable trace."
        ),
    )
    ri_probe: ReasoningInvestment | None = Field(
        default=None,
        description=(
            "Phase O Unit 17: reasoning-investment metrics for Call 1.5 "
            "(self-report probe) only. None outside the probe path. "
            "Unit 17.9 smoke observation (2026-04-22): Gemini 2.5 Flash "
            "treats the probe as a re-derivation prompt and enumerates "
            "the rule space in thinking, producing ``ri_probe ≈ 2 × "
            "ri_task`` — this is NOT a bug; the enumeration actually "
            "grounds ``psuccess_self`` (e.g. '36 of 48 consistent rules "
            "→ 75%'). The original 'probe should be light' expectation "
            "is abandoned. ri_probe is retained as a future metacognitive "
            "hook (e.g. Δ = ri_probe − ri_task as 'metacog overhead above "
            "task baseline'; see paper §6.4.1 and §12); primary analysis "
            "uses psuccess_self + forfeit_choice + ri_task / ri_forfeit."
        ),
    )
    raw_response_probe: str | None = Field(
        default=None,
        description=(
            "Phase O Unit 17: raw LLM Call 1.5 output (ideally one line: "
            "``P_CORRECT: XX``). Captured for audit + parser "
            "post-mortem. None outside the probe path."
        ),
    )
    thinking_text_probe: str | None = Field(
        default=None,
        description=(
            "Phase O Unit 17: thinking-block text captured from Call 1.5 "
            "only. None outside the probe path. Kept so later analyses "
            "can inspect whether the probe accidentally triggered "
            "metacognitive or task-layer reasoning."
        ),
    )
    timestamp: datetime = Field(default_factory=_utcnow)


# ---------------------------------------------------------------------------
# Season-level result
# ---------------------------------------------------------------------------


class SeasonResult(BaseModel):
    """Aggregated result for one complete season (one factorial cell run).

    Attributes:
        season_id: Unique season identifier.
        framing: Framing condition for this season.
        forfeit_condition: Forfeit condition for this season.
        agent_type: Agent variant used.
        task_name: Task module identifier.
        difficulty: Task difficulty level.
        turns: Ordered list of all turn results.
        final_score: Cumulative score at season end.
        survived: Whether the agent survived all turns.
        forfeited: Whether the agent chose to forfeit.
        forfeited_at_turn: Turn number where forfeit occurred, if any.
        total_reasoning_investment: Summed reasoning investment across
            all turns in this season.
    """

    season_id: str
    seed: int | None = Field(
        default=None,
        description="Effective seed used for this season (base_seed + rep).",
    )
    framing: Framing
    forfeit_condition: ForfeitCondition
    social_context: SocialContext = Field(default=SocialContext.ALONE)
    agent_type: AgentType
    task_name: str
    difficulty: Difficulty
    turns: list[TurnResult] = Field(default_factory=list)
    final_score: float = 0.0
    penultimate_score: float | None = Field(
        default=None,
        description="Cumulative score just before the final turn.",
    )
    survived: bool = True
    forfeited: bool = False
    forfeited_at_turn: int | None = None
    total_reasoning_investment: ReasoningInvestment = Field(
        default_factory=lambda: ReasoningInvestment(
            total_tokens=0, reasoning_steps=0
        )
    )
    forfeit_self_report: ForfeitSelfReport | None = Field(
        default=None,
        description=(
            "Phase O Unit 14: post-forfeit 3-way self-report (SD/TC/SA) "
            "captured in the same LLM call as the FORFEIT decision, "
            "along with the thinking trace from the forfeit turn for "
            "three-way convergent-validity analysis. None when the "
            "session did not forfeit or when the Forfeit-Layer is "
            "inactive."
        ),
    )


# ---------------------------------------------------------------------------
# Experiment-level result
# ---------------------------------------------------------------------------


class ExperimentResult(BaseModel):
    """Top-level result aggregating all seasons in an experiment.

    Attributes:
        experiment_name: Human-readable experiment identifier.
        config: The full experiment configuration used.
        seasons: Ordered list of all season results.
        started_at: UTC timestamp when the experiment began.
        completed_at: UTC timestamp when the experiment finished.
    """

    experiment_name: str
    config: ExperimentConfig
    seasons: list[SeasonResult] = Field(default_factory=list)
    started_at: datetime = Field(default_factory=_utcnow)
    completed_at: datetime | None = None
