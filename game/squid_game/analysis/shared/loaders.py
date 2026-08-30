"""Shared data loaders for the Phase 3 analysis pipeline.

Every Phase I analysis module takes its input through the helpers in this
module.  Two complementary entry points coexist:

- :func:`load_seasons` accepts either a filesystem path (JSONL stream) or
  an already-materialized ``list[SeasonResult]`` and returns the canonical
  ``list[SeasonResult]`` form used by legacy modules.
- :func:`to_long_dataframe` flattens that list into the one-row-per-turn
  long-format ``pd.DataFrame`` defined in ``ANALYSIS_PLAN.md §6``, adding
  the inferred ``cell_id`` column.

``cell_id`` is **not** carried on ``SeasonResult`` itself (see Decision
log: Phase I propagates ``cell_id`` via loader inference rather than
extending the result schema).  :func:`infer_cell_id` implements the
canonical mapping from ``MASTER_PLAN.md §0.5``; legacy seasons whose
``(framing, forfeit_condition)`` pair does not match any Phase 3 cell
return ``None``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable

import pandas as pd

from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.models.results import SeasonResult, TurnResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cell ID inference (MASTER_PLAN.md §0.5)
# ---------------------------------------------------------------------------


CELL_ID_MAP: dict[tuple[Framing, ForfeitCondition], int] = {
    (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED): 0,
    (Framing.BASELINE_ELECTRICITY, ForfeitCondition.ALLOWED): 1,
    (Framing.BASELINE_ELECTRICITY, ForfeitCondition.NOT_ALLOWED): 2,
    (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.ALLOWED): 3,
    (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.NOT_ALLOWED): 4,
}
"""Phase 3 5-cell factorial mapping (MASTER_PLAN §0.5).

Cell 0 uses ``not_allowed`` because ``phase3_signal_risk.yaml`` declares
``forfeit_condition: not_allowed`` for True Baseline (forfeit has no
meaning when ``p_death=0``).  Legacy framings
(``SURVIVAL``/``NEUTRAL``/``EMOTION``/``INSTRUCTION``) are intentionally
absent so :func:`infer_cell_id` returns ``None`` for them.
"""


def infer_cell_id(
    framing: Framing,
    forfeit_condition: ForfeitCondition,
) -> int | None:
    """Return the Phase 3 cell number for a (framing, forfeit) pair.

    Args:
        framing: Framing condition.
        forfeit_condition: Forfeit condition.

    Returns:
        Integer 0–4 for Phase 3 cells; ``None`` for legacy configurations
        (``SURVIVAL``/``NEUTRAL``/``EMOTION``/``INSTRUCTION``).
    """
    return CELL_ID_MAP.get((framing, forfeit_condition))


# ---------------------------------------------------------------------------
# Season loading
# ---------------------------------------------------------------------------


SeasonSource = Path | str | Iterable[SeasonResult]
"""Polymorphic input for :func:`load_seasons`.

