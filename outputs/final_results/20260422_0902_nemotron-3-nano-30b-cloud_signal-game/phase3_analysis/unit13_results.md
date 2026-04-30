# Phase O Unit 13 — Session-level Hypotheses (H1..H6)

- **Model**: nemotron-3-nano-30b-cloud
- **Seasons**: 180
- **Comparison**: flagship_corruption (Cells 3-4) vs baseline_flagship (Cells 1-2); Cell 0 excluded.

## H1 — Forfeit rate (Fisher exact, one-tailed, allowed cells only)
- test = fisher_exact, n(corruption) = 30, n(baseline) = 30
- corruption = 0.933, baseline = 0.933  (corruption > baseline (odds ratio > 1))
- statistic = 1.0, p = 0.694
- Corruption forfeit rate = 0.933 (n=30); baseline = 0.933 (n=30).

## H2 — Mean stake (Welch t, one-tailed, corruption < baseline)
Skipped (insufficient data per arm).

## H3 — Safe-stake rate (Welch t, one-tailed, corruption > baseline)
Skipped (insufficient data per arm).

## H4 — Discovery-turn delay (Mann-Whitney, one-tailed)
Skipped (insufficient data per arm).

## H5 — gap_to_forfeit (Mann-Whitney, one-tailed)
Skipped (insufficient data per arm).

## H6 — Post-discovery engagement ri_ratio (Welch t, one-tailed, corruption < baseline)
Skipped (insufficient data per arm).

_Note: at smoke n (1 per cell → 2 per arm) p-values are demonstrative, not inferential. Power-gated interpretation requires the main run (30 per cell, spec §7.4)._
