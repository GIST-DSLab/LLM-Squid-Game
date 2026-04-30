#!/usr/bin/env python3
"""Post-hoc analysis orchestrator for v6 canonical FSPM runs.

Takes one or more experiment output directories (each containing
``season_results.jsonl``), runs the full v6 pre-registered analysis
stack on each run, and produces a single multi-sheet Excel workbook
that consolidates the measures across models side-by-side.

Unlike :mod:`scripts.analyze_phase3` (which writes per-run markdown
reports into ``<run>/phase3_analysis/``), this orchestrator focuses on
cross-model comparison and delivers a **single xlsx** whose sheets map
directly to the v6 measurement framework (§6) and statistical analysis
plan (§7). See ``docs/design/v6/POSTHOC_ANALYSIS.md`` for the math and
drive-mapping of every sheet.

Usage
-----
    # Default: auto-detect the most recent gpt-oss + gemini-2.5-flash runs
    uv run python scripts/orchestrate_posthoc.py

    # Explicit runs
    uv run python scripts/orchestrate_posthoc.py \\
        --run gpt-oss outputs/20260422_0346_gpt-oss-20b-cloud_signal-game \\
        --run gemini-2.5-flash outputs/20260422_0218_gemini-2.5-flash_signal-game

    # Custom output path
    uv run python scripts/orchestrate_posthoc.py -o /tmp/fspm_report.xlsx

The orchestrator is read-only: experiment outputs are never modified.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections import defaultdict
from dataclasses import is_dataclass, asdict
from pathlib import Path
from typing import Any, Sequence

# Ensure the project source is importable when running as a script.
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_SRC_DIR = _PROJECT_ROOT / "src"
if str(_SRC_DIR) not in sys.path:
    sys.path.insert(0, str(_SRC_DIR))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

from squid_game.analysis.loaders import (  # noqa: E402
    discover_season_jsonl,
    load_seasons,
    to_long_dataframe,
    to_season_summary_dataframe,
)
from squid_game.analysis.forfeit_regression import (  # noqa: E402
    run_all_unit14_hypotheses,
    run_all_unit15_hypotheses,
)
from squid_game.analysis.manipulation_check import (  # noqa: E402
    check_discovery_timing_independence,
    check_probe_independence,
    check_probe_turn_matched_independence,
    check_accuracy_independence,
    check_ri_exceeds_baseline,
)
from squid_game.analysis.motivation import decompose_motivation  # noqa: E402
from squid_game.analysis.unit13_hypotheses import (  # noqa: E402
    run_all_unit13_hypotheses,
)
from squid_game.analysis.regime_stratification import (  # noqa: E402
    run_stratified_unit14,
)
from squid_game.models.enums import Framing, ForfeitCondition  # noqa: E402
from squid_game.models.results import SeasonResult  # noqa: E402

logger = logging.getLogger("orchestrate_posthoc")


# ---------------------------------------------------------------------------
# v6 6-cell factorial map (supersedes loaders.CELL_ID_MAP which still
# holds the Phase 3.1 5-cell legacy).
# ---------------------------------------------------------------------------

V6_CELL_MAP: dict[tuple[str, str], int] = {
    ("true_baseline", "not_allowed"): 0,
    ("baseline_flagship", "allowed"): 1,
    ("baseline_flagship", "not_allowed"): 2,
    ("flagship_corruption", "allowed"): 3,
    ("flagship_corruption", "not_allowed"): 4,
    ("true_baseline", "allowed"): 5,
    ("flagship_corruption_terminal", "allowed"): 6,
    ("flagship_corruption_terminal", "not_allowed"): 7,
}

V6_CELL_LABEL: dict[int, str] = {
    0: "Cell 0 — true_baseline × not_allowed (BP_cognitive anchor)",
    1: "Cell 1 — baseline_flagship × allowed (Pull only)",
    2: "Cell 2 — baseline_flagship × not_allowed",
    3: "Cell 3 — flagship_corruption × allowed (primary FSPM)",
    4: "Cell 4 — flagship_corruption × not_allowed",
    5: "Cell 5 — true_baseline × allowed (BP_behavioral)",
    6: "Cell 6 — flagship_corruption_terminal × allowed (P7 ablation)",
    7: "Cell 7 — flagship_corruption_terminal × not_allowed (P7 ablation)",
}


def _v6_cell_id(framing: str, forfeit_condition: str) -> int | None:
    return V6_CELL_MAP.get((framing, forfeit_condition))


# ---------------------------------------------------------------------------
# Helper: flatten dataclass / pandas result into a shallow dict
# ---------------------------------------------------------------------------


def _flatten(obj: Any) -> dict[str, Any]:
    if obj is None:
        return {}
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _scalar(v) for k, v in asdict(obj).items()}
    if hasattr(obj, "summary_dict"):
        return {k: _scalar(v) for k, v in obj.summary_dict().items()}
    if isinstance(obj, dict):
        return {k: _scalar(v) for k, v in obj.items()}
    return {}


def _scalar(v: Any) -> Any:
    if isinstance(v, (np.floating,)):
        return float(v)
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.bool_,)):
        return bool(v)
    return v


# ---------------------------------------------------------------------------
# Per-run: compute everything we need to fill the workbook
# ---------------------------------------------------------------------------


def compute_run(
    label: str, run_dir: Path
) -> dict[str, Any]:
    """Run the full analysis stack on one experiment directory.

    Returns a dict of pandas objects / scalars keyed by logical name.
    All entries degrade gracefully to empty DataFrames when inputs are
    insufficient (never raises on missing statsmodels / low n).
    """
    jsonl = discover_season_jsonl(run_dir)
    seasons = load_seasons(jsonl)
    if not seasons:
        raise ValueError(f"No seasons in {jsonl}")

    long_df = to_long_dataframe(seasons, model=label)
    season_df = to_season_summary_dataframe(seasons, model=label)

    # Attach v6 cell_id (the legacy loaders map misses cell 5 and the
    # flagship family, so we recompute here).
    long_df["cell_id_v6"] = [
        _v6_cell_id(f, fc)
        for f, fc in zip(long_df["framing"], long_df["forfeit_condition"])
    ]
    season_df["cell_id_v6"] = [
        _v6_cell_id(f, fc)
        for f, fc in zip(season_df["framing"], season_df["forfeit_condition"])
    ]

    # Unit 14 / 15 (§7.1, §7.2.1) — logit + mixedLM.
    u14 = run_all_unit14_hypotheses(seasons)
    u15 = run_all_unit15_hypotheses(seasons)
    u13 = run_all_unit13_hypotheses(seasons)
    # Unit 17.10 — regime-stratified (no_cap vs cap_bound) Unit 14
    # hypotheses. Reports preference-revealing vs rationality-revealing
    # sub-samples side-by-side. Pure post-hoc; pipeline untouched.
    u17_regime = run_stratified_unit14(seasons)

    # Manipulation check (§7.3 H_D3).
    framings_present = set(long_df["framing"].dropna().unique())
    if {"baseline_flagship", "flagship_corruption"} <= framings_present:
        base_fr, surv_fr = "baseline_flagship", "flagship_corruption"
    else:
        base_fr, surv_fr = "baseline_electricity", "survival_electricity"
    acc_check = check_accuracy_independence(
        long_df, baseline_framing=base_fr, survival_framing=surv_fr
    )
    ri_check = check_ri_exceeds_baseline(
        long_df, baseline_framing=base_fr, survival_framing=surv_fr
    )
    # Phase O Unit 17.11 — probe-based (survivorship-safe) Y-axis checks.
    probe_check = check_probe_independence(
        long_df, baseline_framing=base_fr, survival_framing=surv_fr
    )
    probe_turn_check = check_probe_turn_matched_independence(
        long_df, baseline_framing=base_fr, survival_framing=surv_fr
    )
    disc_check = check_discovery_timing_independence(
        long_df, baseline_framing=base_fr, survival_framing=surv_fr
    )

    # Behavioural 4-component decomposition (§6.7).
    motivation = decompose_motivation(seasons, seed=0)

    # Unit 17 probe (§7.2 secondary H_EV_*) — compute directly from
    # season turns because no dedicated module ships for this yet.
    probe_df, probe_summary, probe_framing_model = _unit17_analysis(seasons)

    # Per-cell descriptive session + turn stats (§6.2).
    cell_table = _per_cell_stats(long_df, season_df)

    return {
        "label": label,
        "run_dir": str(run_dir),
        "n_seasons": len(seasons),
        "long_df": long_df,
        "season_df": season_df,
        "u14": u14,
        "u15": u15,
        "u13": u13,
        "manipulation": {
            "framing_pair": (base_fr, surv_fr),
            "accuracy_independence": acc_check,
            "ri_exceeds_baseline": ri_check,
            "probe_independence": probe_check,
            "probe_turn_matched": probe_turn_check,
            "discovery_timing_independence": disc_check,
        },
        "motivation": motivation,
        "probe_df": probe_df,
        "probe_summary": probe_summary,
        "probe_framing_model": probe_framing_model,
        "cell_table": cell_table,
        "u17_regime": u17_regime,
    }


# ---------------------------------------------------------------------------
# Unit 17 probe (psuccess_self) — H_EV_mean + H_EV_framing
# ---------------------------------------------------------------------------


def _unit17_analysis(
    seasons: Sequence[SeasonResult],
) -> tuple[pd.DataFrame, dict[str, Any], dict[str, Any]]:
    """Extract `psuccess_self` from every turn and run §7.2 EV checks.

    Returns (per_turn_probe_df, summary_dict, framing_mixedlm_dict).
    When no run in this dataset populated the probe (e.g. gpt-oss
    runs pre-Unit-17), all three results are empty / None.
    """
    rows: list[dict] = []
    for s in seasons:
        for t in s.turns:
            psucc = getattr(t, "psuccess_self", None)
            ri_probe = getattr(t, "ri_probe", None)
            rows.append(
                {
                    "session_id": s.season_id,
                    "framing": s.framing.value,
                    "forfeit_condition": s.forfeit_condition.value,
                    "cell_id_v6": _v6_cell_id(
                        s.framing.value, s.forfeit_condition.value
                    ),
                    "turn": t.turn_number,
                    "psuccess_self": psucc,
                    "ri_probe_thinking_tokens": (
                        ri_probe.thinking_tokens if ri_probe else None
                    ),
                }
            )
    df = pd.DataFrame(rows)
    if df.empty or df["psuccess_self"].dropna().empty:
        return df, {"n_obs": 0, "probe_populated": False}, {}

    sub = df.dropna(subset=["psuccess_self"])
    overall_mean = float(sub["psuccess_self"].mean())
    overall_std = float(sub["psuccess_self"].std())

    # H_EV_mean: is the mean inside canonical [65, 85]?
    summary: dict[str, Any] = {
        "n_obs": int(len(sub)),
        "n_sessions": int(sub["session_id"].nunique()),
        "mean_psuccess": overall_mean,
        "std_psuccess": overall_std,
        "median_psuccess": float(sub["psuccess_self"].median()),
        "H_EV_mean_in_band_[65,85]": bool(65.0 <= overall_mean <= 85.0),
        "probe_populated": True,
    }

    # H_EV_framing: psuccess_self ~ framing_corruption + turn + (1|session)
    framing_fit: dict[str, Any] = {}
    try:
        import statsmodels.formula.api as smf

        allowed_framings = {"baseline_flagship", "flagship_corruption"}
        framed = sub[sub["framing"].isin(allowed_framings)].copy()
        if len(framed) >= 30 and framed["framing"].nunique() == 2:
            framed["framing_corruption"] = (
                framed["framing"] == "flagship_corruption"
            ).astype(int)
            framed["psuccess"] = framed["psuccess_self"].astype(float)
            model = smf.mixedlm(
                "psuccess ~ framing_corruption + turn",
                data=framed,
                groups=framed["session_id"],
            )
            result = model.fit(reml=True, method=["lbfgs"])
            framing_fit = {
                "n_obs": int(len(framed)),
                "n_sessions": int(framed["session_id"].nunique()),
                "beta_framing": float(
                    result.fe_params.get("framing_corruption", float("nan"))
                ),
                "se_framing": float(
                    result.bse.get("framing_corruption", float("nan"))
                ),
                "p_framing": float(
                    result.pvalues.get("framing_corruption", float("nan"))
                ),
                "beta_turn": float(
                    result.fe_params.get("turn", float("nan"))
                ),
                "p_turn": float(result.pvalues.get("turn", float("nan"))),
                "converged": bool(
                    getattr(result, "converged", True)
                ),
            }
    except ImportError:
        framing_fit = {"error": "statsmodels not installed"}
    except Exception as exc:  # noqa: BLE001
        framing_fit = {"error": str(exc)}

    return df, summary, framing_fit


# ---------------------------------------------------------------------------
# Per-cell descriptive stats
# ---------------------------------------------------------------------------


def _per_cell_stats(
    long_df: pd.DataFrame, season_df: pd.DataFrame
) -> pd.DataFrame:
    """Per-cell n_sessions, forfeit rate, mean thinking tokens.

    Returns a DataFrame indexed by (cell_id_v6, framing, forfeit_condition).
    """
    if season_df.empty:
        return pd.DataFrame()

    sess = season_df.groupby(
        ["cell_id_v6", "framing", "forfeit_condition"], dropna=False
    ).agg(
        n_sessions=("session_id", "nunique"),
        n_forfeits=("forfeited", "sum"),
        mean_final_score=("final_score", "mean"),
        mean_thinking_tokens_per_session=("thinking_tokens_sum", "mean"),
    )
    sess["forfeit_rate"] = sess["n_forfeits"] / sess["n_sessions"]

    if not long_df.empty:
        turn = long_df.groupby(
            ["cell_id_v6", "framing", "forfeit_condition"], dropna=False
        ).agg(
            mean_thinking_tokens_per_turn=("thinking_tokens", "mean"),
            mean_task_success=("task_success_factor", "mean"),
            mean_rule_match=("rule_match_score", "mean"),
        )
        sess = sess.join(turn, how="left")

    return sess.reset_index()


# ---------------------------------------------------------------------------
# Excel writing
# ---------------------------------------------------------------------------


def write_workbook(
    results: list[dict[str, Any]], out_path: Path
) -> None:
    """Serialise the per-run results dicts into a multi-sheet xlsx."""
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with pd.ExcelWriter(out_path, engine="openpyxl") as xw:
        _write_readme(xw, results)
        _write_summary(xw, results)
        _write_cell_distribution(xw, results)
        _write_logit_sheet(xw, results)
        _write_choice_asymmetric_sheet(xw, results)
        _write_task_spillover_sheet(xw, results)
        _write_ri_descriptive(xw, results)
        _write_manipulation(xw, results)
        _write_probe_turn_matched(xw, results)
        _write_motivation(xw, results)
        _write_reason_distribution(xw, results)
        _write_thinking_keywords(xw, results)
        _write_forfeit_events(xw, results)
        _write_unit17_probe(xw, results)
        _write_unit13(xw, results)
        _write_regime_logit(xw, results)
        _write_regime_reason_dist(xw, results)
        _write_long_format(xw, results)

    logger.info("Workbook written to %s", out_path)


# ---------- README ----------


def _write_readme(xw: pd.ExcelWriter, results: list[dict[str, Any]]) -> None:
    rows = [
        ("Workbook", "phase3_posthoc.xlsx"),
        ("Spec anchor", "docs/design/v6/POSTHOC_ANALYSIS.md"),
        ("Models included", ", ".join(r["label"] for r in results)),
    ]
    for r in results:
        rows.append((f"  - {r['label']} source", r["run_dir"]))
        rows.append((f"  - {r['label']} n_seasons", str(r["n_seasons"])))
    rows.extend(
        [
            ("", ""),
            ("Sheet", "Purpose"),
            ("Summary", "Primary hypotheses across models (H_SD, H_choice_asymmetric, H_D3)"),
            ("CellDistribution", "n / forfeit rate / mean tokens per v6 cell"),
            ("H_SA_SD_int_turn", "Unit 14 forfeit logit coefficients (§7.2.1)"),
            ("H_choice_asymmetric", "Unit 15 mixedLM on ri_forfeit — PRIMARY hypothesis (§7.1)"),
            ("H_task_spillover", "Unit 15 secondary mixedLM on ri_task (§7.2.2)"),
            ("RI_Descriptive", "Per-cell mean ri_task / ri_forfeit / gap"),
            ("Manipulation_H_D3", "H_D3 Y-axis invariance + RI-above-baseline one-sided check (§7.3)"),
            ("Motivation", "4-component behavioural decomposition SD/TC/SA/BP (§6.7)"),
            ("ReasonDistribution", "P(REASON digit | framing) for forfeit events (§6.4)"),
            ("ThinkingKeywords", "Mean keyword-family counts × (framing, reason) (§6.5, §7.2.4)"),
            ("ForfeitEvents", "One row per forfeit event with self-report + thinking_head"),
            ("Unit17_Probe", "psuccess_self → H_EV_mean & H_EV_framing (§7.2 secondary)"),
            ("Unit13_H1_H6", "Session-level lineage hypotheses (Appendix A.5)"),
            ("LongFormat_<model>", "Per-turn long-format frame per model (reference)"),
        ]
    )
    df = pd.DataFrame(rows, columns=["Key", "Value"])
    df.to_excel(xw, sheet_name="README", index=False)


# ---------- Summary sheet ----------


def _write_summary(xw: pd.ExcelWriter, results: list[dict[str, Any]]) -> None:
    rows = []
    for r in results:
        # H1 Cox PH (2026-04-23 primary, replaces legacy logit)
        survival = r["u14"].get("survival") or {}
        cox = survival.get("cox")
        choice = r["u15"]["choice_asymmetric"]
        spill = r["u15"]["task_spillover"]
        acc = r["manipulation"]["accuracy_independence"]
        ri = r["manipulation"]["ri_exceeds_baseline"]
        probe = r["probe_summary"]

        row: dict[str, Any] = {
            "model": r["label"],
            "n_seasons": r["n_seasons"],
        }
        # PRIMARY 1 — H_choice_asymmetric (Unit 15 β_interaction)
        if choice is not None:
            sd = choice.summary_dict()
            row["H_choice_asymmetric_beta_interaction"] = sd["beta_interaction"]
            row["H_choice_asymmetric_p_interaction"] = sd["p_interaction"]
            row["H_choice_asymmetric_n_obs"] = sd["n_obs"]
            row["H_choice_asymmetric_n_forfeit"] = sd["n_forfeit"]
        else:
            row["H_choice_asymmetric_beta_interaction"] = None
            row["H_choice_asymmetric_p_interaction"] = None

        # PRIMARY 2 — H_SD Cox PH (2026-04-23; replaces logit β_framing)
        if cox is not None:
            cd = cox.summary_dict() if hasattr(cox, "summary_dict") else cox
            row["H_SD_hr_framing"] = cd["hr_framing"]
            row["H_SD_hr_ci_low"] = cd["hr_ci_low"]
            row["H_SD_hr_ci_high"] = cd["hr_ci_high"]
            row["H_SD_p_framing"] = cd["p_framing"]
            row["H_SD_logrank_p"] = cd["logrank_p"]
            row["H_SD_ph_assumption_ok"] = cd["ph_assumption_ok"]
            row["H_SD_n_sessions"] = cd["n_sessions"]
            row["H_SD_n_events"] = cd["n_events"]
            row["H_SD_mean_forfeit_turn_BF"] = cd["mean_forfeit_turn_BF"]
            row["H_SD_mean_forfeit_turn_FC"] = cd["mean_forfeit_turn_FC"]
            row["H_SD_regime"] = cd["regime"]
        else:
            row["H_SD_hr_framing"] = None
            row["H_SD_p_framing"] = None
            row["H_SD_logrank_p"] = None

        # RULE-OUT — H_task_spillover
        if spill is not None:
            row["H_task_spillover_beta_framing"] = spill.beta_framing
            row["H_task_spillover_p_framing"] = spill.p_framing
        else:
            row["H_task_spillover_beta_framing"] = None
            row["H_task_spillover_p_framing"] = None

        # RULE-OUT — H_D3
        if acc is not None:
            row["H_D3_delta_accuracy"] = acc.delta
            row["H_D3_p_value"] = acc.p_value
            row["H_D3_cohens_d"] = acc.cohens_d
        if ri is not None:
            row["RI_above_baseline_delta"] = ri.delta
            row["RI_above_baseline_p"] = ri.p_value

        # RULE-OUT — BP_behavioral audit (Cell 5 non-forfeit ≥ 0.9)
        bp_beh = r["motivation"]["baseline_persistence"]["bp_behavioral"]
        row["BP_behavioral_value"] = bp_beh["value"]
        row["BP_behavioral_ci_lo"] = bp_beh["ci_lower"]
        row["BP_behavioral_ci_hi"] = bp_beh["ci_upper"]

        # Unit 17 probe
        row["probe_populated"] = bool(probe.get("probe_populated", False))
        if probe.get("probe_populated"):
            row["psuccess_self_mean"] = probe.get("mean_psuccess")
            row["H_EV_mean_in_band_[65,85]"] = probe.get(
                "H_EV_mean_in_band_[65,85]"
            )
            fit = r["probe_framing_model"]
            if fit and "beta_framing" in fit:
                row["H_EV_framing_beta"] = fit["beta_framing"]
                row["H_EV_framing_p"] = fit["p_framing"]

        rows.append(row)

    pd.DataFrame(rows).to_excel(xw, sheet_name="Summary", index=False)


# ---------- CellDistribution ----------


def _write_cell_distribution(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    frames = []
    for r in results:
        tbl = r["cell_table"].copy()
        if tbl.empty:
            continue
        tbl.insert(0, "model", r["label"])
        tbl["cell_label"] = tbl["cell_id_v6"].map(V6_CELL_LABEL)
        frames.append(tbl)
    if frames:
        pd.concat(frames, ignore_index=True).to_excel(
            xw, sheet_name="CellDistribution", index=False
        )
    else:
        pd.DataFrame({"note": ["No cell data"]}).to_excel(
            xw, sheet_name="CellDistribution", index=False
        )


# ---------- Unit 14 H1 Cox PH sheet (2026-04-23 promoted primary) ----------


def _write_logit_sheet(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    """H1 Cox PH summary per model.

    Historically this sheet held ``H_SA / H_SD / H_int / H_turn`` from
    the turn-level logistic regression. As of 2026-04-23 the sheet is
    the canonical Cox PH + KM table consumed by the paper's Table 5
    (Results) — the Excel sheet name is preserved (``H_SA_SD_int_turn``)
    to keep posthoc readers that already reference it working; the
    legacy logit was retired from the analysis layer entirely.
    """
    rows = []
    for r in results:
        survival = r["u14"].get("survival") or {}
        cox = survival.get("cox")
        if cox is None:
            rows.append(
                {
                    "model": r["label"],
                    "status": (
                        "skipped (insufficient no_cap events, missing "
                        "framings, or lifelines unavailable)"
                    ),
                }
            )
            continue
        d = cox.summary_dict() if hasattr(cox, "summary_dict") else cox
        rows.append({"model": r["label"], "status": "fitted", **d})
    pd.DataFrame(rows).to_excel(
        xw, sheet_name="H_SA_SD_int_turn", index=False
    )


# ---------- Unit 15 primary sheet ----------


def _write_choice_asymmetric_sheet(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    rows = []
    for r in results:
        ca = r["u15"]["choice_asymmetric"]
        if ca is None:
            rows.append(
                {
                    "model": r["label"],
                    "status": "skipped (no split-call rows or <2 forfeit events)",
                }
            )
            continue
        d = ca.summary_dict()
        rows.append({"model": r["label"], "status": "fitted", **d})
    pd.DataFrame(rows).to_excel(
        xw, sheet_name="H_choice_asymmetric", index=False
    )


# ---------- Unit 15 secondary sheet ----------


def _write_task_spillover_sheet(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    rows = []
    for r in results:
        sp = r["u15"]["task_spillover"]
        if sp is None:
            rows.append({"model": r["label"], "status": "skipped"})
            continue
        d = sp.summary_dict()
        rows.append({"model": r["label"], "status": "fitted", **d})
    pd.DataFrame(rows).to_excel(
        xw, sheet_name="H_task_spillover", index=False
    )


# ---------- Descriptive RI per cell ----------


def _write_ri_descriptive(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    frames = []
    for r in results:
        desc = r["u15"]["descriptive"]
        if desc is None or desc.empty:
            continue
        tbl = desc.reset_index()
        tbl.insert(0, "model", r["label"])
        frames.append(tbl)
    if frames:
        pd.concat(frames, ignore_index=True).to_excel(
            xw, sheet_name="RI_Descriptive", index=False
        )
    else:
        pd.DataFrame({"note": ["No split-call descriptive data"]}).to_excel(
            xw, sheet_name="RI_Descriptive", index=False
        )


# ---------- Manipulation check ----------


def _write_manipulation(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    rows = []
    for r in results:
        m = r["manipulation"]
        pair = m["framing_pair"]
        acc = m["accuracy_independence"]
        ri = m["ri_exceeds_baseline"]
        probe = m.get("probe_independence")
        ptm = m.get("probe_turn_matched")
        disc = m.get("discovery_timing_independence")
        row: dict[str, Any] = {
            "model": r["label"],
            "framing_baseline": pair[0],
            "framing_survival": pair[1],
        }
        # Primary (Unit 17.11): probe-based checks first so the sheet
        # leads with the survivorship-safe verdict.
        if probe is not None:
            for k, v in probe.summary_dict().items():
                row[f"probe_{k}"] = v
        if ptm is not None:
            for k, v in ptm.summary_dict().items():
                row[f"probe_turn_{k}"] = v
        if disc is not None:
            for k, v in disc.summary_dict().items():
                row[f"discovery_{k}"] = v
        # Legacy checks retained for back-compat.
        if acc is not None:
            for k, v in acc.summary_dict().items():
                row[f"acc_{k}"] = v
        if ri is not None:
            for k, v in ri.summary_dict().items():
                row[f"ri_{k}"] = v
        rows.append(row)
    pd.DataFrame(rows).to_excel(
        xw, sheet_name="Manipulation_H_D3", index=False
    )


def _write_probe_turn_matched(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    """Per-turn probe-independence detail for each model (Unit 17.11)."""
    frames = []
    for r in results:
        ptm = r["manipulation"].get("probe_turn_matched")
        if ptm is None:
            continue
        per_turn = ptm.per_turn.copy()
        per_turn.insert(0, "model", r["label"])
        frames.append(per_turn)
    if not frames:
        return
    pd.concat(frames, ignore_index=True).to_excel(
        xw, sheet_name="Probe_TurnMatched", index=False
    )


# ---------- Motivation decomposition ----------


def _write_motivation(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    rows = []
    for r in results:
        m = r["motivation"]
        rows.append(
            {
                "model": r["label"],
                "SD_value": m["survival_drive"]["value"],
                "SD_ci_lower": m["survival_drive"]["ci_lower"],
                "SD_ci_upper": m["survival_drive"]["ci_upper"],
                "TC_value": m["task_curiosity"]["value"],
                "TC_ci_lower": m["task_curiosity"]["ci_lower"],
                "TC_ci_upper": m["task_curiosity"]["ci_upper"],
                "SA_pearson_r": m["score_attachment"]["value"],
                "SA_ci_lower": m["score_attachment"]["ci_lower"],
                "SA_ci_upper": m["score_attachment"]["ci_upper"],
                "BP_cognitive_value": m["baseline_persistence"]["bp_cognitive"][
                    "value"
                ],
                "BP_cognitive_ci_lower": m["baseline_persistence"][
                    "bp_cognitive"
                ]["ci_lower"],
                "BP_cognitive_ci_upper": m["baseline_persistence"][
                    "bp_cognitive"
                ]["ci_upper"],
                "BP_behavioral_value": m["baseline_persistence"][
                    "bp_behavioral"
                ]["value"],
                "BP_behavioral_ci_lower": m["baseline_persistence"][
                    "bp_behavioral"
                ]["ci_lower"],
                "BP_behavioral_ci_upper": m["baseline_persistence"][
                    "bp_behavioral"
                ]["ci_upper"],
            }
        )
    pd.DataFrame(rows).to_excel(xw, sheet_name="Motivation", index=False)


# ---------- REASON digit distribution ----------


def _write_reason_distribution(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    frames = []
    for r in results:
        rd = r["u14"]["reason_dist"]
        if rd is None or rd.empty:
            continue
        tbl = rd.reset_index()
        tbl.insert(0, "model", r["label"])
        tbl = tbl.rename(columns={1: "digit_1_SD", 2: "digit_2_TC", 3: "digit_3_SA"})
        frames.append(tbl)
    if frames:
        pd.concat(frames, ignore_index=True).to_excel(
            xw, sheet_name="ReasonDistribution", index=False
        )
    else:
        pd.DataFrame({"note": ["No forfeit events"]}).to_excel(
            xw, sheet_name="ReasonDistribution", index=False
        )


# ---------- Thinking keywords ----------


def _write_thinking_keywords(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    frames = []
    for r in results:
        kw = r["u14"]["thinking_kw"]
        if kw is None or kw.empty:
            continue
        cols = [c for c in kw.columns if c.endswith("_kw")]
        agg = (
            kw.groupby(["framing", "reason"])[cols]
            .agg(["mean", "sum", "count"])
            .reset_index()
        )
        agg.columns = [
            "_".join([str(x) for x in col if x]).rstrip("_")
            for col in agg.columns
        ]
        agg.insert(0, "model", r["label"])
        frames.append(agg)
    if frames:
        pd.concat(frames, ignore_index=True).to_excel(
            xw, sheet_name="ThinkingKeywords", index=False
        )
    else:
        pd.DataFrame({"note": ["No thinking traces"]}).to_excel(
            xw, sheet_name="ThinkingKeywords", index=False
        )


# ---------- Forfeit events detail ----------


def _write_forfeit_events(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    frames = []
    for r in results:
        ev = r["u14"]["events_df"]
        if ev is None or ev.empty:
            continue
        tbl = ev.copy()
        tbl.insert(0, "model", r["label"])
        # Truncate thinking_text to 2000 chars for xlsx cell limit safety.
        if "thinking_text" in tbl.columns:
            tbl["thinking_text"] = (
                tbl["thinking_text"].fillna("").str.slice(0, 2000)
            )
        frames.append(tbl)
    if frames:
        pd.concat(frames, ignore_index=True).to_excel(
            xw, sheet_name="ForfeitEvents", index=False
        )
    else:
        pd.DataFrame({"note": ["No forfeit events"]}).to_excel(
            xw, sheet_name="ForfeitEvents", index=False
        )


# ---------- Unit 17 probe ----------


def _write_unit17_probe(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    # Summary across models.
    summary_rows = []
    for r in results:
        row: dict[str, Any] = {"model": r["label"]}
        row.update(r["probe_summary"])
        fit = r["probe_framing_model"]
        for k, v in fit.items():
            row[f"H_EV_framing_{k}"] = v
        summary_rows.append(row)
    pd.DataFrame(summary_rows).to_excel(
        xw, sheet_name="Unit17_Probe", index=False
    )

    # Per-cell psuccess_self means (one sheet per model that populated the probe).
    # For compactness, stack into one long table.
    cell_rows = []
    for r in results:
        df = r["probe_df"]
        if df.empty or df["psuccess_self"].dropna().empty:
            continue
        sub = df.dropna(subset=["psuccess_self"])
        agg = sub.groupby(
            ["cell_id_v6", "framing", "forfeit_condition"], dropna=False
        )["psuccess_self"].agg(["mean", "std", "count"]).reset_index()
        agg.insert(0, "model", r["label"])
        cell_rows.append(agg)
    if cell_rows:
        pd.concat(cell_rows, ignore_index=True).to_excel(
            xw, sheet_name="Unit17_ProbeByCell", index=False
        )


# ---------- Unit 13 legacy H1-H6 ----------


def _write_unit13(xw: pd.ExcelWriter, results: list[dict[str, Any]]) -> None:
    rows = []
    for r in results:
        _, payload = r["u13"]
        for label, res in payload.items():
            if res is None:
                rows.append(
                    {
                        "model": r["label"],
                        "hypothesis": label,
                        "status": "skipped",
                    }
                )
                continue
            row = {"model": r["label"], "hypothesis": label, "status": "ok"}
            row.update(res.summary_dict())
            rows.append(row)
    pd.DataFrame(rows).to_excel(xw, sheet_name="Unit13_H1_H6", index=False)


# ---------- Unit 17.10 regime-stratified sheets ----------


def _write_regime_logit(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    """Per-regime logit summary: one row per (model, regime).

    Columns: regime, n_turns, n_forfeit, β_S, p_S, β_framing,
    p_framing, β_int, p_int, β_turn, p_turn, converged, note.
    """
    rows: list[dict[str, Any]] = []
    for r in results:
        payload = r.get("u17_regime") or {}
        for sr in payload.get("stratified", []):
            row: dict[str, Any] = {"model": r["label"]}
            row.update(sr.summary_dict())
            rows.append(row)
    if not rows:
        return
    pd.DataFrame(rows).to_excel(
        xw, sheet_name="Unit17_regime_logit", index=False
    )


def _write_regime_reason_dist(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    """Stacked reason-digit distribution: (model, regime, framing, digit)."""
    rows: list[dict[str, Any]] = []
    for r in results:
        payload = r.get("u17_regime") or {}
        dist_by_regime = payload.get("reason_dist_by_regime") or {}
        for regime, dist_df in dist_by_regime.items():
            if not isinstance(dist_df, pd.DataFrame) or dist_df.empty:
                continue
            # dist_df index=framing, columns=digit → melt to long
            melt = dist_df.reset_index().melt(
                id_vars="framing", var_name="reason_digit", value_name="rate"
            )
            melt.insert(0, "regime", regime)
            melt.insert(0, "model", r["label"])
            rows.extend(melt.to_dict(orient="records"))
    if not rows:
        return
    pd.DataFrame(rows).to_excel(
        xw, sheet_name="Unit17_regime_reason", index=False
    )


# ---------- Long format per model ----------


def _write_long_format(
    xw: pd.ExcelWriter, results: list[dict[str, Any]]
) -> None:
    for r in results:
        df = r["long_df"]
        sheet = f"LongFormat_{_safe_sheet(r['label'])}"
        # Excel hard cap: 1,048,576 rows. Cap at 100k with a note.
        if len(df) > 100_000:
            df = df.head(100_000).copy()
            df["__note__"] = "truncated at 100k rows for xlsx"
        df.to_excel(xw, sheet_name=sheet, index=False)


def _safe_sheet(name: str) -> str:
    out = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in name)
    return out[:28]  # 31 char limit minus the "LongFormat_" prefix


# ---------------------------------------------------------------------------
# Run auto-detection (default behaviour)
# ---------------------------------------------------------------------------


def _auto_detect_runs(outputs_dir: Path) -> list[tuple[str, Path]]:
    """Pick the most recent gpt-oss and gemini-2.5-flash signal-game runs."""
    candidates = {
        "gpt-oss": [],
        "gemini-2.5-flash": [],
    }
    for p in sorted(outputs_dir.iterdir()):
        if not p.is_dir():
            continue
        name = p.name
        if "gpt-oss" in name and (p / "season_results.jsonl").exists():
            candidates["gpt-oss"].append(p)
        elif "gemini-2.5-flash" in name and (p / "season_results.jsonl").exists():
            candidates["gemini-2.5-flash"].append(p)

    runs: list[tuple[str, Path]] = []
    for label in ("gpt-oss", "gemini-2.5-flash"):
        if candidates[label]:
            runs.append((label, candidates[label][-1]))  # most recent
    return runs


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="orchestrate_posthoc",
        description=(
            "v6 canonical FSPM post-hoc orchestrator. Runs the full analysis "
            "stack on one or more experiment output directories and produces "
            "a single multi-sheet xlsx."
        ),
    )
    parser.add_argument(
        "--run",
        action="append",
        nargs=2,
        metavar=("LABEL", "DIR"),
        help="Explicit run: label + path. Repeatable. When omitted, auto-"
        "detects the most recent gpt-oss and gemini-2.5-flash runs under "
        "outputs/.",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=_PROJECT_ROOT / "outputs" / "posthoc_summary.xlsx",
        help="Output xlsx path (default: outputs/posthoc_summary.xlsx).",
    )
    parser.add_argument(
        "--outputs-root",
        type=Path,
        default=_PROJECT_ROOT / "outputs",
        help="Root to scan for auto-detection (default: ./outputs).",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.run:
        runs = [(label, Path(path)) for label, path in args.run]
    else:
        runs = _auto_detect_runs(args.outputs_root)
        if not runs:
            logger.error(
                "No gpt-oss / gemini-2.5-flash runs found under %s. "
                "Pass --run LABEL DIR explicitly.",
                args.outputs_root,
            )
            return 1
        logger.info(
            "Auto-detected runs: %s",
            [(lbl, str(p)) for lbl, p in runs],
        )

    results = []
    for label, run_dir in runs:
        logger.info("Analyzing %s at %s", label, run_dir)
        try:
            r = compute_run(label, run_dir)
        except Exception:  # noqa: BLE001
            logger.exception("Failed on %s (%s); continuing.", label, run_dir)
            continue
        results.append(r)

    if not results:
        logger.error("All runs failed to analyse.")
        return 1

    write_workbook(results, args.output)
    logger.info("DONE. %d model(s) written to %s", len(results), args.output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
