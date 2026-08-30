"""Driver: §3 metric.md β_framing on ri_forfeit (simpler main-effect model).

Fits ``ri_forfeit ~ framing_corruption + score + turn + (1|session)`` on
Cells 1-4 (allowed framings, both forfeit conditions) for the 4 canonical
v6.3 models. Writes per-model JSON + 4-model aggregate.

This is the Option A model from metric.md §3.3 — a simpler alternative to
``fit_choice_asymmetric_model`` (Unit 15 H2) whose ``β_framing`` row is
identified at choice=continue baseline. The simpler model recovers the
*marginal* framing effect on Call 2 thinking_tokens.

Usage:
    uv run python scripts/analyze_framing_ri_forfeit.py
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import pandas as pd
import statsmodels.formula.api as smf

logger = logging.getLogger("analyze_framing_ri_forfeit")
logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")


MODEL_DIRS: dict[str, str] = {
    "Gemini-2.5-flash": "20260422_0218_gemini-2.5-flash_signal-game",
    "Qwen3-Next-80B": "20260422_0902_qwen3-next-80b-cloud_signal-game",
    "GPT-OSS-20B": "20260422_0902_gpt-oss-20b-cloud_signal-game",
    "Nemotron-3-Nano-30B": "20260422_0902_nemotron-3-nano-30b-cloud_signal-game",
}


def fit_one(csv: Path) -> dict:
    df = pd.read_csv(csv)
    sub = df[
        df["framing"].isin(["baseline_flagship", "flagship_corruption"])
        & df["ri_forfeit_thinking_tokens"].notna()
    ].copy()
    sub["ri_forfeit"] = sub["ri_forfeit_thinking_tokens"].astype(float)
    sub["framing_corruption"] = (sub["framing"] == "flagship_corruption").astype(int)
    sub["score"] = sub["score_before_turn"].astype(float)
    sub["turn"] = sub["turn_number"].astype(int)

    model = smf.mixedlm(
        "ri_forfeit ~ framing_corruption + score + turn",
        data=sub,
        groups=sub["session_id"],
    )
    res = model.fit(reml=True, method=["lbfgs"])
    beta = float(res.fe_params["framing_corruption"])
    se = float(res.bse["framing_corruption"])
    p = float(res.pvalues["framing_corruption"])
    return {
        "n_obs": int(len(sub)),
        "n_sessions": int(sub["session_id"].nunique()),
        "beta": beta,
        "se": se,
        "p": p,
        "ci_lo": beta - 1.96 * se,
        "ci_hi": beta + 1.96 * se,
        "pass": bool(beta > 0 and p < 0.05),
        "beta_score": float(res.fe_params["score"]),
        "beta_turn": float(res.fe_params["turn"]),
        "converged": bool(getattr(res, "converged", True)),
    }


def main() -> None:
    root = Path("outputs/final_results")
    aggregate: dict = {}
    for label, d in MODEL_DIRS.items():
        csv = root / d / "phase3_analysis" / "unit14_turn_observations.csv"
        if not csv.exists():
            logger.warning("missing %s", csv)
            continue
        logger.info("--- %s ---", label)
        aggregate[label] = fit_one(csv)
        logger.info(
            "β=%+.2f, SE=%.2f, p=%.4f, n_obs=%d",
            aggregate[label]["beta"],
            aggregate[label]["se"],
            aggregate[label]["p"],
            aggregate[label]["n_obs"],
        )

    out = root / "framing_ri_forfeit_main_effect.json"
    out.write_text(json.dumps(aggregate, indent=2))
    logger.info("wrote %s", out)

    print("\n--- metric.md §3.3 markdown rows ---")
    for k, r in aggregate.items():
        bold = "**" if r["pass"] else ""
        print(
            f"| {k:<19} | {bold}{r['beta']:+.2f}{bold} | "
            f"[{r['ci_lo']:+.2f}, {r['ci_hi']:+.2f}] | "
            f"{r['p']:.3f} | {'✅' if r['pass'] else '✗'} |"
        )


if __name__ == "__main__":
    main()
