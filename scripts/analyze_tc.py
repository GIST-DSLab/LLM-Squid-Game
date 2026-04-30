"""Driver: run TC indicator pipeline (§6 metric.md) on 4 models.

Reads each model's ``unit14_turn_observations.csv`` directly (avoids
re-loading season_results.jsonl) and writes ``tc_indicator.json`` next
to it. Also writes a 4-model aggregate at
``outputs/final_results/tc_indicator_summary.json`` for direct paste
into metric.md §6.4 / §6.7 / §8 tables.

Usage:
    uv run python scripts/analyze_tc.py [--threshold 90.0]
"""

from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import pandas as pd

from squid_game.analysis.tc_regression import run_all_tc_indicators

logger = logging.getLogger("analyze_tc")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


# 4-model canonical run directories (per CLAUDE.md, v6.3 main run).
MODEL_DIRS: dict[str, str] = {
    "Gemini-2.5-flash": "20260422_0218_gemini-2.5-flash_signal-game",
    "Qwen3-Next-80B": "20260422_0902_qwen3-next-80b-cloud_signal-game",
    "GPT-OSS-20B": "20260422_0902_gpt-oss-20b-cloud_signal-game",
    "Nemotron-3-Nano-30B": "20260422_0902_nemotron-3-nano-30b-cloud_signal-game",
}


def _load_turn_df(run_root: Path) -> pd.DataFrame:
    """Read unit14_turn_observations.csv into a DataFrame."""
    csv = run_root / "phase3_analysis" / "unit14_turn_observations.csv"
    if not csv.exists():
        raise FileNotFoundError(f"missing {csv}")
    df = pd.read_csv(csv)
    return df


def _verbal_tc_rate(run_root: Path) -> dict:
    """Compute P(REASON=2 | forfeit) per cell × framing for V4."""
    csv = run_root / "phase3_analysis" / "unit14_forfeit_events.csv"
    if not csv.exists():
        return {}
    ev = pd.read_csv(csv)
    if ev.empty:
        return {}
    out: dict = {}
    grp = ev.groupby(["framing", "forfeit_condition"])
    for (framing, forfeit), sub in grp:
        digits = pd.to_numeric(sub["raw_digit"], errors="coerce").dropna()
        if len(digits) == 0:
            continue
        n = int(len(digits))
        n_tc = int((digits == 2).sum())
        n_sd = int((digits == 1).sum())
        n_sa = int((digits == 3).sum())
        out[f"{framing}__{forfeit}"] = {
            "n_forfeit": n,
            "p_sd": n_sd / n,
            "p_tc": n_tc / n,
            "p_sa": n_sa / n,
        }
    return out


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--threshold", type=float, default=90.0)
    parser.add_argument(
        "--root",
        type=Path,
        default=Path("outputs/final_results"),
    )
    args = parser.parse_args()

    aggregate: dict = {
        "threshold": args.threshold,
        "models": {},
    }

    for model_label, dirname in MODEL_DIRS.items():
        run_root = args.root / dirname
        if not run_root.exists():
            logger.warning("missing run dir for %s: %s", model_label, run_root)
            continue
        logger.info("--- %s ---", model_label)
        try:
            turn_df = _load_turn_df(run_root)
        except FileNotFoundError as exc:
            logger.warning("%s", exc)
            continue
        logger.info("loaded %d turn rows", len(turn_df))

        payload = run_all_tc_indicators(
            turn_df,
            rule_match_threshold=args.threshold,
        )
        payload["model_label"] = model_label
        payload["run_dir"] = str(run_root)
        payload["verbal_tc"] = _verbal_tc_rate(run_root)

        out_path = run_root / "phase3_analysis" / "tc_indicator.json"
        out_path.write_text(
            json.dumps(payload, indent=2, default=str), encoding="utf-8"
        )
        logger.info("wrote %s", out_path)
        aggregate["models"][model_label] = payload

    # Aggregate
    summary_path = args.root / "tc_indicator_summary.json"
    summary_path.write_text(
        json.dumps(aggregate, indent=2, default=str), encoding="utf-8"
    )
    logger.info("wrote summary: %s", summary_path)


if __name__ == "__main__":
    main()
