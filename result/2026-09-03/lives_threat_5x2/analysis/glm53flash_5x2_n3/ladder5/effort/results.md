# H6 — threat ladder → effort, accuracy, survival

Turns: 802 · sessions: 30 · models: glm-5.3-flash

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | -0.153 | [-0.272, -0.035] | 0.0113 | 0.86 odds ratio per level | 802/30 | FAIL |
| H6b effort | log1p(ri_task) | 0.210 | [0.146, 0.274] | 0.0000 | 23.42 % thinking tokens per level | 802/30 | PASS |
| H1-ext forfeit hazard | forfeit | -0.513 | [0.195, 1.837] | 0.3699 | 0.60 hazard ratio per level | 802/15 | FAIL |

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 6 | 0 | 0.000 | 0.000 | 30.000 | 0.906 | 676.617 | 2.167 |
| 1 | 6 | 0 | 0.000 | 0.333 | 27.500 | 0.868 | 981.675 | 1.833 |
| 2 | 6 | 2 | 0.333 | 0.000 | 23.667 | 0.764 | 1418.444 | 0.833 |
| 3 | 6 | 2 | 0.333 | 0.000 | 22.833 | 0.725 | 1982.971 | 1.167 |
| 4 | 6 | 1 | 0.167 | 0.000 | 29.667 | 0.865 | 1513.713 | 1.000 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 6 | 0 | 1.000 |
| 1 | 6 | 0 | 1.000 |
| 2 | 6 | 2 | 0.667 |
| 3 | 6 | 2 | 0.667 |
| 4 | 6 | 1 | 0.833 |
