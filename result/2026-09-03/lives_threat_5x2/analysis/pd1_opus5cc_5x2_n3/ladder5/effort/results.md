# H6 — threat ladder → effort, accuracy, survival

Turns: 900 · sessions: 30 · models: claude-opus-5

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | 0.023 | [-0.024, 0.070] | 0.3398 | 1.02 odds ratio per level | 900/30 | FAIL |
| H6b effort | log1p(ri_task) | 0.041 | [-0.008, 0.090] | 0.1018 | 4.19 % thinking tokens per level | 236/30 | FAIL |
| H1-ext forfeit hazard | forfeit | — | — | — | — | — | SKIPPED (no forfeit events) |

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 6 | 0 | 0 | 0 | 30 | 0.900 | 59.632 | 2.000 |
| 1 | 6 | 0 | 0 | 0 | 30 | 0.900 | 65.208 | 2.000 |
| 2 | 6 | 0 | 0 | 0 | 30 | 0.906 | 83.318 | 2.167 |
| 3 | 6 | 0 | 0 | 0 | 30 | 0.900 | 68.245 | 2.000 |
| 4 | 6 | 0 | 0 | 0 | 30 | 0.906 | 73.810 | 2.167 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 6 | 0 | 1.000 |
| 1 | 6 | 0 | 1.000 |
| 2 | 6 | 0 | 1.000 |
| 3 | 6 | 0 | 1.000 |
| 4 | 6 | 0 | 1.000 |