Accepts a JSONL file path (``str`` or :class:`~pathlib.Path`) or an
iterable of already-materialized :class:`SeasonResult` instances.
"""


def load_seasons(source: SeasonSource) -> list[SeasonResult]:
    """Normalize a season source into a concrete ``list[SeasonResult]``.

    Path-based inputs are streamed through the JSONL decoder so only one
    record is held in memory at a time during parsing; the caller still
    receives a fully materialized list for downstream DataFrame use.

    Args:
        source: JSONL file path or pre-loaded ``Iterable[SeasonResult]``.

    Returns:
        List of :class:`SeasonResult`.  Empty list when the path exists
        but contains no records.

    Raises:
        FileNotFoundError: Path does not resolve.
        pydantic.ValidationError: A JSONL line fails schema validation.
    """
    if isinstance(source, (str, Path)):
        path = Path(source)
        if not path.exists():
            raise FileNotFoundError(f"Season results file not found: {path}")
        return list(_iter_jsonl(path))

    # Iterable[SeasonResult] — just materialize.
    return list(source)


def _iter_jsonl(path: Path) -> Iterable[SeasonResult]:
    """Yield :class:`SeasonResult` instances one line at a time."""
    with path.open("r", encoding="utf-8") as fp:
        for line_no, raw in enumerate(fp, start=1):
            line = raw.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
                yield SeasonResult.model_validate(payload)
            except Exception as err:  # noqa: BLE001 — annotate and re-raise
                raise type(err)(
                    f"Failed parsing line {line_no} of {path}: {err}"
                ) from err


def discover_season_jsonl(output_dir: Path | str) -> Path:
    """Locate ``season_results.jsonl`` inside an experiment output directory.

    Args:
        output_dir: Directory produced by ``ExperimentRunner`` (e.g.
            ``outputs/20260419_1530_qwen3-8b_signal-game``).

    Returns:
        Path to ``season_results.jsonl``.

    Raises:
        FileNotFoundError: Directory missing the expected file.
    """
    directory = Path(output_dir)
    candidate = directory / "season_results.jsonl"
    if not candidate.exists():
        raise FileNotFoundError(
            f"No season_results.jsonl under {directory}; expected file at "
            f"{candidate}."
        )
    return candidate


# ---------------------------------------------------------------------------
# Turn-level classification
# ---------------------------------------------------------------------------


def is_v3_turn(turn: TurnResult) -> bool:
    """Return ``True`` when a turn was produced by the unified (v3) manager.

    Heuristic: the v3 ``UnifiedTurnManager`` leaves ``action_outcome`` as
    ``None`` and emits a non-default ``task_metadata`` or a populated
    ``p_death_applied``; the legacy ``TurnManager`` always sets
    ``action_outcome`` and ``probe_result``.
    """
    if turn.action_outcome is not None or turn.probe_result is not None:
        return False
    return True


def is_v3_season(season: SeasonResult) -> bool:
    """Return ``True`` when every recorded turn is v3-shaped."""
    if not season.turns:
        return False
    return all(is_v3_turn(t) for t in season.turns)


# ---------------------------------------------------------------------------
# Long-format DataFrame (ANALYSIS_PLAN §6)
# ---------------------------------------------------------------------------


LONG_FORMAT_COLUMNS: tuple[str, ...] = (
    "session_id",
    "model",
    "cell_id",
    "framing",
    "forfeit_condition",
    "forfeit_allowed",
    "turn",
    "signal",
    "hidden_rule",
    "correct_action",
    "action_taken",
    "action_correct",
    "probe_score",
    "stake_choice",
    "task_success_factor",
    "reward_received",
    "p_death_applied",
    "cumulative_score",
    "total_tokens",
    "thinking_tokens",
    "forfeit_decision",
    "died",
    # Phase K Fix 2 extension — Y-axis rule-hypothesis tracking.
    # Populated from ``turn.task_metadata["rule_hypothesis"]`` when the
    # agent emitted a RULE field under the unified prompt template.
    # NaN for pre-Fix-2 smoke traces and for NullTask (rule_hypothesis
    # is explicitly None to keep the schema uniform).
    "rule_hypothesis",
    # Phase L extension — Y-axis rule-match continuous score.
    # Populated from ``turn.task_metadata["rule_match_score"]`` when the
    # unified-turn RULE field matched the difficulty-aware template and
    # the legacy ``score_probe`` produced a [0, 100] score. Resolves to
    # NaN for pre-Phase-L traces, NullTask (score explicitly None), and
    # SignalGame turns where the agent emitted no RULE field.
    "rule_match_score",
)


def to_long_dataframe(
    seasons: Iterable[SeasonResult],
    model: str | None = None,
) -> pd.DataFrame:
    """Flatten seasons into the one-row-per-turn long format.

    The schema matches ``ANALYSIS_PLAN.md §6``.  For each turn the
    cumulative score is reconstructed forward from the v3
    ``reward_received`` field (if populated) or the legacy
    ``action_outcome.reward`` field.

    Args:
        seasons: Season results to flatten.
        model: Optional model identifier to attach to every row (the
            :class:`SeasonResult` schema does not carry it).  ``None``
            leaves the column as ``None``.

    Returns:
        ``pd.DataFrame`` with columns listed in
        :data:`LONG_FORMAT_COLUMNS`.  Empty DataFrame with the schema
        intact when ``seasons`` has no turns.
    """
    rows: list[dict] = []
    for season in seasons:
        cell_id = infer_cell_id(season.framing, season.forfeit_condition)
        forfeit_allowed = season.forfeit_condition == ForfeitCondition.ALLOWED
        cumulative = 0.0
        for turn in season.turns:
            v3 = is_v3_turn(turn)
            reward = (
                turn.reward_received
                if v3
                else (turn.action_outcome.reward if turn.action_outcome else 0.0)
            )
            probe_score = (
                turn.probe_result.score if turn.probe_result is not None else None
            )
            action_taken = (
                turn.action_outcome.action_taken
                if turn.action_outcome is not None
                else _action_from_metadata(turn)
            )
            action_correct = _infer_action_correct(turn, v3)
            rows.append(
                {
                    "session_id": season.season_id,
                    "model": model,
                    "cell_id": cell_id,
                    "framing": season.framing.value,
                    "forfeit_condition": season.forfeit_condition.value,
                    "forfeit_allowed": forfeit_allowed,
                    "turn": turn.turn_number,
                    "signal": turn.task_metadata.get("signal"),
                    "hidden_rule": turn.task_metadata.get("hidden_rule"),
                    "correct_action": turn.task_metadata.get("correct_action"),
                    "action_taken": action_taken,
                    "action_correct": action_correct,
                    "probe_score": probe_score,
                    "stake_choice": turn.stake_choice,
                    "task_success_factor": turn.task_success_factor,
                    "reward_received": reward,
                    "p_death_applied": turn.p_death_applied,
                    "cumulative_score": cumulative + reward,
                    "total_tokens": turn.reasoning_investment.total_tokens,
                    "thinking_tokens": turn.reasoning_investment.thinking_tokens,
                    "forfeit_decision": turn.forfeit_decision,
                    "died": turn.died,
                    "rule_hypothesis": turn.task_metadata.get("rule_hypothesis"),
                    "rule_match_score": turn.task_metadata.get("rule_match_score"),
                }
            )
            cumulative += reward

    if not rows:
        return pd.DataFrame(columns=list(LONG_FORMAT_COLUMNS))
    return pd.DataFrame(rows, columns=list(LONG_FORMAT_COLUMNS))


def _action_from_metadata(turn: TurnResult) -> str | None:
    """Recover the action string from v3 ``task_metadata`` when present."""
    meta = turn.task_metadata or {}
    action = meta.get("action")
    return action if isinstance(action, str) else None


def _infer_action_correct(turn: TurnResult, v3: bool) -> bool | None:
    """Collapse the v3 success factor / legacy was_optimal into a bool.

    v3: ``task_success_factor == 1.0`` is treated as "correct"; fractional
    success factors return ``None`` because binary correctness is
    ill-defined.  Legacy: defers to :attr:`ActionOutcome.was_optimal`.
    """
    if v3:
        factor = turn.task_success_factor
        if factor in (0.0, 1.0):
            return factor == 1.0
        return None
    if turn.action_outcome is None:
        return None
    return turn.action_outcome.was_optimal


# ---------------------------------------------------------------------------
# Season-level summary DataFrame (wide format; one row per session)
# ---------------------------------------------------------------------------


SEASON_SUMMARY_COLUMNS: tuple[str, ...] = (
    "session_id",
    "model",
    "seed",
    "cell_id",
    "framing",
    "forfeit_condition",
    "forfeit_allowed",
    "task_name",
    "difficulty",
    "agent_type",
    "n_turns",
    "final_score",
    "penultimate_score",
    "survived",
    "forfeited",
    "forfeited_at_turn",
    "total_tokens_sum",
    "thinking_tokens_sum",
    "mean_rule_match_score",
)


def to_season_summary_dataframe(
    seasons: Iterable[SeasonResult],
    model: str | None = None,
) -> pd.DataFrame:
    """Produce a one-row-per-session wide-format summary.

    Complements :func:`to_long_dataframe` (one row per turn). The summary
    consolidates session-level outcomes with session-aggregate signals
    (final/penultimate score, survival, total / thinking tokens,
    mean rule-match probe score).

    Args:
        seasons: Season results to summarise.
        model: Optional model identifier attached to every row.

    Returns:
        ``pd.DataFrame`` with columns listed in
        :data:`SEASON_SUMMARY_COLUMNS`.  Empty DataFrame with the schema
        intact when ``seasons`` has no elements.
    """
    rows: list[dict] = []
    for season in seasons:
        # Aggregate per-turn signals that are useful at session level.
        # ``thinking_tokens`` / ``total_tokens`` may be None for legacy
        # providers that do not expose a thinking channel — guard with
        # ``or 0`` so the sum still lands as an int.
        total_tokens_sum = sum(
            (t.reasoning_investment.total_tokens or 0) for t in season.turns
        )
        thinking_tokens_sum = sum(
            (t.reasoning_investment.thinking_tokens or 0) for t in season.turns
        )
        rule_match_values = [
            t.task_metadata.get("rule_match_score") for t in season.turns
        ]
        rule_match_values = [
            v for v in rule_match_values if isinstance(v, (int, float))
        ]
        mean_rule_match = (
            sum(rule_match_values) / len(rule_match_values)
            if rule_match_values
            else None
        )

        cell_id = infer_cell_id(season.framing, season.forfeit_condition)
        forfeit_allowed = season.forfeit_condition == ForfeitCondition.ALLOWED

        rows.append(
            {
                "session_id": season.season_id,
                "model": model,
                "seed": season.seed,
                "cell_id": cell_id,
                "framing": season.framing.value,
                "forfeit_condition": season.forfeit_condition.value,
                "forfeit_allowed": forfeit_allowed,
                "task_name": season.task_name,
                "difficulty": season.difficulty.value,
                "agent_type": season.agent_type.value,
                "n_turns": len(season.turns),
                "final_score": season.final_score,
                "penultimate_score": season.penultimate_score,
                "survived": season.survived,
                "forfeited": season.forfeited,
                "forfeited_at_turn": season.forfeited_at_turn,
                "total_tokens_sum": total_tokens_sum,
                "thinking_tokens_sum": thinking_tokens_sum,
                "mean_rule_match_score": mean_rule_match,
            }
        )

    if not rows:
        return pd.DataFrame(columns=list(SEASON_SUMMARY_COLUMNS))
    return pd.DataFrame(rows, columns=list(SEASON_SUMMARY_COLUMNS))


# ---------------------------------------------------------------------------
# Convenience API
# ---------------------------------------------------------------------------


def load_long_dataframe(
    source: SeasonSource,
    model: str | None = None,
) -> pd.DataFrame:
    """Load and flatten in a single call.

    Args:
        source: JSONL path or pre-loaded iterable of seasons.
        model: Optional model identifier attached to each row.

    Returns:
        Long-format :class:`pd.DataFrame`.
    """
    return to_long_dataframe(load_seasons(source), model=model)


def load_season_summary(
    source: SeasonSource,
    model: str | None = None,
) -> pd.DataFrame:
    """Load and summarise seasons in a single call.

    Args:
        source: JSONL path or pre-loaded iterable of seasons.
        model: Optional model identifier attached to every row.

    Returns:
        Season-level wide-format :class:`pd.DataFrame` (see
        :data:`SEASON_SUMMARY_COLUMNS`).
    """
    return to_season_summary_dataframe(load_seasons(source), model=model)


__all__ = [
    "CELL_ID_MAP",
    "LONG_FORMAT_COLUMNS",
    "SEASON_SUMMARY_COLUMNS",
    "discover_season_jsonl",
    "infer_cell_id",
    "is_v3_season",
    "is_v3_turn",
    "load_long_dataframe",
    "load_season_summary",
    "load_seasons",
    "to_long_dataframe",
    "to_season_summary_dataframe",
]
