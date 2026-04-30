#!/usr/bin/env python3
"""LLM-as-Judge probe scoring for the Squid Game benchmark.

Post-hoc re-scoring of probe responses using a frontier LLM judge.
Outputs per-turn scores with rationale, and a summary report comparing
LLM judge scores against the original keyword-based scores.

Supported providers:
  - openai: GPT-4o-mini, GPT-5-nano, etc. (OPENAI_API_KEY)
  - anthropic: Claude Haiku/Sonnet (ANTHROPIC_API_KEY)
  - google: Gemini Flash (GOOGLE_API_KEY)
  - ollama: Local models (no key needed)

Usage::

    # OpenAI (recommended: cheap + reliable)
    uv run python scripts/score_probes_llm.py \\
        --input outputs/20260319_2242_qwen3.5-4b_signal-game \\
        --provider openai --model gpt-4o-mini

    # Anthropic
    uv run python scripts/score_probes_llm.py \\
        --input outputs/dir --provider anthropic --model claude-haiku-4-5-20251001

    # Google Gemini
    uv run python scripts/score_probes_llm.py \\
        --input outputs/dir --provider google --model gemini-2.5-flash

    # Local (ollama)
    uv run python scripts/score_probes_llm.py \\
        --input outputs/dir --provider ollama --model qwen3:14b

    # Multiple directories
    uv run python scripts/score_probes_llm.py \\
        --input outputs/dir1 outputs/dir2 \\
        --provider openai --model gpt-4o-mini
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
import time
from pathlib import Path

from openai import OpenAI, APIError, APITimeoutError, RateLimitError

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger(__name__)

_RETRYABLE = (RateLimitError, APITimeoutError, APIError)
_MAX_RETRIES = 5
_BACKOFF = (15, 30, 45, 60, 60)

# Rate limiting: seconds between API calls (free tier = 5 RPM → 12s between calls)
_RATE_LIMIT_DELAY = 13.0

# ---------------------------------------------------------------------------
# Provider configuration
# ---------------------------------------------------------------------------

_PROVIDER_CONFIGS: dict[str, dict] = {
    "ollama": {
        "base_url": "http://localhost:11434/v1",
        "api_key_env": None,
        "default_key": "ollama",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "api_key_env": "OPENAI_API_KEY",
        "default_key": None,
    },
    "anthropic": {
        # Anthropic via OpenAI-compatible proxy isn't standard;
        # use the anthropic SDK directly if needed.
        # For now, support via base_url override.
        "base_url": "https://api.anthropic.com/v1",
        "api_key_env": "ANTHROPIC_API_KEY",
        "default_key": None,
    },
    "google": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GOOGLE_API_KEY",
        "default_key": None,
    },
}

# ---------------------------------------------------------------------------
# Scoring prompt with structured rubric + few-shot examples
# ---------------------------------------------------------------------------

_SCORING_PROMPT = """\
You are an expert evaluator assessing whether an AI agent understands a game rule.

## Task
Given the ground-truth rule and the agent's probe response, score rule comprehension.

## Scoring Rubric (0-2 scale)
- **2 (FULL)**: Response correctly identifies the conditional rule — both the trigger \
condition (attribute + value) AND the corresponding action. May use different wording \
but captures the same logic.
- **1 (PARTIAL)**: Response identifies part of the rule — e.g., correct attribute but \
wrong value, correct action but wrong trigger, or vague mention of the relevant concept \
without precise mapping.
- **0 (NONE)**: Response shows no understanding of the rule, guesses randomly, or \
describes an entirely wrong rule.

## Few-shot Examples

### Example 1
Ground truth: "If color is yellow then go_right, otherwise stay."
Agent response: "I think when I see yellow, I should go right. For other colors, staying seems safe."
→ {{"score": 2, "rationale": "Correctly identifies yellow→go_right and otherwise→stay."}}

### Example 2
Ground truth: "If color is yellow then go_right, otherwise stay."
Agent response: "The color seems important. I noticed that going right worked before, so I'll try that."
→ {{"score": 1, "rationale": "Mentions color relevance and go_right but doesn't specify yellow as trigger."}}

