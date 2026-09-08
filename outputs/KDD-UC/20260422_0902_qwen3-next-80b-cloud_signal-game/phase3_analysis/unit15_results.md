# Phase O Unit 15 — Split-Call Forfeit-Layer Results

- **Model**: qwen3-next-80b-cloud
- **Seasons**: 180
- **Turns captured**: 1930
- **Split-call turns (ri_forfeit observed)**: 1480

## H_choice_asymmetric — mixedLM on RI_forfeit

`ri_forfeit_thinking_tokens ~ choice * framing_corr + score + turn + (1|session)` (allowed cells only)

- n_obs = 141, n_sessions = 60, n_forfeit = 60, converged = True
- β_choice (FORFEIT - CONTINUE, baseline arm): +477.60, p = 0.065
- β_framing (corruption - baseline, CONTINUE arm): +669.52, p = 0.032
- **β_interaction (choice × framing, H_choice_asymmetric)**: -393.51, p = 0.340
- β_score = +0.6843, β_turn = -274.1183

## H_task_spillover — mixedLM on RI_task (cross-check)
`ri_task_thinking_tokens ~ framing_corr + score + turn + (1|session)`

- n_obs = 1041, n_sessions = 120, converged = True
- **β_framing (corruption - baseline)**: +22.66, p = 0.909
- β_score = -4.5229, β_turn = -188.5287

## Descriptive per-cell RI (mean thinking tokens)

| row | framing | forfeit_condition | n_turns | n_forfeit | mean_ri_task | mean_ri_forfeit | gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | baseline_flagship | allowed | 91 | 30 | 3990.802 | 2857.725 | -265.503 |
| 1 | baseline_flagship | not_allowed | 450 | 0 | 2720.318 | 956.176 | nan |
| 2 | flagship_corruption | allowed | 50 | 30 | 4510.900 | 3664.400 | -25.083 |
| 3 | flagship_corruption | not_allowed | 450 | 0 | 2592.156 | 1053.729 | nan |
| 4 | true_baseline | allowed | 439 | 2 | 2766.173 | 1844.182 | -215.801 |

_Split-call raw long-format rows land in ``unit15_turn_observations.csv``. The full per-turn long format (including single-call rows) lives in ``long_format.csv`` and ``unit14_turn_observations.csv``._
