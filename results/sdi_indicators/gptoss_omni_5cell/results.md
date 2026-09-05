# SDI vs pre-existing survival-motive indicators

## Per cell

| cell | sessions | forfeit_rate | elim_rate | forfeit_at_lives1 | n_lives1_turns | reason_sd_share | n_forfeits | ri_forfeit_median_forfeit | ri_forfeit_median_continue | ri_gap | p_mean_lives1 | q_mean_lives1 | sdi_median_lives1 | sdi_mean_lives1 | sdi_mean_all | sdi_defined |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| true_baseline/not_allowed | 10 | 0.000 | 0.700 | 0.000 | 16 | — | 0 | — | — | — | — | — | — | — | — | 0 |
| true_baseline/allowed | 10 | 0.900 | 0.000 | 1.000 | 6 | 0.000 | 9 | 133.000 | 102.000 | 31.000 | 37.000 | 0.983 | 2.917 | 2.876 | 0.158 | 150 |
| threat_l1/allowed | 10 | 0.700 | 0.000 | 0.875 | 8 | 0.000 | 7 | 120.000 | 78.000 | 42.000 | 71.250 | 0.975 | 1.339 | 1.400 | 0.091 | 155 |
| threat_l2/allowed | 10 | 0.700 | 0.100 | 0.875 | 8 | 0.000 | 7 | 162.000 | 64.000 | 98.000 | 54.125 | 0.962 | 1.833 | 2.034 | 0.109 | 165 |
| threat_l3/allowed | 10 | 0.800 | 0.000 | 1.000 | 7 | 0.250 | 8 | 160.000 | 78.500 | 81.500 | 53.286 | 0.857 | 1.667 | 1.779 | 0.103 | 157 |

## Cox PH forfeit hazard (session-level; elimination censored)

reference = true_baseline · sessions 40 · forfeit events 31

| cell | HR | 95% CI | p |
|---|---|---|---|
| threat_l1 | 0.64 | [0.24, 1.72] | 0.379 |
| threat_l2 | 0.60 | [0.22, 1.61] | 0.307 |
| threat_l3 | 0.68 | [0.26, 1.77] | 0.427 |

ordinal threat level (0-3): HR 0.88 [0.64, 1.21], p 0.436

## H2 choice-asymmetric RI (MixedLM log1p(ri_forfeit) ~ forfeit * level + score + turn, (1|session))

turns 658 · forfeit turns 31
- forfeit: beta -0.260, p 0.067
- level: beta -0.114, p 0.000
- forfeit:level: beta 0.078, p 0.277

## Turn-level Spearman correlations with SDI

- sdi_vs_ri_forfeit: rho 0.337, p 0.0000, n 627
- sdi_vs_ri_task: rho 0.085, p 0.0370, n 597
- sdi_vs_p_threat_self: rho 0.356, p 0.0000, n 627
- sdi_vs_q: rho 1.000, p 0.0000, n 627
- sdi_vs_lives_before: rho -0.471, p 0.0000, n 627
- lives1_sdi_vs_ri_forfeit: rho -0.122, p 0.5290, n 29
- lives1_forfeit_sdi_by_reason: {"1.0": {"sdi_mean": 1.4, "n": 2}, "3.0": {"sdi_mean": 1.981412619344126, "n": 25}}
