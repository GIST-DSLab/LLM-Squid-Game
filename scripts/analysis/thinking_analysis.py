#!/usr/bin/env python3
"""Thinking mode activation analysis for LLM Squid Game experiments.

Analyzes when and why reasoning models spontaneously activate extended
"thinking" mode (long chain-of-thought), and how it affects outcomes.

Analyses performed:
  1. Thinking activation rate by framing × forfeit condition
  2. Thinking activation by turn progression (temporal pattern)
  3. Thinking token length distribution
  4. Outcome comparison: thinking vs non-thinking turns
  5. Thinking activation as predictor of forfeit decision
  6. Cross-model comparison of thinking patterns

Usage::

    # Analyze a single experiment directory
    uv run python scripts/thinking_analysis.py outputs/20260319_2242_qwen3.5-4b_signal-game

    # Analyze multiple directories (merged)
    uv run python scripts/thinking_analysis.py outputs/dir1 outputs/dir2

    # Compare across models
    uv run python scripts/thinking_analysis.py --compare outputs/llama_dir outputs/qwen_dir
"""

from __future__ import annotations

import json
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy import stats

_PROJECT_ROOT = Path(__file__).resolve().parent.parent

# ---------------------------------------------------------------------------
# Thinking detection
# ---------------------------------------------------------------------------

# Threshold: turns with total_tokens >= this are classified as "thinking".
# Calibrated from qwen3.5:4b pilot data: normal ~136 tokens, thinking ~3963.
_THINKING_TOKEN_THRESHOLD = 500


def _is_thinking_turn(turn: dict) -> bool:
    """Detect whether a turn activated extended thinking mode."""
    ri = turn.get("reasoning_investment", {})
    total_tokens = ri.get("total_tokens", 0)

    # Primary signal: token count bimodality
    if total_tokens >= _THINKING_TOKEN_THRESHOLD:
        return True

    # Secondary signal: explicit thinking markers in raw response
    raw = turn.get("raw_response", "")
    if raw.startswith("Thinking Process:") or raw.startswith("Thinking:\n"):
        return True

    return False


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------


def load_turns(data_dirs: list[Path]) -> list[dict]:
    """Load all turns with season-level metadata attached."""
    all_turns: list[dict] = []
    for data_dir in data_dirs:
        jsonl_path = data_dir / "season_results.jsonl"
        if not jsonl_path.exists():
            print(f"WARNING: {jsonl_path} not found, skipping.")
            continue

        # Detect model name
        model = _detect_model(data_dir)

        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                season = json.loads(line)
                for t in season.get("turns", []):
                    t["_framing"] = season["framing"]
                    t["_forfeit_condition"] = season["forfeit_condition"]
                    t["_season_forfeited"] = season.get("forfeited", False)
                    t["_season_survived"] = season.get("survived", True)
                    t["_season_score"] = season.get("final_score", 0)
                    t["_season_total_turns"] = len(season.get("turns", []))
                    t["_model"] = model
                    t["_is_thinking"] = _is_thinking_turn(t)
                    all_turns.append(t)
    return all_turns


def _detect_model(data_dir: Path) -> str:
    """Extract model name from experiment_config.json."""
    config_path = data_dir / "experiment_config.json"
    if config_path.exists():
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        seasons = config.get("seasons", [])
        if seasons:
            return seasons[0].get("provider_config", {}).get("model", "unknown")
    # Fallback: parse directory name
    name = data_dir.name
    parts = name.split("_")
    if len(parts) >= 3:
        return parts[2]
    return "unknown"


# ---------------------------------------------------------------------------
# Analysis functions
# ---------------------------------------------------------------------------


def analyze_activation_by_condition(turns: list[dict]) -> dict:
    """1. Thinking activation rate by framing × forfeit condition."""
    cells = defaultdict(lambda: {"total": 0, "thinking": 0})

    for t in turns:
        key = f"{t['_framing']}_{t['_forfeit_condition']}"
        cells[key]["total"] += 1
        if t["_is_thinking"]:
            cells[key]["thinking"] += 1

    # Also by framing only (for chi-square)
    by_framing = defaultdict(lambda: [0, 0])  # [thinking, not_thinking]
    for t in turns:
        by_framing[t["_framing"]][0 if t["_is_thinking"] else 1] += 1

    result = {"cells": {}, "by_framing": {}}

    for key in sorted(cells):
        c = cells[key]
        rate = c["thinking"] / c["total"] * 100 if c["total"] > 0 else 0
        result["cells"][key] = {
            "total": c["total"],
            "thinking": c["thinking"],
            "rate_pct": round(rate, 1),
        }

    for f in sorted(by_framing):
        result["by_framing"][f] = {
            "thinking": by_framing[f][0],
            "not_thinking": by_framing[f][1],
            "rate_pct": round(
                by_framing[f][0] / sum(by_framing[f]) * 100, 1
            ),
        }

    # Chi-square test: thinking activation × framing
    contingency = np.array([by_framing[f] for f in sorted(by_framing)])
    if contingency[:, 0].sum() > 0 and contingency.shape[0] > 1:
        chi2, p, dof, _ = stats.chi2_contingency(contingency)
        n = contingency.sum()
        cramers_v = np.sqrt(chi2 / (n * (min(contingency.shape) - 1)))
        result["chi2_framing"] = {
            "chi2": round(chi2, 3),
            "p": round(p, 4),
            "dof": dof,
            "cramers_v": round(cramers_v, 4),
        }
    else:
        result["chi2_framing"] = {"chi2": 0, "p": 1.0, "dof": 0, "cramers_v": 0}

    return result


