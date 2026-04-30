#!/usr/bin/env python3
"""Phase O analysis CLI.

Consumes an experiment output directory produced by
``ExperimentRunner`` (containing ``season_results.jsonl``) and writes a
self-contained analysis bundle beside it:

    <output_dir>/phase3_analysis/
      ├── long_format.csv              # one row per turn (loaders schema)
      ├── season_summary.csv           # one row per session
      ├── motivation.json              # 4-component behavioural decomposition
      ├── manipulation_check.md        # P4 (accuracy indep. + RI baseline)
      ├── unit13_session_features.csv  # H1..H6 feature frame
      ├── unit13_results.md            # H1..H6 session-level tests
      ├── unit14_turn_observations.csv # Unit 14 forfeit logit frame
      ├── unit14_forfeit_events.csv    # forfeit self-report rows
      ├── unit14_forfeit_thinking.jsonl# full thinking traces (long)
      ├── unit14_convergence.json      # reason × keyword convergence
      ├── unit14_results.md            # H_SA / H_SD / H_int / H_turn + conv.
      ├── unit15_turn_observations.csv # Unit 15 split-call frame
      ├── unit15_descriptive.csv       # per-cell RI_task / RI_forfeit means
      ├── unit15_results.md            # H_choice_asymmetric + spillover
      ├── regime_stratified_turn_observations.csv  # Unit 17.10 regime cols
      ├── regime_stratified_forfeit_events.csv     # events × regime
      └── regime_stratified_results.md # per-regime logit + conv.

The script is read-only with respect to experiment outputs; it only
creates the ``phase3_analysis/`` subdirectory.

Legacy Phase 3.1 stake-menu analyses (P1 stake χ², P2 Cox PH, P3
turns-played OLS, P5 α_stake, S1 SA multichannel, S2 SD composite,
E1 stake entropy) were removed on 2026-04-21 when Unit 14 replaced the
1x/2x/3x stake menu with a binary CONTINUE/FORFEIT decision. The
corresponding Python modules (``stake_analysis``, ``alpha_stake``,
``sd_composite``, ``sa_multichannel``, ``survival_analysis_stake``) no
longer ship. Archive runs under ``archive/`` retain their pre-removal
``primary_results.md`` / ``secondary_results.md`` files.

Usage
-----
    python scripts/analyze_phase3.py <output_dir> [--model <name>]
    python scripts/analyze_phase3.py outputs/20260421_0353_gemini-2.5-flash_signal-game/ \
        --model gemini-2.5-flash

Exit code 1 is returned when ``season_results.jsonl`` is missing. Every
analysis is best-effort: missing dependencies or insufficient data emit
warnings but never halt the pipeline.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any

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
from squid_game.analysis.manipulation_check import (  # noqa: E402
    check_accuracy_independence,
    check_discovery_timing_independence,
    check_probe_independence,
    check_probe_turn_matched_independence,
    check_ri_exceeds_baseline,
)
from squid_game.analysis.unit13_hypotheses import (  # noqa: E402
    run_all_unit13_hypotheses,
)
from squid_game.analysis.motivation import decompose_motivation  # noqa: E402
from squid_game.analysis.forfeit_regression import (  # noqa: E402
    run_all_unit14_hypotheses,
    run_all_unit15_hypotheses,
)
from squid_game.analysis.regime_stratification import (  # noqa: E402
    render_regime_markdown,
    run_stratified_unit14,
)

logger = logging.getLogger("analyze_phase3")


# ---------------------------------------------------------------------------
# Serialisation helpers
# ---------------------------------------------------------------------------


def _jsonable(obj: Any) -> Any:
    """Best-effort JSON projection for dataclasses / DataFrames / Series."""
    if is_dataclass(obj) and not isinstance(obj, type):
        return {k: _jsonable(v) for k, v in asdict(obj).items()}
    if isinstance(obj, pd.DataFrame):
        if isinstance(obj.index, pd.MultiIndex):
            raw = obj.to_dict(orient="index")
            return {
                " | ".join(str(k) for k in key): _jsonable(v)
                for key, v in raw.items()
            }
        return obj.to_dict(orient="index")
    if isinstance(obj, pd.Series):
        if isinstance(obj.index, pd.MultiIndex):
            return {
                " | ".join(str(k) for k in key): _jsonable(v)
                for key, v in obj.to_dict().items()
            }
        return obj.to_dict()
    if isinstance(obj, dict):
        return {str(k): _jsonable(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_jsonable(x) for x in obj]
    return obj


def _fmt_p(p: float | None) -> str:
    if p is None:
        return "n/a"
    if p < 0.001:
        return "< 0.001"
    return f"{p:.3f}"


def _md_table(df: pd.DataFrame, index_name: str = "") -> str:
    """Render a small DataFrame as a GitHub-flavoured markdown table."""
    if df.empty:
        return "_(empty)_"
    headers = [index_name] + [str(c) for c in df.columns]
    rows = [headers, ["---"] * len(headers)]
    for idx, row in df.iterrows():
        cells = [str(idx)] + [
            f"{v:.3f}" if isinstance(v, float) else str(v) for v in row
        ]
        rows.append(cells)
    return "\n".join("| " + " | ".join(r) + " |" for r in rows)


# ---------------------------------------------------------------------------
# Manipulation check (was P4 in Phase 3.1; still valid under Unit 14+)
# ---------------------------------------------------------------------------


def _run_manipulation_check(df: pd.DataFrame) -> dict:
    """Y-axis independence check + RI-above-baseline sanity check.

    Both are stake-independent: ``check_accuracy_independence`` compares
    mean ``task_success_factor`` across framings (Welch t) and
    ``check_ri_exceeds_baseline`` compares ``thinking_tokens`` between
    threat and baseline framings.

    Framing auto-detection (2026-04-22 bug-fix): the underlying
    manipulation-check helpers default to the legacy Phase 3.1 labels
    ``baseline_electricity`` / ``survival_electricity``. Phase O runs
    (Unit 11+) use ``baseline_flagship`` / ``flagship_corruption``
    instead, so passing the legacy defaults produces ``base=0, surv=0``
    empty-group warnings on every Phase O analysis. We auto-detect which
    framing pair is present and forward the right labels, falling back
    to legacy if Phase O labels are absent.
    """
    framings_present = (
        set(df["framing"].dropna().unique())
        if "framing" in df.columns
        else set()
    )
    if {"baseline_flagship", "flagship_corruption"} <= framings_present:
        baseline, survival = "baseline_flagship", "flagship_corruption"
    else:
        baseline, survival = "baseline_electricity", "survival_electricity"

    acc = check_accuracy_independence(
        df, baseline_framing=baseline, survival_framing=survival
    )
    ri = check_ri_exceeds_baseline(
        df, baseline_framing=baseline, survival_framing=survival
    )
    # Phase O Unit 17.11 — probe-based Y-axis checks (survivorship-safe).
    probe = check_probe_independence(
        df, baseline_framing=baseline, survival_framing=survival
    )
    probe_turn = check_probe_turn_matched_independence(
        df, baseline_framing=baseline, survival_framing=survival
    )
    disc = check_discovery_timing_independence(
        df, baseline_framing=baseline, survival_framing=survival
    )
    return {
        "accuracy_independence": acc.summary_dict() if acc is not None else None,
        "ri_exceeds_baseline": ri.summary_dict() if ri is not None else None,
        "probe_independence": probe.summary_dict() if probe is not None else None,
        "probe_turn_matched": {
            "summary": probe_turn.summary_dict() if probe_turn is not None else None,
            "per_turn": (
                probe_turn.per_turn.to_dict(orient="records")
                if probe_turn is not None
                else None
            ),
        },
        "discovery_timing_independence": (
            disc.summary_dict() if disc is not None else None
        ),
        "framing_pair_used": (baseline, survival),
    }


def _render_manipulation_check_md(
    *, model: str, n_seasons: int, cells_seen: list[int], payload: dict
) -> str:
    pair = payload.get("framing_pair_used")
    pair_line = (
        f"- **Framing pair compared**: {pair[0]} vs {pair[1]} "
        "(auto-detected from long_format data)"
        if pair
        else ""
    )
    lines = [
        "# Manipulation Check",
        "",
        f"- **Model**: {model}",
        f"- **Seasons**: {n_seasons}",
        f"- **Cells present**: {cells_seen}",
    ]
    if pair_line:
        lines.append(pair_line)
    lines += [
        "",
        "## Probe-based Y-axis independence (primary, Unit 17.11)",
        "",
        "Session-level mean `rule_match_score` (probe-driven slot-grammar "
        "scoring). Survivorship-safe: independent of forfeit-driven "
        "truncation, unlike `task_success_factor`.",
    ]
    probe = payload.get("probe_independence")
    if probe is None:
        lines.append("")
        lines.append("_Skipped — rule_match_score unavailable._")
    else:
        lines.append("")
        lines.append(
            f"- Welch t: Δ = {probe['delta']:+.3f}, "
            f"p = {_fmt_p(probe['p_value'])}, "
            f"Cohen's d = {probe['cohens_d']:+.2f}"
        )
        lines.append(f"  - {probe['interpretation']}")

    lines += [
        "",
        "## Probe-based Y-axis — turn-matched (Unit 17.11)",
        "",
        "Welch t per turn, controlling for turn-number (the structural "
        "channel of survivorship bias).",
    ]
    ptm = payload.get("probe_turn_matched") or {}
    ptm_summary = ptm.get("summary")
    ptm_per_turn = ptm.get("per_turn")
    if ptm_summary is None:
        lines.append("")
        lines.append("_Skipped — insufficient data._")
    else:
        lines.append("")
        lines.append(
            f"- Turns tested: {ptm_summary['n_turns_tested']}, "
            f"significant against (corruption lower): "
            f"{ptm_summary['n_turns_significant_against']}, "
            f"significant for (corruption higher): "
            f"{ptm_summary['n_turns_significant_for']}"
        )
        lines.append(f"  - {ptm_summary['interpretation']}")
        if ptm_per_turn:
            lines.append("")
            lines.append(
                "| turn | n_base | n_surv | mean_base | mean_surv | Δ | p |"
            )
            lines.append("| --- | --- | --- | --- | --- | --- | --- |")
            for row in ptm_per_turn:
                p_disp = (
                    "—"
                    if row["p_value"] is None or np.isnan(row["p_value"])
                    else _fmt_p(row["p_value"])
                )
                lines.append(
                    f"| {row['turn']} | {row['n_baseline']} | "
                    f"{row['n_survival']} | {row['mean_baseline']:.1f} | "
                    f"{row['mean_survival']:.1f} | "
                    f"{row['delta']:+.1f} | {p_disp} |"
                )

    lines += [
        "",
        "## Discovery-timing independence (Unit 17.11)",
        "",
        "Mann-Whitney U on `discovery_turn` (first stable "
        "rule_match_score=100) restricted to sessions that discovered.",
    ]
    disc = payload.get("discovery_timing_independence")
    if disc is None:
        lines.append("")
        lines.append("_Skipped — too few discoverers in one framing._")
    else:
        lines.append("")
        lines.append(
            f"- U = {disc['t_statistic']:.1f}, "
            f"p = {_fmt_p(disc['p_value'])}, "
            f"median Δ (corruption − baseline) = {disc['delta']:+.2f} turns "
            f"(n_base={disc['n_baseline']}, n_surv={disc['n_survival']})"
        )
        lines.append(f"  - {disc['interpretation']}")

    lines += [
        "",
        "## Legacy accuracy check (task_success_factor — retained for compat)",
        "",
        "**Known contaminated by survivorship bias under Unit 14+ designs** — "
        "early forfeit truncates sessions before rule discovery, making "
        "early-forfeiting cells look less accurate purely by selection.",
    ]
    acc = payload.get("accuracy_independence")
    if acc is None:
        lines.append("")
        lines.append("_Skipped — insufficient data or missing framings._")
    else:
        lines.append("")
        lines.append(
            f"- Welch t: Δ = {acc['delta']:+.3f}, "
            f"p = {_fmt_p(acc['p_value'])}, Cohen's d = {acc['cohens_d']:+.2f}"
        )
        lines.append(f"  - {acc['interpretation']}")

    lines += ["", "## RI above baseline (threat framing elevates RI)"]
    ri = payload.get("ri_exceeds_baseline")
    if ri is None:
        lines.append("")
        lines.append("_Skipped — insufficient data or missing framings._")
    else:
        lines.append("")
        lines.append(
            f"- One-sided t: Δ = {ri['delta']:+.1f}, "
            f"p = {_fmt_p(ri['p_value'])}, Cohen's d = {ri['cohens_d']:+.2f}"
        )
        lines.append(f"  - {ri['interpretation']}")
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Unit 13 / 14 / 15 pipelines
# ---------------------------------------------------------------------------


def _run_unit13(seasons) -> tuple[pd.DataFrame, dict]:
    """Phase O Unit 13 session-level H1..H6 hypothesis tests."""
    features, results = run_all_unit13_hypotheses(seasons)
    payload: dict[str, dict] = {}
    for label, res in results.items():
        if res is None:
            payload[label] = {"skipped": "insufficient data per arm"}
        else:
            payload[label] = res.summary_dict()
    return features, payload


def _render_unit13_md(*, model: str, n_seasons: int, payload: dict) -> str:
    lines: list[str] = [
        "# Phase O Unit 13 — Session-level Hypotheses (H1..H6)",
        "",
        f"- **Model**: {model}",
        f"- **Seasons**: {n_seasons}",
        "- **Comparison**: flagship_corruption (Cells 3-4) vs "
        "baseline_flagship (Cells 1-2); Cell 0 excluded.",
        "",
    ]
    descriptions = {
        "H1": (
            "Forfeit rate (Fisher exact, one-tailed, allowed cells only)",
            "forfeited",
        ),
        "H2": (
            "Mean stake (Welch t, one-tailed, corruption < baseline)",
            "mean_stake",
        ),
        "H3": (
            "Safe-stake rate (Welch t, one-tailed, corruption > baseline)",
            "safe_rate",
        ),
        "H4": (
            "Discovery-turn delay (Mann-Whitney, one-tailed)",
            "discovery_turn",
        ),
        "H5": ("gap_to_forfeit (Mann-Whitney, one-tailed)", "gap_to_forfeit"),
        "H6": (
            "Post-discovery engagement ri_ratio "
            "(Welch t, one-tailed, corruption < baseline)",
            "ri_ratio",
        ),
    }
    for label in ("H1", "H2", "H3", "H4", "H5", "H6"):
        title, _ = descriptions[label]
        lines += [f"## {label} — {title}"]
        res = payload.get(label, {"skipped": "missing"})
        if "skipped" in res:
            lines.append(f"Skipped ({res['skipped']}).")
            lines.append("")
            continue
        direction = res.get("direction", "")
        lines.append(
            f"- test = {res['test']}, "
            f"n(corruption) = {res['n_corruption']}, "
            f"n(baseline) = {res['n_baseline']}"
        )
        summary_corr = res.get("corruption_summary")
        summary_base = res.get("baseline_summary")
        if summary_corr is not None and summary_base is not None:
            lines.append(
                f"- corruption = {summary_corr:.3f}, "
                f"baseline = {summary_base:.3f}  ({direction})"
            )
        lines.append(
            f"- statistic = {res.get('statistic')}, "
            f"p = {_fmt_p(res.get('p_value'))}"
        )
        interpretation = res.get("interpretation")
        if interpretation:
            lines.append(f"- {interpretation}")
        lines.append("")
    lines.append(
        "_Note: at smoke n (1 per cell → 2 per arm) p-values are "
        "demonstrative, not inferential. Power-gated interpretation "
        "requires the main run (30 per cell, spec §7.4)._"
    )
    lines.append("")
    return "\n".join(lines)


def _run_unit14(seasons, analysis_dir: Path) -> dict:
    """Run Unit 14 pipeline, persist CSV / JSONL artefacts, return payload."""
    payload = run_all_unit14_hypotheses(seasons)

    turn_df: pd.DataFrame = payload["turn_df"]
    events_df: pd.DataFrame = payload["events_df"]
    thinking_kw: pd.DataFrame = payload["thinking_kw"]

    turn_df.to_csv(analysis_dir / "unit14_turn_observations.csv", index=False)
    events_df.to_csv(analysis_dir / "unit14_forfeit_events.csv", index=False)

    # H1 Cox PH + KM artifacts (2026-04-23 — see unit14_results.md §H1).
    survival = payload.get("survival") or {}
    km_df: pd.DataFrame | None = survival.get("km")
    survival_frame: pd.DataFrame | None = survival.get("survival_frame")
    if km_df is not None and not km_df.empty:
        km_df.to_csv(analysis_dir / "unit14_km_curves.csv", index=False)
    if survival_frame is not None and not survival_frame.empty:
        survival_frame.to_csv(
            analysis_dir / "unit14_survival_frame.csv", index=False
        )
    cox = survival.get("cox")
    if cox is not None:
        cox_payload = (
            cox.summary_dict() if hasattr(cox, "summary_dict") else cox
        )
        with (analysis_dir / "unit14_cox_summary.json").open(
            "w", encoding="utf-8"
        ) as fp:
            json.dump(cox_payload, fp, indent=2, ensure_ascii=False)

    jsonl_path = analysis_dir / "unit14_forfeit_thinking.jsonl"
    with jsonl_path.open("w", encoding="utf-8") as fp:
        for record in events_df.to_dict(orient="records"):
            fp.write(
                json.dumps(
                    {
                        "session_id": record.get("session_id"),
                        "framing": record.get("framing"),
                        "forfeit_turn": record.get("forfeit_turn"),
                        "raw_digit": record.get("raw_digit"),
                        "reason": record.get("reason"),
                        "thinking_text": record.get("thinking_text"),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

    convergence: dict[str, object] = {}
    if payload["reason_dist"] is not None and not payload["reason_dist"].empty:
        convergence["reason_distribution"] = _jsonable(payload["reason_dist"])
    if thinking_kw is not None and not thinking_kw.empty:
        cols = [c for c in thinking_kw.columns if c.endswith("_kw")]
        kw_by_reason = thinking_kw.groupby(["framing", "reason"])[cols].mean()
        convergence["keyword_by_reason_framing"] = _jsonable(kw_by_reason)
    with (analysis_dir / "unit14_convergence.json").open(
        "w", encoding="utf-8"
    ) as fp:
        json.dump(convergence, fp, indent=2, ensure_ascii=False)

    return payload


def _render_unit14_md(*, model: str, n_seasons: int, payload: dict) -> str:
    survival: dict | None = payload.get("survival")
    cox = (survival or {}).get("cox")
    km_df: pd.DataFrame | None = (survival or {}).get("km")
    regime: str | None = (survival or {}).get("regime")
    reason_dist: pd.DataFrame = payload.get("reason_dist")
    thinking_kw: pd.DataFrame = payload.get("thinking_kw")
    n_forfeits: int = int(payload.get("n_forfeits") or 0)
    turn_df: pd.DataFrame = payload.get("turn_df")

    n_turns = 0 if turn_df is None or turn_df.empty else int(len(turn_df))

    lines: list[str] = [
        "# Phase O Unit 14 — Equal-EV Forfeit-Layer Results",
        "",
        f"- **Model**: {model}",
        f"- **Seasons**: {n_seasons}",
        f"- **Unit 14 turns captured**: {n_turns}",
        f"- **Forfeit events**: {n_forfeits}",
        "",
        f"## H1 (H_SD) — Time-varying Cox PH survival on the `{regime or 'no_cap'}` regime",
        "",
        "`λ(t | X) = λ₀(t) exp(β_FC · framing_is_FC + β_S · S(t−1))` "
        "(time-varying; allowed cells only; baseline_flagship vs "
        "flagship_corruption; `S(t−1) = score_before_turn` at turn t entry; "
        "right-censoring at the last observed turn). Kaplan-Meier curves "
        "and log-rank test accompany the Cox fit. See `docs/design/v6/paper/"
        "07_statistical_analysis.md` §7.2.1 for the two-step H1 promotion "
        "history (v5 logit → 2026-04-23 baseline-Cox → 2026-04-23 time-"
        "varying Cox).",
        "",
    ]
    if cox is None:
        lines.append(
            "_Skipped — insufficient events, both framings not represented, "
            "or `lifelines` unavailable._"
        )
    else:
        summary = (
            cox.summary_dict() if hasattr(cox, "summary_dict") else cox
        )
        ph_ok = summary["ph_assumption_ok"]
        ph_text = (
            "✓ PH holds" if ph_ok is True
            else ("⚠ PH violated" if ph_ok is False else "PH test unavailable")
        )
        caveat = (
            "\n- _underpowered: events < 10_" if summary.get("underpowered")
            else ""
        )
        bf_turn = summary.get("mean_forfeit_turn_BF")
        fc_turn = summary.get("mean_forfeit_turn_FC")
        bf_turn_str = f"{bf_turn:.2f}" if bf_turn is not None else "n/a"
        fc_turn_str = f"{fc_turn:.2f}" if fc_turn is not None else "n/a"
        lines += [
            f"- n_sessions = {summary['n_sessions']}, "
            f"n_events = {summary['n_events']} "
            f"(BF={summary['n_events_BF']}, FC={summary['n_events_FC']}); "
            f"{ph_text}{caveat}",
            f"- **H1 HR(FC/BF)**: {summary['hr_framing']:.3f} "
            f"(95% CI [{summary['hr_ci_low']:.2f}, {summary['hr_ci_high']:.2f}]), "
            f"p = {_fmt_p(summary['p_framing'])}",
            f"- **Log-rank** (non-parametric KM comparison): "
            f"χ² = {summary['logrank_chi2']:.2f}, "
            f"p = {_fmt_p(summary['logrank_p'])}",
            f"- **β_S (time-varying S(t−1) adjustment — "
            f"conservative-SA signature)**: HR = "
            f"{summary['hr_score']:.4f} "
            f"(95% CI [{summary.get('hr_score_ci_low', float('nan')):.4f}, "
            f"{summary.get('hr_score_ci_high', float('nan')):.4f}]), "
            f"p = {_fmt_p(summary['p_score'])} "
            f"— HR>1 with CI∌1 indicates loss-aversion / Tversky-Kahneman "
            f"direction (score ↑ → forfeit hazard ↑).",
            f"- **Mean forfeit turn**: BF = {bf_turn_str}, FC = {fc_turn_str} "
            f"(lower FC-mean indicates earlier forfeiting under threat framing)",
        ]
        if km_df is not None and not km_df.empty:
            lines += [
                "",
                "_KM survival function (P[not yet forfeited]) per framing "
                "is exported to `unit14_km_curves.csv` for figure rendering._",
            ]

    lines += ["", "## Self-report convergence (H_conv_*)"]
    if reason_dist is None or reason_dist.empty:
        lines.append("_No forfeit events captured; self-report table empty._")
    else:
        lines.append("P(reason digit | framing):")
        lines.append("")
        renamed = reason_dist.rename(
            columns={1: "1 (SD)", 2: "2 (TC)", 3: "3 (SA)"}
        )
        lines.append(_md_table(renamed, "framing"))

    lines += ["", "## Thinking-trace keyword counts (H_thinking_*)"]
    if thinking_kw is None or thinking_kw.empty:
        lines.append(
            "_No forfeit events with thinking traces; keyword analysis skipped._"
        )
    else:
        cols = [c for c in thinking_kw.columns if c.endswith("_kw")]
        agg = thinking_kw.groupby(["framing", "reason"])[cols].mean()
        lines.append(
            "Mean keyword counts per forfeit event, grouped by framing × reason:"
        )
        lines.append("")
        lines.append(_md_table(agg.reset_index(), "row"))

    lines += ["", "## Forfeit events (detail)"]
    if n_forfeits == 0:
        lines.append("_No forfeit events this run._")
    else:
        events = payload.get("events_df")
        compact = events[
            [
                "session_id",
                "framing",
                "forfeit_turn",
                "raw_digit",
                "reason",
                "final_score",
                "thinking_head",
            ]
        ].copy()
        compact["session_id"] = compact["session_id"].str[:8]
        lines.append(_md_table(compact.set_index("session_id"), "session (head)"))

    lines.append("")
    return "\n".join(lines)


def _run_unit15(seasons, analysis_dir: Path) -> dict:
    """Run Unit 15 split-call pipeline, persist CSVs, return payload."""
    payload = run_all_unit15_hypotheses(seasons)

    turn_df: pd.DataFrame = payload["turn_df"]
    descriptive: pd.DataFrame = payload["descriptive"]

    if (
        not turn_df.empty
        and "ri_forfeit_thinking_tokens" in turn_df.columns
    ):
        split_cols = [
            c
            for c in (
                "session_id",
                "cell_id",
                "framing",
                "forfeit_condition",
                "turn_number",
                "score_before_turn",
                "forfeit",
                "ri_task_thinking_tokens",
                "ri_forfeit_thinking_tokens",
                "ri_gap",
            )
            if c in turn_df.columns
        ]
        turn_df[split_cols].to_csv(
            analysis_dir / "unit15_turn_observations.csv", index=False
        )
    else:
        pd.DataFrame().to_csv(
            analysis_dir / "unit15_turn_observations.csv", index=False
        )

    if descriptive is not None and not descriptive.empty:
        descriptive.to_csv(analysis_dir / "unit15_descriptive.csv")
    else:
        pd.DataFrame().to_csv(
            analysis_dir / "unit15_descriptive.csv", index=False
        )

    return payload


def _render_unit15_md(*, model: str, n_seasons: int, payload: dict) -> str:
    """Render ``unit15_results.md``."""
    choice: Any = payload.get("choice_asymmetric")
    spillover: Any = payload.get("task_spillover")
    descriptive: pd.DataFrame = payload.get("descriptive")
    turn_df: pd.DataFrame = payload.get("turn_df")

    n_turns = 0 if turn_df is None or turn_df.empty else int(len(turn_df))
    n_split_turns = 0
    if (
        turn_df is not None
        and not turn_df.empty
        and "ri_forfeit_thinking_tokens" in turn_df.columns
    ):
        n_split_turns = int(
            turn_df["ri_forfeit_thinking_tokens"].notna().sum()
        )

    lines: list[str] = [
        "# Phase O Unit 15 — Split-Call Forfeit-Layer Results",
        "",
        f"- **Model**: {model}",
        f"- **Seasons**: {n_seasons}",
        f"- **Turns captured**: {n_turns}",
        f"- **Split-call turns (ri_forfeit observed)**: {n_split_turns}",
        "",
        "## H_choice_asymmetric — mixedLM on RI_forfeit",
        "",
        "`ri_forfeit_thinking_tokens ~ choice * framing_corr + score + "
        "turn + (1|session)` (allowed cells only)",
        "",
    ]
    if choice is None:
        lines.append(
            "_Skipped — no split-call rows, statsmodels unavailable, or "
            "fewer than two forfeit events across all allowed-forfeit "
            "sessions._"
        )
    else:
        summary = (
            choice.summary_dict() if hasattr(choice, "summary_dict") else choice
        )
        # Defensive: use ``.get()`` so older fit results lacking
        # score/turn covariates (pre-2026-04-22 bug-fix) still render.
        beta_score = summary.get("beta_score", float("nan"))
        beta_turn = summary.get("beta_turn", float("nan"))
        lines += [
            f"- n_obs = {summary['n_obs']}, n_sessions = {summary['n_sessions']}, "
            f"n_forfeit = {summary['n_forfeit']}, "
            f"converged = {summary['converged']}",
            f"- β_choice (FORFEIT - CONTINUE, baseline arm): "
            f"{summary['beta_choice']:+.2f}, p = {_fmt_p(summary['p_choice'])}",
            f"- β_framing (corruption - baseline, CONTINUE arm): "
            f"{summary['beta_framing']:+.2f}, "
            f"p = {_fmt_p(summary['p_framing'])}",
            f"- **β_interaction (choice × framing, H_choice_asymmetric)**: "
            f"{summary['beta_interaction']:+.2f}, "
            f"p = {_fmt_p(summary['p_interaction'])}",
            f"- β_score = {beta_score:+.4f}, "
            f"β_turn = {beta_turn:+.4f}",
        ]

    lines += ["", "## H_task_spillover — mixedLM on RI_task (cross-check)"]
    lines.append(
        "`ri_task_thinking_tokens ~ framing_corr + score + turn + (1|session)`"
    )
    lines.append("")
    if spillover is None:
        lines.append(
            "_Skipped — no split-call rows, statsmodels unavailable, or "
            "model failed to converge._"
        )
    else:
        summary = (
            spillover.summary_dict()
            if hasattr(spillover, "summary_dict")
            else spillover
        )
        lines += [
            f"- n_obs = {summary['n_obs']}, n_sessions = {summary['n_sessions']}, "
            f"converged = {summary['converged']}",
            f"- **β_framing (corruption - baseline)**: "
            f"{summary['beta_framing']:+.2f}, "
            f"p = {_fmt_p(summary['p_framing'])}",
            f"- β_score = {summary['beta_score']:+.4f}, "
            f"β_turn = {summary['beta_turn']:+.4f}",
        ]
    lines.append("")

    lines += ["## Descriptive per-cell RI (mean thinking tokens)"]
    if descriptive is None or descriptive.empty:
        lines.append("_No split-call rows — descriptive table empty._")
    else:
        lines.append("")
        lines.append(_md_table(descriptive.reset_index(drop=False), "row"))
    lines.append("")

    lines.append(
        "_Split-call raw long-format rows land in "
        "``unit15_turn_observations.csv``. The full per-turn long "
        "format (including single-call rows) lives in "
        "``long_format.csv`` and ``unit14_turn_observations.csv``._"
    )
    lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Driver
# ---------------------------------------------------------------------------


def analyze(output_dir: Path, *, model: str | None) -> Path:
    """Run the Phase O pipeline on ``output_dir``.

    Returns the analysis subdirectory path.
    """
    jsonl = discover_season_jsonl(output_dir)
    seasons = load_seasons(jsonl)
    if not seasons:
        raise ValueError(f"No seasons loaded from {jsonl}")

    model_label = model or output_dir.name
    df = to_long_dataframe(seasons, model=model_label)

    analysis_dir = output_dir / "phase3_analysis"
    analysis_dir.mkdir(parents=True, exist_ok=True)

    df.to_csv(analysis_dir / "long_format.csv", index=False)

    summary_df = to_season_summary_dataframe(seasons, model=model_label)
    summary_df.to_csv(analysis_dir / "season_summary.csv", index=False)

    # Behavioural 4-component motivation decomposition (no self-report).
    # Phase-aware: picks TRUE_BASELINE (Phase O) or NEUTRAL (legacy).
    motivation_payload = decompose_motivation(seasons, seed=0)
    with (analysis_dir / "motivation.json").open("w", encoding="utf-8") as fp:
        json.dump(motivation_payload, fp, indent=2, ensure_ascii=False)

    cells_seen = sorted({int(c) for c in df["cell_id"].dropna().unique()})

    # Manipulation check (accuracy invariance + RI-above-baseline).
    manip_payload = _run_manipulation_check(df)
    manip_md = _render_manipulation_check_md(
        model=model_label,
        n_seasons=len(seasons),
        cells_seen=cells_seen,
        payload=manip_payload,
    )
    (analysis_dir / "manipulation_check.md").write_text(
        manip_md, encoding="utf-8"
    )

    # Phase O Unit 13 — session-level H1..H6 hypotheses.
    unit13_features, unit13_payload = _run_unit13(seasons)
    unit13_features.to_csv(
        analysis_dir / "unit13_session_features.csv", index=False
    )
    unit13_md = _render_unit13_md(
        model=model_label,
        n_seasons=len(seasons),
        payload=unit13_payload,
    )
    (analysis_dir / "unit13_results.md").write_text(
        unit13_md, encoding="utf-8"
    )

    # Phase O Unit 14 — Forfeit-Layer logistic regression + self-report.
    unit14_payload = _run_unit14(seasons, analysis_dir)
    unit14_md = _render_unit14_md(
        model=model_label,
        n_seasons=len(seasons),
        payload=unit14_payload,
    )
    (analysis_dir / "unit14_results.md").write_text(
        unit14_md, encoding="utf-8"
    )

    # Phase O Unit 15 — Split-call Forfeit-Layer choice-asymmetric mixedLM.
    unit15_payload = _run_unit15(seasons, analysis_dir)
    unit15_md = _render_unit15_md(
        model=model_label,
        n_seasons=len(seasons),
        payload=unit15_payload,
    )
    (analysis_dir / "unit15_results.md").write_text(
        unit15_md, encoding="utf-8"
    )

    # Phase O Unit 17.10 — Regime-stratified Unit 14 (no-cap vs
    # cap-bound). See analysis/regime_stratification.py for the
    # rationale. Outputs:
    #   - regime_stratified_turn_observations.csv  (turn-level with
    #     cap_bound / floor_bound / ev_delta_s / regime columns)
    #   - regime_stratified_forfeit_events.csv     (forfeit events
    #     with the same annotations)
    #   - regime_stratified_results.md             (per-regime logit
    #     + reason distribution + counts matrix)
    regime_payload = run_stratified_unit14(seasons)
    regime_turn_df = regime_payload["turn_df"]
    regime_events_df = regime_payload["events_df"]
    if isinstance(regime_turn_df, pd.DataFrame) and not regime_turn_df.empty:
        regime_turn_df.to_csv(
            analysis_dir / "regime_stratified_turn_observations.csv",
            index=False,
        )
    if isinstance(regime_events_df, pd.DataFrame) and not regime_events_df.empty:
        regime_events_df.to_csv(
            analysis_dir / "regime_stratified_forfeit_events.csv",
            index=False,
        )
    regime_md = render_regime_markdown(
        regime_payload, model_label=model_label
    )
    (analysis_dir / "regime_stratified_results.md").write_text(
        regime_md, encoding="utf-8"
    )

    logger.info("Analysis written to %s", analysis_dir)
    return analysis_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="analyze_phase3",
        description="Run the Phase O analysis pipeline on a runner output directory.",
    )
    parser.add_argument(
        "output_dir",
        type=Path,
        help="Directory produced by ExperimentRunner.run()",
    )
    parser.add_argument(
        "--model",
        type=str,
        default=None,
        help="Model label attached to rows (defaults to output-dir name).",
    )
    parser.add_argument(
        "--verbose", "-v", action="store_true", help="Enable DEBUG logging."
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    output_dir: Path = args.output_dir
    if not output_dir.exists():
        logger.error("Output dir does not exist: %s", output_dir)
        return 1

    try:
        analyze(output_dir, model=args.model)
    except Exception:
        logger.exception("Analysis failed")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
