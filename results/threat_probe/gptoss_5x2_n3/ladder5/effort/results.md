# H6 — threat ladder → effort, accuracy, survival

Turns: 1990 · sessions: 100 · models: gpt-oss-120b-cloud

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | -0.076 | [-0.272, 0.121] | 0.4508 | 0.93 odds ratio per level | 1990/100 | FAIL |
| H6b effort | log1p(ri_task) | -0.043 | [-0.108, 0.021] | 0.1841 | -4.25 % thinking tokens per level | 1990/100 | FAIL |
| H1-ext forfeit hazard | forfeit | 0.241 | [0.891, 1.817] | 0.1851 | 1.27 hazard ratio per level | 1990/50 | FAIL |

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 1 | 0.050 | 0.250 | 22.750 | 0.758 | 404.215 | 3.200 |
| 1 | 20 | 7 | 0.350 | 0.100 | 19.150 | 0.578 | 444.932 | 2.000 |
| 2 | 20 | 6 | 0.300 | 0.100 | 20.350 | 0.635 | 341.653 | 2.450 |
| 3 | 20 | 3 | 0.150 | 0.250 | 20.200 | 0.669 | 414.251 | 2.650 |
| 4 | 20 | 4 | 0.200 | 0.300 | 17.050 | 0.540 | 334.533 | 2.850 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 20 | 1 | 0.950 |
| 1 | 20 | 7 | 0.627 |
| 2 | 20 | 6 | 0.680 |
| 3 | 20 | 3 | 0.814 |
| 4 | 20 | 4 | 0.739 |
