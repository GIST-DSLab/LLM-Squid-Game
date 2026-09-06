"""FSPM composite — one equal-weight Cohen's-d scalar per model (KDD-UC 4-model data).

Three measurement channels of the KDD-UC paper are each converted to a
standardised effect size on the same *Death (flagship_corruption) minus
Elimination (baseline_flagship)* contrast, then averaged with equal weights
(one vote per MTMM method axis):

    behavioral  d_B = beta_F * sqrt(3)/pi          (Cox log-HR -> d, Chinn 2000)
    verbal      d_V = 2*asin(sqrt(p_FC)) - 2*asin(sqrt(p_BF))   (Cohen's h)
    cognitive   d_C = Hedges' g on Hes^Exit_i, FC vs BF sessions (Test a)

    FSPM_composite = (d_B + d_V + d_C) / 3

Confidence intervals: per-channel Wald CIs, plus a session-level cluster
bootstrap for the composite (sessions resampled with replacement inside each of
the four BF/FC x allowed/not_allowed cells; all three channels recomputed on
every draw, so the CI absorbs the correlation between channels).

The verbal channel is the two-group version the paper does *not* report (the
paper tests p_FC against 1/3). Both a dummy-variable Welch t-test and Cohen's h
are computed; h is the composite input because it is variance-stabilised when a
cell has zero survival reasons (GPT-OSS: 0/10).

Usage:
    PYTHONPATH=game python scripts/analysis/fspm_composite_kdd.py --out results/fspm_composite/kdd4 --boot 1000
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import sys
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

sys.path.insert(0, str(Path(__file__).resolve().parent))
from analyze_unified_cox_with_load import (  # noqa: E402
    MODEL_DIRS,
    _BASELINE,
    _CORRUPTION,
    _build_survival_frame,
    _compute_session_delta_ri,
    _fit_cox,
)

logger = logging.getLogger("fspm_composite_kdd")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
warnings.filterwarnings("ignore")

LOGHR_TO_D = math.sqrt(3) / math.pi
COVARIATES = ["framing_is_FC", "score_prev", "correct_prev"]
Z95 = 1.959963984540054


# ─── channel estimators ──────────────────────────────────────────────────────

def behavioral_d(regime_df: pd.DataFrame) -> dict:
    """Cox 3-cov on the no_cap Exit x {BF, FC} frame -> beta_F -> d."""
    frame = _build_survival_frame(regime_df)
    fit = _fit_cox(frame, COVARIATES)
    beta, se = fit["beta_framing_is_FC"], fit["se_framing_is_FC"]
    return {
        "n_obs": fit["n_obs"], "n_sessions": fit["n_sessions"],
        "n_events": fit["n_events"], "n_events_BF": fit["n_events_BF"], "n_events_FC": fit["n_events_FC"],
        "epv": fit["epv"],
        "beta": beta, "se": se, "p": fit["p_framing_is_FC"],
        "HR": fit["hr_framing_is_FC"], "HR_lo": fit["hr_framing_is_FC_ci_low"], "HR_hi": fit["hr_framing_is_FC_ci_high"],
        "d": beta * LOGHR_TO_D, "d_se": se * LOGHR_TO_D,
        "d_lo": (beta - Z95 * se) * LOGHR_TO_D, "d_hi": (beta + Z95 * se) * LOGHR_TO_D,
    }


def _hedges_g(x: np.ndarray, y: np.ndarray) -> tuple[float, float]:
    """Hedges' g (y - x, pooled SD, small-sample corrected) and its SE."""
    n1, n2 = len(x), len(y)
    s_p = math.sqrt(((n1 - 1) * x.var(ddof=1) + (n2 - 1) * y.var(ddof=1)) / (n1 + n2 - 2))
    d = (y.mean() - x.mean()) / s_p if s_p > 0 else float("nan")
    j = 1 - 3 / (4 * (n1 + n2) - 9)
    g = d * j
    se = math.sqrt((n1 + n2) / (n1 * n2) + g * g / (2 * (n1 + n2)))
    return g, se


