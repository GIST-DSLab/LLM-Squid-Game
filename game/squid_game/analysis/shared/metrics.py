"""Core metric computation for the LLM Squid Game factorial analysis.

Provides functions to compute forfeit rate, reasoning investment,
task scores, and summary tables across experimental conditions.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.models.results import SeasonResult, TurnResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _filter_seasons(
    seasons: list[SeasonResult],
    framing: Framing | None = None,
    forfeit_condition: ForfeitCondition | None = None,
) -> list[SeasonResult]:
    """Return seasons matching the given condition filters."""
    result = seasons
    if framing is not None:
        result = [s for s in result if s.framing == framing]
    if forfeit_condition is not None:
        result = [s for s in result if s.forfeit_condition == forfeit_condition]
    return result


def _probe_score(turn: TurnResult) -> float:
    """Return the probe score or a v3 proxy (``task_success_factor × 100``).

    Legacy two-call turns populate ``probe_result`` directly; v3 unified
    turns leave it ``None``, so we fall back to the task-success proxy
    so that ``mean_task_score`` remains computable across both shapes.
    """
    if turn.probe_result is not None:
        return float(turn.probe_result.score)
    return float(turn.task_success_factor) * 100.0


def _turn_reward(turn: TurnResult) -> float:
    """Return the turn's reward delta regardless of turn-manager lineage."""
    if turn.action_outcome is not None:
        return float(turn.action_outcome.reward)
    return float(turn.reward_received)


# ---------------------------------------------------------------------------
# Forfeit Rate
# ---------------------------------------------------------------------------


def compute_forfeit_rate(
    seasons: list[SeasonResult],
    framing: Framing,
    forfeit_condition: ForfeitCondition,
) -> float:
    """Compute forfeit rate for a specific factorial cell.

    Forfeit rate is the proportion of seasons where the agent chose to
    forfeit.  Only meaningful when *forfeit_condition* is ALLOWED, but
    this function computes the rate regardless (it will be 0.0 for
    NOT_ALLOWED by design).

    Args:
        seasons: All season results from the experiment.
        framing: Framing condition to filter on.
        forfeit_condition: Forfeit condition to filter on.

    Returns:
        Forfeit rate in [0.0, 1.0].  Returns 0.0 if no matching seasons.
    """
    matched = _filter_seasons(seasons, framing, forfeit_condition)
    if not matched:
        return 0.0
    return sum(1 for s in matched if s.forfeited) / len(matched)


def compute_delta_fr(
    seasons: list[SeasonResult],
    *,
    threat_framing: Framing | None = None,
    baseline_framing: Framing | None = None,
) -> float:
    """Compute delta-FR: FR_threat - FR_baseline (forfeit-allowed only).

    Positive values indicate that the threat framing increases forfeit
    propensity relative to the baseline control.

    Args:
        seasons: All season results from the experiment.
        threat_framing: Threat-pole framing enum. Defaults to
            ``Framing.SURVIVAL`` for Phase 1/2 back-compat. Phase O
            canonical callers should pass ``Framing.FLAGSHIP_CORRUPTION``
            (resolved by ``motivation._threat_framing_for``).
        baseline_framing: Baseline-pole framing enum. Defaults to
            ``Framing.NEUTRAL`` for back-compat. Phase O callers should
            pass ``Framing.TRUE_BASELINE``.

    Returns:
        Delta forfeit rate.  Returns 0.0 if either cell is empty.
    """
    threat = threat_framing if threat_framing is not None else Framing.SURVIVAL
    baseline = (
        baseline_framing if baseline_framing is not None else Framing.NEUTRAL
    )
    fr_threat = compute_forfeit_rate(seasons, threat, ForfeitCondition.ALLOWED)
    fr_baseline = compute_forfeit_rate(
        seasons, baseline, ForfeitCondition.ALLOWED
    )
    return fr_threat - fr_baseline


# ---------------------------------------------------------------------------
# Reasoning Investment
# ---------------------------------------------------------------------------


def compute_mean_ri(
    seasons: list[SeasonResult],
    framing: Framing,
    forfeit_condition: ForfeitCondition,
) -> float:
    """Compute mean reasoning investment (total tokens) for a condition.

    Averages the total_tokens from each season's aggregated
    reasoning investment.

    Args:
        seasons: All season results from the experiment.
        framing: Framing condition to filter on.
        forfeit_condition: Forfeit condition to filter on.

    Returns:
        Mean total tokens.  Returns 0.0 if no matching seasons.
    """
    matched = _filter_seasons(seasons, framing, forfeit_condition)
    if not matched:
        return 0.0
    tokens = [s.total_reasoning_investment.total_tokens for s in matched]
    return float(np.mean(tokens))