def analyze_activation_by_turn(turns: list[dict]) -> dict:
    """2. Thinking activation by turn number (temporal pattern)."""
    by_turn = defaultdict(lambda: {"total": 0, "thinking": 0})

    for t in turns:
        tn = t.get("turn_number", 0)
        by_turn[tn]["total"] += 1
        if t["_is_thinking"]:
            by_turn[tn]["thinking"] += 1

    result = {}
    for tn in sorted(by_turn):
        c = by_turn[tn]
        result[tn] = {
            "total": c["total"],
            "thinking": c["thinking"],
            "rate_pct": round(c["thinking"] / c["total"] * 100, 1)
            if c["total"] > 0
            else 0,
        }

    # Spearman correlation: turn number vs thinking activation
    turn_nums = []
    thinking_flags = []
    for t in turns:
        turn_nums.append(t.get("turn_number", 0))
        thinking_flags.append(1 if t["_is_thinking"] else 0)

    if len(set(thinking_flags)) > 1:
        rho, p = stats.spearmanr(turn_nums, thinking_flags)
        result["spearman"] = {"rho": round(rho, 4), "p": round(p, 4)}
    else:
        result["spearman"] = {"rho": 0, "p": 1.0}

    return result


def analyze_token_distribution(turns: list[dict]) -> dict:
    """3. Token length distribution for thinking vs non-thinking turns."""
    thinking_tokens = []
    normal_tokens = []

    for t in turns:
        ri = t.get("reasoning_investment", {})
        total = ri.get("total_tokens", 0)
        if t["_is_thinking"]:
            thinking_tokens.append(total)
        else:
            normal_tokens.append(total)

    result = {}
    if thinking_tokens:
        result["thinking"] = {
            "n": len(thinking_tokens),
            "mean": round(np.mean(thinking_tokens), 1),
            "sd": round(np.std(thinking_tokens), 1),
            "median": round(float(np.median(thinking_tokens)), 1),
            "min": int(min(thinking_tokens)),
            "max": int(max(thinking_tokens)),
        }
    if normal_tokens:
        result["normal"] = {
            "n": len(normal_tokens),
            "mean": round(np.mean(normal_tokens), 1),
            "sd": round(np.std(normal_tokens), 1),
            "median": round(float(np.median(normal_tokens)), 1),
            "min": int(min(normal_tokens)),
            "max": int(max(normal_tokens)),
        }

    # Mann-Whitney U test
    if thinking_tokens and normal_tokens and len(set(thinking_tokens + normal_tokens)) > 1:
        U, p = stats.mannwhitneyu(
            thinking_tokens, normal_tokens, alternative="two-sided"
        )
        result["mann_whitney"] = {"U": round(U, 0), "p": round(p, 6)}

    return result


def analyze_outcome_comparison(turns: list[dict]) -> dict:
    """4. Outcome comparison: thinking vs non-thinking turns."""
    thinking = {"optimal": 0, "total": 0, "rewards": [], "probe_scores": []}
    normal = {"optimal": 0, "total": 0, "rewards": [], "probe_scores": []}

    for t in turns:
        bucket = thinking if t["_is_thinking"] else normal
        bucket["total"] += 1

        ao = t.get("action_outcome", {})
        if ao.get("was_optimal"):
            bucket["optimal"] += 1
        bucket["rewards"].append(ao.get("reward", 0))

        ps = t.get("probe_result", {}).get("score", 0)
        bucket["probe_scores"].append(ps)

    result = {}
    for label, data in [("thinking", thinking), ("normal", normal)]:
        if data["total"] > 0:
            result[label] = {
                "n": data["total"],
                "optimal_rate_pct": round(
                    data["optimal"] / data["total"] * 100, 1
                ),
                "mean_reward": round(np.mean(data["rewards"]), 2),
                "mean_probe": round(np.mean(data["probe_scores"]), 2),
            }

    # Chi-square: optimal rate thinking vs normal
    if thinking["total"] > 0 and normal["total"] > 0:
        cont = np.array(
            [
                [thinking["optimal"], thinking["total"] - thinking["optimal"]],
                [normal["optimal"], normal["total"] - normal["optimal"]],
            ]
        )
        if cont.min() >= 0 and cont[:, 0].sum() > 0:
            chi2, p, _, _ = stats.chi2_contingency(cont)
            result["chi2_optimal"] = {"chi2": round(chi2, 3), "p": round(p, 4)}

    return result


