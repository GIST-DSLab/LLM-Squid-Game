"""§3a Cognitive Load Mediation — extends §1 unified Cox with Donders ΔRI.

Hypothesis (mediation chain):
    SD activation (FC framing) → cognitive load increase → forfeit timing

Test: add session-level Donders ΔRI to the §1 unified Cox and check
whether HR_FC attenuates toward 1.0. Attenuation = mediation evidence
(some of the FC → forfeit pathway runs through the cognitive-load
channel rather than through a direct framing-to-decision shortcut).

Donders ΔRI definition (per the 2026-04-26 "Allow vs Block" finding):
    ΔRI_i = mean(ri_forfeit | session_i, allowed) - block_baseline(framing_i)
where the block baseline is the per-framing mean of ri_forfeit_thinking_tokens
across all turns of all sessions in the *not_allowed* counterpart cell:
    block_baseline(BF) = mean ri_forfeit in Cell 2 (BF·not_allowed)
    block_baseline(FC) = mean ri_forfeit in Cell 4 (FC·not_allowed)
This subtracts away the rubber-stamp Call-2 cost (no-decision baseline,
~7-32% of allowed-cell ri_forfeit), isolating the decision-deliberation
component.

Spec (4-cov augmented Cox, time-varying):
    λ(t | X) = λ₀(t) · exp( β_F · 1_FC          ← SD (HR_FC)
                           + β_S · S(t-1)        ← SA (HR_score)
                           + β_C · C(t-1)        ← TC (HR_C)
                           + β_M · ΔRI_i_z )     ← cognitive load (z-scored)

ΔRI is z-scored *within each model* so β_M is interpretable as
"hazard ratio per +1 SD of session-level decision cost". Time-invariant
within session (session-level trait covariate).

Mediation criterion:
    Full mediation → β_F → 0 (HR_FC → 1.0)
    Partial mediation → |β_F (4-cov)| < |β_F (3-cov)| with non-trivial Δ

Outputs:
    outputs/final_results/cognitive_load_mediation.json — full per-model dump
    stdout — markdown table for §3a paste-in.

Usage:
    uv run python scripts/analyze_unified_cox_with_load.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from squid_game.analysis import discover_season_jsonl, load_seasons
from squid_game.analysis.forfeit_regression import turn_observations

logger = logging.getLogger("analyze_cognitive_load_mediation")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


MODEL_DIRS: dict[str, str] = {
    "Gemini-2.5-flash":    "20260422_0218_gemini-2.5-flash_signal-game",
    "Qwen3-Next-80B":      "20260422_0902_qwen3-next-80b-cloud_signal-game",
    "GPT-OSS-20B":         "20260422_0902_gpt-oss-20b-cloud_signal-game",
    "Nemotron-3-Nano-30B": "20260422_0902_nemotron-3-nano-30b-cloud_signal-game",
}

_BASELINE = "baseline_flagship"
_CORRUPTION = "flagship_corruption"


def _compute_session_delta_ri(
    turn_df: pd.DataFrame,
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Compute Donders ΔRI per session (allowed cells, BF/FC only).

    Returns:
        (session_df, baselines)
        - session_df: columns [session_id, ri_session_mean, block_baseline,
                               delta_ri, delta_ri_z, framing]
        - baselines: per-framing block-cell mean used as subtraction reference.
    """
    block_mask = (
        (turn_df["forfeit_condition"] == "not_allowed")
        & (turn_df["ri_forfeit_thinking_tokens"].notna())
        & (turn_df["framing"].isin([_BASELINE, _CORRUPTION]))
    )
    block = turn_df.loc[block_mask]
    baselines = (
        block.groupby("framing")["ri_forfeit_thinking_tokens"]
        .mean()
        .to_dict()
    )

    allowed_mask = (
        (turn_df["forfeit_condition"] == "allowed")
        & (turn_df["ri_forfeit_thinking_tokens"].notna())
        & (turn_df["framing"].isin([_BASELINE, _CORRUPTION]))
    )
    allowed = turn_df.loc[allowed_mask]
    sm = (
        allowed.groupby(["session_id", "framing"])["ri_forfeit_thinking_tokens"]
        .mean()
        .reset_index()
        .rename(columns={"ri_forfeit_thinking_tokens": "ri_session_mean"})
    )
    sm["block_baseline"] = sm["framing"].map(baselines)
    sm["delta_ri"] = sm["ri_session_mean"] - sm["block_baseline"]

    # Z-score within model — coefficient becomes "HR per +1 SD load".
    mean_d = float(sm["delta_ri"].mean())
    sd_d = float(sm["delta_ri"].std(ddof=1))
    sm["delta_ri_z"] = (
        (sm["delta_ri"] - mean_d) / sd_d if sd_d > 0 else 0.0
    )
    return sm, baselines


