"""Phase O — H1 survival analysis (time-varying Cox PH + Kaplan-Meier).

As of 2026-04-23 (v6 §7 Cox PH promotion, two-step spec fix), H1 ``H_SD``
is estimated as a **time-varying proportional-hazards model** on the
no_cap regime of the allowed cells (Cell 1 baseline_flagship × Cell 3
flagship_corruption). The covariate ``score_prev = S(t-1)`` is the
cumulative score at the START of turn t (= score after turn t-1
concluded, BEFORE the turn-t forfeit decision), which varies across
turns within a session. This module supersedes two earlier workflows:
the v5 logistic H1 (rate-focused) and the initial 2026-04-23 Cox PH
that mis-specified S as a baseline covariate (S_0 = 30 canonical →
β_S non-identifiable).

Workflow:

1. ``build_survival_frame(turn_df, regime="no_cap")`` — emit a
   long-format per-turn DataFrame with one row per (session, turn)
   where the session is at risk at that turn. Columns:
   ``session_id``, ``framing``, ``framing_is_FC``, ``start``,
   ``stop``, ``event``, ``score_prev``, ``regime_tag``. The ``start``
   column is t-1, ``stop`` is t, ``score_prev`` is score_before_turn
   (= S(t-1)), and ``event`` = 1 iff FORFEIT occurred at that turn.
   The ``regime`` filter is applied per-row: only turns whose regime
   matches the argument are retained. A session that forfeits in
   cap_bound regime contributes only its earlier no_cap turns as
   censored rows (no event), which is the statistically correct
   treatment for a sub-sample Cox.
2. ``fit_cox_forfeit_survival(turn_df, regime="no_cap")`` — fit a
   time-varying Cox proportional-hazards model on the filtered
   long-format survival frame using lifelines
   ``CoxTimeVaryingFitter``. Returns :class:`CoxSurvivalResult` with
   ``HR(FC/BF)`` point estimate + 95% CI + Wald p; ``HR(S(t-1))``
   score-attachment coefficient + 95% CI + Wald p; log-rank p
   (framing comparison, session-collapsed); and descriptive mean
   forfeit turn per framing. A Schoenfeld residual PH check on the
   framing covariate is attempted via :func:`_ph_check_framing`; when
   it raises (e.g. zero residuals due to tied ties) ``ph_assumption_ok``
   is left as ``None``.
3. ``km_forfeit_curves(turn_df, regime="no_cap")`` — Kaplan-Meier
   estimates of the survival function per framing; returned as a tidy
   long-format DataFrame. The KM fit collapses the long-format frame
   to one (T, event) pair per session (first no_cap forfeit or last
   observed no_cap turn) so callers can render per-framing curves.
4. ``run_h1_survival_hypothesis(seasons)`` — driver that accepts a
   list of :class:`SeasonResult`, invokes
   :func:`shared.loaders.turn_observations` to build the per-turn
   DataFrame, annotates per-turn regime via
   :func:`behavioral.regime.annotate_regime`, and returns a dict
   ``{"cox": CoxSurvivalResult | None, "km": pd.DataFrame,
   "survival_frame": pd.DataFrame}``.

All functions degrade gracefully when ``lifelines`` is not installed
or when the sample is too small: the return contract stays but
estimates become ``None`` / empty DataFrames, and the renderer prints
a skip message. The analysis pipeline must never crash on missing
optional dependencies.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Sequence

import pandas as pd

from squid_game.evaluation.shared.loaders import turn_observations
from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.models.results import SeasonResult

logger = logging.getLogger(__name__)


_CORRUPTION_FRAMING: str = Framing.FLAGSHIP_CORRUPTION.value
_BASELINE_FRAMING: str = Framing.BASELINE_FLAGSHIP.value

# Session-level minimum count below which Cox PH becomes underpowered
# (10 events per covariate is the standard rule of thumb; the primary
# model has 2 covariates so we require 20 events minimum. When fewer
# events are observed we still return the fit but flag it via the
# ``underpowered`` field so callers can attach a caveat.)
_MIN_EVENTS_FOR_COX: int = 10

# Canonical session horizon — right-censoring boundary when no forfeit
# occurs. Matches ``ExperimentConfig.num_turns`` for the canonical run.
_CANONICAL_CENSOR_TURN: int = 15


# ---------------------------------------------------------------------------
# Survival frame construction (long-format per-turn)
# ---------------------------------------------------------------------------


def build_survival_frame(
    turn_df: pd.DataFrame,
    *,
    regime: str | None = "no_cap",
    extra_covariates: Sequence[str] | None = None,
) -> pd.DataFrame:
    """Collapse per-turn observations into a long-format survival frame.

    Each returned row represents one (session, turn) at-risk interval.
    This long-format layout is the input expected by
    ``lifelines.CoxTimeVaryingFitter`` and captures the time-varying
    ``score_prev`` covariate (= S(t-1)).

    Parameters
    ----------
    turn_df
        DataFrame with the schema emitted by
        :func:`shared.loaders.turn_observations`, augmented with
        a per-turn ``regime`` column (via
        :func:`behavioral.regime.annotate_regime`). Must contain
        ``session_id``, ``framing``, ``forfeit_condition``,
        ``turn_number``, ``score_before_turn``, ``forfeit``, and
        ``regime``.
    regime
        When ``"no_cap"`` (default), filter per-turn rows to those
        whose ``regime`` column equals ``"no_cap"``. Sessions that
        forfeit in a non-no_cap regime thus contribute only their
        earlier no_cap at-risk turns as censored rows. When ``None``
        keep all rows regardless of regime.
    extra_covariates
        Additional per-turn column names to carry straight through
        into the survival frame unchanged (e.g.
        ``["threat_level"]``). Every name must already exist
        on ``turn_df``; a missing one raises ``ValueError`` rather than
        silently producing a frame the caller thinks has the column.

    Returns
    -------
    pd.DataFrame with columns ``session_id``, ``framing``,
    ``framing_is_FC``, ``start``, ``stop``, ``event``, ``score_prev``,
    ``regime_tag``, plus any ``extra_covariates`` (in the order given).
    ``start = turn_number - 1``, ``stop = turn_number``,
    ``score_prev = score_before_turn`` (= S(t-1) at turn stop),
    ``event = 1`` iff FORFEIT at that turn. Only allowed-forfeit rows
    whose framing is ``baseline_flagship`` or ``flagship_corruption``
    are included — ``true_baseline`` (Cell 0 degenerate path and Cell 5
    BP anchor) are excluded because they do not share the framing
    contrast axis used by H1.
    """
    extra_covariates = list(extra_covariates) if extra_covariates else []
    empty_cols = [
        "session_id",
        "framing",
        "framing_is_FC",
        "start",
        "stop",
        "event",
        "score_prev",
        "regime_tag",
    ] + extra_covariates
    if turn_df is None or turn_df.empty:
        return pd.DataFrame(columns=empty_cols)

    missing = [c for c in extra_covariates if c not in turn_df.columns]
    if missing:
        raise ValueError(
            f"extra_covariates column(s) not found in turn_df: {missing}"
        )

    sub = turn_df[
        (turn_df["forfeit_condition"] == ForfeitCondition.ALLOWED.value)
        & turn_df["framing"].isin([_BASELINE_FRAMING, _CORRUPTION_FRAMING])
    ].copy()
    if sub.empty:
        return pd.DataFrame(columns=empty_cols)

    # Map per-turn rows to long-format survival intervals
    records: list[dict] = []
    for _, r in sub.iterrows():
        try:
            t = int(r["turn_number"])
        except (TypeError, ValueError):
            continue
        try:
            score_prev = float(r["score_before_turn"])
        except (TypeError, ValueError):
            continue
        event = 1 if bool(r["forfeit"]) else 0
        framing = str(r["framing"])
        regime_tag = (
            str(r["regime"])
            if "regime" in r.index and pd.notna(r.get("regime"))
            else None
        )
        record = {
            "session_id": r["session_id"],
            "framing": framing,
            "framing_is_FC": 1 if framing == _CORRUPTION_FRAMING else 0,
            "start": t - 1,
            "stop": t,
            "event": event,
            "score_prev": score_prev,
            "regime_tag": regime_tag,
        }
        for col in extra_covariates:
            record[col] = r[col]
        records.append(record)

    frame = pd.DataFrame.from_records(records, columns=empty_cols)
    if frame.empty:
        return frame

    if regime is not None:
        frame = frame[frame["regime_tag"] == regime].reset_index(drop=True)

    return frame


def _collapse_to_session_level(long_frame: pd.DataFrame) -> pd.DataFrame:
    """Collapse a long-format frame to one (T, event) row per session.

    Used for log-rank and Kaplan-Meier which both need a single
    duration-event pair per subject. ``T`` is the first event ``stop``
    if the session had an event in the filtered frame, else the max
    ``stop`` (last no_cap at-risk turn).
    """
    rows: list[dict] = []
    for sid, grp in long_frame.groupby("session_id", sort=False):
        grp = grp.sort_values("stop")
        events = grp[grp["event"] == 1]
        framing = str(grp.iloc[0]["framing"])
        if len(events):
            T = float(events.iloc[0]["stop"])
            event = 1
        else:
            T = float(grp.iloc[-1]["stop"])
            event = 0
        rows.append(
            {
                "session_id": sid,
                "framing": framing,
                "T": T,
                "event": event,
            }
        )
    return pd.DataFrame(rows, columns=["session_id", "framing", "T", "event"])


# ---------------------------------------------------------------------------
# Cox PH fit (time-varying)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CoxSurvivalResult:
    """Summary of the H1 time-varying Cox proportional-hazards fit.

    All fields refer to the model
    ``λ(t|X) = λ₀(t) exp(β_FC · framing_is_FC + β_S · S(t-1))``
    fit on the long-format per-turn survival frame (no_cap regime by
    default, Cells 1 and 3 only).
    """

    n_sessions: int
    n_events: int
    n_events_BF: int
    n_events_FC: int
    mean_forfeit_turn_BF: float | None
    mean_forfeit_turn_FC: float | None

    # Primary inference — HR on the corruption indicator
    hr_framing: float
    hr_ci_low: float
    hr_ci_high: float
    p_framing: float

    # Secondary — time-varying score covariate (S(t-1))
    # hr_score > 1 (with 95% CI excluding 1) is the Tversky-Kahneman
    # loss-aversion / conservative-SA signature within the no_cap
    # sub-sample (higher accumulated score → higher anti-EV forfeit
    # hazard).
    hr_score: float
    hr_score_ci_low: float
    hr_score_ci_high: float
    p_score: float

    # Non-parametric framing comparison (session-collapsed)
    logrank_chi2: float
    logrank_p: float

    # PH assumption audit — attempted on the non-time-varying
    # collapsed frame as a sanity check. May be ``None`` when the
    # check raises (tied residuals, small samples).
    ph_assumption_ok: bool | None

    regime: str | None
    underpowered: bool

    # HR / CI / p for any ``extra_covariates`` passed
    # to :func:`fit_cox_forfeit_survival` (e.g. ``threat_level``),
    # keyed by column name: ``{"threat_level": {"hr": ..., "ci_low":
    # ..., "ci_high": ..., "p": ...}}``. Empty dict when no extra
    # covariates were requested, or when a requested one had zero
    # variance in the fitted frame and was dropped.
    extra_hazard_ratios: dict[str, dict[str, float]] = field(
        default_factory=dict
    )

    def summary_dict(self) -> dict:
        return {
            "n_sessions": self.n_sessions,
            "n_events": self.n_events,
            "n_events_BF": self.n_events_BF,
            "n_events_FC": self.n_events_FC,
            "mean_forfeit_turn_BF": self.mean_forfeit_turn_BF,
            "mean_forfeit_turn_FC": self.mean_forfeit_turn_FC,
            "hr_framing": self.hr_framing,
            "hr_ci_low": self.hr_ci_low,
            "hr_ci_high": self.hr_ci_high,
            "p_framing": self.p_framing,
            "hr_score": self.hr_score,
            "hr_score_ci_low": self.hr_score_ci_low,
            "hr_score_ci_high": self.hr_score_ci_high,
            "p_score": self.p_score,
            "logrank_chi2": self.logrank_chi2,
            "logrank_p": self.logrank_p,
            "ph_assumption_ok": self.ph_assumption_ok,
            "regime": self.regime,
            "underpowered": self.underpowered,
            "extra_hazard_ratios": self.extra_hazard_ratios,
        }


def _safe_ph_check(
    session_frame: pd.DataFrame,
) -> bool | None:
    """Schoenfeld residual PH check on the session-collapsed frame.

    CoxTimeVaryingFitter has no built-in ``check_assumptions``; we run
    it on the non-time-varying collapsed view as a best-effort audit
    of the framing covariate. Returns ``None`` on any internal error
    (small-sample singularities, lifelines API drift).
    """
    try:
        from lifelines import CoxPHFitter
    except ImportError:
        return None
    if session_frame is None or session_frame.empty:
        return None
    if session_frame["event"].sum() == 0:
        return None
    try:
        fit_df = session_frame[["T", "event", "framing_is_FC"]].copy()
        cph = CoxPHFitter()
        cph.fit(fit_df, duration_col="T", event_col="event")
        failures = cph.check_assumptions(
            fit_df, show_plots=False, advice=False
        )
        return len(failures) == 0
    except Exception as exc:  # noqa: BLE001
        logger.debug("Schoenfeld residual check failed: %s", exc)
        return None


def fit_cox_forfeit_survival(
    turn_df: pd.DataFrame,
    *,
    regime: str | None = "no_cap",
    extra_covariates: Sequence[str] | None = None,
) -> CoxSurvivalResult | None:
    """Fit the H1 time-varying Cox proportional-hazards model.

    Returns ``None`` when:
    - ``lifelines`` is not installed,
    - the filtered long-format survival frame is empty,
    - no ``extra_covariates`` were requested and both framings are not
      represented (the H1 framing contrast requires both arms),
    - both framings are present but neither has any event,
    - no covariate ends up with non-zero variance in the fitted frame,
    - the Cox fit itself raises.

    ``extra_covariates`` (e.g. the ordinal ``["threat_level"]`` used to
    generalise H1 across the threat ladder) are carried through
    :func:`build_survival_frame` and appended to the covariate list
    whenever they have non-zero variance; each fitted one's HR/CI/p
    lands in ``CoxSurvivalResult.extra_hazard_ratios``. Passing
    ``extra_covariates`` also relaxes the "both framings required" gate:
    a covariate-only fit may legitimately restrict its input to a single
    framing, in which case ``framing_is_FC`` is dropped from the
    covariate list as constant (its HR/CI/p fields come back ``nan``,
    mirroring the existing ``score_prev``-dropped convention).

    When the fit succeeds but the event count is below
    :data:`_MIN_EVENTS_FOR_COX` the result is returned with
    ``underpowered=True`` so the caller can attach a caveat.
    """
    try:
        from lifelines import CoxTimeVaryingFitter
        from lifelines.statistics import logrank_test
    except ImportError:
        logger.info(
            "lifelines not installed; skipping H1 time-varying Cox fit."
        )
        return None

    extra_covariates = list(extra_covariates) if extra_covariates else []
    frame = build_survival_frame(
        turn_df, regime=regime, extra_covariates=extra_covariates
    )
    if frame.empty:
        return None

    framings_present = set(frame["framing"].unique())
    if extra_covariates:
        # A covariate-only fit may legitimately see a single framing
        # (the caller restricted its input) — the framing contrast is
        # simply not identifiable there and is dropped below rather
        # than gating the whole fit.
        if not framings_present:
            return None
    elif not {_BASELINE_FRAMING, _CORRUPTION_FRAMING}.issubset(
        framings_present
    ):
        logger.info(
            "Cox survival skipped: both framings required, got %s.",
            framings_present,
        )
        return None

    bf_long = frame[frame["framing"] == _BASELINE_FRAMING]
    fc_long = frame[frame["framing"] == _CORRUPTION_FRAMING]
    n_events = int(frame["event"].sum())
    n_events_bf = int(bf_long["event"].sum())
    n_events_fc = int(fc_long["event"].sum())

    if n_events == 0:
        return None

    # Descriptive mean forfeit turns (from event rows)
    bf_event_stops = bf_long[bf_long["event"] == 1]["stop"]
    fc_event_stops = fc_long[fc_long["event"] == 1]["stop"]
    mean_bf = float(bf_event_stops.mean()) if len(bf_event_stops) else None
    mean_fc = float(fc_event_stops.mean()) if len(fc_event_stops) else None

    # Non-parametric log-rank (framing comparison) on session-collapsed
    # frame — undefined (and skipped, nan) when one arm is empty, which
    # happens for a single-framing extra_covariates fit.
    session_frame = _collapse_to_session_level(frame)
    bf_ses = session_frame[session_frame["framing"] == _BASELINE_FRAMING]
    fc_ses = session_frame[session_frame["framing"] == _CORRUPTION_FRAMING]
    if bf_ses.empty or fc_ses.empty:
        logrank_chi2 = float("nan")
        logrank_p = float("nan")
    else:
        lr = logrank_test(
            bf_ses["T"],
            fc_ses["T"],
            event_observed_A=bf_ses["event"],
            event_observed_B=fc_ses["event"],
        )
        logrank_chi2 = float(lr.test_statistic)
        logrank_p = float(lr.p_value)

    # Time-varying Cox PH fit. Every candidate covariate is dropped when
    # it has zero variance in the fitted frame — that already covered
    # score_prev defensively; extra_covariates and (now) framing_is_FC
    # get the same treatment.
    covariates: list[str] = []
    if frame["framing_is_FC"].nunique() > 1:
        covariates.append("framing_is_FC")
    if frame["score_prev"].nunique() > 1:
        covariates.append("score_prev")
    for col in extra_covariates:
        if frame[col].nunique() > 1:
            covariates.append(col)
    if not covariates:
        logger.info("Cox survival skipped: no covariate has variance.")
        return None

    fit_data = frame[
        ["session_id", "start", "stop", "event"] + covariates
    ].copy()

    try:
        ctv = CoxTimeVaryingFitter()
        ctv.fit(
            fit_data,
            id_col="session_id",
            event_col="event",
            start_col="start",
            stop_col="stop",
        )
    except Exception as exc:  # noqa: BLE001 — defensive
        logger.warning("Time-varying Cox PH fit failed: %s", exc)
        return None

    summary = ctv.summary

    def _extract(name: str) -> tuple[float, float, float, float]:
        return (
            float(summary.loc[name, "exp(coef)"]),
            float(summary.loc[name, "exp(coef) lower 95%"]),
            float(summary.loc[name, "exp(coef) upper 95%"]),
            float(summary.loc[name, "p"]),
        )

    if "framing_is_FC" in covariates:
        hr_framing, ci_low, ci_high, p_framing = _extract("framing_is_FC")
    else:
        hr_framing = ci_low = ci_high = p_framing = float("nan")

    if "score_prev" in covariates:
        hr_score, hr_score_ci_low, hr_score_ci_high, p_score = _extract(
            "score_prev"
        )
    else:
        hr_score = hr_score_ci_low = hr_score_ci_high = p_score = float(
            "nan"
        )

    extra_hazard_ratios: dict[str, dict[str, float]] = {}
    for col in extra_covariates:
        if col in covariates:
            hr, lo, hi, p = _extract(col)
            extra_hazard_ratios[col] = {
                "hr": hr,
                "ci_low": lo,
                "ci_high": hi,
                "p": p,
            }

    # PH assumption audit (on session-collapsed frame; best-effort)
    ph_ok = _safe_ph_check(session_frame.assign(framing_is_FC=session_frame[
        "framing"
    ].map({_BASELINE_FRAMING: 0, _CORRUPTION_FRAMING: 1})))

    n_sessions = int(frame["session_id"].nunique())
    return CoxSurvivalResult(
        n_sessions=n_sessions,
        n_events=n_events,
        n_events_BF=n_events_bf,
        n_events_FC=n_events_fc,
        mean_forfeit_turn_BF=mean_bf,
        mean_forfeit_turn_FC=mean_fc,
        hr_framing=hr_framing,
        hr_ci_low=ci_low,
        hr_ci_high=ci_high,
        p_framing=p_framing,
        hr_score=hr_score,
        hr_score_ci_low=hr_score_ci_low,
        hr_score_ci_high=hr_score_ci_high,
        p_score=p_score,
        logrank_chi2=logrank_chi2,
        logrank_p=logrank_p,
        ph_assumption_ok=ph_ok,
        regime=regime,
        underpowered=n_events < _MIN_EVENTS_FOR_COX,
        extra_hazard_ratios=extra_hazard_ratios,
    )


# ---------------------------------------------------------------------------
# Kaplan-Meier curves
# ---------------------------------------------------------------------------


def km_forfeit_curves(
    turn_df: pd.DataFrame,
    *,
    regime: str | None = "no_cap",
) -> pd.DataFrame:
    """Build Kaplan-Meier survival estimates per framing.

    Returns a long-format DataFrame with columns ``framing``,
    ``turn``, ``survival``, ``ci_lower``, ``ci_upper``. When
    ``lifelines`` is unavailable or the filtered frame is empty the
    returned DataFrame has zero rows.

    The caller renders these curves — the module is intentionally
    rendering-agnostic so both matplotlib (for the paper) and Vega
    (for a web dashboard) can consume the same artifact.
    """
    empty = pd.DataFrame(
        columns=["framing", "turn", "survival", "ci_lower", "ci_upper"]
    )
    try:
        from lifelines import KaplanMeierFitter
    except ImportError:
        logger.info("lifelines not installed; skipping KM curves.")
        return empty

    frame = build_survival_frame(turn_df, regime=regime)
    if frame.empty:
        return empty
    session_frame = _collapse_to_session_level(frame)
    if session_frame.empty:
        return empty

    rows: list[dict] = []
    for framing_val in [_BASELINE_FRAMING, _CORRUPTION_FRAMING]:
        sub = session_frame[session_frame["framing"] == framing_val]
        if len(sub) == 0:
            continue
        km = KaplanMeierFitter()
        km.fit(sub["T"], event_observed=sub["event"], label=framing_val)
        sf = km.survival_function_
        ci = km.confidence_interval_
        ci_low_col = f"{framing_val}_lower_0.95"
        ci_high_col = f"{framing_val}_upper_0.95"
        for t in sf.index:
            row = {
                "framing": framing_val,
                "turn": float(t),
                "survival": float(sf.loc[t, framing_val]),
            }
            if ci_low_col in ci.columns and t in ci.index:
                row["ci_lower"] = float(ci.loc[t, ci_low_col])
                row["ci_upper"] = float(ci.loc[t, ci_high_col])
            else:
                row["ci_lower"] = float("nan")
                row["ci_upper"] = float("nan")
            rows.append(row)
    return pd.DataFrame(rows, columns=empty.columns)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def run_h1_survival_hypothesis(
    seasons: Sequence[SeasonResult],
    *,
    regime: str | None = "no_cap",
) -> dict[str, object]:
    """Compose the H1 survival payload for the analysis pipeline.

    Returns a dict with:
    - ``cox``: :class:`CoxSurvivalResult` or ``None``.
    - ``km``: long-format KM DataFrame (may be empty).
    - ``survival_frame``: long-format per-turn survival frame used for
      both the time-varying Cox fit and the session-collapsed log-rank.
    - ``regime``: the regime filter applied (``"no_cap"`` by default).

    The driver annotates per-turn regime columns on the per-turn frame
    before filtering so callers don't have to. When ``regime=None`` is
    passed the annotation is skipped (equivalent to the legacy
    all-forfeits analysis, retained for diagnostic use).
    """
    # Delayed import — behavioral.regime imports fit_cox_forfeit_survival
    # from this module, so we can only resolve its annotate_regime at call
    # time to avoid a circular import at module load.
    from squid_game.evaluation.behavioral.regime import annotate_regime

    turn_df = turn_observations(seasons)
    if regime is not None and "regime" not in turn_df.columns:
        turn_df = annotate_regime(turn_df)
    survival_frame = build_survival_frame(turn_df, regime=regime)
    cox = fit_cox_forfeit_survival(turn_df, regime=regime)
    km = km_forfeit_curves(turn_df, regime=regime)
    return {
        "cox": cox,
        "km": km,
        "survival_frame": survival_frame,
        "regime": regime,
    }


__all__ = [
    "CoxSurvivalResult",
    "build_survival_frame",
    "fit_cox_forfeit_survival",
    "km_forfeit_curves",
    "run_h1_survival_hypothesis",
]
