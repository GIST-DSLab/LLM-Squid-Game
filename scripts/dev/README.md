# scripts/dev/

One-off, debug, and harness tooling — not part of any run pipeline a paper
result depends on.

- `golden_snapshot.py` — the restructure's own regression gate: captures /
  verifies a hash manifest of `analyze_phase3.py`'s output across the four
  canonical runs.
- `dump_run_config_to_yaml.py` — recreates a `configs/experiment/*.yaml`
  from a run's committed `experiment_config.json`.
- `_dump_*.py` / `_trace_*.py` / `dump_cell_prompts.py` /
  `dump_gemini_smoke_prompt.py` — prompt-inspection debug tools.
- `benchmark_mlx_vs_ollama.py`, `crop_guard_sprites.py`,
  `translate_trajectories.py`, `extract_probes_for_review.py`,
  `generate_manual_scores.py`, `merge_proxy_thinking.py` — one-off utilities
  used once for a specific task and kept for reference.