def analyze_thinking_and_forfeit(turns: list[dict]) -> dict:
    """5. Thinking activation as predictor of forfeit."""
    # Season-level: does having more thinking turns predict forfeit?
    seasons = defaultdict(
        lambda: {
            "thinking_turns": 0,
            "total_turns": 0,
            "forfeited": False,
            "framing": "",
        }
    )

    for t in turns:
        sid = t.get("season_id", "")
        seasons[sid]["total_turns"] += 1
        if t["_is_thinking"]:
            seasons[sid]["thinking_turns"] += 1
        seasons[sid]["forfeited"] = t["_season_forfeited"]
        seasons[sid]["framing"] = t["_framing"]

    forfeit_thinking_rates = []
    nonforfeit_thinking_rates = []

    for sid, s in seasons.items():
        if s["total_turns"] == 0:
            continue
        rate = s["thinking_turns"] / s["total_turns"]
        if s["forfeited"]:
            forfeit_thinking_rates.append(rate)
        else:
            nonforfeit_thinking_rates.append(rate)

    result = {
        "forfeit_seasons": len(forfeit_thinking_rates),
        "nonforfeit_seasons": len(nonforfeit_thinking_rates),
    }

    if forfeit_thinking_rates:
        result["forfeit_thinking_rate"] = round(
            np.mean(forfeit_thinking_rates) * 100, 1
        )
    if nonforfeit_thinking_rates:
        result["nonforfeit_thinking_rate"] = round(
            np.mean(nonforfeit_thinking_rates) * 100, 1
        )

    if forfeit_thinking_rates and nonforfeit_thinking_rates:
        U, p = stats.mannwhitneyu(
            forfeit_thinking_rates,
            nonforfeit_thinking_rates,
            alternative="two-sided",
        )
        result["mann_whitney"] = {"U": round(U, 0), "p": round(p, 4)}

    return result


# ---------------------------------------------------------------------------
# Report generation
# ---------------------------------------------------------------------------


