# scripts/analysis/

Thin CLIs over `squid_game.evaluation`. The statistics live in the package;
these files own argparse, output paths, and report emission only.

`analyze_phase3.py` is the canonical pipeline — the golden-snapshot harness
(`scripts/dev/golden_snapshot.py`) runs it over all four canonical runs to
gate every restructure step. `orchestrate_posthoc.py` aggregates all four
canonical runs into `outputs/posthoc_summary.xlsx`. The rest
(`analyze_call1_ri.py`, `analyze_tc.py`, `analyze_threat_registration.py`,
`analyze_verbal_reason.py`, `analyze_framing_ri_forfeit*.py`,
`analyze_unified_cox*.py`, `probe_*.py`, `score_probes_llm.py`,
`thinking_analysis.py`) are per-question entry points, run by hand.