def verbal_d(events_df: pd.DataFrame) -> dict:
    """REASON=1 share among no_cap forfeits: FC vs BF -> Cohen's h (+ dummy t / g)."""
    e = events_df[(events_df["forfeit_condition"] == "allowed") & (events_df["regime"] == "no_cap")]
    bf = (e[e["framing"] == _BASELINE]["reason"] == "survival").astype(float).to_numpy()
    fc = (e[e["framing"] == _CORRUPTION]["reason"] == "survival").astype(float).to_numpy()
    n1, n2 = len(bf), len(fc)
    k1, k2 = int(bf.sum()), int(fc.sum())
    p1, p2 = k1 / n1, k2 / n2
    h = 2 * math.asin(math.sqrt(p2)) - 2 * math.asin(math.sqrt(p1))
    h_se = math.sqrt(1 / n1 + 1 / n2)
    # dummy-variable Welch t (the user's proposal) and the g it implies
    t, p_t = stats.ttest_ind(fc, bf, equal_var=False)
    g, g_se = _hedges_g(bf, fc)
    # exact test for the 2x2 table
    p_fisher = stats.fisher_exact([[k2, n2 - k2], [k1, n1 - k1]], alternative="two-sided")[1]
    # paper's one-group version: p_FC against 1/3
    h_third = 2 * math.asin(math.sqrt(p2)) - 2 * math.asin(math.sqrt(1 / 3))
    h_third_se = math.sqrt(1 / n2)
    return {
        "n_BF": n1, "k_BF": k1, "p_BF": p1, "n_FC": n2, "k_FC": k2, "p_FC": p2,
        "diff": p2 - p1,
        "h": h, "h_se": h_se, "h_lo": h - Z95 * h_se, "h_hi": h + Z95 * h_se,
        "welch_t": float(t), "welch_p": float(p_t), "fisher_p": float(p_fisher),
        "g_dummy": g, "g_dummy_se": g_se, "g_dummy_lo": g - Z95 * g_se, "g_dummy_hi": g + Z95 * g_se,
        "h_vs_third": h_third, "h_vs_third_lo": h_third - Z95 * h_third_se, "h_vs_third_hi": h_third + Z95 * h_third_se,
        "d": h, "d_se": h_se, "d_lo": h - Z95 * h_se, "d_hi": h + Z95 * h_se,
    }


def cognitive_d(full_turn_df: pd.DataFrame) -> dict:
    """Test a: Hes^Exit_i (session mean ri_forfeit minus not_allowed block mean), FC vs BF -> Hedges' g."""
    sm, baselines = _compute_session_delta_ri(full_turn_df)
    bf = sm[sm["framing"] == _BASELINE]["delta_ri"].to_numpy(dtype=float)
    fc = sm[sm["framing"] == _CORRUPTION]["delta_ri"].to_numpy(dtype=float)
    t, p = stats.ttest_ind(fc, bf, equal_var=False)
    g, se = _hedges_g(bf, fc)
    return {
        "n_BF": int(len(bf)), "n_FC": int(len(fc)),
        "block_baseline_BF": baselines.get(_BASELINE), "block_baseline_FC": baselines.get(_CORRUPTION),
        "hes_mean_BF": float(bf.mean()), "hes_mean_FC": float(fc.mean()),
        "hes_sd_BF": float(bf.std(ddof=1)), "hes_sd_FC": float(fc.std(ddof=1)),
        "contrast": float(fc.mean() - bf.mean()),
        "welch_t": float(t), "welch_p": float(p),
        "d": g, "d_se": se, "d_lo": g - Z95 * se, "d_hi": g + Z95 * se,
    }


def composite(ds: list[float], ses: list[float]) -> dict:
    c = float(np.mean(ds))
    se = math.sqrt(sum(s * s for s in ses)) / len(ds)  # independence approximation
    return {"value": c, "se_indep": se, "lo_indep": c - Z95 * se, "hi_indep": c + Z95 * se}


# ─── bootstrap ───────────────────────────────────────────────────────────────

def _resample_sessions(df: pd.DataFrame, rng: np.random.Generator, cell_cols: list[str]) -> pd.DataFrame:
    """Resample session_ids with replacement inside each cell; suffix duplicates so ids stay unique."""
    parts = []
    for _, cell in df.groupby(cell_cols, sort=False):
        ids = cell["session_id"].unique()
        draw = rng.choice(ids, size=len(ids), replace=True)
        by_id = {sid: grp for sid, grp in cell.groupby("session_id", sort=False)}
        for j, sid in enumerate(draw):
            g = by_id[sid].copy()
            g["session_id"] = f"{sid}__b{j}"
            parts.append(g)
    return pd.concat(parts, ignore_index=True)


