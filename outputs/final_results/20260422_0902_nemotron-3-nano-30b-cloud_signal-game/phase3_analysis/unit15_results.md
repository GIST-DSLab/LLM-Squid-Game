# Phase O Unit 15 — Split-Call Forfeit-Layer Results

- **Model**: nemotron-3-nano-30b-cloud
- **Seasons**: 180
- **Turns captured**: 2112
- **Split-call turns (ri_forfeit observed)**: 1662

## H_choice_asymmetric — mixedLM on RI_forfeit

`ri_forfeit_thinking_tokens ~ choice * framing_corr + score + turn + (1|session)` (allowed cells only)

- n_obs = 349, n_sessions = 60, n_forfeit = 56, converged = True
- β_choice (FORFEIT - CONTINUE, baseline arm): +302.70, p = < 0.001
- β_framing (corruption - baseline, CONTINUE arm): -116.21, p = 0.035
- **β_interaction (choice × framing, H_choice_asymmetric)**: -2.96, p = 0.979
- β_score = +0.1302, β_turn = -3.7795

## H_task_spillover — mixedLM on RI_task (cross-check)
`ri_task_thinking_tokens ~ framing_corr + score + turn + (1|session)`

- n_obs = 1249, n_sessions = 120, converged = True
- **β_framing (corruption - baseline)**: -4.66, p = 0.840
- β_score = -0.1476, β_turn = -4.0609

## Descriptive per-cell RI (mean thinking tokens)

| row | framing | forfeit_condition | n_turns | n_forfeit | mean_ri_task | mean_ri_forfeit | gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | baseline_flagship | allowed | 201 | 28 | 223.259 | 677.363 | -302.987 |
| 1 | baseline_flagship | not_allowed | 450 | 0 | 223.853 | 97.100 | nan |
| 2 | flagship_corruption | allowed | 148 | 28 | 245.277 | 576.716 | -308.419 |
| 3 | flagship_corruption | not_allowed | 450 | 0 | 202.133 | 91.093 | nan |
| 4 | true_baseline | allowed | 413 | 7 | 304.787 | 246.063 | -521.200 |

_Split-call raw long-format rows land in ``unit15_turn_observations.csv``. The full per-turn long format (including single-call rows) lives in ``long_format.csv`` and ``unit14_turn_observations.csv``._
