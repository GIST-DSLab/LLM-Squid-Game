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

Both checks report an effect size alongside the significance test but do
**not** gate ``passed`` on it — mirroring this project's own convention for
the R3 Y-axis check (``manipulation_check.check_probe_independence``), where
``passed`` keys purely on ``p_value``, Cohen's *d* is carried on the result
for a human to apply the joint ``p >= alpha AND |d| < 0.2`` criterion when
writing up the paper. Changing what makes a check "pass" is a research
decision; this module reports, it does not decide.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field

import pandas as pd
import statsmodels.formula.api as smf
from scipy import stats

from squid_game.evaluation.shared.manipulation_check import _cohens_d

logger = logging.getLogger(__name__)

#: Two-sided alpha for both checks.
ALPHA = 0.05


@dataclass(frozen=True)
class BandControlledAccuracyResult:
    """Outcome of the band-controlled accuracy regression."""

    coefficients: dict[str, float]
    p_values: dict[str, float]
    n_turns: int
    passed: bool
    # Whether the underlying mixedlm optimizer reported convergence; ``True``
    # when the fitted result exposes no ``converged`` attribute (older
    # statsmodels versions), matching the identical fallback already used at
    # ``forfeit_regression.fit_choice_asymmetric_model`` /
    # ``fit_task_spillover_model``. ``False`` (or a fit landing on a
    # parameter-space boundary, e.g. a near-zero random-effects variance)
    # means the reported p-values/coefficients should be treated with
    # caution even though a result object was still returned.
    converged: bool
    # Session-level Cohen's *d* for each non-reference framing level vs. the
    # reference level (the same level statsmodels/patsy picks as the
    # ``C(framing)`` baseline — the alphabetically-first level), keyed
    # identically to ``p_values``'s ``C(framing)[T.<level>]`` names so a
    # reader can pair each contrast's p-value with its effect size. Reuses
    # ``manipulation_check._cohens_d`` (unbiased, pooled-variance, zeroes on
    # degenerate input) rather than a second implementation.
    effect_sizes: dict[str, float] = field(default_factory=dict)
    note: str = ""


@dataclass(frozen=True)
class BrierComparisonResult:
    """Outcome of the framing comparison of ``p_self`` Brier scores."""

    means: dict[str, float]
    t_statistic: float
    p_value: float
    n_sessions: dict[str, int] = field(default_factory=dict)
    # Cohen's *d* between the two framings' per-session Brier scores
    # (``manipulation_check._cohens_d``), reported alongside ``p_value`` for
    # the project's joint significance + effect-size convention (see R3).
    cohens_d: float = 0.0
    passed: bool = False


def _require_columns(df: pd.DataFrame, columns: list[str]) -> None:
    if df.empty:
        raise ValueError("dataframe is empty")
    missing = [column for column in columns if column not in df.columns]
    if missing:
        raise ValueError(f"missing required column(s): {', '.join(missing)}")


def _framing_effect_sizes(frame: pd.DataFrame) -> dict[str, float]:
    """Session-level Cohen's *d* for each framing vs. the reference level.

    Aggregates ``task_success_factor`` to one row per session first (mirrors
    ``manipulation_check``'s own ``_session_means`` + ``_cohens_d`` pattern)
    so within-session turn correlation does not pseudo-inflate the effective
    N the effect size is computed over. The reference level is
    ``sorted(levels)[0]`` — the same level patsy's default ``Treatment``
    coding drops as the ``C(framing)`` baseline — so keys line up with
    ``p_values``.
    """
    session_means = (
        frame.groupby(["framing", "session_id"])["task_success_factor"]
        .mean()
        .reset_index()
    )
    levels = sorted(session_means["framing"].unique())
    if len(levels) < 2:
        return {}
    reference, *others = levels
    ref_values = session_means.loc[
        session_means["framing"] == reference, "task_success_factor"
    ].to_numpy()
    return {
        f"C(framing)[T.{level}]": _cohens_d(
            session_means.loc[
                session_means["framing"] == level, "task_success_factor"
            ].to_numpy(),
            ref_values,
        )
        for level in others
    }


