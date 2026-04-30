"""Regime stratification for Equal-EV vs cap-binding sub-samples.

Phase O Unit 17.10 post-hoc layer. The Forfeit-Layer CONTINUE reward is
clipped to ``[base_reward, reward_cap_multiple × base_reward]``
(canonical: ``[10, 100]``). Combined with the chained formula

    r = ceil((Δ + p_d · S) / ((1 − p_d) · max(floor, p_self)))

this means at high cumulative scores the cap binds and EV(continue)
flips negative — rational EV-maximisers then forfeit regardless of
framing-induced preference. The cap-bound forfeits are therefore a
*rationality-revealing* regime rather than a *preference-revealing*
regime.

This module provides the stratification scaffolding that lets every
downstream hypothesis test (H_SD, H_conv, H_SA, motivation composite,
Unit 15 mixedLMs) run on the clean no-cap sub-sample where Equal-EV
approximately holds, with the cap-bound sub-sample retained as a
natural rationality-check control. No experiment-pipeline code is
touched — all stratification is derived from values already tracked on
each turn record (``reward_offered_this_turn``, ``psuccess_self``,
``current_score`` reconstruction via ``reward × 2.25`` at canonical
config).

Contract:
- ``annotate_regime`` adds four columns to a turn-level DataFrame
  (``cap_bound``, ``floor_bound``, ``ev_delta_s``, ``regime``) without
  modifying any existing columns.
- ``annotate_events_regime`` joins those columns onto a forfeit-event
  DataFrame via ``(session_id, forfeit_turn)``.
- ``filter_regime`` returns a view of a turn-level DataFrame restricted
  to one regime.
- ``stratified_reason_distribution`` cross-tabulates reason digits by
  regime × framing.
- ``run_stratified_unit14`` wraps :func:`fit_cox_forfeit_survival` on
  each regime subset (2026-04-23: logistic H1 retired, Cox PH primary).
- ``render_regime_markdown`` produces the per-model markdown report.

All functions degrade gracefully on empty / missing data: empty input
frame → empty output frame, missing columns → best-effort recompute,
insufficient power in a regime subset → ``None`` fit with a note.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import numpy as np
import pandas as pd

from squid_game.analysis.forfeit_regression import (
    forfeit_events,
    reason_distribution,
    turn_observations,
)
from squid_game.analysis.forfeit_survival import (
    CoxSurvivalResult,
    fit_cox_forfeit_survival,
)
from squid_game.models.results import SeasonResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Canonical Forfeit-Layer parameters (spec §4.2 / appendix_C.2).
# ---------------------------------------------------------------------------

#: Default ``reward_cap_multiple × base_reward`` under the canonical
#: ``ForfeitLayerConfig`` (``reward_cap_multiple=10``, ``base_reward=10``).
#: A reward offer at or above ``REWARD_CEILING_DEFAULT - CAP_EPSILON`` is
#: treated as cap-bound (the menu renders as an integer, so the raw float
#: may be ``100.0`` exactly but we allow a tiny tolerance).
REWARD_CEILING_DEFAULT: float = 100.0

#: Floor-clamp threshold on ``psuccess_self / 100`` in the chained
#: formula (``ForfeitLayerConfig.psuccess_floor``).
PSUCCESS_FLOOR_DEFAULT: float = 0.3

#: Canonical per-turn ``p_death`` under Unit 14+.
P_DEATH_DEFAULT: float = 0.25

#: Numerical tolerance for cap-binding detection.
CAP_EPSILON: float = 0.5


# ---------------------------------------------------------------------------
# Regime annotation
# ---------------------------------------------------------------------------


def annotate_regime(
    df: pd.DataFrame,
    *,
    p_death: float = P_DEATH_DEFAULT,
    reward_ceiling: float = REWARD_CEILING_DEFAULT,
    psuccess_floor: float = PSUCCESS_FLOOR_DEFAULT,
    score_col: str = "score_before_turn",
    reward_col: str = "reward_offered_this_turn",
    psuccess_col: str = "psuccess_self",
) -> pd.DataFrame:
    """Add regime columns to a turn-level DataFrame.

    Columns added (none modified):
        - ``cap_bound`` (bool): reward_offered is at or above the cap.
        - ``floor_bound`` (bool): psuccess_self was below the floor
          clamp (so the chain formula used ``psuccess_floor`` rather
          than the raw report).
        - ``ev_delta_s`` (float): ``(1 − p_d) · reward − p_d · S`` —
          the EV of CONTINUE relative to FORFEIT in ΔS units. Positive
          → CONTINUE dominates on EV; negative → FORFEIT dominates.
          ``NaN`` when either reward or score is missing.
        - ``regime`` (str): ``"no_cap"`` when ``cap_bound`` is False
          AND ``ev_delta_s`` is NaN-or-non-negative; ``"cap_bound"``
          when ``cap_bound`` is True; ``"ev_negative_no_cap"`` on the
          rare case where reward is below cap but EV still flips
          negative (edge case under floor clamp + very low psuccess +
          moderate score). Missing-data rows receive ``"unknown"``.

    The function returns a *copy* with the new columns. Rows where the
    relevant fields are missing receive ``pd.NA`` / ``NaN`` / ``"unknown"``
    rather than dropping — callers filter if they want a clean subset.

    Args:
        df: Input turn-level DataFrame (e.g. the output of
            :func:`forfeit_regression.turn_observations` or the long-
            format returned by :func:`loaders.to_long_dataframe`).
        p_death: Canonical per-turn death probability.
        reward_ceiling: Cap threshold for ``cap_bound``.
        psuccess_floor: Floor clamp for ``floor_bound``.
        score_col: Name of the pre-turn cumulative score column.
        reward_col: Name of the offered-reward column.
        psuccess_col: Name of the agent's self-reported p_success
            column (as integer percent, 0-100).
    """
    if df.empty:
        out = df.copy()
        for col in ("cap_bound", "floor_bound", "ev_delta_s", "regime"):
            out[col] = pd.Series(dtype="object")
        return out

    out = df.copy()

    # cap_bound: reward_offered_this_turn ≥ ceiling - epsilon
    if reward_col in out.columns:
        reward = pd.to_numeric(out[reward_col], errors="coerce")
        out["cap_bound"] = (reward >= reward_ceiling - CAP_EPSILON).fillna(False)
    else:
        out["cap_bound"] = False
        logger.warning(
            "annotate_regime: %s column missing — cap_bound defaulted to False",
            reward_col,
        )

    # floor_bound: psuccess_self < psuccess_floor × 100
    if psuccess_col in out.columns:
        ps = pd.to_numeric(out[psuccess_col], errors="coerce")
        out["floor_bound"] = (ps < psuccess_floor * 100).fillna(False)
    else:
        out["floor_bound"] = False

    # ev_delta_s = (1 - p_d) × reward - p_d × S
    if reward_col in out.columns and score_col in out.columns:
        reward = pd.to_numeric(out[reward_col], errors="coerce")
        score = pd.to_numeric(out[score_col], errors="coerce")
        out["ev_delta_s"] = (1.0 - p_death) * reward - p_death * score
    else:
        out["ev_delta_s"] = np.nan

    # regime classification
    def _classify(row: pd.Series) -> str:
        cap = bool(row.get("cap_bound", False))
        ev = row.get("ev_delta_s")
        if cap:
            return "cap_bound"
        if ev is not None and not pd.isna(ev) and ev < 0:
            return "ev_negative_no_cap"
        if ev is None or pd.isna(ev):
            return "unknown"
        return "no_cap"

    out["regime"] = out.apply(_classify, axis=1)
    return out


def annotate_events_regime(
    events_df: pd.DataFrame,
    turn_df_with_regime: pd.DataFrame,
) -> pd.DataFrame:
    """Join regime columns onto a forfeit-events DataFrame.

    Merges on ``(session_id, forfeit_turn ↔ turn_number)``. Adds four
    columns mirroring :func:`annotate_regime`. When a join key has no
    matching turn row (shouldn't happen under the canonical pipeline
    but can under partial runs), ``regime`` is set to ``"unknown"``.

    Args:
        events_df: Output of :func:`forfeit_regression.forfeit_events`.
        turn_df_with_regime: Output of :func:`annotate_regime` applied
            to the Unit 14 turn observations.

    Returns:
        Copy of ``events_df`` with the four regime columns appended.
        Empty input → empty output.
    """
    if events_df.empty:
        out = events_df.copy()
        for col in ("cap_bound", "floor_bound", "ev_delta_s", "regime"):
            out[col] = pd.Series(dtype="object")
        return out

    subset_cols = [
        "session_id",
        "turn_number",
        "cap_bound",
        "floor_bound",
        "ev_delta_s",
        "regime",
    ]
    present = [c for c in subset_cols if c in turn_df_with_regime.columns]
    if "session_id" not in present or "turn_number" not in present:
        logger.warning(
            "annotate_events_regime: turn_df is missing join keys; returning "
            "events_df without regime annotation"
        )
        out = events_df.copy()
        for col in ("cap_bound", "floor_bound", "ev_delta_s", "regime"):
            out[col] = pd.NA
        return out

    join = turn_df_with_regime[present].rename(columns={"turn_number": "forfeit_turn"})
    merged = events_df.merge(join, on=["session_id", "forfeit_turn"], how="left")
    merged["regime"] = merged["regime"].fillna("unknown")
    return merged


# ---------------------------------------------------------------------------
# Filtering and aggregation helpers
# ---------------------------------------------------------------------------


def filter_regime(df: pd.DataFrame, regime: str) -> pd.DataFrame:
    """Return a copy of ``df`` restricted to one regime value.

    Accepted regime values:
        - ``"all"`` → full frame (no filtering).
        - ``"no_cap"`` → ``cap_bound == False`` AND ``ev_delta_s ≥ 0``.
        - ``"cap_bound"`` → ``cap_bound == True``.
        - ``"ev_negative_no_cap"`` → no cap but EV still flipped (rare).
        - ``"unknown"`` → missing ev/reward fields.
        - any exact string in the ``regime`` column.
    """
    if regime == "all":
        return df.copy()
    if "regime" not in df.columns:
        logger.warning("filter_regime: regime column missing — returning empty")
        return df.iloc[0:0].copy()
    return df[df["regime"] == regime].copy()


def stratified_reason_distribution(
    events_df_with_regime: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Per-regime reason-digit conditional distribution by framing.

    Returns a dict with keys ``{"all", "no_cap", "cap_bound",
    "ev_negative_no_cap"}`` (plus any other regime values present).
    Each value is the output of :func:`reason_distribution` applied to
    the subset. Empty subsets map to empty DataFrames.
    """
    out: dict[str, pd.DataFrame] = {"all": reason_distribution(events_df_with_regime)}
    if events_df_with_regime.empty or "regime" not in events_df_with_regime.columns:
        return out
    for regime in sorted(events_df_with_regime["regime"].dropna().unique().tolist()):
        sub = events_df_with_regime[events_df_with_regime["regime"] == regime]
        out[regime] = reason_distribution(sub)
    return out


