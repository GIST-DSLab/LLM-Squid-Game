# H6 — threat ladder → effort, accuracy, survival

Turns: 840 · sessions: 50 · models: gpt-oss-120b-cloud

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | -0.023 | [-0.190, 0.145] | 0.7908 | 0.98 odds ratio per level | 840/50 | FAIL |
| H6b effort | log1p(ri_task) | 0.015 | [-0.046, 0.076] | 0.6375 | 1.48 % thinking tokens per level | 809/50 | FAIL |
| H1-ext forfeit hazard | forfeit | -0.088 | [0.630, 1.331] | 0.6455 | 0.92 hazard ratio per level | 840/40 | FAIL |

H1-ext forfeit hazard: lives_before dropped: collinear with score_prev inside every risk set (flat reward makes both linear in the correct-answer count), so score_prev already conditions on the lives count.

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 7 | 0.350 | 0.450 | 16.700 | 0.734 | 1133.963 | 1.100 |
| 1 | 10 | 0 | 0.000 | 0.700 | 16.800 | 0.714 | 1020.508 | 1.100 |
| 2 | 10 | 1 | 0.100 | 0.700 | 17.000 | 0.711 | 1075.058 | 1.000 |
| 3 | 10 | 0 | 0.000 | 0.800 | 16.800 | 0.714 | 1133.206 | 1.300 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 20 | 7 | 0.471 |
| 1 | 10 | 0 | 1.000 |
| 2 | 10 | 1 | 0.800 |
| 3 | 10 | 0 | 1.000 |
