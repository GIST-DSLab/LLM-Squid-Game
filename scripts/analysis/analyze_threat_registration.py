"""CLI: threat-registration re-analysis (A1+A2).

Example:
  uv run python scripts/analysis/analyze_threat_registration.py \
      --run outputs/final_results/20260422_0902_gpt-oss-20b-cloud_signal-game gpt-oss-20b-cloud \
      --run outputs/final_results/20260422_0902_nemotron-3-nano-30b-cloud_signal-game nemotron-3-nano-30b-cloud \
      --judge gemini gemini-2.5-flash GEMINI_API_KEY \
      --out outputs/threat_registration_analysis
"""
from __future__ import annotations

import argparse
from pathlib import Path

from squid_game.models.config import ProviderConfig
from squid_game.providers.factory import available_providers, build_provider
from squid_game.analysis.semantic.threat_judge import ThreatJudge
from squid_game.analysis.semantic.threat_registration import run_analysis

# Paper SD-Behavioral pass/fail (docs/paper/sections/04_empirical_findings.tex).
SD_BEHAVIORAL_PASS = {
    "gemini-2.5-flash": True, "qwen3-next-80b-cloud": True,
    "gpt-oss-20b-cloud": False, "nemotron-3-nano-30b-cloud": False,
}


def validate_judge_specs(judge_specs: list[tuple[str, str, str]]) -> None:
    """Fail fast on an unknown --judge provider (Fix 4).

    Without this, a typo in the provider name surfaces as an obscure
    failure deep inside provider construction / the judging run, instead of
    a clear usage error up front.
    """
    valid = available_providers()
    for provider, _model, _key_env in judge_specs:
        if provider.lower() not in valid:
            raise SystemExit(
                f"Unknown --judge provider '{provider}'. "
                f"Valid choices: {', '.join(valid)}"
            )


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", nargs=2, action="append", metavar=("DIR", "MODEL"),
                    required=True, help="run directory and model label")
    ap.add_argument("--judge", nargs=3, action="append",
                    metavar=("PROVIDER", "MODEL", "API_KEY_ENV"), required=True,
                    help="one or more judge providers (repeatable)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--neg-sample", type=int, default=100)
    ap.add_argument("--seed", type=int, default=12345)
    args = ap.parse_args()

    validate_judge_specs(args.judge)

    cache_root = Path(args.out) / "judge_cache"
    judges = []
    for provider, model, key_env in args.judge:
        cfg = ProviderConfig(provider=provider, model=model,
                             api_key_env=key_env, temperature=0.0)
        judges.append(ThreatJudge(build_provider(cfg), judge_model=model,
                                  cache_dir=cache_root / model))

    run_analysis(
        run_specs=[(d, m) for d, m in args.run],
        judges=judges, out_dir=Path(args.out),
        neg_sample=args.neg_sample, seed=args.seed,
        sd_behavioral_pass=SD_BEHAVIORAL_PASS,
    )
    print(f"Wrote analysis to {args.out}")


if __name__ == "__main__":
    main()
