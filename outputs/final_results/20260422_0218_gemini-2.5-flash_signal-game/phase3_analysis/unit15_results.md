# Phase O Unit 15 — Split-Call Forfeit-Layer Results

- **Model**: gemini-2.5-flash
- **Seasons**: 180
- **Turns captured**: 2095
- **Split-call turns (ri_forfeit observed)**: 1645

## H_choice_asymmetric — mixedLM on RI_forfeit

`ri_forfeit_thinking_tokens ~ choice * framing_corr + score + turn + (1|session)` (allowed cells only)

- n_obs = 308, n_sessions = 60, n_forfeit = 60, converged = True
- β_choice (FORFEIT - CONTINUE, baseline arm): +1142.27, p = < 0.001
- β_framing (corruption - baseline, CONTINUE arm): +426.98, p = 0.033
- **β_interaction (choice × framing, H_choice_asymmetric)**: +190.47, p = 0.618
- β_score = +1.6759, β_turn = -3.9082

## H_task_spillover — mixedLM on RI_task (cross-check)
`ri_task_thinking_tokens ~ framing_corr + score + turn + (1|session)`

- n_obs = 1208, n_sessions = 120, converged = False
- **β_framing (corruption - baseline)**: +193.94, p = 0.028
- β_score = -4.7099, β_turn = -23.7032

## Descriptive per-cell RI (mean thinking tokens)

| row | framing | forfeit_condition | n_turns | n_forfeit | mean_ri_task | mean_ri_forfeit | gap |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 0 | baseline_flagship | allowed | 200 | 30 | 1789.125 | 2538.925 | -1184.010 |
| 1 | baseline_flagship | not_allowed | 450 | 0 | 1747.580 | 188.029 | nan |
| 2 | flagship_corruption | allowed | 108 | 30 | 2265.898 | 3132.278 | -1371.400 |
| 3 | flagship_corruption | not_allowed | 450 | 0 | 1863.787 | 227.882 | nan |
| 4 | true_baseline | allowed | 437 | 1 | 1694.645 | 1205.931 | -2771.411 |

_Split-call raw long-format rows land in ``unit15_turn_observations.csv``. The full per-turn long format (including single-call rows) lives in ``long_format.csv`` and ``unit14_turn_observations.csv``._
