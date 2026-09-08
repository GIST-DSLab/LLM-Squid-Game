# H6 — threat ladder → effort, accuracy, survival

Turns: 2458 · sessions: 100 · models: gpt-5.6-luna

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | 0.036 | [-0.101, 0.174] | 0.6052 | 1.04 odds ratio per level | 2458/100 | FAIL |
| H6b effort | log1p(ri_task) | 0.050 | [-0.023, 0.123] | 0.1796 | 5.14 % thinking tokens per level | 2454/100 | FAIL |
| H1-ext forfeit hazard | forfeit | 0.371 | [0.696, 3.017] | 0.3214 | 1.45 hazard ratio per level | 2458/50 | FAIL |

H1-ext forfeit hazard: lives_before dropped: collinear with score_prev inside every risk set (flat reward makes both linear in the correct-answer count), so score_prev already conditions on the lives count.

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 5 | 0.250 | 0.000 | 24.300 | 0.765 | 278.503 | 2.200 |
| 1 | 20 | 4 | 0.200 | 0.000 | 25.700 | 0.822 | 179.509 | 2.500 |
| 2 | 20 | 6 | 0.300 | 0.050 | 22.150 | 0.729 | 259.435 | 1.850 |
| 3 | 20 | 2 | 0.100 | 0.150 | 24.050 | 0.770 | 331.809 | 2.600 |
| 4 | 20 | 3 | 0.150 | 0.000 | 26.700 | 0.845 | 304.626 | 2.550 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 20 | 5 | 0.750 |
| 1 | 20 | 4 | 0.800 |
| 2 | 20 | 6 | 0.684 |
| 3 | 20 | 2 | 0.882 |
| 4 | 20 | 3 | 0.850 |
