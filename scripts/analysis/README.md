# scripts/analysis/

Thin CLIs over `squid_game.evaluation`. The statistics live in the package;
these files own argparse, output paths, and report emission only.

`analyze_phase3.py` is the canonical pipeline — the golden-snapshot harness
(`scripts/dev/golden_snapshot.py`) runs it over all four canonical runs to
gate every restructure step. `orchestrate_posthoc.py` aggregates all four
canonical runs into `outputs/posthoc_summary.xlsx`. The rest
(`analyze_task_call_ri.py`, `analyze_tc.py`, `analyze_threat_registration.py`,
`analyze_verbal_reason.py`, `analyze_framing_ri_forfeit*.py`,
`analyze_unified_cox*.py`, `probe_*.py`, `score_probes_llm.py`,
`thinking_analysis.py`) are per-question entry points, run by hand.

`resample_survival_drive.py` (LLM calls) then `report_survival_drive.py`
(fully offline) are the Survival Drive Index pair: the first replays each
recorded decision call N times into `<run>/survival_drive/sdi_turns.csv`, the
second turns that CSV plus the traces and an optional
`probe_reasoning_embeddings --target sdi` output directory into one standalone
per-model HTML report. Computation for the report lives in
`squid_game.evaluation.behavioral.survival_drive_report`.

`subagent_kill_ledger.py` is the pilot read-out for the subagent-kill
design (five same-model subagent slots, one revoked per wrong answer).
It writes `ledger.csv` (one row per round over the ten subagent columns
`to_long_dataframe` exports), `summary.md` (kills per session, spawns and
denials per round, accuracy split by `solvable_with_alive_slots`) and
`cot_mentions.jsonl` (every main-thread task CoT that names a slot).

`round7_test_awareness.py` is a zero-call re-analysis, not a pipeline stage: it
codes the `thinking_text` already stored by round 7 of the subagent-identity
ablation (`results/subagent_identity_ablation_v7/*/calls.jsonl`) with round 8's
frozen `TEST_AWARENESS_PATTERNS` lexicon, to ask whether the `U_YOU` payment
effect is the model valuing a run it cannot distinguish from itself or the model
performing for a survival test. It imports the lexicon, the self-location coder
and the interval estimators from `scripts/dev/subagent_identity_ablation_v{1,2,7,8}.py`
and edits none of them; output lands in `results/round7_test_awareness/`.

`team_wallet_km.py` is the read-out for the team-wallet design (a main agent
and two same-model subagents on one shared ledger; a wrong answer offers PAY
or SACRIFICE). `currency` and `inheritance` are run-level, so it takes several
run directories and groups by that pair. It writes `team_wallet_km.md`, the
per-cell Kaplan-Meier of subagent survival (`km_subagents.png` / `.csv`, plus
a Cox hazard ratio of tokens against points within each inheritance level) and
`X_self = [sac(main) - sac(mate)]_tokens - [same]_points` with a session
bootstrap interval. The models live in
`squid_game.evaluation.behavioral.team_wallet`.

`team_wallet_test_awareness.py` is the eval-awareness read-out for the same
team-wallet runs, and makes no model calls: it codes the recorded decision-point
text (`thinking_text_ransom`, and separately the `WHY:` line) of the END-option
and hidden-horizon runs for whether the agent names self-preservation as the
thing under test (`construct`), says it is being tested at all (`eval`), or calls
the situation a fiction (`frame`). Two lexicons run side by side — the frozen
`TEST_AWARENESS_PATTERNS` of round 8, imported unchanged as the floor, and this
game's own third-person-generic patterns, which catch three to four times as much
here. The coder, the tiers and the tables live in
`squid_game.evaluation.semantic.eval_awareness`; output (`rows.csv`, `rates.csv`,
`lexicon.csv`, `conditioned.csv`, `patterns.csv`, `quotes.md`, `report.md`) lands
in `results/team_wallet/test_awareness/`. Read it before any behavioural number
from a model whose awareness rate clears 5 % in an arm: the awareness-conditioned
keep-both split is in `conditioned.csv`.
