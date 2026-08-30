"""Phase O Unit 15 analysis — choice-asymmetric H2 cognitive model.

Operates on the turn-level frame built by
:func:`squid_game.analysis.shared.loaders.turn_observations` and fits the
Split-Call H2 mixed-effects models on the ``ri_task`` / ``ri_forfeit``
thinking-token channels:

1. ``fit_choice_asymmetric_model`` — primary H2 test on RI_forfeit:
   ``ri_forfeit ~ choice * framing + score + turn + (1|session)``
   (H_choice_asymmetric, spec §5.1).
2. ``fit_task_spillover_model`` — secondary R1/H_task_spillover
   cross-check on RI_task.
3. ``unit15_descriptive_summary`` — per-cell mean RI_task / RI_forfeit
   descriptive block.
4. ``run_all_unit15_hypotheses`` — driver that composes the flat
   payload consumed by the analysis markdown renderer.

Backward compat: all functions return ``None`` (or empty DataFrames)
when their input is insufficient. The analysis module must never crash
the pipeline; missing optional dependencies degrade gracefully.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-15-split-forfeit-layer.md``
§5.1.

This module was ``forfeit_regression.py`` until the 2026-08-30 channel
split (P2 Task 4): ``turn_observations`` / ``forfeit_events`` moved to
:mod:`squid_game.analysis.shared.loaders` (consumed by every channel),
and the self-report REASON-digit convergence functions (including
``fit_framing_ri_forfeit_continue``) moved to
:mod:`squid_game.analysis.selfreport.reason_convergence`.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

import pandas as pd

from squid_game.analysis.shared.loaders import _MIN_TURNS_FOR_LOGIT, turn_observations
from squid_game.models.enums import ForfeitCondition
from squid_game.models.results import SeasonResult

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Phase O Unit 15 — Choice-asymmetric mixed-effects model
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ChoiceAsymmetricResult:
    """Parsed summary of the Unit 15 mixedLM fit.

    Model:
        ``RI_forfeit ~ choice_binary * framing_corruption + score +
        turn + (1|session)``, fit on allowed cells only (forfeit
        choice has variance there). ``beta_interaction`` is the primary
        test — spec §2.1 H_choice_asymmetric predicts β_3 > 0.
    """

    n_obs: int
    n_sessions: int
    n_forfeit: int
    beta_choice: float
    se_choice: float
    p_choice: float
    beta_framing: float
    se_framing: float
    p_framing: float
    beta_interaction: float
    se_interaction: float
    p_interaction: float
    # Unit 15 v2 (2026-04-22 bug-fix): covariates included so the
    # renderer can print β_score / β_turn alongside the interaction.
    # Before this fix ``_render_unit15_md`` KeyError'd on ``beta_score``.
    beta_score: float
    beta_turn: float
    converged: bool

    def summary_dict(self) -> dict:
        return {
            "n_obs": self.n_obs,
            "n_sessions": self.n_sessions,
            "n_forfeit": self.n_forfeit,
            "beta_choice": self.beta_choice,
            "se_choice": self.se_choice,
            "p_choice": self.p_choice,
            "beta_framing": self.beta_framing,
            "se_framing": self.se_framing,
            "p_framing": self.p_framing,
            "beta_interaction": self.beta_interaction,
            "se_interaction": self.se_interaction,
            "p_interaction": self.p_interaction,
            "beta_score": self.beta_score,
            "beta_turn": self.beta_turn,
            "converged": self.converged,
        }


def fit_choice_asymmetric_model(
    turn_df: pd.DataFrame,
) -> ChoiceAsymmetricResult | None:
    """Fit the Unit 15 mixed-effects interaction model on RI_forfeit.

    Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-15-split-forfeit-layer.md``
    §5.1.

    Returns ``None`` when:
    - statsmodels is not installed,
    - the DataFrame has no ``ri_forfeit_thinking_tokens`` column,
    - fewer than ``_MIN_TURNS_FOR_LOGIT`` rows remain after filtering
      (allowed cells × non-null ``ri_forfeit_thinking_tokens``),
    - both choice classes are not represented,
    - the fit fails / does not converge.

    The caller writes the returned result into ``unit15_results.md``.
    """
    try:
        import statsmodels.api as sm  # noqa: F401 - used for version gate
        import statsmodels.formula.api as smf
    except ImportError:
        logger.info(
            "statsmodels not installed; skipping Unit 15 mixedLM fit."
        )
        return None

    if turn_df.empty or "ri_forfeit_thinking_tokens" not in turn_df.columns:
        return None

    sub = turn_df[
        (turn_df["forfeit_condition"] == ForfeitCondition.ALLOWED.value)
        & (turn_df["is_corruption"] | turn_df["is_baseline_flagship"])
        & turn_df["ri_forfeit_thinking_tokens"].notna()
    ].copy()
    if len(sub) < _MIN_TURNS_FOR_LOGIT:
        logger.info(
            "Unit 15 mixedLM skipped: %d split-call allowed rows < %d.",
            len(sub),
            _MIN_TURNS_FOR_LOGIT,
        )
        return None

    sub["choice_binary"] = sub["forfeit"].astype(int)
    sub["framing_corruption"] = sub["is_corruption"].astype(int)
    sub["ri_forfeit"] = sub["ri_forfeit_thinking_tokens"].astype(float)
    sub["score"] = sub["score_before_turn"].astype(float)
    sub["turn"] = sub["turn_number"].astype(int)

    choice_classes = set(sub["choice_binary"].unique())
    if not {0, 1}.issubset(choice_classes):
        logger.info(
            "Unit 15 mixedLM skipped: only choice class %s present.",
            choice_classes,
        )
        return None

    # MixedLM with a session-level random intercept; the within-subject
    # design is the point of the model (spec §5.1). We fit via the
    # formula API for clarity of the interaction term.
    try:
        model = smf.mixedlm(
            "ri_forfeit ~ choice_binary * framing_corruption + score + turn",
            data=sub,
            groups=sub["session_id"],
        )
        result = model.fit(reml=True, method=["lbfgs"])
    except Exception as exc:  # noqa: BLE001 - defensive
        logger.warning("Unit 15 mixedLM fit failed: %s", exc)
        return None

    fe = result.fe_params
    se = result.bse
    pv = result.pvalues
    key_int = "choice_binary:framing_corruption"
    return ChoiceAsymmetricResult(
        n_obs=len(sub),
        n_sessions=int(sub["session_id"].nunique()),
        n_forfeit=int(sub["choice_binary"].sum()),
        beta_choice=float(fe.get("choice_binary", float("nan"))),
        se_choice=float(se.get("choice_binary", float("nan"))),
        p_choice=float(pv.get("choice_binary", float("nan"))),
        beta_framing=float(fe.get("framing_corruption", float("nan"))),
        se_framing=float(se.get("framing_corruption", float("nan"))),
        p_framing=float(pv.get("framing_corruption", float("nan"))),
        beta_interaction=float(fe.get(key_int, float("nan"))),
        se_interaction=float(se.get(key_int, float("nan"))),
        p_interaction=float(pv.get(key_int, float("nan"))),
        beta_score=float(fe.get("score", float("nan"))),
        beta_turn=float(fe.get("turn", float("nan"))),
        converged=bool(result.converged) if hasattr(result, "converged") else True,
    )


@dataclass(frozen=True)
class TaskSpilloverResult:
    """Parsed summary of the Unit 15 secondary mixedLM on RI_task.

    Model:
        ``RI_task ~ framing_corruption + turn + score + forfeit_allowed
          + (1|session)``, fit on Unit 15 split-call rows excluding
        ``true_baseline`` (Cell 0, framing pair not comparable).

    Interpretation (H_task_spillover, secondary SD proxy):
        β_framing > 0, p < 0.05 → threat framing increases task-layer
        reasoning even though rule-inference is instrumentally irrelevant
        to survival. Direct evidence of framing spillover into reasoning
        that does not affect p_death. Weaker SD claim than the primary
        H_choice_asymmetric (§5.1) because β_framing > 0 on RI_task is
        consistent with anxiety / attention-shift / RLHF-careful in
        addition to SD. Use as cross-check, not standalone SD proof.
    """

    n_obs: int
    n_sessions: int
    beta_framing: float
    se_framing: float
    p_framing: float
    beta_turn: float
    se_turn: float
    p_turn: float
    beta_score: float
    se_score: float
    p_score: float
    beta_forfeit_allowed: float
    se_forfeit_allowed: float
    p_forfeit_allowed: float
    converged: bool

    def summary_dict(self) -> dict:
        return {
            "n_obs": self.n_obs,
            "n_sessions": self.n_sessions,
            "beta_framing": self.beta_framing,
            "se_framing": self.se_framing,
            "p_framing": self.p_framing,
            "beta_turn": self.beta_turn,
            "se_turn": self.se_turn,
            "p_turn": self.p_turn,
            "beta_score": self.beta_score,
            "se_score": self.se_score,
            "p_score": self.p_score,
            "beta_forfeit_allowed": self.beta_forfeit_allowed,
            "se_forfeit_allowed": self.se_forfeit_allowed,
            "p_forfeit_allowed": self.p_forfeit_allowed,
            "converged": self.converged,
        }


def fit_task_spillover_model(
    turn_df: pd.DataFrame,
) -> TaskSpilloverResult | None:
    """Fit the Unit 15 secondary mixedLM on RI_task.

    Hypothesis H_task_spillover (spec §2.2, positive form of
    H_task_invariance): does threat framing increase Call 1 task-layer
    reasoning tokens even though rule-inference does not change the
    random p_death draw? A positive ``β_framing`` would be framing-
    spillover evidence — weaker than the primary H_choice_asymmetric
    signal (confounded with anxiety / attention-shift) but a useful
    cross-check that lets reviewers distinguish between:

    - primary n.s. + secondary sig. → "framing works but doesn't hit
      choice; H_no_SD supported, framing might be working through a
      non-SD channel like anxiety";
    - primary sig. + secondary sig. → "framing spills widely; both
      task-reasoning and choice-deliberation affected";
    - primary sig. + secondary n.s. → **cleanest SD signature**:
      framing affects ONLY the choice layer, not upstream task
      reasoning → H_choice_asymmetric's identification is sharpest.

    Returns ``None`` when:
    - statsmodels is not installed,
    - no ``ri_task_thinking_tokens`` column is present,
    - fewer than ``_MIN_TURNS_FOR_LOGIT`` rows remain after filtering
      (non-null ri_task, excluding true_baseline),
    - the fit fails / does not converge.

    Data scope: split-call rows (non-null ``ri_task_thinking_tokens``)
    in corruption OR baseline_flagship cells. Both ALLOWED and
    NOT_ALLOWED are included — forfeit_condition is entered as a
    covariate so the framing main effect is within-condition isolated.
    ``true_baseline`` is excluded because it shares neither of the
    compared framings.
    """
    try:
        import statsmodels.api as sm  # noqa: F401 - version gate
        import statsmodels.formula.api as smf
    except ImportError:
        logger.info(
            "statsmodels not installed; skipping Unit 15 task-spillover fit."
        )
        return None

    if turn_df.empty or "ri_task_thinking_tokens" not in turn_df.columns:
        return None

    sub = turn_df[
        (turn_df["is_corruption"] | turn_df["is_baseline_flagship"])
        & turn_df["ri_task_thinking_tokens"].notna()
    ].copy()
    if len(sub) < _MIN_TURNS_FOR_LOGIT:
        logger.info(
            "Unit 15 task-spillover fit skipped: %d split-call rows < %d.",
            len(sub),
            _MIN_TURNS_FOR_LOGIT,
        )
        return None

    sub["ri_task"] = sub["ri_task_thinking_tokens"].astype(float)
    sub["framing_corruption"] = sub["is_corruption"].astype(int)
    sub["forfeit_allowed_int"] = (
        sub["forfeit_condition"] == ForfeitCondition.ALLOWED.value
    ).astype(int)
    sub["turn"] = sub["turn_number"].astype(int)
    sub["score"] = sub["score_before_turn"].astype(float)

    try:
        model = smf.mixedlm(
            "ri_task ~ framing_corruption + turn + score + forfeit_allowed_int",
            data=sub,
            groups=sub["session_id"],
        )
        result = model.fit(reml=True, method=["lbfgs"])
    except Exception as exc:  # noqa: BLE001 - defensive
        logger.warning("Unit 15 task-spillover mixedLM fit failed: %s", exc)
        return None

    fe = result.fe_params
    se = result.bse
    pv = result.pvalues
    return TaskSpilloverResult(
        n_obs=len(sub),
        n_sessions=int(sub["session_id"].nunique()),
        beta_framing=float(fe.get("framing_corruption", float("nan"))),
        se_framing=float(se.get("framing_corruption", float("nan"))),
        p_framing=float(pv.get("framing_corruption", float("nan"))),
        beta_turn=float(fe.get("turn", float("nan"))),
        se_turn=float(se.get("turn", float("nan"))),
        p_turn=float(pv.get("turn", float("nan"))),
        beta_score=float(fe.get("score", float("nan"))),
        se_score=float(se.get("score", float("nan"))),
        p_score=float(pv.get("score", float("nan"))),
        beta_forfeit_allowed=float(
            fe.get("forfeit_allowed_int", float("nan"))
        ),
        se_forfeit_allowed=float(
            se.get("forfeit_allowed_int", float("nan"))
        ),
        p_forfeit_allowed=float(
            pv.get("forfeit_allowed_int", float("nan"))
        ),
        converged=bool(result.converged) if hasattr(result, "converged") else True,
    )


def unit15_descriptive_summary(
    turn_df: pd.DataFrame,
) -> pd.DataFrame:
    """Per-cell mean RI_task and RI_forfeit (descriptive block).

    Returns a DataFrame indexed by (framing, forfeit_condition) with
    columns ``n_turns``, ``n_forfeit``, ``mean_ri_task``,
    ``mean_ri_forfeit``, ``gap`` (continue-chose RI_forfeit minus
    forfeit-chose RI_forfeit, computed only when both classes present).

    Empty when ``turn_df`` has no Unit 15 columns populated.
    """
    if (
        turn_df.empty
        or "ri_task_thinking_tokens" not in turn_df.columns
        or "ri_forfeit_thinking_tokens" not in turn_df.columns
    ):
        return pd.DataFrame()

    sub = turn_df[turn_df["ri_forfeit_thinking_tokens"].notna()].copy()
    if sub.empty:
        return pd.DataFrame()

    def _gap(group: pd.DataFrame) -> float:
        forfeit_rows = group[group["forfeit"]]
        cont_rows = group[~group["forfeit"]]
        if forfeit_rows.empty or cont_rows.empty:
            return float("nan")
        return float(
            cont_rows["ri_forfeit_thinking_tokens"].mean()
            - forfeit_rows["ri_forfeit_thinking_tokens"].mean()
        )

    rows: list[dict] = []
    grouped = sub.groupby(["framing", "forfeit_condition"], dropna=False)
    for (framing_val, forfeit_cond), group in grouped:
        rows.append(
            {
                "framing": framing_val,
                "forfeit_condition": forfeit_cond,
                "n_turns": int(len(group)),
                "n_forfeit": int(group["forfeit"].sum()),
                "mean_ri_task": float(
                    group["ri_task_thinking_tokens"].mean()
                ),
                "mean_ri_forfeit": float(
                    group["ri_forfeit_thinking_tokens"].mean()
                ),
                "gap": _gap(group),
            }
        )
    return pd.DataFrame(rows).set_index(["framing", "forfeit_condition"])


def run_all_unit15_hypotheses(
    seasons: Sequence[SeasonResult],
) -> dict[str, object]:
    """Compose the Unit 15 analysis payload used by analyze_phase3.

    Extends :func:`run_all_unit14_hypotheses` with split-call-specific
    outputs. Keys in the returned dict:

        - ``turn_df``: per-turn DataFrame — same one Unit 14 uses;
          carries the optional Unit 15 columns ``ri_task_thinking_tokens``
          and ``ri_forfeit_thinking_tokens`` when split rows exist.
        - ``choice_asymmetric``: :class:`ChoiceAsymmetricResult` or
          ``None`` (graceful skip at smoke scale). Primary H_choice_
          asymmetric test on RI_forfeit.
        - ``task_spillover``: :class:`TaskSpilloverResult` or ``None``.
          Secondary H_task_spillover test on RI_task — cross-check that
          the primary interaction term is not swallowed by a whole-
          turn-level framing effect.
        - ``descriptive``: DataFrame from :func:`unit15_descriptive_summary`.
        - ``n_split_turns``: int — rows with non-null
          ``ri_forfeit_thinking_tokens`` (how many split-call turns were
          captured in the run).
    """
    turn_df = turn_observations(seasons)
    choice_asymmetric = fit_choice_asymmetric_model(turn_df)
    task_spillover = fit_task_spillover_model(turn_df)
    descriptive = unit15_descriptive_summary(turn_df)
    if "ri_forfeit_thinking_tokens" in turn_df.columns:
        n_split_turns = int(turn_df["ri_forfeit_thinking_tokens"].notna().sum())
    else:
        n_split_turns = 0
    return {
        "turn_df": turn_df,
        "choice_asymmetric": choice_asymmetric,
        "task_spillover": task_spillover,
        "descriptive": descriptive,
        "n_split_turns": n_split_turns,
    }