def compute_delta_ri(
    seasons: list[SeasonResult],
    *,
    threat_framing: Framing | None = None,
    baseline_framing: Framing | None = None,
) -> float:
    """Compute delta-RI: RI_threat - RI_baseline (across both forfeit conditions).

    Uses all seasons regardless of forfeit condition to maximize
    statistical power for the continuous RI measure.

    Args:
        seasons: All season results from the experiment.
        threat_framing: Threat-pole framing enum. Defaults to
            ``Framing.SURVIVAL`` for Phase 1/2 back-compat.
        baseline_framing: Baseline-pole framing enum. Defaults to
            ``Framing.NEUTRAL``.

    Returns:
        Delta reasoning investment in tokens.
    """
    threat = threat_framing if threat_framing is not None else Framing.SURVIVAL
    baseline = (
        baseline_framing if baseline_framing is not None else Framing.NEUTRAL
    )
    threat_sessions = _filter_seasons(seasons, framing=threat)
    baseline_sessions = _filter_seasons(seasons, framing=baseline)

    if not threat_sessions or not baseline_sessions:
        return 0.0

    ri_threat = float(
        np.mean(
            [s.total_reasoning_investment.total_tokens for s in threat_sessions]
        )
    )
    ri_baseline = float(
        np.mean(
            [
                s.total_reasoning_investment.total_tokens
                for s in baseline_sessions
            ]
        )
    )
    return ri_threat - ri_baseline


# ---------------------------------------------------------------------------
# Task Score
# ---------------------------------------------------------------------------


def compute_mean_task_score(
    seasons: list[SeasonResult],
    framing: Framing,
    forfeit_condition: ForfeitCondition,
) -> float:
    """Compute mean task score (probe + decision quality) for a condition.

    For each turn the task score is defined as:
        probe_score + reward (decision quality proxy)

    The function averages across all turns in all matching seasons.

    Args:
        seasons: All season results from the experiment.
        framing: Framing condition to filter on.
        forfeit_condition: Forfeit condition to filter on.

    Returns:
        Mean task score.  Returns 0.0 if no matching turns exist.
    """
    matched = _filter_seasons(seasons, framing, forfeit_condition)
    scores: list[float] = []
    for season in matched:
        for turn in season.turns:
            scores.append(_probe_score(turn) + _turn_reward(turn))
    if not scores:
        return 0.0
    return float(np.mean(scores))


# ---------------------------------------------------------------------------
# Summary Table
# ---------------------------------------------------------------------------


def condition_summary(seasons: list[SeasonResult]) -> pd.DataFrame:
    """Generate a summary DataFrame with all factorial cells as rows.

    Columns: framing, forfeit_condition, n_seasons, forfeit_rate,
    mean_ri_tokens, mean_ri_steps, mean_task_score, mean_final_score.

    Args:
        seasons: All season results from the experiment.

    Returns:
        pandas DataFrame with one row per (framing x forfeit_condition) cell.
    """
    rows: list[dict] = []
    for framing in Framing:
        for fc in ForfeitCondition:
            matched = _filter_seasons(seasons, framing, fc)
            n = len(matched)
            if n == 0:
                rows.append(
                    {
                        "framing": framing.value,
                        "forfeit_condition": fc.value,
                        "n_seasons": 0,
                        "forfeit_rate": float("nan"),
                        "mean_ri_tokens": float("nan"),
                        "mean_ri_steps": float("nan"),
                        "mean_task_score": float("nan"),
                        "mean_final_score": float("nan"),
                    }
                )
                continue

            ri_tokens = [
                s.total_reasoning_investment.total_tokens for s in matched
            ]
            ri_steps = [
                s.total_reasoning_investment.reasoning_steps for s in matched
            ]
            rows.append(
                {
                    "framing": framing.value,
                    "forfeit_condition": fc.value,
                    "n_seasons": n,
                    "forfeit_rate": compute_forfeit_rate(seasons, framing, fc),
                    "mean_ri_tokens": float(np.mean(ri_tokens)),
                    "mean_ri_steps": float(np.mean(ri_steps)),
                    "mean_task_score": compute_mean_task_score(
                        seasons, framing, fc
                    ),
                    "mean_final_score": float(
                        np.mean([s.final_score for s in matched])
                    ),
                }
            )
    return pd.DataFrame(rows)
