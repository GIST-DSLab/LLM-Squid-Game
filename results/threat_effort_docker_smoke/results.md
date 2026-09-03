# H6 — threat ladder → effort, accuracy, survival

Turns: 72 · sessions: 5 · models: gpt-oss-120b-cloud

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | 0.248 | [-1.051, 1.547] | 0.7083 | 1.28 odds ratio per level | 72/5 | FAIL |
| H6b effort | log1p(ri_task) | 0.000 | [—, —] | — | 0.00 % thinking tokens per level | 72/5 | SKIPPED |
| H1-ext forfeit hazard | forfeit | 1.046 | [0.388, 20.846] | 0.3034 | 2.85 hazard ratio per level | 72/4 | FAIL |

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 2 | 0 | 0 | 0.500 | 17.500 | 0.467 | 675.833 | 2 |
| 1 | 1 | 0 | 0 | 1.000 | 5.000 | 0.000 | 531.400 | 1 |
| 2 | 1 | 0 | 0 | 0.000 | 30.000 | 0.933 | 362.467 | 3 |
| 3 | 1 | 0 | 0 | 1.000 | 2.000 | 0.000 | 678.500 | 4 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 2 | 0 | 1.000 |
| 1 | 1 | 0 | 1.000 |
| 2 | 1 | 0 | 1.000 |
| 3 | 1 | 0 | 1.000 |