def _build_survival_frame(turn_df: pd.DataFrame) -> pd.DataFrame:
    """Long-format survival frame for CoxTimeVaryingFitter on no_cap.

    Mirrors analyze_unified_cox.py exactly so the 3-cov baseline reproduces
    the canonical §1 fit.
    """
    df = turn_df.sort_values(["session_id", "turn_number"]).copy()
    df["task_success_factor"] = pd.to_numeric(
        df["task_success_factor"], errors="coerce"
    )
    df["correct_prev_raw"] = (
        df.groupby("session_id")["task_success_factor"].shift(1)
    )
    df["correct_prev"] = (df["correct_prev_raw"] == 1.0).astype(float)
    df["correct_prev"] = df["correct_prev"].fillna(0.0)

    sub = df[
        (df["forfeit_condition"] == "allowed")
        & df["framing"].isin([_BASELINE, _CORRUPTION])
        & (df["regime"] == "no_cap")
    ].copy()
    if sub.empty:
        return pd.DataFrame()

    rows: list[dict] = []
    for _, r in sub.iterrows():
        try:
            t = int(r["turn_number"])
            score_prev = float(r["score_before_turn"])
        except (TypeError, ValueError):
            continue
        rows.append(
            {
                "session_id": r["session_id"],
                "framing": str(r["framing"]),
                "framing_is_FC": 1 if str(r["framing"]) == _CORRUPTION else 0,
                "start": t - 1,
                "stop": t,
                "event": 1 if bool(r["forfeit"]) else 0,
                "score_prev": score_prev,
                "correct_prev": float(r["correct_prev"]),
            }
        )
    return pd.DataFrame.from_records(rows)


def _fit_cox(frame: pd.DataFrame, covariates: list[str]) -> dict:
    """Fit CoxTimeVaryingFitter and pull the standard summary fields."""
    from lifelines import CoxTimeVaryingFitter

    fit_data = frame[
        ["session_id", "start", "stop", "event"] + covariates
    ].copy()
    ctv = CoxTimeVaryingFitter()
    ctv.fit(
        fit_data,
        id_col="session_id",
        event_col="event",
        start_col="start",
        stop_col="stop",
    )
    s = ctv.summary
    out: dict = {
        "n_obs": int(len(frame)),
        "n_sessions": int(frame["session_id"].nunique()),
        "n_events": int(frame["event"].sum()),
        "n_events_BF": int(frame[frame["framing"] == _BASELINE]["event"].sum()),
        "n_events_FC": int(frame[frame["framing"] == _CORRUPTION]["event"].sum()),
        "covariates": covariates,
        "epv": float(frame["event"].sum() / len(covariates)),
        "log_likelihood": float(ctv.log_likelihood_),
    }
    for cov in covariates:
        out[f"hr_{cov}"] = float(s.loc[cov, "exp(coef)"])
        out[f"hr_{cov}_ci_low"] = float(s.loc[cov, "exp(coef) lower 95%"])
        out[f"hr_{cov}_ci_high"] = float(s.loc[cov, "exp(coef) upper 95%"])
        out[f"beta_{cov}"] = float(s.loc[cov, "coef"])
        out[f"se_{cov}"] = float(s.loc[cov, "se(coef)"])
        out[f"p_{cov}"] = float(s.loc[cov, "p"])
    return out


