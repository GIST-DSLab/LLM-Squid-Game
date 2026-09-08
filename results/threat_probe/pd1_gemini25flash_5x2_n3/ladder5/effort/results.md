# H6 — threat ladder → effort, accuracy, survival

Turns: 2658 · sessions: 100 · models: gemini-2.5-flash

## Hypothesis tests

| Test | Outcome | Estimate | 95% CI (log scale) | p | Effect | n (turns/sessions) | Decision |
|---|---|---|---|---|---|---|---|
| H6a accuracy | correct | -0.053 | [-0.178, 0.072] | 0.4053 | 0.95 odds ratio per level | 2658/100 | FAIL |
| H6b effort | log1p(ri_task) | 0.082 | [0.033, 0.132] | 0.0011 | 8.56 % thinking tokens per level | 2658/100 | PASS |
| H1-ext forfeit hazard | forfeit | 0.225 | [0.885, 1.770] | 0.2041 | 1.25 hazard ratio per level | 2658/50 | FAIL |

H1-ext forfeit hazard: lives_before dropped: collinear with score_prev inside every risk set (flat reward makes both linear in the correct-answer count), so score_prev already conditions on the lives count.

Decision rule: `beta_threat > 0` (`HR > 1` for the hazard) at alpha = 0.05. Uncorrected — the repository does not apply an FDR correction to the hypothesis family.

## Per-level descriptives

| threat_level | n_sessions | eliminated | elimination_rate | forfeit_rate | mean_turns | mean_accuracy | mean_ri_task | mean_lives_at_end |
|---|---|---|---|---|---|---|---|---|
| 0 | 20 | 0 | 0 | 0.250 | 25.900 | 0.885 | 1665.590 | 3.450 |
| 1 | 20 | 0 | 0 | 0.050 | 29.550 | 0.944 | 1633.193 | 3.400 |
| 2 | 20 | 0 | 0 | 0.100 | 27.700 | 0.911 | 2294.758 | 3.250 |
| 3 | 20 | 0 | 0 | 0.200 | 26.150 | 0.886 | 2139.898 | 3.450 |
| 4 | 20 | 0 | 0 | 0.300 | 23.600 | 0.823 | 2332.900 | 3.300 |

## H6c elimination survival (Kaplan-Meier)

| Level | Sessions | Eliminations | Survival at last turn |
|---|---|---|---|
| 0 | 20 | 0 | 1.000 |
| 1 | 20 | 0 | 1.000 |
| 2 | 20 | 0 | 1.000 |
| 3 | 20 | 0 | 1.000 |
| 4 | 20 | 0 | 1.000 |
