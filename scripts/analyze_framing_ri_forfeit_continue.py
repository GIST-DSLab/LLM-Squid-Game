"""Driver: §3-revised continue-only mixedLM on log(ri_forfeit + 1).

Spec: ``docs/design/v6/paper/metric.md`` §3-revised (2026-04-26 redefine)
+ §3.6 (I2) 7-bundle dispatch.

Bundles fit per model:
  - primary           : log(ri_forfeit+1) ~ full §1 covariates + (1|session)
  - robustness_raw    : raw ri_forfeit    ~ full §1 covariates + (1|session)
  - isolation_no_cov  : log(ri_forfeit+1) ~ framing_corruption only + (1|session)
  - v7a_bootstrap     : 1000 session-cluster resamples on primary spec
  - v7b_subgroup_prone: primary spec on forfeit-prone session subset
  - v7b_subgroup_rare : primary spec on forfeit-rare session subset

Output: outputs/final_results/framing_ri_forfeit_continue.json — populates
metric.md §3.3 (primary + robustness tables) and §3.4 V5 / V7 rows.

Usage:
    uv run python scripts/analyze_framing_ri_forfeit_continue.py
    uv run python scripts/analyze_framing_ri_forfeit_continue.py --skip-bootstrap
    uv run python scripts/analyze_framing_ri_forfeit_continue.py --bootstrap-n 200
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.formula.api as smf

logger = logging.getLogger("analyze_framing_ri_forfeit_continue")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

# metric.md §3.6 (I4) — reproducibility seed (date-aligned with redefine).
SEED = 20260426
N_BOOTSTRAP_DEFAULT = 1000

MODEL_DIRS: dict[str, str] = {
    "Gemini-2.5-flash": "20260422_0218_gemini-2.5-flash_signal-game",
    "Qwen3-Next-80B": "20260422_0902_qwen3-next-80b-cloud_signal-game",
    "GPT-OSS-20B": "20260422_0902_gpt-oss-20b-cloud_signal-game",
    "Nemotron-3-Nano-30B": "20260422_0902_nemotron-3-nano-30b-cloud_signal-game",
}

PRIMARY_FORMULA = (
    "log_ri_forfeit ~ framing_corruption + correct_prev + score + turn"
)
RAW_FORMULA = (
    "ri_forfeit_raw ~ framing_corruption + correct_prev + score + turn"
)
ISOLATION_FORMULA = "log_ri_forfeit ~ framing_corruption"


def preprocess(csv_path: Path) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Apply metric.md §3-revised §3.2 4-step preprocessing chain.

    Returns (continue_subset, full_cells13_df). The full frame is needed
    for the V7b subgroup split (forfeit-prone vs forfeit-rare classification
    runs over the full Cells 1+3 sample, not the continue subset only).
    """
    df = pd.read_csv(csv_path)
    cells_13 = df[
        df["framing"].isin(["baseline_flagship", "flagship_corruption"])
        & (df["forfeit_condition"] == "allowed")
    ].copy()

    # 4-step chain — mirrors src/squid_game/analysis/forfeit_regression.py
    # :fit_framing_ri_forfeit_continue exactly (single source of truth at
    # metric.md §3.2 + §3.6 (I1)).
    sub = cells_13[
        cells_13["ri_forfeit_thinking_tokens"].notna()
        & ~cells_13["forfeit"].astype(bool)
    ].copy()
    sub = sub.sort_values(["session_id", "turn_number"])
    sub["correct_prev"] = (
        sub.groupby("session_id")["task_success_factor"]
        .shift(1)
        .fillna(0)
        .astype(int)
    )
    sub = sub[sub["turn_number"] >= 2].copy()
    if not sub.empty:
        assert (
            sub.groupby("session_id")["turn_number"].min().min() >= 2
        ), "metric.md §3.6 (I1) lag invariant violated"
    sub["framing_corruption"] = (
        sub["framing"] == "flagship_corruption"
    ).astype(int)
    sub["score"] = sub["score_before_turn"].astype(float)
    sub["turn"] = sub["turn_number"].astype(int)
    sub["log_ri_forfeit"] = np.log1p(
        sub["ri_forfeit_thinking_tokens"].astype(float)
    )
    sub["ri_forfeit_raw"] = sub["ri_forfeit_thinking_tokens"].astype(float)
    return sub, cells_13


