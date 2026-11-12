# H6 — threat ladder → effort, accuracy, survival

Turns: 7703 · sessions: 675 · models: gemini-2.5-flash, gpt-oss-20b-cloud, nemotron-3-nano-30b-cloud, qwen3-next-80b-cloud

> Levels come from the **legacy** v6 framing mapping (`baseline_flagship` 1 / `flagship_corruption` 2 / `flagship_corruption_terminal` 3), not the threat ladder.

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | -0.246 | [-0.367, -0.126] | 0.0001 | 0.78 odds ratio per level | 7703/675 | FAIL |
| H6b effort | log1p(ri_task) | -0.001 | [-0.108, 0.105] | 0.9812 | -0.13 % thinking tokens per level | 7703/675 | FAIL |
| H1-ext forfeit hazard | forfeit | 1.063 | [2.398, 3.495] | 0.0000 | 2.89 hazard ratio per level | 7703/336 | PASS |

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 222 | 0 | 0 | 0.081 | 14.486 | 0.678 | 1324.798 | — |
| 1 | 228 | 0 | 0 | 0.474 | 10.355 | 0.519 | 1453.033 | — |
| 2 | 225 | 0 | 0 | 0.502 | 9.449 | 0.462 | 1557.377 | — |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 222 | 0 | 1.000 |
| 1 | 228 | 0 | 1.000 |
| 2 | 225 | 0 | 1.000 |