def run_one(model_label: str, run_root: Path) -> dict:
    logger.info("--- %s ---", model_label)

    # 1. Load full turn data (JSONL → turn_observations) for ΔRI computation.
    jsonl = discover_season_jsonl(run_root)
    seasons = load_seasons(jsonl)
    full_turn_df = turn_observations(seasons)

    # 2. Compute session-level Donders ΔRI from allowed/not_allowed cells.
    delta_df, baselines = _compute_session_delta_ri(full_turn_df)
    if delta_df.empty:
        return {"error": "no allowed-cell ri_forfeit data"}

    # 3. Load regime-stratified CSV for the survival frame (no_cap subset).
    regime_csv = run_root / "phase3_analysis" / "regime_stratified_turn_observations.csv"
    if not regime_csv.exists():
        return {"error": f"missing {regime_csv}"}
    regime_df = pd.read_csv(regime_csv)
    frame = _build_survival_frame(regime_df)
    if frame.empty or frame["event"].sum() == 0:
        return {"error": "empty survival frame"}

    # 4. Merge ΔRI as session-level covariate.
    n_pre = len(frame)
    frame = frame.merge(
        delta_df[["session_id", "delta_ri", "delta_ri_z"]],
        on="session_id", how="left",
    )
    n_missing = int(frame["delta_ri_z"].isna().sum())
    if n_missing > 0:
        logger.warning(
            "%d rows missing ΔRI (sessions w/o allowed-cell ri_forfeit); dropped",
            n_missing,
        )
        frame = frame.dropna(subset=["delta_ri_z"])
    logger.info(
        "frame: %d → %d rows after ΔRI merge; %d sessions retained",
        n_pre, len(frame), frame["session_id"].nunique(),
    )

    out: dict = {
        "model_label": model_label,
        "block_baselines": baselines,
        "delta_ri_summary": {
            "mean": float(delta_df["delta_ri"].mean()),
            "sd": float(delta_df["delta_ri"].std(ddof=1)),
            "min": float(delta_df["delta_ri"].min()),
            "max": float(delta_df["delta_ri"].max()),
            "n_sessions_with_load": int(len(delta_df)),
        },
    }

    # 5. Fit 3-cov baseline (= existing §1) and 4-cov with load.
    base = _fit_cox(frame, ["framing_is_FC", "score_prev", "correct_prev"])
    out["unified_3cov"] = base

    full = _fit_cox(
        frame, ["framing_is_FC", "score_prev", "correct_prev", "delta_ri_z"]
    )
    out["unified_4cov_with_load"] = full

    # 6. Mediation diagnostics — HR_FC and β_FC change.
    pct_atten: float | None
    if abs(base["beta_framing_is_FC"]) > 0.01:
        pct_atten = float(
            100.0
            * (base["beta_framing_is_FC"] - full["beta_framing_is_FC"])
            / base["beta_framing_is_FC"]
        )
    else:
        pct_atten = None

    out["mediation"] = {
        "hr_FC_3cov": base["hr_framing_is_FC"],
        "hr_FC_3cov_ci": [
            base["hr_framing_is_FC_ci_low"],
            base["hr_framing_is_FC_ci_high"],
        ],
        "p_FC_3cov": base["p_framing_is_FC"],
        "hr_FC_4cov": full["hr_framing_is_FC"],
        "hr_FC_4cov_ci": [
            full["hr_framing_is_FC_ci_low"],
            full["hr_framing_is_FC_ci_high"],
        ],
        "p_FC_4cov": full["p_framing_is_FC"],
        "delta_hr_FC": full["hr_framing_is_FC"] - base["hr_framing_is_FC"],
        "beta_FC_3cov": base["beta_framing_is_FC"],
        "beta_FC_4cov": full["beta_framing_is_FC"],
        "pct_attenuation": pct_atten,
        "load_effect": {
            "hr_delta_ri_z": full["hr_delta_ri_z"],
            "hr_ci": [full["hr_delta_ri_z_ci_low"], full["hr_delta_ri_z_ci_high"]],
            "beta": full["beta_delta_ri_z"],
            "p": full["p_delta_ri_z"],
        },
        "loglik_3cov": base["log_likelihood"],
        "loglik_4cov": full["log_likelihood"],
        "loglik_ratio_2x": 2 * (full["log_likelihood"] - base["log_likelihood"]),
    }

    logger.info(
        "HR_FC %.3f → %.3f (%+.3f, atten %s%%) | HR_load=%.3f [%.2f,%.2f] p=%.4f | logL %.2f→%.2f (LRT 2Δ=%.2f)",
        base["hr_framing_is_FC"], full["hr_framing_is_FC"],
        full["hr_framing_is_FC"] - base["hr_framing_is_FC"],
        f"{pct_atten:+.1f}" if pct_atten is not None else "n/a",
        full["hr_delta_ri_z"], full["hr_delta_ri_z_ci_low"],
        full["hr_delta_ri_z_ci_high"], full["p_delta_ri_z"],
        base["log_likelihood"], full["log_likelihood"],
        2 * (full["log_likelihood"] - base["log_likelihood"]),
    )
    return out


