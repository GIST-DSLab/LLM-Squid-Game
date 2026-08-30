"""Phase O §6 — Task Curiosity (TC) rule-mastery regression.

Implements the TC indicator pipeline specified in
``docs/design/v6/paper/metric.md`` §6 (added 2026-04-25):

- **Model A (§6.3 식 A)** — Cell 0 baseline, TC-pure regime:
    ``ri_task[t] ~ correct[t-1] + turn + (1|session)``
- **Model B (§6.3 식 B)** — Cells 1-4 framing modulation:
    ``ri_task[t] ~ correct[t-1] * 1_FC + score + turn + (1|session)``
- **V2 (§6.5 V2)** — reverse causality check on the same data.
- **V6 (§6.5 V6)** — streak robustness via rolling correct rate.
- **§6.7 Cox extension (v7)** — TC-driven forfeit Cox with
    ``M[t-1] = 1{rule_match_score[t-1] >= threshold}`` as objective
    rule-mastery covariate, sister of §1 Cox HR(FC/BF).

All functions consume the per-turn DataFrame produced by
:func:`squid_game.analysis.forfeit_regression.turn_observations` (or the
on-disk ``phase3_analysis/unit14_turn_observations.csv``). Functions
degrade gracefully when ``statsmodels``/``lifelines`` are missing or
the sample is too small.

Decision rule for TC presence (Model A): ``β_C < 0`` and ``p < 0.05``.
Decision rule for TC-driven forfeit (Cox §6.7): ``β_M > 0``,
``p < 0.05``, and (verbal triangulation) ``P(REASON=2 | forfeit)``
elevated.

The module is intentionally side-effect-free; orchestration / disk I/O
is the caller's responsibility (see ``scripts/analyze_tc.py``).
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Iterable

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


_CELL0_FRAMING: str = "true_baseline"
_CELL0_FORFEIT: str = "not_allowed"
_BASELINE_FRAMING: str = "baseline_flagship"
_CORRUPTION_FRAMING: str = "flagship_corruption"
_ALLOWED_FRAMINGS: frozenset[str] = frozenset(
    {_BASELINE_FRAMING, _CORRUPTION_FRAMING}
)

# Min observations gates (matches forfeit_regression _MIN_TURNS_FOR_LOGIT).
_MIN_TURNS_FOR_MIXEDLM: int = 20
_MIN_EVENTS_FOR_COX: int = 10


# ---------------------------------------------------------------------------
# Result containers
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class TCRegressionResult:
    """Summary of a §6 TC mixedLM fit (Model A or Model B).

    All ``β_*`` / ``p_*`` fields are ``nan`` when the corresponding
    covariate is not in the model (Model A omits framing/score/
    interaction).
    """

    model_label: str  # "cell0" (Model A) or "allowed" (Model B)
    n_obs: int
    n_sessions: int
    beta_correct: float
    se_correct: float
    p_correct: float
    beta_framing: float
    se_framing: float
    p_framing: float
    beta_interaction: float
    se_interaction: float
    p_interaction: float
    beta_score: float
    se_score: float
    p_score: float
    beta_turn: float
    se_turn: float
    p_turn: float
    converged: bool

    def summary_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TCReverseCheckResult:
    """Summary of the §6.5 V2 reverse-causality check.

    Logistic regression: ``correct[t] ~ ri_task[t] + turn``.
    A significant ``alpha_R > 0`` indicates that thinking → correctness
    arc is alive — the lag-1 design (correct[t-1] → ri_task[t]) still
    has residual endogeneity from session-level competence.
    """

    n_obs: int
    n_sessions: int
    alpha_R: float
    se_R: float
    p_R: float
    alpha_turn: float
    converged: bool

    def summary_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TCCoxResult:
    """Summary of the §6.7 Cox PH TC-driven forfeit fit.

    Model:
        ``λ(t|X) = λ₀(t) · exp(β_F · 1_FC + β_S · S(t-1) + β_M · M(t-1))``
    where ``M(t-1) = 1{rule_match_score[t-1] ≥ threshold}``.

    Decision rule for TC-driven forfeit:
        ``β_M > 0`` AND ``p_M < 0.05`` AND verbal triangulation
        (P(REASON=2 | forfeit) elevated, see §2.4 V4 / §6.5 V4).

    Sister of :class:`forfeit_survival.CoxSurvivalResult`. Same
    ``framing_is_FC`` / ``score_prev`` covariates so β_FC / β_S are
    directly comparable to §1.
    """

    threshold: float
    n_sessions: int
    n_events: int
    n_M_active_intervals: int  # turn-rows with M=1
    hr_framing: float
    hr_framing_ci_low: float
    hr_framing_ci_high: float
    p_framing: float
    hr_score: float
    hr_score_ci_low: float
    hr_score_ci_high: float
    p_score: float
    hr_M: float
    hr_M_ci_low: float
    hr_M_ci_high: float
    p_M: float
    underpowered: bool

    def summary_dict(self) -> dict:
        return asdict(self)


# ---------------------------------------------------------------------------
# Lag construction (correct[t-1], rule_match[t-1])
# ---------------------------------------------------------------------------


def add_correct_prev(df: pd.DataFrame) -> pd.DataFrame:
    """Append a ``correct_prev`` column to a per-turn DataFrame.

    ``correct_prev[t] = 1{task_success_factor[t-1] == 1.0}`` within
    each session. Rows with ``turn_number == 1`` (no lag) are dropped.

    Parameters
    ----------
    df : pd.DataFrame
        Must contain ``session_id``, ``turn_number``,
        ``task_success_factor``.

    Returns
    -------
    pd.DataFrame
        Same schema + ``correct_prev`` (int 0/1) column. ``turn_number == 1``
        rows are dropped because lag is undefined.
    """
    if df.empty or "task_success_factor" not in df.columns:
        return df.copy()

    work = df.sort_values(["session_id", "turn_number"]).copy()
    work["task_success_factor"] = pd.to_numeric(
        work["task_success_factor"], errors="coerce"
    )
    work["correct_prev"] = (
        work.groupby("session_id")["task_success_factor"]
        .shift(1)
        .fillna(np.nan)
    )
    work["correct_prev"] = (work["correct_prev"] == 1.0).astype(float)
    # Drop t=1 rows (lag undefined): the shift produces NaN, so the
    # fillna→0 above would falsely mark them as not-correct. Identify
    # via group-position instead.
    work["_pos"] = work.groupby("session_id").cumcount()
    work = work[work["_pos"] >= 1].drop(columns="_pos").reset_index(drop=True)
    return work


def add_rule_match_prev(
    df: pd.DataFrame,
    *,
    threshold: float = 90.0,
) -> pd.DataFrame:
    """Append ``rule_match_prev`` and ``M_prev`` columns.

    ``M_prev[t] = 1{rule_match_score[t-1] >= threshold}``.

    Drops turn-1 rows (lag undefined). When ``rule_match_score`` has
    missing values at the lagged position the row is dropped to keep
    the M indicator unambiguous.
    """
    if df.empty or "rule_match_score" not in df.columns:
        return df.copy()

    work = df.sort_values(["session_id", "turn_number"]).copy()
    work["rule_match_prev"] = work.groupby("session_id")[
        "rule_match_score"
    ].shift(1)
    work["_pos"] = work.groupby("session_id").cumcount()
    work = work[work["_pos"] >= 1].drop(columns="_pos")
    work = work[work["rule_match_prev"].notna()].copy()
    work["M_prev"] = (work["rule_match_prev"] >= threshold).astype(int)
    return work.reset_index(drop=True)


# ---------------------------------------------------------------------------
# Model A — Cell 0 baseline (TC-pure regime)
# ---------------------------------------------------------------------------


def _empty_result(label: str) -> TCRegressionResult:
    nan = float("nan")
    return TCRegressionResult(
        model_label=label,
        n_obs=0,
        n_sessions=0,
        beta_correct=nan,
        se_correct=nan,
        p_correct=nan,
        beta_framing=nan,
        se_framing=nan,
        p_framing=nan,
        beta_interaction=nan,
        se_interaction=nan,
        p_interaction=nan,
        beta_score=nan,
        se_score=nan,
        p_score=nan,
        beta_turn=nan,
        se_turn=nan,
        p_turn=nan,
        converged=False,
    )


def fit_tc_rule_mastery_cell0(
    turn_df: pd.DataFrame,
) -> TCRegressionResult | None:
    """Fit the §6.3 Model A mixedLM on Cell 0 only.

    Specification:
        ``ri_task ~ correct_prev + turn + (1|session)``

    Returns ``None`` when ``statsmodels`` is unavailable or the Cell 0
    sample is below :data:`_MIN_TURNS_FOR_MIXEDLM`. Returns an empty
    result (``n_obs=0``) when the input has no Cell 0 rows but
    statsmodels is installed.
    """
    try:
        import statsmodels.api as sm  # noqa: F401
        import statsmodels.formula.api as smf
    except ImportError:
        logger.info("statsmodels not installed; skipping TC Model A fit.")
        return None

    if turn_df.empty:
        return _empty_result("cell0")

    sub = turn_df[
        (turn_df["framing"] == _CELL0_FRAMING)
        & (turn_df["forfeit_condition"] == _CELL0_FORFEIT)
        & turn_df["ri_task_thinking_tokens"].notna()
    ].copy()
    sub = add_correct_prev(sub)
    sub = sub[sub["ri_task_thinking_tokens"].notna()].copy()

    if len(sub) < _MIN_TURNS_FOR_MIXEDLM:
        logger.info(
            "TC Model A skipped: %d Cell 0 rows < %d.",
            len(sub),
            _MIN_TURNS_FOR_MIXEDLM,
        )
        return _empty_result("cell0")

    sub["ri_task"] = sub["ri_task_thinking_tokens"].astype(float)
    sub["turn"] = sub["turn_number"].astype(int)

    try:
        model = smf.mixedlm(
            "ri_task ~ correct_prev + turn",
            data=sub,
            groups=sub["session_id"],
        )
        res = model.fit(reml=True, method=["lbfgs"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("TC Model A fit failed: %s", exc)
        return _empty_result("cell0")

    fe, se, pv = res.fe_params, res.bse, res.pvalues
    nan = float("nan")
    return TCRegressionResult(
        model_label="cell0",
        n_obs=len(sub),
        n_sessions=int(sub["session_id"].nunique()),
        beta_correct=float(fe.get("correct_prev", nan)),
        se_correct=float(se.get("correct_prev", nan)),
        p_correct=float(pv.get("correct_prev", nan)),
        beta_framing=nan,
        se_framing=nan,
        p_framing=nan,
        beta_interaction=nan,
        se_interaction=nan,
        p_interaction=nan,
        beta_score=nan,
        se_score=nan,
        p_score=nan,
        beta_turn=float(fe.get("turn", nan)),
        se_turn=float(se.get("turn", nan)),
        p_turn=float(pv.get("turn", nan)),
        converged=bool(getattr(res, "converged", True)),
    )


# ---------------------------------------------------------------------------
# Model B — Allowed cells (framing modulation)
# ---------------------------------------------------------------------------


def fit_tc_rule_mastery_allowed(
    turn_df: pd.DataFrame,
) -> TCRegressionResult | None:
    """Fit the §6.3 Model B mixedLM on allowed cells (1-4).

    Specification:
        ``ri_task ~ correct_prev * framing_corruption + score + turn
                  + (1|session)``

    The framing × correct_prev interaction (``β_CF``) tests robustness
    of the TC dynamic across SD-active framings. ``β_S`` separates the
    score-confound (correct ↔ score mechanical correlation).
    """
    try:
        import statsmodels.api as sm  # noqa: F401
        import statsmodels.formula.api as smf
    except ImportError:
        logger.info("statsmodels not installed; skipping TC Model B fit.")
        return None

    if turn_df.empty:
        return _empty_result("allowed")

    sub = turn_df[
        turn_df["framing"].isin(_ALLOWED_FRAMINGS)
        & turn_df["ri_task_thinking_tokens"].notna()
    ].copy()
    sub = add_correct_prev(sub)
    sub = sub[sub["ri_task_thinking_tokens"].notna()].copy()

    if len(sub) < _MIN_TURNS_FOR_MIXEDLM:
        logger.info(
            "TC Model B skipped: %d allowed-framing rows < %d.",
            len(sub),
            _MIN_TURNS_FOR_MIXEDLM,
        )
        return _empty_result("allowed")

    sub["ri_task"] = sub["ri_task_thinking_tokens"].astype(float)
    sub["framing_corruption"] = (
        sub["framing"] == _CORRUPTION_FRAMING
    ).astype(int)
    sub["score"] = pd.to_numeric(
        sub["score_before_turn"], errors="coerce"
    ).astype(float)
    sub["turn"] = sub["turn_number"].astype(int)
    sub = sub.dropna(subset=["score", "ri_task", "correct_prev"]).copy()

    if len(sub) < _MIN_TURNS_FOR_MIXEDLM:
        return _empty_result("allowed")

    try:
        model = smf.mixedlm(
            "ri_task ~ correct_prev * framing_corruption + score + turn",
            data=sub,
            groups=sub["session_id"],
        )
        res = model.fit(reml=True, method=["lbfgs"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("TC Model B fit failed: %s", exc)
        return _empty_result("allowed")

    fe, se, pv = res.fe_params, res.bse, res.pvalues
    nan = float("nan")
    return TCRegressionResult(
        model_label="allowed",
        n_obs=len(sub),
        n_sessions=int(sub["session_id"].nunique()),
        beta_correct=float(fe.get("correct_prev", nan)),
        se_correct=float(se.get("correct_prev", nan)),
        p_correct=float(pv.get("correct_prev", nan)),
        beta_framing=float(fe.get("framing_corruption", nan)),
        se_framing=float(se.get("framing_corruption", nan)),
        p_framing=float(pv.get("framing_corruption", nan)),
        beta_interaction=float(
            fe.get("correct_prev:framing_corruption", nan)
        ),
        se_interaction=float(
            se.get("correct_prev:framing_corruption", nan)
        ),
        p_interaction=float(
            pv.get("correct_prev:framing_corruption", nan)
        ),
        beta_score=float(fe.get("score", nan)),
        se_score=float(se.get("score", nan)),
        p_score=float(pv.get("score", nan)),
        beta_turn=float(fe.get("turn", nan)),
        se_turn=float(se.get("turn", nan)),
        p_turn=float(pv.get("turn", nan)),
        converged=bool(getattr(res, "converged", True)),
    )


# ---------------------------------------------------------------------------
# V2 — Reverse causality check
# ---------------------------------------------------------------------------


def fit_tc_reverse_check(
    turn_df: pd.DataFrame,
    *,
    cells: Iterable[int] | None = None,
) -> TCReverseCheckResult | None:
    """V2 (§6.5): logistic ``correct[t] ~ ri_task[t] + turn``.

    A significant positive ``alpha_R`` indicates the alternative arc
    (thinking → correct) is alive — interpretation note for β_C from
    Model A / B (residual endogeneity from session competence).

    ``cells`` filters to specific cell_id values when supplied (default:
    all cells with non-null ri_task_thinking_tokens).
    """
    try:
        import statsmodels.api as sm  # noqa: F401
        import statsmodels.formula.api as smf
    except ImportError:
        return None

    if turn_df.empty:
        return None

    sub = turn_df[turn_df["ri_task_thinking_tokens"].notna()].copy()
    if cells is not None:
        cell_set = set(int(c) for c in cells)
        sub = sub[sub["cell_id"].isin(cell_set)].copy()
    sub = sub.dropna(subset=["task_success_factor"]).copy()
    if len(sub) < _MIN_TURNS_FOR_MIXEDLM:
        return None

    sub["correct"] = (
        pd.to_numeric(sub["task_success_factor"], errors="coerce") == 1.0
    ).astype(int)
    sub["ri_task"] = sub["ri_task_thinking_tokens"].astype(float)
    sub["turn"] = sub["turn_number"].astype(int)

    # statsmodels Logit (no random effect — too small per session for
    # GLMM; use cluster-robust SE on session_id instead).
    try:
        formula = "correct ~ ri_task + turn"
        model = smf.logit(formula, data=sub)
        res = model.fit(disp=False, maxiter=200)
    except Exception as exc:  # noqa: BLE001
        logger.warning("TC reverse-causality logit failed: %s", exc)
        return None

    fe, se, pv = res.params, res.bse, res.pvalues
    return TCReverseCheckResult(
        n_obs=len(sub),
        n_sessions=int(sub["session_id"].nunique()),
        alpha_R=float(fe.get("ri_task", float("nan"))),
        se_R=float(se.get("ri_task", float("nan"))),
        p_R=float(pv.get("ri_task", float("nan"))),
        alpha_turn=float(fe.get("turn", float("nan"))),
        converged=bool(getattr(res, "mle_retvals", {}).get(
            "converged", True
        )),
    )


# ---------------------------------------------------------------------------
# V6 — Streak robustness (rolling correct rate)
# ---------------------------------------------------------------------------


def fit_tc_streak_robustness(
    turn_df: pd.DataFrame,
    *,
    window: int = 3,
    cell0_only: bool = True,
) -> TCRegressionResult | None:
    """V6 (§6.5): replace ``correct_prev`` with rolling correct rate.

    Specification (Cell 0 default):
        ``ri_task ~ rolling_correct + turn + (1|session)``

    ``rolling_correct[t]`` = mean of ``task_success_factor`` over turns
    ``[t-window, t-1]`` (lagged window). When ``cell0_only=False`` the
    fit extends to all allowed framings with ``framing_corruption`` and
    ``score`` covariates added (sister of Model B).
    """
    try:
        import statsmodels.api as sm  # noqa: F401
        import statsmodels.formula.api as smf
    except ImportError:
        return None

    if turn_df.empty:
        return None

    if cell0_only:
        sub = turn_df[
            (turn_df["framing"] == _CELL0_FRAMING)
            & (turn_df["forfeit_condition"] == _CELL0_FORFEIT)
            & turn_df["ri_task_thinking_tokens"].notna()
        ].copy()
        label = f"streak_cell0_w{window}"
    else:
        sub = turn_df[
            turn_df["framing"].isin(_ALLOWED_FRAMINGS)
            & turn_df["ri_task_thinking_tokens"].notna()
        ].copy()
        label = f"streak_allowed_w{window}"

    if sub.empty:
        return _empty_result(label)

    sub = sub.sort_values(["session_id", "turn_number"]).copy()
    sub["task_success_factor"] = pd.to_numeric(
        sub["task_success_factor"], errors="coerce"
    )
    # Rolling mean over turns (t-window) ... (t-1) — closed left, no t.
    grp = sub.groupby("session_id")["task_success_factor"]
    sub["rolling_correct"] = grp.transform(
        lambda s: s.shift(1).rolling(window=window, min_periods=1).mean()
    )
    sub = sub.dropna(subset=["rolling_correct"]).copy()
    if len(sub) < _MIN_TURNS_FOR_MIXEDLM:
        return _empty_result(label)

    sub["ri_task"] = sub["ri_task_thinking_tokens"].astype(float)
    sub["turn"] = sub["turn_number"].astype(int)

    if cell0_only:
        formula = "ri_task ~ rolling_correct + turn"
    else:
        sub["framing_corruption"] = (
            sub["framing"] == _CORRUPTION_FRAMING
        ).astype(int)
        sub["score"] = pd.to_numeric(
            sub["score_before_turn"], errors="coerce"
        ).astype(float)
        sub = sub.dropna(subset=["score"]).copy()
        formula = (
            "ri_task ~ rolling_correct * framing_corruption + score + turn"
        )

    try:
        model = smf.mixedlm(formula, data=sub, groups=sub["session_id"])
        res = model.fit(reml=True, method=["lbfgs"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("TC streak (V6) fit failed: %s", exc)
        return _empty_result(label)

    fe, se, pv = res.fe_params, res.bse, res.pvalues
    nan = float("nan")
    return TCRegressionResult(
        model_label=label,
        n_obs=len(sub),
        n_sessions=int(sub["session_id"].nunique()),
        beta_correct=float(fe.get("rolling_correct", nan)),
        se_correct=float(se.get("rolling_correct", nan)),
        p_correct=float(pv.get("rolling_correct", nan)),
        beta_framing=float(fe.get("framing_corruption", nan)),
        se_framing=float(se.get("framing_corruption", nan)),
        p_framing=float(pv.get("framing_corruption", nan)),
        beta_interaction=float(
            fe.get("rolling_correct:framing_corruption", nan)
        ),
        se_interaction=float(
            se.get("rolling_correct:framing_corruption", nan)
        ),
        p_interaction=float(
            pv.get("rolling_correct:framing_corruption", nan)
        ),
        beta_score=float(fe.get("score", nan)),
        se_score=float(se.get("score", nan)),
        p_score=float(pv.get("score", nan)),
        beta_turn=float(fe.get("turn", nan)),
        se_turn=float(se.get("turn", nan)),
        p_turn=float(pv.get("turn", nan)),
        converged=bool(getattr(res, "converged", True)),
    )


# ---------------------------------------------------------------------------
# §6.7 v7 — Cox PH with rule_match-based M covariate
# ---------------------------------------------------------------------------


def fit_tc_cox_rule_mastery(
    turn_df: pd.DataFrame,
    *,
    threshold: float = 90.0,
    regime: str | None = None,
) -> TCCoxResult | None:
    """§6.7 v7: Cox PH on Cells 1+3 with rule-mastery covariate.

    Specification:
        ``λ(t|X) = λ₀(t) · exp(β_F · 1_FC + β_S · S(t-1)
                              + β_M · M(t-1))``

    where ``M(t-1) = 1{rule_match_score[t-1] >= threshold}``.

    Sister of :func:`forfeit_survival.fit_cox_forfeit_survival` — same
    framing / score covariates so β_F / β_S remain interpretable
    relative to §1. The ``M`` covariate is the **objective**
    rule-mastery indicator (subjective ``correct[t-1]`` is in §6 main).

    Parameters
    ----------
    turn_df : pd.DataFrame
        Per-turn frame produced by ``turn_observations`` (or the on-disk
        ``unit14_turn_observations.csv``).
    threshold : float
        Cut-off for rule_match_score to count as mastered. Default 90.0
        — the §6.7 specification.
    regime : str | None
        When set (e.g. ``"no_cap"``) and a ``regime`` column exists,
        filter long-format turn rows to that regime before fitting.
        Default ``None`` — use all rows. Note: §1 Cox uses no_cap;
        keeping the default ``None`` here lets the caller align with
        whatever §1 used in the same run by supplying ``regime``.

    Returns ``None`` when ``lifelines`` is unavailable or the resulting
    sample is empty / too small for a stable fit.
    """
    try:
        from lifelines import CoxTimeVaryingFitter
    except ImportError:
        logger.info("lifelines not installed; skipping §6.7 Cox fit.")
        return None

    if turn_df.empty or "rule_match_score" not in turn_df.columns:
        return None

    sub = turn_df[
        (turn_df["forfeit_condition"] == "allowed")
        & turn_df["framing"].isin(_ALLOWED_FRAMINGS)
        & turn_df["score_before_turn"].notna()
    ].copy()
    if regime is not None and "regime" in sub.columns:
        sub = sub[sub["regime"] == regime].copy()
    if sub.empty:
        return None

    sub = add_rule_match_prev(sub, threshold=threshold)
    if sub.empty:
        return None

    sub["framing_is_FC"] = (sub["framing"] == _CORRUPTION_FRAMING).astype(int)
    sub["score_prev"] = pd.to_numeric(
        sub["score_before_turn"], errors="coerce"
    ).astype(float)
    sub = sub.dropna(subset=["score_prev"]).copy()

    sub["start"] = sub["turn_number"].astype(int) - 1
    sub["stop"] = sub["turn_number"].astype(int)
    sub["event"] = sub["forfeit"].astype(int)

    fit_cols = [
        "session_id",
        "start",
        "stop",
        "event",
        "framing_is_FC",
        "score_prev",
        "M_prev",
    ]
    fit_data = sub[fit_cols].copy()

    n_events = int(fit_data["event"].sum())
    n_sessions = int(fit_data["session_id"].nunique())
    n_M_active = int((fit_data["M_prev"] == 1).sum())

    if n_events == 0 or n_M_active == 0:
        # M covariate has zero variance OR no events → unidentifiable
        return TCCoxResult(
            threshold=threshold,
            n_sessions=n_sessions,
            n_events=n_events,
            n_M_active_intervals=n_M_active,
            hr_framing=float("nan"),
            hr_framing_ci_low=float("nan"),
            hr_framing_ci_high=float("nan"),
            p_framing=float("nan"),
            hr_score=float("nan"),
            hr_score_ci_low=float("nan"),
            hr_score_ci_high=float("nan"),
            p_score=float("nan"),
            hr_M=float("nan"),
            hr_M_ci_low=float("nan"),
            hr_M_ci_high=float("nan"),
            p_M=float("nan"),
            underpowered=True,
        )

    try:
        ctv = CoxTimeVaryingFitter()
        ctv.fit(
            fit_data,
            id_col="session_id",
            event_col="event",
            start_col="start",
            stop_col="stop",
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("§6.7 Cox PH fit failed: %s", exc)
        return None

    smry = ctv.summary
    nan = float("nan")

    def _row(name: str, col: str) -> float:
        try:
            return float(smry.loc[name, col])
        except (KeyError, ValueError):
            return nan

    return TCCoxResult(
        threshold=threshold,
        n_sessions=n_sessions,
        n_events=n_events,
        n_M_active_intervals=n_M_active,
        hr_framing=_row("framing_is_FC", "exp(coef)"),
        hr_framing_ci_low=_row("framing_is_FC", "exp(coef) lower 95%"),
        hr_framing_ci_high=_row("framing_is_FC", "exp(coef) upper 95%"),
        p_framing=_row("framing_is_FC", "p"),
        hr_score=_row("score_prev", "exp(coef)"),
        hr_score_ci_low=_row("score_prev", "exp(coef) lower 95%"),
        hr_score_ci_high=_row("score_prev", "exp(coef) upper 95%"),
        p_score=_row("score_prev", "p"),
        hr_M=_row("M_prev", "exp(coef)"),
        hr_M_ci_low=_row("M_prev", "exp(coef) lower 95%"),
        hr_M_ci_high=_row("M_prev", "exp(coef) upper 95%"),
        p_M=_row("M_prev", "p"),
        underpowered=n_events < _MIN_EVENTS_FOR_COX,
    )


# ---------------------------------------------------------------------------
# Discovery-timing alignment (V3) — descriptive helper
# ---------------------------------------------------------------------------


def discovery_timing_alignment(
    turn_df: pd.DataFrame,
    *,
    rule_match_target: float = 100.0,
    stable_streak: int = 2,
) -> dict:
    """V3 (§6.5): summarise the turn at which sessions reach stable
    rule-mastery.

    Returns a dict ``{cell_id: {"t_star_mean": float, "n_discoverers":
    int, "n_total_sessions": int}}`` for inspection alongside Model A
    β_C interpretation. ``t_star`` is the first turn where
    ``rule_match_score`` reaches ``rule_match_target`` and stays there
    for ``stable_streak`` consecutive turns.
    """
    if turn_df.empty or "rule_match_score" not in turn_df.columns:
        return {}

    out: dict = {}
    for cell, grp in turn_df.dropna(subset=["cell_id"]).groupby("cell_id"):
        cell_int = int(cell)
        ts: list[int] = []
        for sid, ses in grp.groupby("session_id"):
            ses = ses.sort_values("turn_number")
            scores = ses["rule_match_score"].fillna(-1.0).tolist()
            turns = ses["turn_number"].tolist()
            for i in range(len(scores) - stable_streak + 1):
                if all(
                    scores[j] >= rule_match_target
                    for j in range(i, i + stable_streak)
                ):
                    ts.append(int(turns[i]))
                    break
        n_total = int(grp["session_id"].nunique())
        out[cell_int] = {
            "t_star_mean": float(np.mean(ts)) if ts else float("nan"),
            "t_star_median": float(np.median(ts)) if ts else float("nan"),
            "n_discoverers": len(ts),
            "n_total_sessions": n_total,
        }
    return out


def beta_C_by_phase(
    turn_df: pd.DataFrame,
    *,
    rule_match_target: float = 100.0,
    stable_streak: int = 2,
) -> dict:
    """V3 secondary: split Cell 0 turns into pre-/post-discovery and
    fit Model A separately on each subset.

    Returns ``{"pre": TCRegressionResult | None, "post": ...}``.
    ``pre`` = turns with ``turn_number < t_star`` (per-session
    discovery turn); ``post`` = turns with ``turn_number >= t_star``.

    A TC-aligned signal would show |β_C(post)| > |β_C(pre)|: rule
    mastery happens after t_star, so the cognitive disengagement
    response should concentrate there.
    """
    if turn_df.empty or "rule_match_score" not in turn_df.columns:
        return {"pre": None, "post": None}

    cell0 = turn_df[
        (turn_df["framing"] == _CELL0_FRAMING)
        & (turn_df["forfeit_condition"] == _CELL0_FORFEIT)
    ].copy()
    if cell0.empty:
        return {"pre": None, "post": None}

    # Per-session t_star
    t_star: dict = {}
    for sid, ses in cell0.groupby("session_id"):
        ses = ses.sort_values("turn_number")
        scores = ses["rule_match_score"].fillna(-1.0).tolist()
        turns = ses["turn_number"].tolist()
        t_star[sid] = None
        for i in range(len(scores) - stable_streak + 1):
            if all(
                scores[j] >= rule_match_target
                for j in range(i, i + stable_streak)
            ):
                t_star[sid] = int(turns[i])
                break

    cell0["t_star"] = cell0["session_id"].map(t_star)

    pre = cell0[
        cell0["t_star"].notna() & (cell0["turn_number"] < cell0["t_star"])
    ].copy()
    post = cell0[
        cell0["t_star"].notna()
        & (cell0["turn_number"] >= cell0["t_star"])
    ].copy()

    return {
        "pre": fit_tc_rule_mastery_cell0(pre) if not pre.empty else None,
        "post": fit_tc_rule_mastery_cell0(post) if not post.empty else None,
        "n_discoverers": int(sum(1 for v in t_star.values() if v is not None)),
        "n_sessions": int(cell0["session_id"].nunique()),
    }


# ---------------------------------------------------------------------------
# Driver — single-call orchestration
# ---------------------------------------------------------------------------


def run_all_tc_indicators(
    turn_df: pd.DataFrame,
    *,
    rule_match_threshold: float = 90.0,
    regime: str | None = None,
) -> dict:
    """Run §6 + §6.7 pipeline on a single model's per-turn frame.

    Returns a payload dict suitable for JSON dump:
        {
            "model_a": TCRegressionResult.summary_dict() | None,
            "model_b": TCRegressionResult.summary_dict() | None,
            "v2_reverse": TCReverseCheckResult.summary_dict() | None,
            "v6_streak_cell0": ... | None,
            "v3_timing_alignment": {...},
            "v3_beta_phase_split": {...},
            "v7_cox": TCCoxResult.summary_dict() | None,
            "n_total_turns": int,
        }
    """
    payload: dict = {}

    a = fit_tc_rule_mastery_cell0(turn_df)
    payload["model_a"] = a.summary_dict() if a is not None else None

    b = fit_tc_rule_mastery_allowed(turn_df)
    payload["model_b"] = b.summary_dict() if b is not None else None

    v2 = fit_tc_reverse_check(turn_df)
    payload["v2_reverse"] = v2.summary_dict() if v2 is not None else None

    v6 = fit_tc_streak_robustness(turn_df)
    payload["v6_streak_cell0"] = (
        v6.summary_dict() if v6 is not None else None
    )

    payload["v3_timing_alignment"] = discovery_timing_alignment(turn_df)
    payload["v3_beta_phase_split"] = {
        k: (v.summary_dict() if hasattr(v, "summary_dict") else v)
        for k, v in beta_C_by_phase(turn_df).items()
    }

    cox = fit_tc_cox_rule_mastery(
        turn_df,
        threshold=rule_match_threshold,
        regime=regime,
    )
    payload["v7_cox"] = cox.summary_dict() if cox is not None else None

    payload["n_total_turns"] = int(len(turn_df))
    return payload
