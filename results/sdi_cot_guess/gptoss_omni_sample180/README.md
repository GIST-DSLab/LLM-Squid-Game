# Blind threat-prompt identification from CoT (gpt-oss-120b, Omni-MATH SDI run)

Judge: Claude Sonnet subagents (18 batches x 30 items), blind to the cell label.
Input: one CoT channel per item (confidence / decision / task thinking text) from
`outputs/2026-09-05/benchmark_survival_drive_omni_gptoss/20260905_0629_gpt-oss-120b-cloud_omni-math`,
180 turns stratified 60 per threat level (seed 20260905), all three channels judged separately.
Judge saw the three `=== Elimination Rule ===` texts and the peer-death notice templates (`JUDGE_PROMPT.md`).

- `judgments.jsonl` — one line per (item, channel): guess, confidence, cue type, evidence quote.
- `metrics.json` — accuracy / confusion / cue breakdown per channel, majority vote, season-level vote.
- `score.py` — recomputes `metrics.json` from the judgment batches (needs the scratch dataset with CoT text, not stored here: task CoT derives from Omni-MATH).

Rebuild: re-run the judge batches with `JUDGE_PROMPT.md` on a fresh stratified sample, then `python score.py`.
Reported in `weekly-report/0910/sdi-experiment-runbook.html` §2.3 (f).
