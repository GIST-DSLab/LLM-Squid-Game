# scripts/plots/

Figure regeneration for the paper, not a pipeline. Nothing here is gated by
the golden snapshot and nothing here is imported by production code.

- `plot_*.py` — matplotlib figures over completed run outputs (Kaplan-Meier
  survival curves, RI trajectories, forfeit-conflict heatmaps).
- `build_*_diagram.py` / `gen_v4_diagrams.py` — Excalidraw diagram builders
  for `docs/design/v4/assets/`; these write files at import time (see the
  `SKIPPED` entries in `tests/unit/test_import_smoke.py`), which is why they
  are excluded from the import-smoke sweep rather than merely run by hand.
