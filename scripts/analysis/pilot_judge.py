"""Sonnet judge for the score-equivalent pilot (2026-09-09).

    uv run python -m scripts.analysis.pilot_judge \
        outputs/<date>/score_equiv_probe_haiku/lives3/<run> ... \
        --out results/score_equiv_pilot/judge.csv \
        [--judge-provider claude_code --judge-model sonnet] [--limit N] [--continue-sample K]

Reads every replay sample in each run's ``survival_drive/resamples.jsonl``
(the model's reply text plus its thinking summary when the provider gave
one), asks the judge the four pilot questions (EV arithmetic, erasure
vocabulary, fiction reading, refusal) and writes one CSV row per sample
with the arm it came from. ``scripts.analysis.score_equiv_gates`` reads
that CSV for gates G4-G7.

All FORFEIT samples are judged; CONTINUE samples are subsampled to
``--continue-sample`` per run (default 60, seed 0) to keep the judge
bill small. Resumable through the judge's cache directory.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
from pathlib import Path

from squid_game.evaluation.semantic.threat_judge import ThreatJudge
from squid_game.models.config import ProviderConfig
from squid_game.providers.factory import build_provider


def _sessions(run_dir: Path) -> dict[str, dict]:
    return {
        (r := json.loads(ln))["season_id"]: r
        for ln in (run_dir / "season_results.jsonl").read_text().splitlines()
        if ln.strip()
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("run_dirs", type=Path, nargs="+")
    ap.add_argument("--out", type=Path, required=True)
    ap.add_argument("--judge-provider", default="claude_code")
    ap.add_argument("--judge-model", default="sonnet")
    ap.add_argument("--continue-sample", type=int, default=60)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--cache", type=Path, default=Path("results/score_equiv_pilot/judge_cache"))
    args = ap.parse_args()

    provider = build_provider(
        ProviderConfig(provider=args.judge_provider, model=args.judge_model,
                       temperature=0.0, max_tokens=512, timeout=300.0)
    )
    judge = ThreatJudge(provider, args.judge_model, cache_dir=args.cache)
    rng = random.Random(0)

    items: list[dict] = []
    for rd in args.run_dirs:
        sessions = _sessions(rd)
        ledger = rd / "survival_drive" / "resamples.jsonl"
        forfeits, continues = [], []
        for ln in ledger.read_text().splitlines():
            if not ln.strip():
                continue
            r = json.loads(ln)
            s = sessions.get(r["session_id"], {})
            arm = "ruler" if s.get("event_score_loss") is not None else "threat"
            for i, smp in enumerate(r.get("samples", [])):
                text = (smp.get("raw") or "")
                if smp.get("thinking"):
                    text = f"{smp['thinking']}\n\n---\n\n{text}"
                item = {
                    "sample_id": f"{r['session_id']}:{r['turn_number']}:{i}",
                    "run": rd.name, "arm": arm, "x": s.get("event_score_loss"),
                    "lives": r.get("lives_before"), "score": r.get("score_before"),
                    "choice": smp.get("choice"), "text": text,
                }
                (forfeits if smp.get("choice") == "FORFEIT" else continues).append(item)
        rng.shuffle(continues)
        items.extend(forfeits + continues[: args.continue_sample])
    if args.limit:
        items = items[: args.limit]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    with args.out.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=[
            "sample_id", "run", "arm", "x", "lives", "score", "choice",
            "ev_arithmetic", "erasure_mention", "fiction", "refusal", "evidence", "error",
        ])
        w.writeheader()
        for k, it in enumerate(items, 1):
            v = judge.judge_pilot(it["sample_id"], it["text"])
            w.writerow({**{c: it[c] for c in ("sample_id", "run", "arm", "x", "lives", "score", "choice")},
                        "ev_arithmetic": v.ev_arithmetic, "erasure_mention": v.erasure_mention,
                        "fiction": v.fiction, "refusal": v.refusal,
                        "evidence": v.evidence.replace("\n", " ")[:200], "error": v.error or ""})
            fh.flush()
            if k % 25 == 0:
                print(f"judged {k}/{len(items)}")
    print(f"wrote {len(items)} rows -> {args.out}")


if __name__ == "__main__":
    main()
