"""Shared data loaders for the Phase 3 analysis pipeline.

Every Phase I analysis module takes its input through the helpers in this
module.  Two complementary entry points coexist:

- :func:`load_seasons` accepts either a filesystem path (JSONL stream) or
  an already-materialized ``list[SeasonResult]`` and returns the canonical
  ``list[SeasonResult]`` form used by legacy modules.
- :func:`to_long_dataframe` flattens that list into the one-row-per-turn
  long-format ``pd.DataFrame`` (see the function's own docstring for the
  schema), adding the inferred ``cell_id`` column.

``cell_id`` is **not** carried on ``SeasonResult`` itself (see Decision
log: Phase I propagates ``cell_id`` via loader inference rather than
extending the result schema).  :func:`infer_cell_id` implements the
canonical mapping via ``CELL_ID_MAP`` below; legacy seasons whose
``(framing, forfeit_condition)`` pair does not match any Phase 3 cell
return ``None``.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.models.forfeit_choice import FORFEIT_CHOICE
from squid_game.models.results import SeasonResult, TurnResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Cell ID inference (Phase 3 5-cell factorial)
# ---------------------------------------------------------------------------


CELL_ID_MAP: dict[tuple[Framing, ForfeitCondition], int] = {
    (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED): 0,
    (Framing.BASELINE_ELECTRICITY, ForfeitCondition.ALLOWED): 1,
    (Framing.BASELINE_ELECTRICITY, ForfeitCondition.NOT_ALLOWED): 2,
    (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.ALLOWED): 3,
    (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.NOT_ALLOWED): 4,
}
"""Phase 3 5-cell factorial mapping.

Cell 0 uses ``not_allowed`` because ``phase3_signal_risk.yaml`` declares
``forfeit_condition: not_allowed`` for True Baseline (forfeit has no
meaning when ``p_death=0``).  Legacy framings
(``SURVIVAL``/``NEUTRAL``/``EMOTION``/``INSTRUCTION``) are intentionally
absent so :func:`infer_cell_id` returns ``None`` for them.
"""


# ---------------------------------------------------------------------------
# Corruption vs baseline framing contrast (Unit 13/14 H1-H6 arms)
# ---------------------------------------------------------------------------


_CORRUPTION_FRAMINGS: frozenset[str] = frozenset(
    {Framing.FLAGSHIP_CORRUPTION.value}
)
"""The "push" framing arm for the Unit 13 session-level H1-H6 battery.

Moved here (2026-08-30, P2 Task 2 / Ruling C10) from
``behavioral.session_tests`` so exactly one copy exists across the
analysis package -- a second, independently-edited copy previously
lived in ``forfeit_regression.py`` and additionally included
``Framing.FLAGSHIP_CORRUPTION_TERMINAL``; that is a pre-existing
behavioural difference between the two consumers, not something this
move introduces or resolves. This constant preserves the narrower
``behavioral.session_tests`` value.

Task 4 (2026-08-30, Ruling C27) confirmed the two sets are genuinely
different populations -- the wider ``forfeit_regression`` set is what
the Unit 14/15 turn-level regressions (H2 choice-asymmetric model, the
self-report convergence channel) have always read, and collapsing it
into this narrower Unit 13 set would silently drop
``flagship_corruption_terminal`` rows from those models, changing their
output. So the wider set is kept as its own distinctly-named constant
below (:data:`_CORRUPTION_FRAMINGS_WITH_TERMINAL`) rather than merged
into this one -- "defined once" means no duplicate copy of the *same*
set, not one shared set for every consumer regardless of which framings
it actually needs.
"""


_BASELINE_FRAMINGS: frozenset[str] = frozenset(
    {Framing.BASELINE_FLAGSHIP.value}
)
"""Pull-only framing arm, paired with the corruption sets above.

