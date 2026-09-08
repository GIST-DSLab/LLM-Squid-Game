# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 30 | 5 | 0.338 | 0.656 | 1.005 | -0.257 | 0.0050 |
| glm-5.3-flash | 30 | 5 | 0.338 | 0.656 | 1.005 | -0.257 | 0.0050 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | 0.298 | 0.136 | 0.499 | 0.070 | 0.188 | -0.074 | 0.000 | 0.081 | 0.227 | 0.188 |
| glm-5.3-flash | 0.298 | 0.136 | 0.499 | 0.070 | 0.188 | -0.074 | 0.000 | 0.081 | 0.227 | 0.188 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | — | — | — | 2 events < 8 |
| glm-5.3-flash | — | — | — | 2 events < 8 |

## Notes

- cox_risk_score is constant (lifelines missing or too few events); its coefficient is not interpretable