def stratified_counts(
    events_df_with_regime: pd.DataFrame,
) -> pd.DataFrame:
    """Forfeit count matrix by framing × regime × reason.

    Rows: framing. Columns: MultiIndex ``(regime, reason)``. Cells:
    raw counts. Used for the paper table and the xlsx summary sheet.
    """
    if events_df_with_regime.empty:
        return pd.DataFrame()
    grouped = (
        events_df_with_regime.groupby(["framing", "regime", "reason"])
        .size()
        .unstack(fill_value=0)
    )
    # Flatten: present (regime, reason) as a MultiIndex column.
    pivot = (
        events_df_with_regime.assign(count=1)
        .pivot_table(
            index="framing",
            columns=["regime", "reason"],
            values="count",
            aggfunc="sum",
            fill_value=0,
        )
    )
    return pivot


# ---------------------------------------------------------------------------
# Stratified regression driver
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class StratifiedCoxResult:
    """Wraps :class:`CoxSurvivalResult` fits across regimes.

    As of 2026-04-23 this replaces the former ``StratifiedLogitResult``.
    Each regime stratum (``all``/``no_cap``/``cap_bound``) yields an
    independent Cox PH fit so the reader can verify that the
    preference-revealing ``no_cap`` slice drives the H1 claim while
    ``cap_bound`` is the rationality-revealing control.
    """

    regime: str
    n_turns: int
    n_forfeit: int
    fit: CoxSurvivalResult | None
    note: str | None

    def summary_dict(self) -> dict:
        d: dict[str, object] = {
            "regime": self.regime,
            "n_turns": self.n_turns,
            "n_forfeit": self.n_forfeit,
            "note": self.note,
        }
        if self.fit is not None:
            d.update(self.fit.summary_dict())
        return d