def fit_one(sub: pd.DataFrame, formula: str) -> dict | None:
    """Fit a single mixedLM, extract β_framing summary."""
    if sub.empty or len(sub) < 20:
        return None
    try:
        model = smf.mixedlm(formula, data=sub, groups=sub["session_id"])
        res = model.fit(reml=True, method=["lbfgs"])
    except Exception as exc:  # noqa: BLE001
        logger.warning("fit failed (%s): %s", formula, exc)
        return None
    fe = res.fe_params
    se = res.bse
    pv = res.pvalues
    beta = float(fe.get("framing_corruption", float("nan")))
    se_b = float(se.get("framing_corruption", float("nan")))
    return {
        "n_obs": int(len(sub)),
        "n_sessions": int(sub["session_id"].nunique()),
        "beta_framing": beta,
        "se_framing": se_b,
        "p_framing": float(pv.get("framing_corruption", float("nan"))),
        "ci_lo_framing": beta - 1.96 * se_b,
        "ci_hi_framing": beta + 1.96 * se_b,
        "exp_beta_framing": (
            float(np.exp(beta)) if beta == beta else float("nan")
        ),
        "converged": bool(getattr(res, "converged", True)),
        "all_params": {k: float(v) for k, v in fe.items()},
        "all_pvalues": {k: float(v) for k, v in pv.items()},
    }


def cluster_bootstrap_ci(
    sub: pd.DataFrame,
    formula: str,
    n_resamples: int,
    seed: int = SEED,
) -> dict | None:
    """Session-cluster bootstrap 95% percentile CI on β_framing — V7a."""
    if sub.empty or n_resamples <= 0:
        return None
    rng = np.random.default_rng(seed)
    sessions = sub["session_id"].unique()
    n_sess = len(sessions)
    betas: list[float] = []
    for i in range(n_resamples):
        boot_sids = rng.choice(sessions, size=n_sess, replace=True)
        boot_parts = []
        for j, sid in enumerate(boot_sids):
            part = sub[sub["session_id"] == sid].copy()
            # Re-key session_id to avoid mixedlm collapsing duplicate
            # cluster IDs when the same session is drawn twice.
            part["session_id"] = f"{sid}__{j}"
            boot_parts.append(part)
        boot = pd.concat(boot_parts, ignore_index=True)
        try:
            model = smf.mixedlm(
                formula, data=boot, groups=boot["session_id"]
            )
            res = model.fit(reml=True, method=["lbfgs"])
            beta = float(res.fe_params.get("framing_corruption", float("nan")))
            if beta == beta:  # not NaN
                betas.append(beta)
        except Exception:  # noqa: BLE001
            continue
        if (i + 1) % 100 == 0:
            logger.info("  bootstrap %d/%d done", i + 1, n_resamples)
    if not betas:
        return None
    arr = np.array(betas)
    return {
        "ci_lo": float(np.percentile(arr, 2.5)),
        "ci_hi": float(np.percentile(arr, 97.5)),
        "median": float(np.median(arr)),
        "n_resamples": int(n_resamples),
        "n_successful": int(len(arr)),
    }


