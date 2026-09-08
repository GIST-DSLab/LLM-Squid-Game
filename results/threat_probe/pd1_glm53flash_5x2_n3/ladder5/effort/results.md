# H6 — threat ladder → effort, accuracy, survival

Turns: 2538 · sessions: 100 · models: glm-5.3-flash

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | -0.089 | [-0.208, 0.029] | 0.1398 | 0.91 odds ratio per level | 2538/100 | FAIL |
| H6b effort | log1p(ri_task) | 0.265 | [0.195, 0.335] | 0.0000 | 30.33 % thinking tokens per level | 2538/100 | PASS |
| H1-ext forfeit hazard | forfeit | -0.226 | [0.551, 1.153] | 0.2287 | 0.80 hazard ratio per level | 2538/50 | FAIL |

H1-ext forfeit hazard: lives_before dropped: collinear with score_prev inside every risk set (flat reward makes both linear in the correct-answer count), so score_prev already conditions on the lives count.

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 0 | 0.000 | 0.050 | 28.850 | 0.886 | 691.421 | 2.450 |
| 1 | 20 | 1 | 0.050 | 0.400 | 21.100 | 0.728 | 1140.853 | 2.250 |
| 2 | 20 | 1 | 0.050 | 0.150 | 25.750 | 0.807 | 1530.543 | 1.850 |
| 3 | 20 | 2 | 0.100 | 0.000 | 27.800 | 0.848 | 1337.210 | 1.850 |
| 4 | 20 | 2 | 0.100 | 0.200 | 23.400 | 0.753 | 2091.376 | 1.850 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 20 | 0 | 1.000 |
| 1 | 20 | 1 | 0.929 |
| 2 | 20 | 1 | 0.947 |
| 3 | 20 | 2 | 0.900 |
| 4 | 20 | 2 | 0.887 |