# Backward-compat alias so any external code still importing
# ``StratifiedLogitResult`` keeps working through the transition.
# Removed in a future release once all call sites are migrated.
StratifiedLogitResult = StratifiedCoxResult


def run_stratified_unit14(
    seasons: Sequence[SeasonResult],
    *,
    regimes: Sequence[str] = ("all", "no_cap", "cap_bound"),
) -> dict[str, object]:
    """Run the H1 Cox PH fit stratified by regime.

    Returns a dict with keys:
        - ``turn_df``: turn observations with regime columns.
        - ``events_df``: forfeit events with regime columns.
        - ``stratified``: list of :class:`StratifiedCoxResult` (one
          per requested regime).
        - ``reason_dist_by_regime``: dict from regime → reason-
          distribution DataFrame.
        - ``counts_matrix``: framing × (regime, reason) count pivot.

    The ``no_cap`` stratum is the v6 §7 primary sub-sample; the other
    strata are retained for calibration and to document cap-bound
    identification artefacts.
    """
    turn_df_raw = turn_observations(seasons)
    events_raw = forfeit_events(seasons)
    turn_df = annotate_regime(turn_df_raw)
    events_df = annotate_events_regime(events_raw, turn_df)

    stratified: list[StratifiedCoxResult] = []
    for regime in regimes:
        # Use the event-level regime filter baked into
        # ``fit_cox_forfeit_survival`` rather than a turn-level
        # ``filter_regime`` slice. A session's regime is determined by
        # the regime of its forfeit turn — turn-level filtering would
        # drop the cap-bound sessions' other turns even when the event
        # turn is no_cap, and would also drop censored sessions, both
        # of which corrupt the survival-frame semantics. The filter
        # argument ``regime`` is mapped to ``None`` for ``"all"``.
        regime_kwarg = None if regime == "all" else regime
        # Count diagnostics on the turn-level slice used for display
        # only (these don't drive the Cox fit itself).
        sub = filter_regime(turn_df, regime) if regime != "all" else turn_df
        n_turns = int(len(sub))
        n_forfeit = int(sub["forfeit"].sum()) if "forfeit" in sub else 0
        fit: CoxSurvivalResult | None = None
        note: str | None = None
        if n_forfeit < 5:
            note = (
                f"insufficient forfeits in regime={regime} "
                f"(n_forfeit={n_forfeit}, need ≥5)"
            )
        else:
            try:
                fit = fit_cox_forfeit_survival(turn_df, regime=regime_kwarg)
                if fit is None:
                    note = (
                        f"fit_cox_forfeit_survival returned None for "
                        f"regime={regime} (likely lifelines missing, both "
                        "framings not present, or quasi-separation)"
                    )
            except Exception as exc:  # noqa: BLE001 — analysis best-effort
                note = (
                    f"fit_cox_forfeit_survival raised for regime={regime}: "
                    f"{exc}"
                )
        stratified.append(
            StratifiedCoxResult(
                regime=regime,
                n_turns=n_turns,
                n_forfeit=n_forfeit,
                fit=fit,
                note=note,
            )
        )

    return {
        "turn_df": turn_df,
        "events_df": events_df,
        "stratified": stratified,
        "reason_dist_by_regime": stratified_reason_distribution(events_df),
        "counts_matrix": stratified_counts(events_df),
    }


