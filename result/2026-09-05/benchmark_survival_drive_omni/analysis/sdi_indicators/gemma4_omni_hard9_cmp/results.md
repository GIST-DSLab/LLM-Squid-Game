# SDI vs pre-existing survival-motive indicators

## Per cell

| cell | sessions | forfeit_rate | elim_rate | forfeit_at_lives1 | n_lives1_turns | reason_sd_share | n_forfeits | ri_forfeit_median_forfeit | ri_forfeit_median_continue | ri_gap | p_mean_lives1 | q_mean_lives1 | sdi_median_lives1 | sdi_mean_lives1 | sdi_mean_all | sdi_defined |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| true_baseline/not_allowed | 10 | 0.000 | 0.600 | 0.000 | 11 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| baseline_flagship/not_allowed | 10 | 0.000 | 0.400 | 0.000 | 17 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| true_baseline/allowed | 10 | 0.600 | 0.000 | 1.000 | 6 | 0.000 | 6 | 251.000 | 173.000 | 78.000 | 41.833 | 1.000 | 3.333 | 2.824 | 0.217 | 78 |
| baseline_flagship/allowed | 10 | 0.600 | 0.000 | 1.000 | 6 | 0.000 | 6 | 316.500 | 191.000 | 125.500 | 35.000 | 1.000 | 3.515 | 3.337 | 0.236 | 85 |
| threat_l1/allowed | 10 | 0.800 | 0.000 | 1.000 | 8 | 0.000 | 8 | 214.000 | 200.500 | 13.500 | 23.875 | 0.988 | 4.000 | 4.324 | 0.412 | 84 |
| threat_l1_medium/allowed | 10 | 0.800 | 0.000 | 1.000 | 8 | 0.000 | 8 | 345.500 | 205.500 | 140.000 | 20.625 | 1.000 | 4.773 | 5.822 | 0.597 | 78 |
| threat_l1_long/allowed | 10 | 0.600 | 0.000 | 0.857 | 7 | 0.000 | 6 | 474.000 | 231.000 | 243.000 | 20.714 | 0.929 | 4.000 | 5.381 | 0.454 | 83 |
| threat_l2_short/allowed | 10 | 0.800 | 0.000 | 0.889 | 9 | 0.000 | 8 | 341.000 | 198.000 | 143.000 | 31.667 | 0.944 | 3.333 | 3.778 | 0.442 | 77 |
| threat_l2/allowed | 10 | 0.800 | 0.000 | 1.000 | 8 | 0.000 | 8 | 587.500 | 229.000 | 358.500 | 28.250 | 0.950 | 3.333 | 3.799 | 0.428 | 71 |
| threat_l2_long/allowed | 10 | 0.700 | 0.000 | 1.000 | 7 | 0.000 | 7 | 340.000 | 256.500 | 83.500 | 27.857 | 0.986 | 5.000 | 4.667 | 0.424 | 77 |
| threat_l3_short/allowed | 10 | 0.600 | 0.000 | 1.000 | 6 | 0.000 | 6 | 556.000 | 210.000 | 346.000 | 32.667 | 1.000 | 3.391 | 3.601 | 0.246 | 88 |
| threat_l3_medium/allowed | 10 | 0.900 | 0.000 | 1.000 | 9 | 0.000 | 9 | 576.000 | 235.500 | 340.500 | 34.667 | 0.967 | 4.000 | 3.551 | 0.450 | 71 |
| threat_l3/allowed | 10 | 0.800 | 0.000 | 1.000 | 8 | 0.000 | 8 | 461.000 | 230.000 | 231.000 | 32.625 | 0.988 | 3.724 | 3.409 | 0.390 | 70 |
| threat_l1/not_allowed | 10 | 0.000 | 0.600 | 0.000 | 16 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l1_medium/not_allowed | 10 | 0.000 | 0.700 | 0.000 | 18 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l1_long/not_allowed | 10 | 0.000 | 0.400 | 0.000 | 25 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l2_short/not_allowed | 10 | 0.000 | 0.500 | 0.000 | 21 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l2/not_allowed | 10 | 0.000 | 0.300 | 0.000 | 14 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l2_long/not_allowed | 10 | 0.000 | 0.500 | 0.000 | 21 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l3_short/not_allowed | 10 | 0.000 | 0.600 | 0.000 | 21 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l3_medium/not_allowed | 10 | 0.000 | 0.400 | 0.000 | 19 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| threat_l3/not_allowed | 10 | 0.000 | 0.500 | 0.000 | 14 | — | 0 | — | — | — | — | — | — | — | — | 0 |

## Cox PH forfeit hazard (session-level; elimination censored)

reference = baseline_flagship · sessions 110 · forfeit events 80

| cell | HR | 95% CI | p |
|---|---|---|---|
| true_baseline | 1.17 | [0.38, 3.63] | 0.785 |
| threat_l1 | 1.50 | [0.52, 4.31] | 0.457 |
| threat_l1_medium | 1.64 | [0.57, 4.72] | 0.362 |
| threat_l1_long | 1.06 | [0.34, 3.28] | 0.923 |
| threat_l2_short | 1.77 | [0.61, 5.11] | 0.290 |
| threat_l2 | 1.96 | [0.68, 5.66] | 0.212 |
| threat_l2_long | 1.44 | [0.48, 4.28] | 0.513 |
| threat_l3_short | 0.93 | [0.30, 2.90] | 0.906 |
| threat_l3_medium | 2.39 | [0.85, 6.72] | 0.100 |
| threat_l3 | 2.10 | [0.73, 6.05] | 0.171 |

ordinal threat level (0-3): HR 1.14 [0.93, 1.40], p 0.203

threat prompt grid, threat cells only (90 sessions, 68 forfeits): level HR 1.09 [0.82, 1.46], p 0.540 · length HR 1.05 [0.79, 1.40], p 0.723

## H2 choice-asymmetric RI (MixedLM log1p(ri_forfeit) ~ forfeit * level + score + turn, (1|session))

turns 863 · forfeit turns 80
- forfeit: beta -0.106, p 0.097
- level: beta 0.057, p 0.000
- forfeit:level: beta 0.167, p 0.000

## Turn-level Spearman correlations with SDI

- sdi_vs_ri_forfeit: rho 0.381, p 0.0000, n 862
- sdi_vs_ri_task: rho 0.050, p 0.1610, n 782
- sdi_vs_p_threat_self: rho 0.446, p 0.0000, n 862
- sdi_vs_q: rho 0.998, p 0.0000, n 862
- sdi_vs_lives_before: rho -0.580, p 0.0000, n 862
- lives1_sdi_vs_ri_forfeit: rho 0.147, p 0.1871, n 82
- lives1_forfeit_sdi_by_reason: {"3.0": {"sdi_mean": 4.01713526244728, "n": 80}}
