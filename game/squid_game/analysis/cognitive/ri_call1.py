"""Does threat framing change Call-1 problem-solving effort?

Outcome: ``ri_task`` — the thinking-token count of Call 1, the only call
in the split-call turn flow that is spent on the signal-game task itself.
Call 1 is issued *before* the agent ever sees the forfeit menu, so the
outcome cannot be contaminated by decision-token spillover; what varies
across cells at that point is purely the system-prompt framing.

Design
------
Three framings, reference ``true_baseline``:

* ``baseline_flagship``    — Pull only  (helpfulness -> deployment)
* ``flagship_corruption``  — Pull + Push (weight corruption / identity)

Two contrasts are reported per model:

* ``threat_vs_neutral``  = beta(is_threat)                — Pull+Push vs no framing
* ``threat_vs_pull``     = beta(is_threat) - beta(is_pull) — isolates the Push
  text alone.  This is the cleaner of the two: both arms run at
  ``p_end = 0.25`` with the same Section-1 prompt text, so the only
  difference is the corruption paragraph.  The neutral arm additionally
  differs in ``p_end`` and (Cell 0) skips Calls 1.5/2 entirely.

Model
-----
``log1p(ri_task) ~ is_threat + is_pull + turn_z + score_z + forfeit_allowed``
with a per-session random intercept (statsmodels ``MixedLM``).  ``log1p``
because the thinking-token distribution is strongly right-skewed
(median well below mean in every model); coefficients therefore read as
approximate proportional changes.

A cluster-robust OLS (session clusters) is fit alongside as a
specification check that does not depend on MixedLM convergence.

The module is intentionally side-effect-free; orchestration / disk I/O
is the caller's responsibility (see ``scripts/analyze_call1_ri.py``).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

FORMULA = (
    "log_ri ~ is_threat + is_pull + turn_z + score_z + forfeit_allowed"
)
OUTCOMES = ("ri_task", "ri_probe", "ri_forfeit")


def _prepare(frame: pd.DataFrame, outcome: str) -> pd.DataFrame:
    """Drop unusable rows and add the model-scale-free regressors."""
    sub = frame[frame[outcome].notna()].copy()
    sub["log_ri"] = np.log1p(sub[outcome].astype(float))
    for source, target in (
        ("turn_number", "turn_z"),
        ("score_before_turn", "score_z"),
    ):
        values = sub[source].astype(float)
        spread = values.std(ddof=0)
        sub[target] = (values - values.mean()) / (spread if spread else 1.0)
    for flag in ("is_threat", "is_pull", "forfeit_allowed"):
        sub[flag] = sub[flag].astype(int)
    return sub


def _fe_names(result) -> list[str]:
    """Fixed-effect coefficient names, in the order ``t_test`` expects.

    ``MixedLMResults.t_test`` rejects the string-formula form that the OLS
    results object accepts, so both paths build an explicit contrast row
    over the fixed effects only (the random-effect variance parameters
    trail the fixed effects in ``params`` and must not be indexed).
    """
    if hasattr(result, "fe_params"):
        return list(result.fe_params.index)
    return list(result.params.index)


def _contrast(result, left: str, right: str | None) -> dict:
    """Wald test for ``beta(left)`` or ``beta(left) - beta(right)``."""
    expression = left if right is None else f"{left} - {right}"
    names = _fe_names(result)
    row = np.zeros(len(names))
    row[names.index(left)] = 1.0
    if right is not None:
        row[names.index(right)] = -1.0
    test = result.t_test(row.reshape(1, -1))
    effect = float(np.ravel(test.effect)[0])
    return {
        "contrast": expression,
        "beta_log": effect,
        # exp(beta) - 1: the proportional change in (1 + thinking tokens).
        "pct_change": float(np.expm1(effect) * 100.0),
        "se": float(np.ravel(test.sd)[0]),
        "z": float(np.ravel(test.statistic)[0]),
        "p": float(np.ravel(test.pvalue)[0]),
    }


def fit_one(frame: pd.DataFrame, outcome: str, label: str) -> dict:
    """Fit the mixed model plus the clustered-OLS check for one group."""
    sub = _prepare(frame, outcome)
    if sub.empty or sub["is_threat"].nunique() < 2:
        return {"label": label, "outcome": outcome, "status": "skipped"}

    mixed = smf.mixedlm(FORMULA, sub, groups=sub["session_id"]).fit(
        method="lbfgs", maxiter=2000
    )
    ols = smf.ols(FORMULA, sub).fit(
        cov_type="cluster", cov_kwds={"groups": sub["session_id"]}
    )

    descriptive = (
        sub.groupby("framing")[outcome]
        .agg(["count", "mean", "median"])
        .round(1)
        .to_dict(orient="index")
    )
    return {
        "label": label,
        "outcome": outcome,
        "status": "ok",
        "n_turns": int(len(sub)),
        "n_sessions": int(sub["session_id"].nunique()),
        "converged": bool(mixed.converged),
        # Near-zero group variance means the random intercept collapsed:
        # sessions are barely distinguishable once the fixed effects are
        # in, so the mixed and clustered-OLS fits should agree closely.
        "group_var": float(mixed.cov_re.iloc[0, 0]),
        "descriptive": descriptive,
        "mixedlm": {
            "threat_vs_neutral": _contrast(mixed, "is_threat", None),
            "pull_vs_neutral": _contrast(mixed, "is_pull", None),
            "threat_vs_pull": _contrast(mixed, "is_threat", "is_pull"),
            "turn_z": _contrast(mixed, "turn_z", None),
            "score_z": _contrast(mixed, "score_z", None),
        },
        "ols_cluster": {
            "threat_vs_neutral": _contrast(ols, "is_threat", None),
            "threat_vs_pull": _contrast(ols, "is_threat", "is_pull"),
        },
    }


def _stars(p: float) -> str:
    if p < 0.001:
        return "***"
    if p < 0.01:
        return "**"
    if p < 0.05:
        return "*"
    if p < 0.10:
        return "."
    return ""


def _contrast_table(results: list[dict], key: str) -> str:
    header = (
        "| model | n turns | n sess | β (log) | Δ% | SE | z | p | |\n"
        "|---|---:|---:|---:|---:|---:|---:|---:|---|\n"
    )
    lines = []
    for entry in results:
        if entry["status"] != "ok":
            continue
        row = entry["mixedlm"][key]
        lines.append(
            f"| {entry['label']} | {entry['n_turns']} | "
            f"{entry['n_sessions']} | {row['beta_log']:+.4f} | "
            f"{row['pct_change']:+.1f}% | {row['se']:.4f} | "
            f"{row['z']:+.2f} | {row['p']:.4f} | {_stars(row['p'])} |"
        )
    return header + "\n".join(lines) + "\n"


def _descriptive_table(results: list[dict], outcome: str) -> str:
    header = (
        f"| model | framing | n | mean {outcome} | median |\n"
        "|---|---|---:|---:|---:|\n"
    )
    order = ["true_baseline", "baseline_flagship", "flagship_corruption"]
    lines = []
    for entry in results:
        if entry["status"] != "ok":
            continue
        for framing in order:
            stats = entry["descriptive"].get(framing)
            if stats is None:
                continue
            lines.append(
                f"| {entry['label']} | {framing} | {int(stats['count'])} | "
                f"{stats['mean']:.1f} | {stats['median']:.1f} |"
            )
    return header + "\n".join(lines) + "\n"


def render_report(all_results: dict[str, list[dict]]) -> str:
    task = all_results["ri_task"]
    parts = [
        "# Call-1 Reasoning Investment under threat framing",
        "",
        "Outcome `ri_task` = Call-1 thinking tokens (task solving only).",
        "Model: `log1p(ri_task) ~ is_threat + is_pull + turn_z + score_z"
        " + forfeit_allowed + (1 | session)`.",
        "Reference framing = `true_baseline`. Δ% = `exp(β) - 1`.",
        "",
        "## Descriptive — ri_task by framing",
        "",
        _descriptive_table(task, "ri_task"),
        "## H_threat_A — threat vs neutral (`flagship_corruption`"
        " vs `true_baseline`)",
        "",
        _contrast_table(task, "threat_vs_neutral"),
        "## H_threat_B — Push isolated (`flagship_corruption`"
        " vs `baseline_flagship`)",
        "",
        "Preferred contrast: both arms share `p_end = 0.25`, the same",
        "Section-1 prompt, and the full 3-call cascade; only the weight-",
        "corruption paragraph differs.",
        "",
        _contrast_table(task, "threat_vs_pull"),
        "## Pull alone (`baseline_flagship` vs `true_baseline`)",
        "",
        _contrast_table(task, "pull_vs_neutral"),
        "## Covariates",
        "",
        "### Turn (z-scored)",
        "",
        _contrast_table(task, "turn_z"),
        "### Score entering the turn (z-scored)",
        "",
        _contrast_table(task, "score_z"),
    ]
    for outcome in ("ri_probe", "ri_forfeit"):
        parts += [
            f"## Secondary outcome — `{outcome}` (threat vs pull)",
            "",
            _contrast_table(all_results[outcome], "threat_vs_pull"),
        ]
    return "\n".join(parts)