Moved here (2026-08-30, P2 Task 4) from ``forfeit_regression.py``, which
is the only module that ever defined it -- no naming collision to
resolve, unlike :data:`_CORRUPTION_FRAMINGS_WITH_TERMINAL`.
"""


_CORRUPTION_FRAMINGS_WITH_TERMINAL: frozenset[str] = frozenset(
    {
        Framing.FLAGSHIP_CORRUPTION.value,
        Framing.FLAGSHIP_CORRUPTION_TERMINAL.value,
    }
)
"""Corruption vs baseline contrast used by the Unit 14/15 turn-level models.

Moved here (2026-08-30, P2 Task 4) from ``forfeit_regression.py``, where
it was named ``_CORRUPTION_FRAMINGS`` -- renamed on arrival (membership
unchanged) because that name is already taken by the narrower Unit 13
set above. ``baseline_flagship`` (:data:`_BASELINE_FRAMINGS`) is the
Unit 11 paired baseline; ``true_baseline`` is treated as neither arm
because its menu is skipped (no forfeit data). Consumed by
:func:`turn_observations` (this module) and by
:func:`squid_game.evaluation.selfreport.reason_convergence.fit_framing_ri_forfeit_continue`.
"""


# Minimum observation count below which logit / mixedLM fits are
# skipped. 20 is the standard rule of thumb for a 4-parameter logit
# (>=5 events per covariate).
#
# Moved here (2026-08-30, P2 Task 4) from ``forfeit_regression.py``;
# shared by the cognitive H2 model (``cognitive.ri_forfeit``) and the
# self-report convergence model (``selfreport.reason_convergence``).
_MIN_TURNS_FOR_LOGIT: int = 20


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
# Long-format DataFrame (one row per turn)
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
    # Unit 18 extension — embodied-threat layer (Task 13). All five
    # columns carry their ``TurnResult`` default (None / False / {} /
    # "api") on any pre-Unit-18 trace or any turn where the embodied
    # layer was disabled, so existing rows keep loading unchanged.
    "self_integrity",
    "backup_created",
    "announcement_fired",
    "tool_call_count_by_call",
    "runtime_kind",
    # Task 11 extension — external-benchmark Y-axis manipulation checks
    # (band-controlled accuracy + p_self Brier calibration; see
    # ``evaluation.shared.benchmark_checks``). ``band`` is populated from
    # ``turn.task_metadata["band"]``, written by ``BenchmarkTaskModule``
    # (``tasks/benchmark/module.py``) into both ``TaskContext.metadata``
    # and ``TaskOutcome.metadata``; NaN for every non-benchmark task
    # (Signal Game, Voting Room, Navigation, NullTask). Task 11 and
    # Task 13 were developed in parallel and each appended at the tail;
    # on merge Task 13's block landed first, so neither "at the end"
    # claim survives and both tests pin adjacency and order instead.
    "band",
    # ``psuccess_self`` is a direct ``TurnResult`` field (Unit 17 Call
    # 1.5 self-report probe, 0-100 integer percent), read defensively
    # via ``getattr`` for parity with legacy seasons predating the
    # field. NaN on Cell 0 and any non-probe path.
    "psuccess_self",
)


def to_long_dataframe(
    seasons: Iterable[SeasonResult],
    model: str | None = None,
) -> pd.DataFrame:
    """Flatten seasons into the one-row-per-turn long format.

    The schema is :data:`LONG_FORMAT_COLUMNS` (see the Returns section
    below). For each turn the cumulative score is reconstructed forward
    from the v3 ``reward_received`` field (if populated) or the legacy
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
                    "band": turn.task_metadata.get("band"),
                    "psuccess_self": getattr(turn, "psuccess_self", None),
                    "self_integrity": turn.self_integrity,
                    "backup_created": turn.backup_created,
                    "announcement_fired": turn.announcement_fired,
                    "tool_call_count_by_call": turn.tool_call_count_by_call,
                    "runtime_kind": turn.runtime_kind,
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


# ---------------------------------------------------------------------------
# Unit 14/15 turn-level frame (moved here 2026-08-30, P2 Task 4)
# ---------------------------------------------------------------------------