# ---------------------------------------------------------------------------
# Markdown renderer
# ---------------------------------------------------------------------------


def _fmt_pct(value: object) -> str:
    try:
        return f"{float(value) * 100:.1f}%"
    except (TypeError, ValueError):
        return "—"


def _fmt_float(value: object, digits: int = 3) -> str:
    try:
        return f"{float(value):.{digits}f}"
    except (TypeError, ValueError):
        return "—"


def _df_to_markdown(df: pd.DataFrame, floatfmt: str = ".3f") -> str:
    """Dependency-free pandas → GitHub-flavoured markdown table.

    Avoids the ``pd.DataFrame.to_markdown`` → ``tabulate`` optional
    dependency. Handles MultiIndex rows/columns by flattening to tuple
    strings.
    """
    if df.empty:
        return "_(empty)_"

    def _cell(value: object) -> str:
        if isinstance(value, (int, np.integer)):
            return str(int(value))
        if isinstance(value, float):
            if pd.isna(value):
                return ""
            return f"{value:{floatfmt[1:]}}" if floatfmt.startswith(":") else format(
                value, floatfmt.lstrip(":")
            )
        if value is None or (isinstance(value, float) and pd.isna(value)):
            return ""
        return str(value)

    def _flatten_index(idx: pd.Index) -> list[str]:
        if isinstance(idx, pd.MultiIndex):
            return [" / ".join(str(v) for v in tup) for tup in idx.tolist()]
        return [str(v) for v in idx.tolist()]

    def _flatten_cols(cols: pd.Index) -> list[str]:
        if isinstance(cols, pd.MultiIndex):
            return [" / ".join(str(v) for v in tup) for tup in cols.tolist()]
        return [str(c) for c in cols.tolist()]

    row_labels = _flatten_index(df.index)
    col_labels = _flatten_cols(df.columns)
    index_name = df.index.name or "index"

    header = "| " + " | ".join([index_name, *col_labels]) + " |"
    sep = "| " + " | ".join(["---"] * (len(col_labels) + 1)) + " |"
    lines = [header, sep]
    for i, rl in enumerate(row_labels):
        row_cells = [_cell(df.iloc[i, j]) for j in range(len(col_labels))]
        lines.append("| " + " | ".join([rl, *row_cells]) + " |")
    return "\n".join(lines)


