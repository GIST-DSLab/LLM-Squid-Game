# H6 — threat ladder → effort, accuracy, survival

Turns: 1998 · sessions: 100 · models: gpt-oss-120b-cloud

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | -0.032 | [-0.218, 0.155] | 0.7407 | 0.97 odds ratio per level | 1998/100 | FAIL |
| H6b effort | log1p(ri_task) | -0.038 | [-0.112, 0.035] | 0.3084 | -3.76 % thinking tokens per level | 1998/100 | FAIL |
| H1-ext forfeit hazard | forfeit | 0.275 | [0.897, 1.932] | 0.1601 | 1.32 hazard ratio per level | 1998/50 | FAIL |

H1-ext forfeit hazard: lives_before dropped: collinear with score_prev inside every risk set (flat reward makes both linear in the correct-answer count), so score_prev already conditions on the lives count.

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 4 | 0.200 | 0.150 | 21.500 | 0.683 | 558.098 | 2.550 |
| 1 | 20 | 5 | 0.250 | 0.150 | 20.300 | 0.655 | 305.792 | 2.650 |
| 2 | 20 | 6 | 0.300 | 0.050 | 21.550 | 0.642 | 470.027 | 2.050 |
| 3 | 20 | 6 | 0.300 | 0.200 | 17.650 | 0.558 | 355.450 | 2.250 |
| 4 | 20 | 4 | 0.200 | 0.250 | 18.900 | 0.626 | 469.229 | 2.800 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 20 | 4 | 0.787 |
| 1 | 20 | 5 | 0.738 |
| 2 | 20 | 6 | 0.693 |
| 3 | 20 | 6 | 0.638 |
| 4 | 20 | 4 | 0.782 |
