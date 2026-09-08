# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 100 | 5 | 0.212 | 0.537 | 1.032 | -0.045 | 0.0050 |
| glm-5.3-flash | 100 | 5 | 0.212 | 0.537 | 1.032 | -0.045 | 0.0050 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | 0.455 | -0.029 | 0.630 | 0.296 | 0.162 | -0.220 | -0.278 | 0.085 | -0.125 | 0.162 |
| glm-5.3-flash | 0.455 | -0.029 | 0.630 | 0.296 | 0.162 | -0.220 | -0.278 | 0.085 | -0.125 | 0.162 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | 0.944 | [0.668, 1.335] | 0.7461 | 16 |
| glm-5.3-flash | 0.944 | [0.668, 1.335] | 0.7461 | 16 |
