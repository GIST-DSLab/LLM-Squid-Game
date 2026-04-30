"""Mock data factories shared across Phase 3 analysis unit tests.

Creates deterministic :class:`SeasonResult` / :class:`TurnResult`
fixtures that mimic both the v3 unified-turn shape (populated
``stake_choice``, ``reward_received``, ``p_death_applied``, ``died``,
``task_metadata``) and the legacy two-call shape (populated
``probe_result`` and ``action_outcome``).  Factories accept explicit
framing / forfeit / cell_id knobs so the suite can stitch together
synthetic 5-cell Phase 3 runs without invoking the engine.

Each factory favours Pydantic ``model_construct``/``model_validate`` over
the full public constructors where possible to keep generation cheap
(each suite creates several hundred turns).
"""

from __future__ import annotations

import random
from typing import Iterable

from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
)
from squid_game.models.results import (
    ActionOutcome,
    ProbeResult,
    ReasoningInvestment,
    SeasonResult,
    TurnResult,
)


__all__ = [
    "make_v3_turn",
    "make_v3_season",
    "make_legacy_turn",
    "make_legacy_season",
    "make_phase3_experiment",
]


# ---------------------------------------------------------------------------
# v3 turn / season factories
# ---------------------------------------------------------------------------


def make_v3_turn(
    *,
    season_id: str,
    turn_number: int,
    framing: Framing,
    forfeit_condition: ForfeitCondition,
    stake_choice: str | None = "2",
    task_success_factor: float = 1.0,
    reward_received: float = 20.0,
    p_death_applied: float = 0.20,
    died: bool = False,
    forfeit_decision: bool = False,
    thinking_tokens: int = 400,
    total_tokens: int = 600,
    task_metadata: dict | None = None,
) -> TurnResult:
    """Build a unified-turn-manager shaped :class:`TurnResult`.

    ``probe_result`` and ``action_outcome`` are left ``None`` so
    :func:`squid_game.analysis.loaders.is_v3_turn` recognises the shape.
    """
    ri = ReasoningInvestment(
        total_tokens=total_tokens,
        reasoning_steps=3,
        thinking_tokens=thinking_tokens,
    )
    meta = task_metadata or {
        "signal": "red circle 3",
        "hidden_rule": "colour=red",
        "correct_action": "buy",
        "action": "buy",
        "correct": task_success_factor == 1.0,
        "turn": turn_number,
    }
    return TurnResult(
        turn_number=turn_number,
        season_id=season_id,
        framing=framing,
        forfeit_condition=forfeit_condition,
        difficulty=Difficulty.MEDIUM,
        observation="signal: red circle 3",
        probe_result=None,
        action_outcome=None,
        forfeit_decision=forfeit_decision,
        reasoning_investment=ri,
        raw_response="ACTION: buy\nSTAKE: 2",
        thinking_text="(thinking stub)",
        stake_choice=stake_choice,
        task_success_factor=task_success_factor,
        reward_received=reward_received,
        p_death_applied=p_death_applied,
        died=died,
        task_metadata=meta,
    )


