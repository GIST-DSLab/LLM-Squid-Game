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
