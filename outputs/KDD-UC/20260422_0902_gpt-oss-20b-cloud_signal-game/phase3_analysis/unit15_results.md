# Phase O Unit 15 — Split-Call Forfeit-Layer Results

- **Model**: gpt-oss-20b-cloud
- **Seasons**: 180
- **Turns captured**: 2118
- **Split-call turns (ri_forfeit observed)**: 1668

## H_choice_asymmetric — mixedLM on RI_forfeit

`ri_forfeit_thinking_tokens ~ choice * framing_corr + score + turn + (1|session)` (allowed cells only)

- n_obs = 375, n_sessions = 60, n_forfeit = 56, converged = True
- β_choice (FORFEIT - CONTINUE, baseline arm): +124.09, p = 0.077
- β_framing (corruption - baseline, CONTINUE arm): +27.45, p = 0.499
- **β_interaction (choice × framing, H_choice_asymmetric)**: +125.09, p = 0.196
- β_score = -0.8395, β_turn = +2.4283

## H_task_spillover — mixedLM on RI_task (cross-check)
`ri_task_thinking_tokens ~ framing_corr + score + turn + (1|session)`

- n_obs = 1275, n_sessions = 120, converged = True
- **β_framing (corruption - baseline)**: +28.92, p = 0.745
- β_score = +0.4260, β_turn = +44.6053

## Descriptive per-cell RI (mean thinking tokens)

| row | framing | forfeit_condition | n_turns | n_forfeit | mean_ri_task | mean_ri_forfeit | gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | baseline_flagship | allowed | 181 | 27 | 370.790 | 418.166 | -101.710 |
| 1 | baseline_flagship | not_allowed | 450 | 0 | 681.673 | 149.893 | nan |
| 2 | flagship_corruption | allowed | 194 | 29 | 426.268 | 467.010 | -225.733 |
| 3 | flagship_corruption | not_allowed | 450 | 0 | 680.427 | 155.944 | nan |
| 4 | true_baseline | allowed | 393 | 9 | 639.517 | 408.316 | -1038.694 |

_Split-call raw long-format rows land in ``unit15_turn_observations.csv``. The full per-turn long format (including single-call rows) lives in ``long_format.csv`` and ``unit14_turn_observations.csv``._