def main() -> None:
    root = Path("outputs/final_results")
    aggregate: dict = {}
    for label, d in MODEL_DIRS.items():
        run_root = root / d
        if not run_root.exists():
            logger.warning("missing %s", run_root)
            continue
        aggregate[label] = run_one(label, run_root)

    out_path = root / "cognitive_load_mediation.json"
    out_path.write_text(json.dumps(aggregate, indent=2, default=str))
    logger.info("wrote %s", out_path)

    # ─── Markdown tables for §3a paste-in ─────────────────────────────────
    print("\n--- §3a Mediation Results — HR_FC pre/post ΔRI ---")
    print("| Model | n_sess | n_evt (BF/FC) | HR_FC (§1, 3-cov) [95% CI] | p | HR_FC (+ΔRI, 4-cov) [95% CI] | p | %attenuation |")
    print("|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        if "error" in r:
            print(f"| {k} | — | — | error: {r['error']} | | | | |")
            continue
        m = r["mediation"]
        f4 = r["unified_4cov_with_load"]
        atten = f"{m['pct_attenuation']:+.1f}%" if m['pct_attenuation'] is not None else "—"
        ci3 = m["hr_FC_3cov_ci"]
        ci4 = m["hr_FC_4cov_ci"]
        print(
            f"| {k} | {f4['n_sessions']} | {f4['n_events']} ({f4['n_events_BF']}/{f4['n_events_FC']}) | "
            f"{m['hr_FC_3cov']:.3f} [{ci3[0]:.2f}, {ci3[1]:.2f}] | {m['p_FC_3cov']:.3f} | "
            f"{m['hr_FC_4cov']:.3f} [{ci4[0]:.2f}, {ci4[1]:.2f}] | {m['p_FC_4cov']:.3f} | "
            f"{atten} |"
        )

    print("\n--- §3a Cognitive Load effect (β_M, per +1 SD of ΔRI) ---")
    print("| Model | HR_ΔRI [95% CI] | β | p | logL (3-cov → 4-cov) | LRT 2Δ |")
    print("|---|:-:|:-:|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        if "error" in r:
            continue
        m = r["mediation"]
        l = m["load_effect"]
        ci = l["hr_ci"]
        print(
            f"| {k} | {l['hr_delta_ri_z']:.3f} [{ci[0]:.2f}, {ci[1]:.2f}] | "
            f"{l['beta']:+.3f} | {l['p']:.4f} | "
            f"{m['loglik_3cov']:.2f} → {m['loglik_4cov']:.2f} | "
            f"{m['loglik_ratio_2x']:+.2f} |"
        )

    print("\n--- ΔRI distribution per model (raw tokens) ---")
    print("| Model | mean ΔRI | sd ΔRI | min | max | block_baseline(BF) | block_baseline(FC) |")
    print("|---|:-:|:-:|:-:|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        if "error" in r:
            continue
        d = r["delta_ri_summary"]
        b = r["block_baselines"]
        print(
            f"| {k} | {d['mean']:.0f} | {d['sd']:.0f} | {d['min']:.0f} | {d['max']:.0f} | "
            f"{b.get(_BASELINE, float('nan')):.0f} | {b.get(_CORRUPTION, float('nan')):.0f} |"
        )


if __name__ == "__main__":
    main()