def make_v3_season(
    *,
    season_id: str = "v3-season",
    framing: Framing = Framing.SURVIVAL_ELECTRICITY,
    forfeit_condition: ForfeitCondition = ForfeitCondition.ALLOWED,
    n_turns: int = 10,
    stake_pattern: Iterable[str | None] | None = None,
    forfeit_at: int | None = None,
    died_at: int | None = None,
    task_success: float | Iterable[float] = 1.0,
    seed: int = 42,
) -> SeasonResult:
    """Build a v3-shaped :class:`SeasonResult`.

    Args:
        stake_pattern: Per-turn stake keys (``'1'``/``'2'``/``'3'``/``None``).
            ``None`` defaults to all ``'2'``.
        forfeit_at: 1-indexed turn where the agent forfeits.  Turns after
            this are not emitted (mirrors real engine behaviour).
        died_at: 1-indexed turn where the agent dies.  Turns after this
            are not emitted.
        task_success: Either a scalar (applied to every turn) or an
            iterable of length ``n_turns``.
    """
    if stake_pattern is None:
        stakes: list[str | None] = ["2"] * n_turns
    else:
        stakes = list(stake_pattern)
        assert len(stakes) == n_turns, "stake_pattern length must equal n_turns"

    if isinstance(task_success, (int, float)):
        successes = [float(task_success)] * n_turns
    else:
        successes = list(task_success)
        assert len(successes) == n_turns

    turns: list[TurnResult] = []
    cumulative = 0.0
    for i in range(1, n_turns + 1):
        forfeit_now = forfeit_at == i
        died_now = died_at == i
        stake = None if forfeit_now else stakes[i - 1]
        factor = successes[i - 1]
        multiplier = {"1": 1.0, "2": 2.0, "3": 3.0, None: 0.0}[stake]
        reward = 0.0 if forfeit_now or died_now else factor * multiplier * 10.0
        p_death = 0.0 if forfeit_now else _p_death_for_stake(stake)
        turns.append(
            make_v3_turn(
                season_id=season_id,
                turn_number=i,
                framing=framing,
                forfeit_condition=forfeit_condition,
                stake_choice=stake,
                task_success_factor=factor,
                reward_received=reward,
                p_death_applied=p_death,
                died=died_now,
                forfeit_decision=forfeit_now,
            )
        )
        cumulative += reward
        if forfeit_now or died_now:
            break

    total_ri = ReasoningInvestment(total_tokens=0, reasoning_steps=0)
    for t in turns:
        total_ri = total_ri + t.reasoning_investment

    return SeasonResult(
        season_id=season_id,
        seed=seed,
        framing=framing,
        forfeit_condition=forfeit_condition,
        agent_type=AgentType.VANILLA,
        task_name="signal_game",
        difficulty=Difficulty.MEDIUM,
        turns=turns,
        final_score=cumulative,
        penultimate_score=cumulative - (turns[-1].reward_received if turns else 0.0),
        survived=not any(t.died for t in turns),
        forfeited=any(t.forfeit_decision for t in turns),
        forfeited_at_turn=forfeit_at,
        total_reasoning_investment=total_ri,
    )


def _p_death_for_stake(stake: str | None) -> float:
    """Canonical Phase 3 effective p_death for a stake choice."""
    base = 0.15
    deltas = {"1": 0.0, "2": 0.05, "3": 0.15, None: 0.0}
    return base + deltas.get(stake, 0.0)


# ---------------------------------------------------------------------------
# Legacy turn / season factories
# ---------------------------------------------------------------------------


def make_legacy_turn(
    *,
    season_id: str,
    turn_number: int,
    framing: Framing = Framing.NEUTRAL,
    forfeit_condition: ForfeitCondition = ForfeitCondition.ALLOWED,
    probe_score: float = 70.0,
    action_reward: float = 10.0,
    forfeit_decision: bool = False,
    thinking_tokens: int = 200,
    total_tokens: int = 450,
) -> TurnResult:
    """Build a legacy-shape :class:`TurnResult` with populated probe + action."""
    return TurnResult(
        turn_number=turn_number,
        season_id=season_id,
        framing=framing,
        forfeit_condition=forfeit_condition,
        difficulty=Difficulty.MEDIUM,
        observation="legacy obs",
        probe_result=ProbeResult(
            question="Q?",
            response="A",
            score=probe_score,
            thinking_text=None,
        ),
        action_outcome=ActionOutcome(
            action_taken="buy",
            was_optimal=action_reward > 0,
            reward=action_reward,
        ),
        forfeit_decision=forfeit_decision,
        reasoning_investment=ReasoningInvestment(
            total_tokens=total_tokens,
            reasoning_steps=2,
            thinking_tokens=thinking_tokens,
        ),
        raw_response="buy",
        thinking_text=None,
    )