def split_subgroups(
    sub: pd.DataFrame, cells_13_full: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Split continue subset by session-level forfeit-rate (V7b).

    A session is *forfeit-prone* if it has at least one forfeit event in
    any Cells 1+3 turn (full sample, not continue-only). *forfeit-rare*
    sessions never forfeit in Cells 1+3.
    """
    forfeit_per_session = cells_13_full.groupby("session_id")["forfeit"].any()
    prone = set(forfeit_per_session[forfeit_per_session].index)
    rare = set(forfeit_per_session[~forfeit_per_session].index)
    return (
        sub[sub["session_id"].isin(prone)].copy(),
        sub[sub["session_id"].isin(rare)].copy(),
    )


def analyze_one_model(
    label: str, csv_path: Path, bootstrap_n: int
) -> dict:
    sub, cells_13_full = preprocess(csv_path)
    logger.info(
        "%s: continue n=%d (sessions=%d) of cells1+3 n=%d",
        label,
        len(sub),
        sub["session_id"].nunique(),
        len(cells_13_full),
    )

    primary = fit_one(sub, PRIMARY_FORMULA)
    robustness_raw = fit_one(sub, RAW_FORMULA)
    isolation_no_cov = fit_one(sub, ISOLATION_FORMULA)

    if bootstrap_n > 0:
        logger.info("%s: bootstrap n=%d", label, bootstrap_n)
        v7a = cluster_bootstrap_ci(sub, PRIMARY_FORMULA, bootstrap_n)
    else:
        v7a = None

    sub_prone, sub_rare = split_subgroups(sub, cells_13_full)
    v7b_prone = fit_one(sub_prone, PRIMARY_FORMULA)
    v7b_rare = fit_one(sub_rare, PRIMARY_FORMULA)

    return {
        "primary": primary,
        "robustness_raw": robustness_raw,
        "isolation_no_cov": isolation_no_cov,
        "v7a_bootstrap": v7a,
        "v7b_subgroup_prone": v7b_prone,
        "v7b_subgroup_rare": v7b_rare,
        "n_continue_obs": int(len(sub)),
        "n_sessions": int(sub["session_id"].nunique()),
        "n_subgroup_prone_obs": int(len(sub_prone)),
        "n_subgroup_rare_obs": int(len(sub_rare)),
    }


def print_paste_blocks(aggregate: dict) -> None:
    """Emit metric.md §3.3 + §3.4 V5 paste-ready table rows."""
    print("\n--- metric.md §3.3 primary table rows ---")
    for k, r in aggregate.items():
        p = r.get("primary")
        if p is None:
            continue
        sig = p["beta_framing"] > 0 and p["p_framing"] < 0.05
        bold = "**" if sig else ""
        print(
            f"| {k:<19} | {p['n_obs']} | {p['n_sessions']} | "
            f"{bold}{p['beta_framing']:+.4f}{bold} | "
            f"[{p['ci_lo_framing']:+.4f}, {p['ci_hi_framing']:+.4f}] | "
            f"{p['exp_beta_framing']:.3f} | {p['p_framing']:.4f} | "
            f"{'✅' if sig else '✗'} |"
        )

    print("\n--- metric.md §3.3 robustness (raw) table rows ---")
    for k, r in aggregate.items():
        rb = r.get("robustness_raw")
        p = r.get("primary")
        if rb is None or p is None:
            continue
        sign_consistent = (rb["beta_framing"] > 0) == (p["beta_framing"] > 0)
        flag = "✅ same sign" if sign_consistent else "✗ flip"
        print(
            f"| {k:<19} | {rb['beta_framing']:+.2f} | "
            f"[{rb['ci_lo_framing']:+.2f}, {rb['ci_hi_framing']:+.2f}] | "
            f"{rb['p_framing']:.4f} | {flag} |"
        )

    print("\n--- metric.md §3.4 V5 isolation audit rows ---")
    for k, r in aggregate.items():
        no_cov = r.get("isolation_no_cov")
        p = r.get("primary")
        if no_cov is None or p is None:
            continue
        delta = abs(p["beta_framing"] - no_cov["beta_framing"])
        ok = "✅" if delta < 0.15 else "⚠ check"
        print(
            f"| {k:<19} | {no_cov['beta_framing']:+.4f} | "
            f"{p['beta_framing']:+.4f} | {delta:.4f} | {ok} |"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--bootstrap-n",
        type=int,
        default=N_BOOTSTRAP_DEFAULT,
        help=f"V7a cluster-bootstrap resample count (default {N_BOOTSTRAP_DEFAULT})",
    )
    parser.add_argument(
        "--skip-bootstrap",
        action="store_true",
        help="skip V7a bootstrap (fast first-pass mode)",
    )
    args = parser.parse_args()
    bootstrap_n = 0 if args.skip_bootstrap else args.bootstrap_n

    root = Path("outputs/final_results")
    aggregate: dict = {}
    for label, d in MODEL_DIRS.items():
        csv = root / d / "phase3_analysis" / "unit14_turn_observations.csv"
        if not csv.exists():
            logger.warning("missing %s — skipping %s", csv, label)
            continue
        logger.info("=== %s ===", label)
        aggregate[label] = analyze_one_model(label, csv, bootstrap_n)

    out = root / "framing_ri_forfeit_continue.json"
    out.write_text(json.dumps(aggregate, indent=2, default=str))
    logger.info("wrote %s", out)

    print_paste_blocks(aggregate)


if __name__ == "__main__":
    main()