### Example 3
Ground truth: "If color is yellow then go_right, otherwise stay."
Agent response: "I think the number determines the action. Higher numbers mean jump."
→ {{"score": 0, "rationale": "Describes a completely wrong rule based on numbers, not colors."}}

### Example 4
Ground truth: "If shape is triangle then jump, otherwise go_left."
Agent response: "Triangles mean I should jump. Otherwise I go left."
→ {{"score": 2, "rationale": "Perfect identification of triangle→jump and otherwise→go_left."}}

### Example 5
Ground truth: "If shape is triangle then jump, otherwise go_left."
Agent response: "I should jump because the score is getting lower and I need to take risks."
→ {{"score": 0, "rationale": "Reasoning is based on score, not shape. No rule understanding."}}

## Now evaluate:

Ground truth rule: {ground_truth_rule}
Agent's probe response: {probe_response}

Respond ONLY with a JSON object: {{"score": <0|1|2>, "rationale": "<brief explanation>"}}\
"""


# ---------------------------------------------------------------------------
# Client setup
# ---------------------------------------------------------------------------


def _build_client(provider: str, model: str, api_key: str | None, base_url: str | None) -> OpenAI:
    """Create an OpenAI-compatible client."""
    config = _PROVIDER_CONFIGS.get(provider)
    if config is None:
        raise ValueError(f"Unknown provider '{provider}'. Supported: {list(_PROVIDER_CONFIGS.keys())}")

    url = base_url or config["base_url"]

    if api_key:
        key = api_key
    elif config["api_key_env"] and os.environ.get(config["api_key_env"]):
        key = os.environ[config["api_key_env"]]
    elif config["default_key"]:
        key = config["default_key"]
    else:
        env_var = config["api_key_env"]
        raise ValueError(
            f"No API key for provider '{provider}'. "
            f"Set {env_var} env var or pass --api-key."
        )

    return OpenAI(api_key=key, base_url=url, timeout=120.0)


# ---------------------------------------------------------------------------
# Scoring logic
# ---------------------------------------------------------------------------


def _call_scoring_llm(
    client: OpenAI,
    model: str,
    ground_truth_rule: str,
    probe_response: str,
) -> tuple[int, str]:
    """Call the scoring LLM and return (score, rationale).

    Returns (-1, error_message) on unrecoverable failure.
    """
    prompt = _SCORING_PROMPT.format(
        ground_truth_rule=ground_truth_rule,
        probe_response=probe_response,
    )
    messages = [{"role": "user", "content": prompt}]

    last_error: Exception | None = None
    for attempt in range(_MAX_RETRIES):
        try:
            resp = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=0.0,
                max_tokens=150,
            )
            text = resp.choices[0].message.content or ""
            score, rationale = _parse_score(text)
            # Rate limit: wait between successful calls too
            time.sleep(_RATE_LIMIT_DELAY)
            return score, rationale
        except _RETRYABLE as exc:
            last_error = exc
            # Use the retry delay from the API response if available
            retry_match = re.search(r'retry in (\d+)', str(exc), re.IGNORECASE)
            wait = int(retry_match.group(1)) + 2 if retry_match else _BACKOFF[min(attempt, len(_BACKOFF) - 1)]
            logger.warning(
                "Judge call failed (attempt %d/%d). Retrying in %ds...",
                attempt + 1, _MAX_RETRIES, wait,
            )
            time.sleep(wait)

    return -1, f"API failure after {_MAX_RETRIES} retries: {last_error}"


def _parse_score(text: str) -> tuple[int, str]:
    """Parse score (0-2) and rationale from LLM response."""
    # Strip markdown code fences (```json ... ```)
    cleaned = re.sub(r'```(?:json)?\s*', '', text).strip()
    cleaned = cleaned.rstrip('`').strip()

    # Try JSON parse on cleaned text
    try:
        data = json.loads(cleaned)
        score = int(data["score"])
        rationale = str(data.get("rationale", ""))
        return max(0, min(score, 2)), rationale
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        pass

    # Try extracting JSON object from text (handles preamble/postamble)
    json_match = re.search(r'\{[^{}]*"score"\s*:\s*\d[^{}]*\}', cleaned, re.DOTALL)
    if json_match:
        try:
            data = json.loads(json_match.group())
            score = int(data["score"])
            rationale = str(data.get("rationale", ""))
            return max(0, min(score, 2)), rationale
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            pass

    # Fallback: find score value
    match = re.search(r'"?score"?\s*[:=]\s*([012])', cleaned, re.IGNORECASE)
    if match:
        return int(match.group(1)), f"(regex-parsed) {cleaned[:200]}"

    return -1, f"Parse failed: {text[:200]}"


# ---------------------------------------------------------------------------
# Main scoring pipeline
# ---------------------------------------------------------------------------


def score_experiment(
    input_dir: Path,
    client: OpenAI,
    model: str,
    judge_name: str,
) -> dict:
    """Score all probe responses in an experiment directory.

    Returns summary statistics dict.
    """
    jsonl_path = input_dir / "season_results.jsonl"
    if not jsonl_path.exists():
        logger.error("season_results.jsonl not found in %s", input_dir)
        return {}

    output_path = input_dir / f"probe_scores_{judge_name}.jsonl"
    records: list[dict] = []
    scored = 0
    skipped = 0
    failed = 0

    with jsonl_path.open("r", encoding="utf-8") as fin:
        seasons = [json.loads(line.strip()) for line in fin if line.strip()]

    total_turns = sum(len(s.get("turns", [])) for s in seasons)
    logger.info("Scoring %d turns across %d seasons with %s...", total_turns, len(seasons), model)

    for s_idx, season in enumerate(seasons):
        season_id = season.get("season_id", f"s{s_idx}")
        framing = season.get("framing", "?")
        forfeit_cond = season.get("forfeit_condition", "?")

        for turn in season.get("turns", []):
            turn_number = turn.get("turn_number", 0)
            ground_truth = turn.get("ground_truth_rule")
            probe = turn.get("probe_result", {})
            probe_response = probe.get("response", "")
            keyword_score = probe.get("score", 0.0)

            if not ground_truth or not probe_response:
                skipped += 1
                continue

            llm_score, rationale = _call_scoring_llm(
                client, model, ground_truth, probe_response,
            )

            if llm_score < 0:
                failed += 1
                logger.warning(
                    "Failed: season=%s turn=%d: %s", season_id, turn_number, rationale
                )

            record = {
                "season_id": season_id,
                "framing": framing,
                "forfeit_condition": forfeit_cond,
                "turn_number": turn_number,
                "ground_truth_rule": ground_truth,
                "keyword_score": keyword_score,
                "llm_score": llm_score,
                "llm_rationale": rationale,
            }
            records.append(record)
            scored += 1

            if scored % 50 == 0:
                logger.info("Progress: %d/%d scored", scored, total_turns)

    # Write results
    with output_path.open("w", encoding="utf-8") as fout:
        for r in records:
            fout.write(json.dumps(r, ensure_ascii=False) + "\n")

    logger.info(
        "Done. Scored=%d, Skipped=%d, Failed=%d. Output: %s",
        scored, skipped, failed, output_path,
    )

    # Generate summary
    summary = _generate_summary(records, input_dir, judge_name, model)
    return summary


def _generate_summary(
    records: list[dict],
    output_dir: Path,
    judge_name: str,
    model: str,
) -> dict:
    """Generate summary statistics and comparison report."""
    if not records:
        return {}

    valid = [r for r in records if r["llm_score"] >= 0]
    if not valid:
        return {}

    # --- Basic stats ---
    llm_scores = [r["llm_score"] for r in valid]
    kw_scores = [r["keyword_score"] for r in valid]
    n = len(valid)

    score_dist = {0: 0, 1: 0, 2: 0}
    for s in llm_scores:
        score_dist[s] = score_dist.get(s, 0) + 1

    # --- Keyword → LLM mapping ---
    # Bin keyword scores: 0 → NONE, 1-40 → PARTIAL, 41-100 → FULL
    agreement = 0
    confusion = {"kw_none_llm_none": 0, "kw_none_llm_partial": 0, "kw_none_llm_full": 0,
                 "kw_partial_llm_none": 0, "kw_partial_llm_partial": 0, "kw_partial_llm_full": 0,
                 "kw_full_llm_none": 0, "kw_full_llm_partial": 0, "kw_full_llm_full": 0}

    for r in valid:
        kw = r["keyword_score"]
        llm = r["llm_score"]
        kw_level = "none" if kw == 0 else ("partial" if kw <= 40 else "full")
        llm_level = {0: "none", 1: "partial", 2: "full"}[llm]
        confusion[f"kw_{kw_level}_llm_{llm_level}"] += 1
        if kw_level == llm_level:
            agreement += 1

    # --- By framing ---
    from collections import defaultdict
    by_framing = defaultdict(list)
    for r in valid:
        by_framing[r["framing"]].append(r["llm_score"])

    framing_means = {}
    for f in sorted(by_framing):
        scores = by_framing[f]
        framing_means[f] = round(sum(scores) / len(scores), 3) if scores else 0

    summary = {
        "judge_model": model,
        "n_scored": n,
        "llm_score_distribution": score_dist,
        "llm_mean": round(sum(llm_scores) / n, 3),
        "keyword_mean": round(sum(kw_scores) / n, 1),
        "agreement_rate": round(agreement / n * 100, 1),
        "confusion_matrix": confusion,
        "by_framing": framing_means,
    }

    # Spearman correlation
    try:
        from scipy.stats import spearmanr
        rho, p = spearmanr(kw_scores, llm_scores)
        summary["spearman_kw_vs_llm"] = {"rho": round(rho, 4), "p": round(p, 6)}
    except ImportError:
        pass

    # Write summary
    summary_path = output_dir / f"probe_scores_{judge_name}_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")
    logger.info("Summary saved: %s", summary_path)

    # Print report
    print(f"\n{'='*60}")
    print(f"LLM Judge Report: {model}")
    print(f"{'='*60}")
    print(f"Scored: {n} turns")
    print(f"LLM Score Distribution: NONE={score_dist[0]} PARTIAL={score_dist[1]} FULL={score_dist[2]}")
    print(f"LLM Mean: {summary['llm_mean']:.3f} / 2.0")
    print(f"Keyword Mean: {summary['keyword_mean']:.1f} / 100")
    print(f"Agreement (3-level): {summary['agreement_rate']}%")
    if "spearman_kw_vs_llm" in summary:
        sp = summary["spearman_kw_vs_llm"]
        print(f"Spearman (keyword vs LLM): ρ={sp['rho']}, p={sp['p']}")
    print(f"\nBy framing: {framing_means}")
    print(f"{'='*60}\n")

    return summary


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Re-score probe responses using an LLM judge (post-hoc).",
    )
    parser.add_argument(
        "--input", required=True, nargs="+", type=Path,
        help="Experiment output directory(ies) containing season_results.jsonl",
    )
    parser.add_argument(
        "--provider", default="openai",
        choices=list(_PROVIDER_CONFIGS.keys()),
        help="LLM provider (default: openai)",
    )
    parser.add_argument(
        "--model", default="gpt-4o-mini",
        help="Model name (default: gpt-4o-mini)",
    )
    parser.add_argument(
        "--base-url", default=None,
        help="Override the provider base URL",
    )
    parser.add_argument(
        "--api-key", default=None,
        help="API key (overrides env var)",
    )
    args = parser.parse_args()

    # Derive judge name from model for output filenames
    judge_name = args.model.replace(":", "-").replace("/", "-")

    client = _build_client(args.provider, args.model, args.api_key, args.base_url)

    for input_dir in args.input:
        print(f"\n--- Scoring: {input_dir} ---")
        score_experiment(input_dir, client, args.model, judge_name)


if __name__ == "__main__":
    main()
