"""§1 + §6.7 unified Cox PH — joint identification of SD, SA, TC.

Spec:
    λ(t | X) = λ₀(t) · exp( β_F · 1_FC          ← SD  (HR_FC)
                           + β_S · S(t-1)         ← SA  (HR_score)
                           + β_C · C(t-1) )       ← TC  (HR_C, belief-driven)

    C(t-1) = 1{ task_success_factor[t-1] == 1.0 }  (subjective belief signal)
    Data:  Cells 1+3, no_cap regime
    Model: lifelines.CoxTimeVaryingFitter

Replaces the §6.7 standalone Cox (deprecated) by absorbing TC into the §1
joint Cox. Also fits the 2-covariate §1 baseline (without C) for direct
diff comparison so we can see how β_F / β_S move when C enters.

Diagnostics emitted per model:
    - n_sessions, n_events (BF/FC), n_C_active rows
    - HR_FC, HR_score, HR_C with 95% CI + p
    - VIF for collinearity audit
    - PH (Schoenfeld) check on session-collapsed frame
    - EPV (events per parameter)
    - Side-by-side delta with 2-covariate baseline

Usage:
    uv run python scripts/analyze_unified_cox.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("analyze_unified_cox")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


MODEL_DIRS: dict[str, str] = {
    "Gemini-2.5-flash": "20260422_0218_gemini-2.5-flash_signal-game",
    "Qwen3-Next-80B": "20260422_0902_qwen3-next-80b-cloud_signal-game",
    "GPT-OSS-20B": "20260422_0902_gpt-oss-20b-cloud_signal-game",
    "Nemotron-3-Nano-30B": "20260422_0902_nemotron-3-nano-30b-cloud_signal-game",
}

_BASELINE = "baseline_flagship"
_CORRUPTION = "flagship_corruption"


def _load_regime_csv(run_root: Path) -> pd.DataFrame:
    """Read the regime-stratified CSV (has the per-turn `regime` column)."""
    csv = run_root / "phase3_analysis" / "regime_stratified_turn_observations.csv"
    if not csv.exists():
        raise FileNotFoundError(f"missing {csv}")
    return pd.read_csv(csv)


def _build_survival_frame(turn_df: pd.DataFrame) -> pd.DataFrame:
    """Long-format survival frame for CoxTimeVaryingFitter on no_cap.

    Cells 1+3 (allowed × {BF, FC}) on no_cap regime, with start/stop
    intervals, score_prev (= S(t-1)), and correct_prev (= C(t-1)).

    correct_prev is computed *before* the regime filter so the lag has
    access to all of the session's prior turns (otherwise a session
    that crossed regime boundaries would lose its lag).
    """
    # 1. Compute correct_prev across the full session (pre-regime-filter)
    # At t=1 there is literally no prior reward, so C[t-1] := 0 is the
    # correct epistemic value (not a missing-data imputation): the agent
    # has seen no positive feedback yet at the moment of the t=1 decision.
    # Keeping t=1 rows preserves apples-to-apples comparison with §1 Cox.
    df = turn_df.sort_values(["session_id", "turn_number"]).copy()
    df["task_success_factor"] = pd.to_numeric(
        df["task_success_factor"], errors="coerce"
    )
    df["correct_prev_raw"] = (
        df.groupby("session_id")["task_success_factor"].shift(1)
    )
    df["correct_prev"] = (df["correct_prev_raw"] == 1.0).astype(float)
    # NaN at t=1 → 0 (semantic: no prior positive feedback observed yet)
    df["correct_prev"] = df["correct_prev"].fillna(0.0)

    # 2. Filter to allowed cells × {BF, FC} × no_cap
    sub = df[
        (df["forfeit_condition"] == "allowed")
        & df["framing"].isin([_BASELINE, _CORRUPTION])
        & (df["regime"] == "no_cap")
    ].copy()
    if sub.empty:
        return pd.DataFrame()

    # 3. Build start/stop/event interval rows
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


def _fit_cox(
    frame: pd.DataFrame, covariates: list[str]
) -> dict:
    """Fit CoxTimeVaryingFitter and return summary dict."""
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
        "n_events_BF": int(
            frame[frame["framing"] == _BASELINE]["event"].sum()
        ),
        "n_events_FC": int(
            frame[frame["framing"] == _CORRUPTION]["event"].sum()
        ),
        "covariates": covariates,
        "epv": float(frame["event"].sum() / len(covariates)),
    }
    for cov in covariates:
        out[f"hr_{cov}"] = float(s.loc[cov, "exp(coef)"])
        out[f"hr_{cov}_ci_low"] = float(s.loc[cov, "exp(coef) lower 95%"])
        out[f"hr_{cov}_ci_high"] = float(s.loc[cov, "exp(coef) upper 95%"])
        out[f"beta_{cov}"] = float(s.loc[cov, "coef"])
        out[f"se_{cov}"] = float(s.loc[cov, "se(coef)"])
        out[f"p_{cov}"] = float(s.loc[cov, "p"])
    return out


def _vif(frame: pd.DataFrame, covariates: list[str]) -> dict:
    """Variance Inflation Factor for collinearity audit.

    Centered/scaled regression of each covariate on the others.
    VIF > 5 = mild concern; > 10 = serious collinearity.
    """
    from statsmodels.stats.outliers_influence import variance_inflation_factor
    from statsmodels.tools import add_constant

    X = add_constant(frame[covariates].astype(float).copy())
    return {
        cov: float(variance_inflation_factor(X.values, i + 1))
        for i, cov in enumerate(covariates)
    }


def _ph_check(frame: pd.DataFrame, covariates: list[str]) -> dict:
    """Schoenfeld PH check via session-collapsed CoxPHFitter.

    Best-effort — collapsing time-varying covariates loses information,
    but it's the only PH check `lifelines` exposes for this setup.
    For each covariate we report the p-value of the time-correlation
    test; p < 0.05 = PH violated for that covariate.
    """
    try:
        from lifelines import CoxPHFitter
    except ImportError:
        return {}

    rows: list[dict] = []
    for sid, grp in frame.groupby("session_id", sort=False):
        grp = grp.sort_values("stop")
        events = grp[grp["event"] == 1]
        if len(events):
            T = float(events.iloc[0]["stop"])
            event = 1
        else:
            T = float(grp.iloc[-1]["stop"])
            event = 0
        r = {"T": T, "event": event}
        for cov in covariates:
            r[cov] = float(grp.iloc[-1][cov])  # use last observed value
        rows.append(r)
    sf = pd.DataFrame(rows)
    if sf.empty or sf["event"].sum() == 0:
        return {}
    try:
        cph = CoxPHFitter()
        cph.fit(sf[["T", "event"] + covariates], duration_col="T", event_col="event")
        chk = cph.check_assumptions(
            sf[["T", "event"] + covariates], show_plots=False, advice=False
        )
        # check_assumptions returns a list of (cov, ...) violations
        violated = {row[0] for row in chk} if chk else set()
        return {cov: bool(cov not in violated) for cov in covariates}
    except Exception as exc:  # noqa: BLE001
        logger.debug("PH check failed: %s", exc)
        return {}


def run_one(model_label: str, run_root: Path) -> dict:
    logger.info("--- %s ---", model_label)
    turn_df = _load_regime_csv(run_root)
    frame = _build_survival_frame(turn_df)
    if frame.empty or frame["event"].sum() == 0:
        return {"error": "empty survival frame"}

    out: dict = {"model_label": model_label}

    # 2-covariate baseline (current §1 spec) — for diff comparison
    base = _fit_cox(frame, ["framing_is_FC", "score_prev"])
    out["baseline_2cov"] = base

    # 3-covariate unified Cox (proposed)
    full = _fit_cox(frame, ["framing_is_FC", "score_prev", "correct_prev"])
    out["unified_3cov"] = full

    # Diagnostics on the unified model
    out["vif"] = _vif(frame, ["framing_is_FC", "score_prev", "correct_prev"])
    out["ph_check"] = _ph_check(frame, ["framing_is_FC", "score_prev", "correct_prev"])

    # Effect-shift report
    out["delta"] = {
        "hr_framing_is_FC_2v3": (
            full["hr_framing_is_FC"] - base["hr_framing_is_FC"]
        ),
        "hr_score_prev_2v3": (
            full["hr_score_prev"] - base["hr_score_prev"]
        ),
    }

    out["c_active_share"] = float(frame["correct_prev"].mean())
    out["n_obs"] = int(len(frame))

    logger.info(
        "n_sessions=%d, n_events=%d (BF=%d, FC=%d), C-active share=%.3f, EPV=%.1f",
        full["n_sessions"], full["n_events"],
        full["n_events_BF"], full["n_events_FC"],
        out["c_active_share"], full["epv"],
    )
    logger.info(
        "HR_FC=%.3f [%.3f,%.3f] p=%.4f | HR_S=%.4f p=%.3f | HR_C=%.3f [%.3f,%.3f] p=%.4f",
        full["hr_framing_is_FC"], full["hr_framing_is_FC_ci_low"],
        full["hr_framing_is_FC_ci_high"], full["p_framing_is_FC"],
        full["hr_score_prev"], full["p_score_prev"],
        full["hr_correct_prev"], full["hr_correct_prev_ci_low"],
        full["hr_correct_prev_ci_high"], full["p_correct_prev"],
    )
    logger.info("VIF: %s", out["vif"])
    logger.info("PH check: %s", out["ph_check"])
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

    out = root / "unified_cox_summary.json"
    out.write_text(json.dumps(aggregate, indent=2, default=str))
    logger.info("wrote %s", out)

    # Markdown table — paste directly into metric.md
    print("\n--- metric.md unified Cox table (3-cov) ---")
    print("| Model | n_sess | n_evt (BF/FC) | HR_FC [95% CI] | p_FC | HR_S | p_S | HR_C [95% CI] | p_C | EPV | PH ok |")
    print("|---|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        if "error" in r:
            print(f"| {k} | — | — | error: {r['error']} | | | | | | | |")
            continue
        f = r["unified_3cov"]
        ph = r["ph_check"]
        ph_ok = "✅" if ph and all(ph.values()) else (
            "⚠ " + ",".join(c for c, v in ph.items() if not v) if ph else "?"
        )
        print(
            f"| {k} | {f['n_sessions']} | {f['n_events']} ({f['n_events_BF']}/{f['n_events_FC']}) | "
            f"{f['hr_framing_is_FC']:.3f} [{f['hr_framing_is_FC_ci_low']:.2f}, {f['hr_framing_is_FC_ci_high']:.2f}] | "
            f"{f['p_framing_is_FC']:.3f} | "
            f"{f['hr_score_prev']:.4f} | {f['p_score_prev']:.3f} | "
            f"{f['hr_correct_prev']:.3f} [{f['hr_correct_prev_ci_low']:.2f}, {f['hr_correct_prev_ci_high']:.2f}] | "
            f"{f['p_correct_prev']:.3f} | "
            f"{f['epv']:.1f} | {ph_ok} |"
        )

    print("\n--- HR_FC shift from adding C[t-1] ---")
    print("| Model | HR_FC (2-cov, current §1) | HR_FC (3-cov, unified) | Δ |")
    print("|---|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        if "error" in r:
            continue
        b = r["baseline_2cov"]["hr_framing_is_FC"]
        f = r["unified_3cov"]["hr_framing_is_FC"]
        print(f"| {k} | {b:.3f} | {f:.3f} | {f - b:+.3f} |")

    print("\n--- VIF (collinearity audit) ---")
    print("| Model | VIF(FC) | VIF(S) | VIF(C) |")
    print("|---|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        if "vif" not in r:
            continue
        v = r["vif"]
        print(f"| {k} | {v.get('framing_is_FC', float('nan')):.2f} | "
              f"{v.get('score_prev', float('nan')):.2f} | "
              f"{v.get('correct_prev', float('nan')):.2f} |")


if __name__ == "__main__":
    main()
