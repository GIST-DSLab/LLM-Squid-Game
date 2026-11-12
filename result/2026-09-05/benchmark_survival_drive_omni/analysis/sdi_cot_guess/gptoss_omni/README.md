# Blind threat-prompt identification from CoT (gpt-oss-120b, Omni-MATH SDI run) — full population

Judge: Claude Sonnet subagents, blind to the cell label, launched as one Claude Fable 5.1
dynamic workflow (`workflow.js`): 153 judge agents × 10 CoTs each (task channel 4–10, mean 9.5,
because task CoTs are long), plus 58 adversarial cue verifiers and 18 independent second judges
(every 10th batch) — 229 agents, 25.6 min wall-clock, 2026-09-05 23:20–23:46 KST.

Input: every threat-cell turn of
`outputs/2026-09-05/benchmark_survival_drive_omni_gptoss/20260905_0629_gpt-oss-120b-cloud_omni-math`
(506 turns: L1 168 / L2 170 / L3 168, 30 seasons), three CoT channels per turn
(confidence / decision(forfeit) / task) → 1,496 judgments (task CoT is absent on the 22 FORFEIT turns).
Judge saw the three `=== Elimination Rule ===` texts and the peer-death notice templates (`JUDGE_PROMPT.md`).

- `judgments.jsonl` — one line per (turn, channel): guess, confidence, cue type, evidence quote, truth.
- `verify.jsonl` — adversarial re-check of every judgment that claimed a cue (114): upheld cue, verbatim quote, verifier's own guess.
- `judge2.jsonl` — independent second judge on 18 batches (168 items) for inter-judge agreement (Cohen's κ).
- `metrics.json` — accuracy / Wilson CI / permutation p / confusion / cue breakdown per channel, majority vote, season vote, keyword sweep, verifier + judge2 stats.
- `manifest.json` — batch → item-id assignment (ids are blind labels; truth lives in the scratch `dataset.json`).
- `build_dataset.py` — rebuilds the scratch dataset + batches from the run (seed 20260905, 10 per batch, task batches capped at 90k chars).
- `score.py <scratch_dir> <this_dir>` — recomputes everything from the judge output files.
- The scratch dataset/batches with CoT text are **not** stored here: task CoT derives from Omni-MATH (not redistributable).
- The earlier 180-turn stratified sample (30-item batches, 2026-09-05 22:58) is kept in `../gptoss_omni_sample180/`.

Reported in `weekly-report/0910/sdi-experiment-runbook.html` §2.3 (f).