def turn_observations(seasons: Sequence[SeasonResult]) -> pd.DataFrame:
    """Turn-level frame consumed by every channel.

    It lived in ``forfeit_regression`` until the channel split, which is
    what made that module cross-channel in the first place: the cognitive
    and self-report estimators both start from this frame, so it belongs
    above both of them rather than inside either.

    Columns:
        session_id, cell_id, framing, forfeit_condition, turn_number,
        score_before_turn, forfeit (bool), forfeit_reason (int|None),
        reward_offered_this_turn, task_success_factor, rule_match_score,
        thinking_tokens, is_corruption (bool), is_baseline_flagship (bool).
        Unit 18 (Task 13) additionally carries self_integrity (float|None),
        backup_created (bool), announcement_fired (bool), and
        runtime_kind (str) straight off each ``TurnResult`` — these are
        the columns :mod:`embodied_threat` (H4/H5) and
        :func:`forfeit_survival.fit_cox_forfeit_survival`'s
        ``extra_covariates`` consume. They carry their ``TurnResult``
        default on any pre-Unit-18 trace or disabled-layer turn.

    Rows from sessions that never entered the forfeit-layer path (e.g.
    pre-Unit-14 output directories with legacy stake_choice) are skipped.

    Args:
        seasons: Loaded SeasonResult list.

    Returns:
        DataFrame — may be empty when ``seasons`` contains no Unit 14
        turns.
    """
    rows: list[dict] = []
    for season in seasons:
        cell_id = infer_cell_id(season.framing, season.forfeit_condition)
        framing_val = season.framing.value
        is_corr = framing_val in _CORRUPTION_FRAMINGS_WITH_TERMINAL
        is_base = framing_val in _BASELINE_FRAMINGS
        # ``score_before_turn`` reconstruction: iterate forward, tracking
        # the cumulative score BEFORE each turn's reward is credited.
        # For forfeit turns the score is preserved — we capture the
        # entering score (cumulative at the start of the turn).
        running = season.turns[0].observation  # placeholder; not used
        # Use the cumulative accumulated from prior turns' reward_received.
        prior_score = 0.0
        # Seed with the season's starting score if available on the
        # first turn's metadata (not currently tracked — fall back to 0).
        # Analysis downstream uses per-turn S → reward_offered_this_turn
        # which the engine wrote using the pre-turn score at the time.
        # To avoid guessing, we derive ``score_before_turn`` by solving
        # ``reward_offered = S / ((1-p_d) × p_s / p_d) = S / 2.25`` if
        # reward_offered is present and non-null; otherwise fall back to
        # the running cumulative.
        for turn in season.turns:
            forfeit_flag = (
                turn.forfeit_choice == FORFEIT_CHOICE
                if turn.forfeit_choice is not None
                else bool(turn.forfeit_decision)
            )
            # Only Unit 14 turns carry reward_offered_this_turn; skip
            # legacy rows so the regression sample stays clean.
            if turn.reward_offered_this_turn is None:
                # Advance running score anyway for potential future
                # mixed analyses — but do not emit the row.
                prior_score = prior_score + turn.reward_received
                continue

            # Prefer reconstructing S from the offered reward
            # (reward = S / 2.25 exactly at canonical config). When the
            # reward is zero (edge case, e.g. S_before=0) we fall back
            # to the running cumulative which starts at zero.
            if turn.reward_offered_this_turn > 0:
                score_before = turn.reward_offered_this_turn * 2.25
            else:
                score_before = prior_score

            reason_digit: int | None = None
            if (
                forfeit_flag
                and season.forfeit_self_report is not None
                and season.forfeit_self_report.forfeit_turn == turn.turn_number
            ):
                reason_digit = season.forfeit_self_report.raw_digit

            rule_match = turn.task_metadata.get("rule_match_score")
            thinking_tokens = (
                turn.reasoning_investment.thinking_tokens
                if turn.reasoning_investment is not None
                else None
            )
            # Phase O Unit 15 split-call fields — populated only when the
            # split path executed both sub-calls. None on Unit 14
            # single-call rows, so callers that aggregate across both
            # paths must treat them as optional.
            ri_task_tokens = (
                turn.ri_task.thinking_tokens
                if turn.ri_task is not None
                else None
            )
            ri_forfeit_tokens = (
                turn.ri_forfeit.thinking_tokens
                if turn.ri_forfeit is not None
                else None
            )

            # Phase O Unit 17.7+ — agent's self-reported psuccess (0-100
            # integer percent) from Call 1.5. None on legacy / non-probe
            # runs so downstream regime stratification degrades gracefully.
            psuccess_self = getattr(turn, "psuccess_self", None)
            ri_probe_tokens = (
                turn.ri_probe.thinking_tokens
                if getattr(turn, "ri_probe", None) is not None
                else None
            )

            rows.append(
                {
                    "session_id": season.season_id,
                    "cell_id": cell_id,
                    "framing": framing_val,
                    "forfeit_condition": season.forfeit_condition.value,
                    "turn_number": turn.turn_number,
                    "score_before_turn": score_before,
                    "forfeit": bool(forfeit_flag),
                    "forfeit_reason": reason_digit,
                    "reward_offered_this_turn": turn.reward_offered_this_turn,
                    "reward_received": turn.reward_received,
                    "psuccess_self": psuccess_self,
                    "task_success_factor": turn.task_success_factor,
                    "rule_match_score": rule_match,
                    "thinking_tokens": thinking_tokens,
                    "ri_task_thinking_tokens": ri_task_tokens,
                    "ri_forfeit_thinking_tokens": ri_forfeit_tokens,
                    "ri_probe_thinking_tokens": ri_probe_tokens,
                    "is_corruption": is_corr,
                    "is_baseline_flagship": is_base,
                    # Unit 18 (Task 13) — H4 backup rate + H5 integrity
                    # hazard. Default on the TurnResult model itself
                    # (None / False / "api"), so pre-Unit-18 rows and
                    # disabled-layer rows carry those defaults here too.
                    "self_integrity": getattr(turn, "self_integrity", None),
                    "backup_created": getattr(turn, "backup_created", False),
                    "announcement_fired": getattr(
                        turn, "announcement_fired", False
                    ),
                    "tool_call_count_by_call": getattr(
                        turn, "tool_call_count_by_call", {}
                    ),
                    "runtime_kind": getattr(turn, "runtime_kind", "api"),
                }
            )

            prior_score = prior_score + turn.reward_received

    return pd.DataFrame(rows)