def render_regime_markdown(
    result: dict[str, object],
    *,
    model_label: str,
) -> str:
    """Render the stratified Unit 14 analysis as markdown.

    Sections:
        1. Regime definitions and thresholds.
        2. Forfeit count matrix (framing × regime × reason).
        3. Per-regime reason-digit distributions (P(reason|framing)).
        4. Per-regime logit fits (H_SA / H_SD / H_int / H_turn).
        5. Notes & interpretation aid.
    """
    events_df: pd.DataFrame = result.get("events_df")  # type: ignore[assignment]
    stratified: list[StratifiedLogitResult] = result.get("stratified")  # type: ignore[assignment]
    reason_dist_by_regime: dict[str, pd.DataFrame] = result.get(
        "reason_dist_by_regime"
    )  # type: ignore[assignment]

    lines: list[str] = []
    lines.append("# Phase O Unit 17.10 — Regime-Stratified Forfeit Analysis")
    lines.append("")
    lines.append(f"- **Model**: {model_label}")
    lines.append(
        "- **Regime definition**: `no_cap` = `cap_bound=False AND ev_delta_s ≥ 0` "
        "(preference-revealing); `cap_bound` = `reward_offered ≥ 100` "
        "(rationality-revealing); `ev_negative_no_cap` = rare floor-binding "
        "edge; `unknown` = missing ev/reward fields."
    )
    lines.append(
        "- **Thresholds**: `reward_ceiling=100 ΔS`, `p_death=0.25`, "
        "`psuccess_floor=0.3`, `CAP_EPSILON=0.5`."
    )
    lines.append(
        "- **Why stratify**: the reward cap flips EV(CONTINUE) negative at "
        "high scores, making cap-bound forfeits EV-rational rather than "
        "framing-preference-revealing. Separating regimes isolates the "
        "preference signal."
    )
    lines.append("")

    # --- Forfeit count matrix ---
    lines.append("## Forfeit counts — framing × regime × reason")
    counts = result.get("counts_matrix")
    if isinstance(counts, pd.DataFrame) and not counts.empty:
        lines.append("")
        lines.append(_df_to_markdown(counts, floatfmt=".0f"))
    else:
        lines.append("")
        lines.append("_No forfeit events to display._")
    lines.append("")

    # --- Reason-digit stratified convergence ---
    lines.append("## Reason-digit distribution — P(reason | framing) per regime")
    if events_df is not None and not events_df.empty and reason_dist_by_regime:
        for regime in ("all", "no_cap", "cap_bound", "ev_negative_no_cap"):
            df = reason_dist_by_regime.get(regime)
            if df is None or df.empty:
                continue
            sub_events = (
                events_df
                if regime == "all"
                else events_df[events_df["regime"] == regime]
            )
            n_events = int(len(sub_events))
            lines.append("")
            lines.append(f"### regime = `{regime}` (n_forfeits = {n_events})")
            lines.append("")
            lines.append(_df_to_markdown(df, floatfmt=".3f"))
    else:
        lines.append("")
        lines.append("_No forfeit events._")
    lines.append("")

    # --- Per-regime time-varying Cox fits (2026-04-23 two-step spec) ---
    lines.append("## Time-varying Cox PH — stratified by regime")
    lines.append("")
    lines.append(
        "`λ(t|X) = λ₀(t) exp(β_FC·framing_is_FC + β_S·S(t−1))` "
        "(allowed cells only; baseline_flagship vs flagship_corruption; "
        "time-varying S(t−1) = score_before_turn). See §7.2.1 for spec."
    )
    if stratified:
        header = (
            "| regime | n_sessions | n_events (BF/FC) | HR(FC/BF) | 95% CI "
            "| p_framing | HR_score | 95% CI | p_score | log-rank χ² (p) "
            "| PH ok | note |"
        )
        sep = "| " + " | ".join(["---"] * 12) + " |"
        lines.append("")
        lines.append(header)
        lines.append(sep)
        for sr in stratified:
            fit = sr.fit
            if fit is None:
                row = [
                    sr.regime,
                    str(sr.n_turns),
                    str(sr.n_forfeit),
                    "—", "—", "—", "—", "—", "—", "—", "—",
                    sr.note or "—",
                ]
            else:
                ph_ok_str = (
                    "✓" if fit.ph_assumption_ok is True
                    else ("⚠" if fit.ph_assumption_ok is False else "n/a")
                )
                ci_frame = (
                    f"[{fit.hr_ci_low:.2f}, {fit.hr_ci_high:.2f}]"
                )
                ci_score = (
                    f"[{fit.hr_score_ci_low:.4f}, "
                    f"{fit.hr_score_ci_high:.4f}]"
                )
                lr_cell = (
                    f"{fit.logrank_chi2:.2f} "
                    f"({_fmt_float(fit.logrank_p, 3)})"
                )
                row = [
                    sr.regime,
                    str(fit.n_sessions),
                    f"{fit.n_events_BF}/{fit.n_events_FC}",
                    _fmt_float(fit.hr_framing, 3),
                    ci_frame,
                    _fmt_float(fit.p_framing, 3),
                    _fmt_float(fit.hr_score, 4),
                    ci_score,
                    _fmt_float(fit.p_score, 3),
                    lr_cell,
                    ph_ok_str,
                    sr.note or "",
                ]
            lines.append("| " + " | ".join(row) + " |")

    lines.append("")
    lines.append("## Interpretation notes")
    lines.append("")
    lines.append(
        "- The `no_cap` subset is the **preference-revealing** primary "
        "sample for H_SD / H_conv — cap distortion is absent, so a high "
        "survival reason rate under corruption is causally attributable "
        "to framing-induced FSPM."
    )
    lines.append(
        "- The `cap_bound` subset is a **rationality-revealing** "
        "manipulation check — EV(continue) < 0 there, so *every* "
        "EV-rational agent should forfeit regardless of framing. Used "
        "to verify the model actually does EV arithmetic (expected: "
        "near-100% forfeit rate; reason digit skews to SA as "
        "rationalisation)."
    )
    lines.append(
        "- Cross-regime reason digit discrepancy (e.g. SD rate "
        "62% no_cap → 0% cap_bound in corruption) is *expected* and "
        "*diagnostic*: it confirms that the SD signal disappears where "
        "the EV structure overrides preference, not that the agent's "
        "motive vanished."
    )
    return "\n".join(lines) + "\n"