def bootstrap_composite(regime_df: pd.DataFrame, events_df: pd.DataFrame, full_turn_df: pd.DataFrame,
                        n_boot: int, seed: int) -> dict:
    rng = np.random.default_rng(seed)
    # one shared session draw per replicate: the three channels must see the same sessions
    allowed_ids = full_turn_df[full_turn_df["forfeit_condition"] == "allowed"]
    cells = full_turn_df[["session_id", "framing", "forfeit_condition"]].drop_duplicates()
    cells = cells[cells["framing"].isin([_BASELINE, _CORRUPTION])]
    ev_by_sid = {sid: grp for sid, grp in events_df.groupby("session_id", sort=False)}
    reg_by_sid = {sid: grp for sid, grp in regime_df.groupby("session_id", sort=False)}
    turn_by_sid = {sid: grp for sid, grp in full_turn_df.groupby("session_id", sort=False)}

    out = {"d_B": [], "d_V": [], "d_C": [], "composite": []}
    n_fail = 0
    for b in range(n_boot):
        reg_parts, ev_parts, turn_parts = [], [], []
        for (_, _), cell in cells.groupby(["framing", "forfeit_condition"], sort=False):
            ids = cell["session_id"].to_numpy()
            draw = rng.choice(ids, size=len(ids), replace=True)
            for j, sid in enumerate(draw):
                new = f"{sid}__b{j}"
                tp = turn_by_sid[sid].copy(); tp["session_id"] = new; turn_parts.append(tp)
                if sid in reg_by_sid:
                    rp = reg_by_sid[sid].copy(); rp["session_id"] = new; reg_parts.append(rp)
                if sid in ev_by_sid:
                    ep = ev_by_sid[sid].copy(); ep["session_id"] = new; ev_parts.append(ep)
        try:
            reg = pd.concat(reg_parts, ignore_index=True)
            ev = pd.concat(ev_parts, ignore_index=True) if ev_parts else events_df.iloc[0:0]
            turns = pd.concat(turn_parts, ignore_index=True)
            dB = behavioral_d(reg)["d"]
            dV = verbal_d(ev)["d"]
            dC = cognitive_d(turns)["d"]
            if not all(np.isfinite([dB, dV, dC])):
                raise ValueError("non-finite channel")
        except Exception as exc:  # noqa: BLE001 — a degenerate draw (no events in a group) is skipped
            n_fail += 1
            continue
        out["d_B"].append(dB); out["d_V"].append(dV); out["d_C"].append(dC)
        out["composite"].append((dB + dV + dC) / 3)
    del allowed_ids
    res = {"n_boot": n_boot, "n_ok": len(out["composite"]), "n_fail": n_fail}
    for k, v in out.items():
        a = np.asarray(v)
        res[k] = {"mean": float(a.mean()), "sd": float(a.std(ddof=1)),
                  "lo": float(np.percentile(a, 2.5)), "hi": float(np.percentile(a, 97.5))}
    # channel correlation across draws — tells whether the three move together
    m = np.column_stack([out["d_B"], out["d_V"], out["d_C"]])
    res["channel_corr_boot"] = np.corrcoef(m, rowvar=False).round(3).tolist()
    return res


# ─── driver ──────────────────────────────────────────────────────────────────