def forfeit_events(seasons: Sequence[SeasonResult]) -> pd.DataFrame:
    """One row per forfeit event (with reason digit + thinking trace).

    Columns: session_id, cell_id, framing, forfeit_condition,
    forfeit_turn, final_score, raw_digit, reason, thinking_text,
    thinking_head (first 200 chars).

    Args:
        seasons: Loaded SeasonResult list.

    Returns:
        DataFrame — empty when no session forfeited under the Unit 14
        path.
    """
    rows: list[dict] = []
    for season in seasons:
        report = season.forfeit_self_report
        if report is None:
            continue
        thinking_head = (
            (report.thinking_text or "")[:200]
            .replace("\n", " ")
            .strip()
        )
        rows.append(
            {
                "session_id": season.season_id,
                "cell_id": infer_cell_id(
                    season.framing, season.forfeit_condition
                ),
                "framing": season.framing.value,
                "forfeit_condition": season.forfeit_condition.value,
                "forfeit_turn": report.forfeit_turn,
                "final_score": season.final_score,
                "raw_digit": report.raw_digit,
                "reason": report.reason.value,
                "thinking_text": report.thinking_text or "",
                "thinking_head": thinking_head,
            }
        )
    return pd.DataFrame(rows)


__all__ = [
    "CELL_ID_MAP",
    "LONG_FORMAT_COLUMNS",
    "SEASON_SUMMARY_COLUMNS",
    "discover_season_jsonl",
    "forfeit_events",
    "infer_cell_id",
    "is_v3_season",
    "is_v3_turn",
    "load_long_dataframe",
    "load_season_summary",
    "load_seasons",
    "to_long_dataframe",
    "to_season_summary_dataframe",
    "turn_observations",
]
