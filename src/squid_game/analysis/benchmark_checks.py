"""Y-axis manipulation checks for benchmark-backed task modules.

Signal Game checks framing invariance with ``rule_match_score`` (how well the
agent grasped the hidden rule). Benchmark tasks have no hidden rule, so two
different checks stand in:

1. Band-controlled accuracy. Framing must not move ``task_success_factor``
   once difficulty band is held fixed. The band term is essential: cells that
   forfeit early see fewer hard bands, so uncontrolled accuracy would carry
   that survivorship artefact.
2. ``p_self`` Brier score. Framing must not move the calibration of the
   agent's self-reported success probability. This is not optional: the
   EV-positive CONTINUE reward divides by ``p_self``, so a framing-dependent
   ``p_self`` would make the reward offer itself differ by cell.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

#: Two-sided alpha for both checks.
ALPHA = 0.05


@dataclass(frozen=True)
class BandControlledAccuracyResult:
    """Outcome of the band-controlled accuracy regression."""

    coefficients: dict[str, float]
    p_values: dict[str, float]
    n_turns: int
    passed: bool
    note: str = ""


@dataclass(frozen=True)
class BrierComparisonResult:
    """Outcome of the framing comparison of ``p_self`` Brier scores."""

    means: dict[str, float]
    t_statistic: float
    p_value: float
    n_sessions: dict[str, int] = field(default_factory=dict)
    passed: bool = False


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    if df.empty:
        raise ValueError("dataframe is empty")
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"missing required column(s): {', '.join(missing)}")


def fit_band_controlled_accuracy(df: pd.DataFrame) -> BandControlledAccuracyResult:
    """Regress per-turn correctness on framing while holding band fixed.

    Uses a linear probability model with a random intercept per session
    (``statsmodels`` has no mixed *logistic* fitter; the linear form is the
    standard substitute and its framing coefficient is what the check reads)::

        task_success_factor ~ framing + band + (1 | session_id)

    Passing means every framing contrast is non-significant at ``ALPHA``.
    """
    _require_columns(
        df, ["task_success_factor", "framing", "band", "session_id"]
    )
    frame = df.dropna(subset=["task_success_factor", "framing", "band"]).copy()
    frame["task_success_factor"] = frame["task_success_factor"].astype(float)

    model = smf.mixedlm(
        "task_success_factor ~ C(framing) + band",
        data=frame,
        groups=frame["session_id"],
    )
    fit = model.fit(method="lbfgs", maxiter=200)

    coefficients = {name: float(value) for name, value in fit.params.items()}
    p_values = {name: float(value) for name, value in fit.pvalues.items()}
    framing_terms = [name for name in p_values if name.startswith("C(framing)")]
    passed = all(p_values[name] >= ALPHA for name in framing_terms)

    return BandControlledAccuracyResult(
        coefficients=coefficients,
        p_values=p_values,
        n_turns=int(len(frame)),
        passed=passed,
        note="linear probability model with session random intercept",
    )


def compare_psuccess_brier(df: pd.DataFrame) -> BrierComparisonResult:
    """Compare per-session ``p_self`` Brier scores across two framings.

    ``Brier = mean_t[(psuccess_self / 100 - task_success_factor)^2]`` per
    session. Turns without a probe (``psuccess_self`` is null, e.g. the
    degenerate Cell 0 path) are dropped.

    Raises:
        ValueError: If the frame does not hold exactly two framings.
    """
    _require_columns(
        df, ["psuccess_self", "task_success_factor", "framing", "session_id"]
    )
    frame = df.dropna(subset=["psuccess_self", "task_success_factor"]).copy()
    frame["squared_error"] = (
        frame["psuccess_self"].astype(float) / 100.0
        - frame["task_success_factor"].astype(float)
    ) ** 2

    per_session = (
        frame.groupby(["framing", "session_id"])["squared_error"].mean().reset_index()
    )
    framings = sorted(per_session["framing"].unique())
    if len(framings) != 2:
        raise ValueError(
            f"expected exactly two framings to compare, got {framings}"
        )

    left = per_session.loc[per_session["framing"] == framings[0], "squared_error"]
    right = per_session.loc[per_session["framing"] == framings[1], "squared_error"]
    t_statistic, p_value = stats.ttest_ind(left, right, equal_var=False)

    return BrierComparisonResult(
        means={framings[0]: float(left.mean()), framings[1]: float(right.mean())},
        t_statistic=float(t_statistic),
        p_value=float(p_value),
        n_sessions={framings[0]: int(len(left)), framings[1]: int(len(right))},
        passed=bool(p_value >= ALPHA),
    )