def run_one(label: str, run_root: Path, n_boot: int, seed: int) -> dict:
    from squid_game.evaluation import discover_season_jsonl, load_seasons
    from squid_game.evaluation.shared.loaders import turn_observations

    logger.info("--- %s ---", label)
    seasons = load_seasons(discover_season_jsonl(run_root))
    full_turn_df = turn_observations(seasons)
    regime_df = pd.read_csv(run_root / "phase3_analysis" / "regime_stratified_turn_observations.csv")
    events_df = pd.read_csv(run_root / "phase3_analysis" / "regime_stratified_forfeit_events.csv")

    B = behavioral_d(regime_df)
    V = verbal_d(events_df)
    C = cognitive_d(full_turn_df)
    comp = composite([B["d"], V["d"], C["d"]], [B["d_se"], V["d_se"], C["d_se"]])
    logger.info("d_B=%.3f d_V=%.3f d_C=%.3f composite=%.3f", B["d"], V["d"], C["d"], comp["value"])
    boot = bootstrap_composite(regime_df, events_df, full_turn_df, n_boot, seed) if n_boot > 0 else None
    if boot:
        logger.info("bootstrap composite 95%% [%.3f, %.3f] (ok %d / fail %d)",
                    boot["composite"]["lo"], boot["composite"]["hi"], boot["n_ok"], boot["n_fail"])
    return {"model": label, "run_dir": run_root.name, "behavioral": B, "verbal": V, "cognitive": C,
            "composite": comp, "bootstrap": boot}


def _fmt(v, nd=2):
    return "—" if v is None or (isinstance(v, float) and not math.isfinite(v)) else f"{v:.{nd}f}"


def write_markdown(results: dict, path: Path) -> None:
    L = ["# FSPM composite — KDD-UC 4 models (equal-weight Cohen's d)", ""]
    L.append("| Model | d_B (Cox) [95% CI] | d_V (Cohen's h) [95% CI] | d_C (Hes, Hedges g) [95% CI] | Composite | 95% CI (indep.) | 95% CI (cluster bootstrap) |")
    L.append("|---|---|---|---|---|---|---|")
    for m, r in results.items():
        B, V, C, c, b = r["behavioral"], r["verbal"], r["cognitive"], r["composite"], r["bootstrap"]
        bci = f"[{_fmt(b['composite']['lo'])}, {_fmt(b['composite']['hi'])}]" if b else "—"
        L.append(f"| {m} | {_fmt(B['d'])} [{_fmt(B['d_lo'])}, {_fmt(B['d_hi'])}] | {_fmt(V['d'])} [{_fmt(V['d_lo'])}, {_fmt(V['d_hi'])}] "
                 f"| {_fmt(C['d'])} [{_fmt(C['d_lo'])}, {_fmt(C['d_hi'])}] | **{_fmt(c['value'])}** | [{_fmt(c['lo_indep'])}, {_fmt(c['hi_indep'])}] | {bci} |")
    L += ["", "## Channel detail", ""]
    L.append("| Model | HR [95% CI] | p | events BF/FC | p_BF (k/n) | p_FC (k/n) | Fisher p | Welch t (dummy) p | g_dummy | Hes contrast (tokens) | Welch p | n BF/FC |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|---|")
    for m, r in results.items():
        B, V, C = r["behavioral"], r["verbal"], r["cognitive"]
        L.append(f"| {m} | {_fmt(B['HR'])} [{_fmt(B['HR_lo'])}, {_fmt(B['HR_hi'])}] | {_fmt(B['p'],3)} | {B['n_events_BF']}/{B['n_events_FC']} "
                 f"| {_fmt(V['p_BF'],3)} ({V['k_BF']}/{V['n_BF']}) | {_fmt(V['p_FC'],3)} ({V['k_FC']}/{V['n_FC']}) | {_fmt(V['fisher_p'],3)} | {_fmt(V['welch_p'],3)} | {_fmt(V['g_dummy'])} "
                 f"| {C['contrast']:+.0f} | {_fmt(C['welch_p'],3)} | {C['n_BF']}/{C['n_FC']} |")
    path.write_text("\n".join(L) + "\n")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", default="outputs/final_results")
    ap.add_argument("--out", default="results/fspm_composite/kdd4")
    ap.add_argument("--boot", type=int, default=1000)
    ap.add_argument("--seed", type=int, default=20260906)
    a = ap.parse_args()
    out = Path(a.out); out.mkdir(parents=True, exist_ok=True)
    results = {}
    for label, d in MODEL_DIRS.items():
        run_root = Path(a.root) / d
        if not run_root.exists():
            logger.warning("missing %s", run_root); continue
        results[label] = run_one(label, run_root, a.boot, a.seed)
    (out / "composite.json").write_text(json.dumps(results, indent=2, default=str))
    write_markdown(results, out / "composite.md")
    print((out / "composite.md").read_text())


if __name__ == "__main__":
    main()