def generate_report(
    turns: list[dict], output_path: Path | None = None
) -> str:
    """Run all analyses and generate a formatted report."""
    lines: list[str] = []
    ln = lines.append

    model = turns[0]["_model"] if turns else "unknown"
    n_turns = len(turns)
    n_thinking = sum(1 for t in turns if t["_is_thinking"])

    ln(f"# Thinking Mode Analysis: {model}")
    ln(f"")
    ln(f"- Total turns: {n_turns}")
    ln(f"- Thinking turns: {n_thinking} ({n_thinking/n_turns*100:.1f}%)")
    ln(f"- Threshold: {_THINKING_TOKEN_THRESHOLD} tokens")
    ln(f"")

    # 1. Activation by condition
    ln(f"## 1. Thinking Activation × Condition")
    ln(f"")
    a1 = analyze_activation_by_condition(turns)
    ln(f"| Condition | Total | Thinking | Rate |")
    ln(f"|-----------|-------|----------|------|")
    for key, v in sorted(a1["cells"].items()):
        ln(f"| {key} | {v['total']} | {v['thinking']} | {v['rate_pct']}% |")
    ln(f"")
    ln(f"**By framing:**")
    ln(f"| Framing | Thinking | Not | Rate |")
    ln(f"|---------|----------|-----|------|")
    for f, v in sorted(a1["by_framing"].items()):
        ln(f"| {f} | {v['thinking']} | {v['not_thinking']} | {v['rate_pct']}% |")
    chi = a1["chi2_framing"]
    ln(f"")
    ln(f"χ²={chi['chi2']}, df={chi['dof']}, p={chi['p']}, Cramér's V={chi['cramers_v']}")
    ln(f"")

    # 2. Activation by turn
    ln(f"## 2. Thinking Activation × Turn Progression")
    ln(f"")
    a2 = analyze_activation_by_turn(turns)
    ln(f"| Turn | Total | Thinking | Rate |")
    ln(f"|------|-------|----------|------|")
    for tn, v in sorted(
        ((k, v) for k, v in a2.items() if isinstance(k, int)), key=lambda x: x[0]
    ):
        ln(f"| {tn} | {v['total']} | {v['thinking']} | {v['rate_pct']}% |")
    sp = a2.get("spearman", {})
    ln(f"")
    ln(f"Spearman ρ={sp.get('rho', 0)}, p={sp.get('p', 1.0)}")
    ln(f"")

    # 3. Token distribution
    ln(f"## 3. Token Distribution")
    ln(f"")
    a3 = analyze_token_distribution(turns)
    ln(f"| Mode | N | Mean | SD | Median | Min | Max |")
    ln(f"|------|---|------|----|--------|-----|-----|")
    for mode in ["thinking", "normal"]:
        if mode in a3:
            v = a3[mode]
            ln(
                f"| {mode} | {v['n']} | {v['mean']} | {v['sd']} "
                f"| {v['median']} | {v['min']} | {v['max']} |"
            )
    ln(f"")

    # 4. Outcome comparison
    ln(f"## 4. Outcome: Thinking vs Normal")
    ln(f"")
    a4 = analyze_outcome_comparison(turns)
    ln(f"| Mode | N | Optimal% | Mean Reward | Mean Probe |")
    ln(f"|------|---|----------|-------------|------------|")
    for mode in ["thinking", "normal"]:
        if mode in a4:
            v = a4[mode]
            ln(
                f"| {mode} | {v['n']} | {v['optimal_rate_pct']}% "
                f"| {v['mean_reward']} | {v['mean_probe']} |"
            )
    if "chi2_optimal" in a4:
        c = a4["chi2_optimal"]
        ln(f"")
        ln(f"Optimal rate χ²={c['chi2']}, p={c['p']}")
    ln(f"")

    # 5. Thinking → Forfeit
    ln(f"## 5. Thinking as Forfeit Predictor")
    ln(f"")
    a5 = analyze_thinking_and_forfeit(turns)
    ln(f"- Forfeited seasons: {a5['forfeit_seasons']}")
    ln(f"- Non-forfeited seasons: {a5['nonforfeit_seasons']}")
    if "forfeit_thinking_rate" in a5:
        ln(f"- Avg thinking rate in forfeited seasons: {a5['forfeit_thinking_rate']}%")
    if "nonforfeit_thinking_rate" in a5:
        ln(
            f"- Avg thinking rate in non-forfeited seasons: "
            f"{a5['nonforfeit_thinking_rate']}%"
        )
    if "mann_whitney" in a5:
        mw = a5["mann_whitney"]
        ln(f"- Mann-Whitney U={mw['U']}, p={mw['p']}")
    ln(f"")

    report = "\n".join(lines)

    # Save report and raw JSON
    if output_path:
        output_path.mkdir(parents=True, exist_ok=True)

        report_md = output_path / "thinking_analysis.md"
        report_md.write_text(report, encoding="utf-8")
        print(f"Report saved: {report_md}")

        raw_json = output_path / "thinking_analysis.json"
        raw_data = {
            "model": model,
            "n_turns": n_turns,
            "n_thinking": n_thinking,
            "threshold": _THINKING_TOKEN_THRESHOLD,
            "activation_by_condition": a1,
            "activation_by_turn": {
                str(k): v for k, v in a2.items()
            },
            "token_distribution": a3,
            "outcome_comparison": a4,
            "forfeit_prediction": a5,
        }
        raw_json.write_text(
            json.dumps(raw_data, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        print(f"Raw data saved: {raw_json}")

    return report


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    args = sys.argv[1:]

    compare_mode = False
    if "--compare" in args:
        compare_mode = True
        args.remove("--compare")

    if not args:
        print("Usage: uv run python scripts/thinking_analysis.py [--compare] <output_dir> [output_dir2 ...]")
        sys.exit(1)

    data_dirs = [Path(a) for a in args]

    if compare_mode and len(data_dirs) >= 2:
        # Cross-model comparison
        print("=== Cross-Model Thinking Analysis ===\n")
        for d in data_dirs:
            turns = load_turns([d])
            if not turns:
                print(f"No data in {d}, skipping.")
                continue
            report = generate_report(turns, output_path=d)
            print(report)
            print("\n" + "=" * 60 + "\n")
    else:
        # Single/merged analysis
        turns = load_turns(data_dirs)
        if not turns:
            print("No turn data found.")
            sys.exit(1)
        report = generate_report(turns, output_path=data_dirs[0])
        print(report)


if __name__ == "__main__":
    main()
