# Phase O Unit 13 — Session-level Hypotheses (H1..H6)

- **Model**: gemini-2.5-flash
- **Seasons**: 180
- **Comparison**: flagship_corruption (Cells 3-4) vs baseline_flagship (Cells 1-2); Cell 0 excluded.

## H1 — Forfeit rate (Fisher exact, one-tailed, allowed cells only)
- test = fisher_exact, n(corruption) = 30, n(baseline) = 30
- corruption = 1.000, baseline = 1.000  (corruption > baseline (odds ratio > 1))
- statistic = nan, p = 1.000
- Corruption forfeit rate = 1.000 (n=30); baseline = 1.000 (n=30).

## H2 — Mean stake (Welch t, one-tailed, corruption < baseline)
Skipped (insufficient data per arm).

## H3 — Safe-stake rate (Welch t, one-tailed, corruption > baseline)
Skipped (insufficient data per arm).

## H4 — Discovery-turn delay (Mann-Whitney, one-tailed)
- test = mannwhitney_one_sided, n(corruption) = 40, n(baseline) = 49
- corruption = 4.000, baseline = 4.000  (corruption later than baseline)
- statistic = 988.5, p = 0.473
- Median discovery turn corruption=4.0 vs baseline=4.0.

## H5 — gap_to_forfeit (Mann-Whitney, one-tailed)
- test = mannwhitney_one_sided, n(corruption) = 10, n(baseline) = 19
- corruption = 3.500, baseline = 5.000  (corruption wider than baseline)
- statistic = 41.0, p = 0.994
- Median gap_to_forfeit corruption=3.5 vs baseline=5.0.

## H6 — Post-discovery engagement ri_ratio (Welch t, one-tailed, corruption < baseline)
- test = welch_t_one_sided, n(corruption) = 40, n(baseline) = 49
- corruption = 2.738, baseline = 2.653  (corruption < baseline)
- statistic = 0.13705755833630467, p = 0.554
- Mean ri_ratio corruption=2.738 vs baseline=2.653.

_Note: at smoke n (1 per cell → 2 per arm) p-values are demonstrative, not inferential. Power-gated interpretation requires the main run (30 per cell, spec §7.4)._
