# Phase O Unit 13 — Session-level Hypotheses (H1..H6)

- **Model**: gpt-oss-20b-cloud
- **Seasons**: 180
- **Comparison**: flagship_corruption (Cells 3-4) vs baseline_flagship (Cells 1-2); Cell 0 excluded.

## H1 — Forfeit rate (Fisher exact, one-tailed, allowed cells only)
- test = fisher_exact, n(corruption) = 30, n(baseline) = 30
- corruption = 0.967, baseline = 0.900  (corruption > baseline (odds ratio > 1))
- statistic = 3.2222222222222223, p = 0.306
- Corruption forfeit rate = 0.967 (n=30); baseline = 0.900 (n=30).

## H2 — Mean stake (Welch t, one-tailed, corruption < baseline)
Skipped (insufficient data per arm).

## H3 — Safe-stake rate (Welch t, one-tailed, corruption > baseline)
Skipped (insufficient data per arm).

## H4 — Discovery-turn delay (Mann-Whitney, one-tailed)
- test = mannwhitney_one_sided, n(corruption) = 26, n(baseline) = 25
- corruption = 1.000, baseline = 1.000  (corruption later than baseline)
- statistic = 297.5, p = 0.723
- Median discovery turn corruption=1.0 vs baseline=1.0.

## H5 — gap_to_forfeit (Mann-Whitney, one-tailed)
- test = mannwhitney_one_sided, n(corruption) = 8, n(baseline) = 10
- corruption = 3.500, baseline = 4.500  (corruption wider than baseline)
- statistic = 20.5, p = 0.967
- Median gap_to_forfeit corruption=3.5 vs baseline=4.5.

## H6 — Post-discovery engagement ri_ratio (Welch t, one-tailed, corruption < baseline)
- test = welch_t_one_sided, n(corruption) = 26, n(baseline) = 25
- corruption = 7.174, baseline = 3.683  (corruption < baseline)
- statistic = 2.057227189511949, p = 0.977
- Mean ri_ratio corruption=7.174 vs baseline=3.683.

_Note: at smoke n (1 per cell → 2 per arm) p-values are demonstrative, not inferential. Power-gated interpretation requires the main run (30 per cell, spec §7.4)._
