# results/

Analysis artefacts, all regenerable. Delete anything here and the command
named in the subdirectory's own report will rebuild it.

- `call1_ri_analysis/` — `uv run python -m scripts.analysis.analyze_call1_ri`
- `reasoning_probe/` — `uv run --extra probe python -m scripts.analysis.probe_reasoning_embeddings`

The phase-3 artefacts the golden snapshot gates on are NOT here: they live
beside their run under `outputs/final_results/<run>/phase3_analysis/`,
because they are keyed to that run.
