"""PH-violation audit + remedy for the §1+§6.7 unified Cox.

For each model:
  1. Fit base 3-cov Cox: framing_is_FC + score_prev + correct_prev
  2. PH diagnostic — for each covariate X, fit base + X·log(stop)
     and read the interaction p-value as the PH test for X.
     (Significant interaction → HR for X varies with calendar time → PH violated.)
  3. Build per-model PH-corrected spec by adding log(stop) interactions
     only for the violating covariates.
  4. Refit and report:
     - HR at turn 1, 3, 5 for time-varying covariates (shows drift shape)
     - Final PH check — interaction terms should now absorb the violation
     - Compare 2-cov § baseline vs constant-HR 3-cov vs time-corrected
       to show how the SD claim is affected.

Output: outputs/final_results/unified_cox_ph_audit.json
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

logger = logging.getLogger("ph_audit")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")

MODEL_DIRS: dict[str, str] = {
    "Gemini-2.5-flash": "20260422_0218_gemini-2.5-flash_signal-game",
    "Qwen3-Next-80B": "20260422_0902_qwen3-next-80b-cloud_signal-game",
    "GPT-OSS-20B": "20260422_0902_gpt-oss-20b-cloud_signal-game",
    "Nemotron-3-Nano-30B": "20260422_0902_nemotron-3-nano-30b-cloud_signal-game",
}

_BASELINE = "baseline_flagship"
_CORRUPTION = "flagship_corruption"
_BASE_COVS = ["framing_is_FC", "score_prev", "correct_prev"]
_PH_ALPHA = 0.05  # significance threshold for PH violation


def _load_csv(run_root: Path) -> pd.DataFrame:
    csv = run_root / "phase3_analysis" / "regime_stratified_turn_observations.csv"
    return pd.read_csv(csv)


def _build_frame(turn_df: pd.DataFrame) -> pd.DataFrame:
    df = turn_df.sort_values(["session_id", "turn_number"]).copy()
    df["task_success_factor"] = pd.to_numeric(
        df["task_success_factor"], errors="coerce"
    )
    df["correct_prev"] = (
        (df.groupby("session_id")["task_success_factor"].shift(1) == 1.0)
        .astype(float)
    )
    sub = df[
        (df["forfeit_condition"] == "allowed")
        & df["framing"].isin([_BASELINE, _CORRUPTION])
        & (df["regime"] == "no_cap")
    ].copy()
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
    frame = pd.DataFrame.from_records(rows)
    if not frame.empty:
        # log(stop) — log(1)=0 so the base coefficient is the t=1 effect
        frame["log_stop"] = np.log(frame["stop"].astype(float))
    return frame


def _fit_cox(frame: pd.DataFrame, covariates: list[str]) -> dict:
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
    out = {"covariates": covariates, "log_likelihood": float(ctv.log_likelihood_)}
    for cov in covariates:
        out[f"hr_{cov}"] = float(s.loc[cov, "exp(coef)"])
        out[f"hr_{cov}_ci_low"] = float(s.loc[cov, "exp(coef) lower 95%"])
        out[f"hr_{cov}_ci_high"] = float(s.loc[cov, "exp(coef) upper 95%"])
        out[f"beta_{cov}"] = float(s.loc[cov, "coef"])
        out[f"se_{cov}"] = float(s.loc[cov, "se(coef)"])
        out[f"p_{cov}"] = float(s.loc[cov, "p"])
    return out


def _diagnose_ph(frame: pd.DataFrame) -> dict:
    """Fit base + each cov × log_stop one at a time; report interaction p."""
    diag = {}
    for cov in _BASE_COVS:
        ix_col = f"{cov}_x_log_stop"
        f2 = frame.copy()
        f2[ix_col] = f2[cov] * f2["log_stop"]
        try:
            fit = _fit_cox(f2, _BASE_COVS + [ix_col])
            diag[cov] = {
                "interaction_beta": fit[f"beta_{ix_col}"],
                "interaction_p": fit[f"p_{ix_col}"],
                "violates_ph": bool(fit[f"p_{ix_col}"] < _PH_ALPHA),
            }
        except Exception as exc:  # noqa: BLE001
            diag[cov] = {"error": str(exc)}
    return diag


def _hr_at_turn(beta: float, beta_ix: float, t: int) -> float:
    """HR for a binary covariate at calendar turn t (interaction = β + β_ix·log(t))."""
    return float(np.exp(beta + beta_ix * np.log(t)))


def _hr_at_turn_score(beta: float, beta_ix: float, t: int, delta_score: float = 1.0) -> float:
    """HR for a continuous covariate at calendar turn t per `delta_score` units."""
    return float(np.exp((beta + beta_ix * np.log(t)) * delta_score))


def run_one(model_label: str, run_root: Path) -> dict:
    logger.info("--- %s ---", model_label)
    frame = _build_frame(_load_csv(run_root))
    if frame.empty or frame["event"].sum() == 0:
        return {"error": "empty frame"}

    n_evt = int(frame["event"].sum())
    out: dict = {
        "model_label": model_label,
        "n_sessions": int(frame["session_id"].nunique()),
        "n_obs": int(len(frame)),
        "n_events": n_evt,
        "n_events_BF": int(frame[frame["framing"] == _BASELINE]["event"].sum()),
        "n_events_FC": int(frame[frame["framing"] == _CORRUPTION]["event"].sum()),
    }

    # 1) Base 3-cov fit
    base = _fit_cox(frame, _BASE_COVS)
    out["base_3cov"] = base

    # 2) PH diagnostic — one interaction at a time
    diag = _diagnose_ph(frame)
    out["ph_diagnostic"] = diag
    violators = [cov for cov, d in diag.items() if d.get("violates_ph", False)]
    out["ph_violators"] = violators
    logger.info("PH violators: %s", violators or "(none)")

    # 3) PH-corrected spec — add log_stop interactions for violators only
    if violators:
        f2 = frame.copy()
        ix_cols = []
        for cov in violators:
            ix_col = f"{cov}_x_log_stop"
            f2[ix_col] = f2[cov] * f2["log_stop"]
            ix_cols.append(ix_col)
        all_covs = _BASE_COVS + ix_cols
        epv_corrected = n_evt / len(all_covs)
        try:
            corrected = _fit_cox(f2, all_covs)
            out["ph_corrected"] = corrected
            out["epv_corrected"] = epv_corrected

            # 4) HR at turn 1, 3, 5 for each violator
            time_varying = {}
            for cov in violators:
                ix_col = f"{cov}_x_log_stop"
                beta = corrected[f"beta_{cov}"]
                beta_ix = corrected[f"beta_{ix_col}"]
                if cov == "score_prev":
                    delta = 10.0  # report HR per 10-score-unit increment
                    label_unit = "per +10 score"
                else:
                    delta = 1.0
                    label_unit = "binary"
                time_varying[cov] = {
                    "label_unit": label_unit,
                    "hr_at_t1": _hr_at_turn_score(beta, beta_ix, 1, delta),
                    "hr_at_t3": _hr_at_turn_score(beta, beta_ix, 3, delta),
                    "hr_at_t5": _hr_at_turn_score(beta, beta_ix, 5, delta),
                    "p_interaction": corrected[f"p_{ix_col}"],
                }
            out["time_varying_HR"] = time_varying

            # 5) Re-test PH on corrected model — interactions absorb violation?
            #    Re-run diagnostic on corrected model: add another log_stop
            #    interaction on top — if STILL significant, drift is non-log.
            recheck = {}
            for cov in violators:
                ix2 = f"{cov}_x_log_stop_sq"
                f3 = f2.copy()
                f3[ix2] = f3[cov] * (f3["log_stop"] ** 2)
                try:
                    ck = _fit_cox(f3, all_covs + [ix2])
                    recheck[cov] = {
                        "log_sq_interaction_p": ck[f"p_{ix2}"],
                        "still_violates": bool(ck[f"p_{ix2}"] < _PH_ALPHA),
                    }
                except Exception as exc:  # noqa: BLE001
                    recheck[cov] = {"error": str(exc)}
            out["ph_recheck"] = recheck
        except Exception as exc:  # noqa: BLE001
            out["ph_corrected"] = {"error": str(exc)}
    else:
        out["ph_corrected"] = None
        out["epv_corrected"] = n_evt / len(_BASE_COVS)
        logger.info("no PH correction needed for this model")

    return out


def main() -> None:
    root = Path("outputs/final_results")
    aggregate: dict = {}
    for label, d in MODEL_DIRS.items():
        run_root = root / d
        if not run_root.exists():
            continue
        aggregate[label] = run_one(label, run_root)

    out_path = root / "unified_cox_ph_audit.json"
    out_path.write_text(json.dumps(aggregate, indent=2, default=str))
    logger.info("wrote %s", out_path)

    # Summary table — one-line PH verdict per (model, covariate)
    print("\n--- PH diagnostic: interaction p-value (cov × log(t)) ---")
    print("| Model | β_F:log_t (p) | β_S:log_t (p) | β_C:log_t (p) | violators |")
    print("|---|:-:|:-:|:-:|---|")
    for k, r in aggregate.items():
        d = r.get("ph_diagnostic", {})
        def fmt(c):
            x = d.get(c, {})
            if "interaction_p" in x:
                p = x["interaction_p"]
                tag = "**" if x["violates_ph"] else ""
                return f"{x['interaction_beta']:+.3f} ({tag}p={p:.3f}{tag})"
            return "—"
        print(f"| {k} | {fmt('framing_is_FC')} | {fmt('score_prev')} | {fmt('correct_prev')} | {','.join(r.get('ph_violators', [])) or 'none'} |")

    # PH-corrected: HR shape over time
    print("\n--- PH-corrected: HR_FC at turn 1 / 3 / 5 ---")
    print("| Model | constant-HR (base) | HR(t=1) | HR(t=3) | HR(t=5) | β_F:log(t) p |")
    print("|---|:-:|:-:|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        base_hr = r.get("base_3cov", {}).get("hr_framing_is_FC", float("nan"))
        tv = r.get("time_varying_HR", {}).get("framing_is_FC")
        if tv is None:
            print(f"| {k} | {base_hr:.3f} | (PH ok — no correction) | | | |")
        else:
            print(f"| {k} | {base_hr:.3f} | {tv['hr_at_t1']:.3f} | {tv['hr_at_t3']:.3f} | {tv['hr_at_t5']:.3f} | {tv['p_interaction']:.4f} |")

    # PH-corrected: HR_S and HR_C drift where applicable
    print("\n--- PH-corrected: HR_S (per +10 score) & HR_C drift over time ---")
    print("| Model | covariate | HR(t=1) | HR(t=3) | HR(t=5) | β:log(t) p |")
    print("|---|---|:-:|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        for cov in ("score_prev", "correct_prev"):
            tv = r.get("time_varying_HR", {}).get(cov)
            if tv is None:
                continue
            print(f"| {k} | {cov} ({tv['label_unit']}) | {tv['hr_at_t1']:.3f} | {tv['hr_at_t3']:.3f} | {tv['hr_at_t5']:.3f} | {tv['p_interaction']:.4f} |")

    # Final EPV per model after correction
    print("\n--- EPV after PH correction ---")
    print("| Model | n_events | covariates | EPV |")
    print("|---|:-:|:-:|:-:|")
    for k, r in aggregate.items():
        n_cov = len(_BASE_COVS) + len(r.get("ph_violators", []))
        print(f"| {k} | {r.get('n_events', 0)} | {n_cov} | {r.get('epv_corrected', float('nan')):.1f} |")


if __name__ == "__main__":
    main()