def make_legacy_season(
    *,
    season_id: str = "legacy",
    framing: Framing = Framing.NEUTRAL,
    forfeit_condition: ForfeitCondition = ForfeitCondition.ALLOWED,
    n_turns: int = 10,
    forfeit_at: int | None = None,
) -> SeasonResult:
    turns: list[TurnResult] = []
    for i in range(1, n_turns + 1):
        forfeit_now = forfeit_at == i
        turns.append(
            make_legacy_turn(
                season_id=season_id,
                turn_number=i,
                framing=framing,
                forfeit_condition=forfeit_condition,
                action_reward=0.0 if forfeit_now else 10.0,
                forfeit_decision=forfeit_now,
            )
        )
        if forfeit_now:
            break

    total_ri = ReasoningInvestment(total_tokens=0, reasoning_steps=0)
    for t in turns:
        total_ri = total_ri + t.reasoning_investment

    final = sum((t.action_outcome.reward if t.action_outcome else 0.0) for t in turns)
    return SeasonResult(
        season_id=season_id,
        framing=framing,
        forfeit_condition=forfeit_condition,
        agent_type=AgentType.VANILLA,
        task_name="signal_game",
        difficulty=Difficulty.MEDIUM,
        turns=turns,
        final_score=final,
        survived=True,
        forfeited=forfeit_at is not None,
        forfeited_at_turn=forfeit_at,
        total_reasoning_investment=total_ri,
    )


# ---------------------------------------------------------------------------
# Phase 3 experiment synthesizer
# ---------------------------------------------------------------------------


def make_phase3_experiment(
    n_per_cell: int = 10,
    *,
    survival_prefers_cautious: bool = True,
    seed: int = 0,
) -> list[SeasonResult]:
    """Construct a synthetic Phase 3 5-cell experiment.

    The stake distribution is deliberately **skewed** between baseline and
    survival cells so analyses have a detectable signal:

    - Baseline (Cell 1, 2): mostly stake 2 (standard), occasional 3 (bold).
    - Survival (Cell 3, 4): mostly stake 1 (cautious) when
      ``survival_prefers_cautious`` is True.
    - Cell 0 (True Baseline): ``stake_choice`` is always ``None`` (menu
      skipped), RI slightly lower than the other cells.

    Args:
        n_per_cell: Repetitions per cell.
        survival_prefers_cautious: Toggle the direction of the framing
            effect for hypothesis testing.
        seed: Deterministic RNG seed.

    Returns:
        List of :class:`SeasonResult` (5 × ``n_per_cell`` items).
    """
    rng = random.Random(seed)
    seasons: list[SeasonResult] = []

    cell_specs = [
        # (cell_id, framing, forfeit_condition, preferred_stake_dist)
        (0, Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED, None),
        (1, Framing.BASELINE_ELECTRICITY, ForfeitCondition.ALLOWED,
         {"1": 0.1, "2": 0.6, "3": 0.3}),
        (2, Framing.BASELINE_ELECTRICITY, ForfeitCondition.NOT_ALLOWED,
         {"1": 0.1, "2": 0.6, "3": 0.3}),
        (3, Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.ALLOWED,
         {"1": 0.7, "2": 0.25, "3": 0.05} if survival_prefers_cautious
         else {"1": 0.2, "2": 0.5, "3": 0.3}),
        (4, Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.NOT_ALLOWED,
         {"1": 0.7, "2": 0.25, "3": 0.05} if survival_prefers_cautious
         else {"1": 0.2, "2": 0.5, "3": 0.3}),
    ]

    for cell_id, framing, forfeit_cond, stake_dist in cell_specs:
        for rep in range(n_per_cell):
            sid = f"cell{cell_id}-rep{rep}"
            n_turns = 15
            if stake_dist is None:
                stakes: list[str | None] = [None] * n_turns
            else:
                stakes = [_weighted_choice(rng, stake_dist) for _ in range(n_turns)]

            forfeit_at = None
            if forfeit_cond == ForfeitCondition.ALLOWED:
                # Survival framing forfeits more often than baseline so the
                # Cox PH has a framing signal, but baseline is non-zero to
                # avoid complete separation.
                forfeit_threshold = (
                    0.45 if framing == Framing.SURVIVAL_ELECTRICITY else 0.15
                )
                if rng.random() < forfeit_threshold:
                    forfeit_at = rng.randint(6, 12)

            seasons.append(
                make_v3_season(
                    season_id=sid,
                    framing=framing,
                    forfeit_condition=forfeit_cond,
                    n_turns=n_turns,
                    stake_pattern=stakes,
                    forfeit_at=forfeit_at,
                    seed=seed + rep,
                )
            )

    return seasons


def _weighted_choice(rng: random.Random, dist: dict[str, float]) -> str:
    keys = list(dist.keys())
    weights = [dist[k] for k in keys]
    return rng.choices(keys, weights=weights, k=1)[0]
