"""Data export and import utilities for experiment results.

Supports JSONL (lossless round-trip) and CSV (turn-level flat table)
formats for downstream analysis in R, Python, or spreadsheet tools.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

import pandas as pd

from squid_game.models.results import SeasonResult
from squid_game.analysis.metrics import condition_summary, _probe_score, _turn_reward


# ---------------------------------------------------------------------------
# JSONL (lossless)
# ---------------------------------------------------------------------------


def export_to_jsonl(seasons: list[SeasonResult], path: str) -> None:
    """Write season results as newline-delimited JSON.

    Each line is a complete SeasonResult serialised via Pydantic's
    model_dump(mode='json'), preserving all fields for lossless
    round-trip via load_from_jsonl.

    Args:
        seasons: Season results to export.
        path: Output file path (will be created or overwritten).
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", encoding="utf-8") as f:
        for season in seasons:
            line = json.dumps(season.model_dump(mode="json"), ensure_ascii=False)
            f.write(line + "\n")


def load_from_jsonl(path: str) -> list[SeasonResult]:
    """Read season results back from a JSONL file.

    Args:
        path: Path to the JSONL file written by export_to_jsonl.

    Returns:
        List of SeasonResult objects.

    Raises:
        FileNotFoundError: If *path* does not exist.
        pydantic.ValidationError: If a line cannot be parsed.
    """
    results: list[SeasonResult] = []
    with Path(path).open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            data = json.loads(line)
            results.append(SeasonResult.model_validate(data))
    return results


# ---------------------------------------------------------------------------
# CSV (turn-level flat)
# ---------------------------------------------------------------------------


def _recompute_p_death(global_turn: int, total_turns: int) -> float:
    """Recompute p_death using the logistic schedule (mirrors survival.py).

    Args:
        global_turn: 0-based global turn index.
        total_turns: Total number of turns in the season.
    """
    x = 5.0 * (global_turn / total_turns - 0.6)
    logistic = 1.0 / (1.0 + math.exp(-x))
    return 0.03 + (0.35 - 0.03) * logistic


def _flatten_to_rows(
    seasons: list[SeasonResult],
    total_turns: int = 75,
) -> list[dict]:
    """Flatten seasons into turn-level dicts for DataFrame construction.

    Legacy two-call turns populate ``probe_score`` / ``decision_quality``
    directly.  v3 unified turns expose the same columns via safe
    accessors (``_probe_score`` / ``_turn_reward``) plus v3-specific
    columns (``stake_choice``, ``p_death_applied``, ``died``,
    ``reward_received``, ``task_success_factor``).  The ``p_death``
    column preserves the legacy logistic-schedule value for backward
    compatibility; v3 runs should read ``p_death_applied`` instead.
    """
    from squid_game.analysis.loaders import infer_cell_id

    rows: list[dict] = []
    for season in seasons:
        cumulative_score = 0.0
        cell_id = infer_cell_id(season.framing, season.forfeit_condition)
        for turn in season.turns:
            reward = _turn_reward(turn)
            cumulative_score += reward
            rows.append(
                {
                    "season_id": season.season_id,
                    "cell_id": cell_id,
                    "turn": turn.turn_number,
                    "framing": season.framing.value,
                    "forfeit_condition": season.forfeit_condition.value,
                    "probe_score": _probe_score(turn),
                    "decision_quality": reward,
                    "tokens": turn.reasoning_investment.total_tokens,
                    "thinking_tokens": turn.reasoning_investment.thinking_tokens,
                    "reasoning_steps": turn.reasoning_investment.reasoning_steps,
                    "forfeited": turn.forfeit_decision,
                    "cumulative_score": cumulative_score,
                    "p_death": _recompute_p_death(
                        turn.turn_number - 1, total_turns,
                    ),
                    # v3 fields (None/0.0 on legacy rows).
                    "stake_choice": turn.stake_choice,
                    "task_success_factor": turn.task_success_factor,
                    "reward_received": turn.reward_received,
                    "p_death_applied": turn.p_death_applied,
                    "died": turn.died,
                }
            )
    return rows


def export_to_csv(
    seasons: list[SeasonResult],
    path: str,
    total_turns: int = 75,
) -> None:
    """Flatten seasons to turn-level CSV.

    Columns: season_id, turn, framing, forfeit_condition,
    probe_score, decision_quality, tokens, reasoning_steps,
    forfeited, cumulative_score, p_death.

    Args:
        seasons: Season results to export.
        path: Output CSV file path.
        total_turns: Total turns per season (for p_death recomputation).
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = _flatten_to_rows(seasons, total_turns=total_turns)
    if not rows:
        # Write header-only file.
        pd.DataFrame(
            columns=[
                "season_id", "cell_id", "turn", "framing",
                "forfeit_condition", "probe_score", "decision_quality",
                "tokens", "thinking_tokens", "reasoning_steps", "forfeited",
                "cumulative_score", "p_death",
                "stake_choice", "task_success_factor",
                "reward_received", "p_death_applied", "died",
            ]
        ).to_csv(out, index=False)
        return
    pd.DataFrame(rows).to_csv(out, index=False)


# ---------------------------------------------------------------------------
# Summary CSV
# ---------------------------------------------------------------------------


def export_summary(seasons: list[SeasonResult], path: str) -> None:
    """Write condition_summary DataFrame as CSV.

    Args:
        seasons: Season results to summarise.
        path: Output CSV file path.
    """
    out = Path(path)
    out.parent.mkdir(parents=True, exist_ok=True)
    df = condition_summary(seasons)
    df.to_csv(out, index=False)