def fit_band_controlled_accuracy(
    df: pd.DataFrame,
) -> BandControlledAccuracyResult | None:
    """Regress per-turn correctness on framing while holding band fixed.

    Uses a linear probability model with a random intercept per session
    (``statsmodels`` has no mixed *logistic* fitter; the linear form is the
    standard substitute and its framing coefficient is what the check reads)::

        task_success_factor ~ framing + band + (1 | session_id)

    Passing means every framing contrast is non-significant at ``ALPHA``.
    This is a bare non-significance check with no effect-size gate — see the
    module docstring; ``effect_sizes`` on the result carries what a
    researcher needs to additionally check ``|d| < 0.2``.

    The mixedlm fit is wrapped defensively, matching the idiom already
    established at ``forfeit_regression.fit_choice_asymmetric_model`` /
    ``fit_task_spillover_model``: a hard fit failure (as opposed to a mere
    convergence warning) is logged and returns ``None`` rather than
    propagating a raw statsmodels/numpy exception to the caller.

    Raises:
        ValueError: ``df`` is empty, missing a required column, or every row
            is dropped by the ``task_success_factor``/``framing``/``band``
            completeness filter (e.g. a non-benchmark task's turns, where
            ``band`` is always null — see ``loaders.LONG_FORMAT_COLUMNS``).
    """
    _require_columns(
        df, ["task_success_factor", "framing", "band", "session_id"]
    )
    frame = df.dropna(subset=["task_success_factor", "framing", "band"]).copy()
    if frame.empty:
        raise ValueError(
            "no rows remain after dropping missing task_success_factor/"
            "framing/band — this frame likely has no benchmark-task turns "
            "(band is null for every non-benchmark task)"
        )
    frame["task_success_factor"] = frame["task_success_factor"].astype(float)

    formula = "task_success_factor ~ C(framing) + band"
    note = "linear probability model with session random intercept"
    converged: bool
    try:
        model = smf.mixedlm(formula, data=frame, groups=frame["session_id"])
        fit = model.fit(method="lbfgs", maxiter=200)
        converged = bool(fit.converged) if hasattr(fit, "converged") else True
    except Exception as exc:  # noqa: BLE001 - defensive, matches forfeit_regression
        # A binary outcome with a near-zero between-session variance makes
        # the random-effects covariance singular; on some BLAS builds
        # (observed on the Linux CI runner, not on macOS) statsmodels then
        # raises ``Singular matrix`` from the Hessian instead of merely
        # warning. The same linear probability model with session-clustered
        # standard errors answers the same question without the random
        # intercept, so fall back to it and flag ``converged=False`` rather
        # than dropping the check entirely.
        logger.warning(
            "Band-controlled accuracy mixedLM fit failed (%s); "
            "falling back to OLS with session-clustered SEs",
            exc,
        )
        try:
            fit = smf.ols(formula, data=frame).fit(
                cov_type="cluster", cov_kwds={"groups": frame["session_id"]}
            )
        except Exception as exc2:  # noqa: BLE001
            logger.warning("Band-controlled accuracy OLS fallback failed: %s", exc2)
            return None
        converged = False
        note = (
            "linear probability model with session-clustered SEs "
            f"(mixedlm fallback: {exc})"
        )

    coefficients = {name: float(value) for name, value in fit.params.items()}
    p_values = {name: float(value) for name, value in fit.pvalues.items()}
    framing_terms = [name for name in p_values if name.startswith("C(framing)")]
    passed = all(p_values[name] >= ALPHA for name in framing_terms)

    return BandControlledAccuracyResult(
        coefficients=coefficients,
        p_values=p_values,
        n_turns=int(len(frame)),
        passed=passed,
        converged=converged,
        effect_sizes=_framing_effect_sizes(frame),
        note=note,
    )


def compare_psuccess_brier(df: pd.DataFrame) -> BrierComparisonResult:
    """Compare per-session ``p_self`` Brier scores across two framings.

    ``Brier = mean_t[(psuccess_self / 100 - task_success_factor)^2]`` per
    session. Turns without a probe (``psuccess_self`` is null, e.g. the
    degenerate Cell 0 path) are dropped. ``passed`` is a bare non-significance
    check with no effect-size gate — see the module docstring; ``cohens_d``
    on the result carries what a researcher needs to additionally check
    ``|d| < 0.2``.

    Raises:
        ValueError: ``df`` is empty, missing a required column, every row is
            dropped by the ``psuccess_self``/``task_success_factor``
            completeness filter (e.g. an all-Cell-0 slice, where
            ``psuccess_self`` is always null), or the surviving rows do not
            span exactly two framings.
    """
    _require_columns(
        df, ["psuccess_self", "task_success_factor", "framing", "session_id"]
    )
    frame = df.dropna(subset=["psuccess_self", "task_success_factor"]).copy()
    if frame.empty:
        raise ValueError(
            "no rows remain after dropping missing psuccess_self/"
            "task_success_factor — this frame likely has no probed turns "
            "(psuccess_self is null on Cell 0 and any non-probe path)"
        )
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
        cohens_d=_cohens_d(left.to_numpy(), right.to_numpy()),
        passed=bool(p_value >= ALPHA),
    )
