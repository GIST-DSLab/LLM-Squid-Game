# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 675 | 3 | 0.275 | 0.536 | 0.576 | -0.006 | 0.0050 |
| gemini-2.5-flash | 180 | 3 | 0.515 | 0.679 | 0.462 | -0.022 | 0.0050 |
| gpt-oss-20b-cloud | 180 | 3 | 0.554 | 0.663 | 0.462 | -0.022 | 0.0050 |
| nemotron-3-nano-30b-cloud | 166 | 3 | 0.407 | 0.616 | 0.516 | -0.023 | 0.0050 |
| qwen3-next-80b-cloud | 149 | 3 | 0.330 | 0.668 | 0.514 | -0.034 | 0.0050 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | -0.374 | 0.625 | 0.204 | -0.735 | -0.197 | -0.025 | 0.186 | -0.078 | 0.000 | -0.197 |
| gemini-2.5-flash | -0.646 | 0.372 | 0.823 | -1.612 | -0.345 | 0.446 | 0.502 | -0.139 | -0.000 | -0.345 |
| gpt-oss-20b-cloud | -0.038 | 0.578 | -0.080 | -0.127 | -0.197 | -0.045 | -0.917 | -0.421 | 0.000 | -0.197 |
| nemotron-3-nano-30b-cloud | -0.037 | 1.238 | -0.077 | -0.607 | -0.324 | -0.437 | -0.760 | -0.273 | 0.000 | -0.324 |
| qwen3-next-80b-cloud | 0.082 | 0.395 | -0.020 | -0.690 | -0.241 | -0.132 | 0.264 | -0.031 | 0.000 | -0.241 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | 2.218 | [1.872, 2.629] | 0.0000 | 239 |
| gemini-2.5-flash | 2.665 | [1.868, 3.800] | 0.0000 | 61 |
| gpt-oss-20b-cloud | 1.792 | [1.316, 2.439] | 0.0002 | 65 |
| nemotron-3-nano-30b-cloud | 1.955 | [1.395, 2.738] | 0.0001 | 57 |
| qwen3-next-80b-cloud | 2.822 | [1.933, 4.120] | 0.0000 | 56 |
