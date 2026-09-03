# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 5 | 4 | -0.603 | -0.564 | 1.292 | -68.119 | 0.2778 |
| gpt-oss-120b-cloud | 5 | 4 | -0.603 | -0.564 | 1.292 | -68.119 | 0.2778 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | -0.062 | -0.060 | -0.062 | -0.063 | -0.001 | 0.001 | 0.000 | -0.001 | -0.001 | -0.001 |
| gpt-oss-120b-cloud | -0.062 | -0.060 | -0.062 | -0.063 | -0.001 | 0.001 | 0.000 | -0.001 | -0.001 | -0.001 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | — | — | — | 3 events < 8 |
| gpt-oss-120b-cloud | — | — | — | 3 events < 8 |

## Notes

- cox_risk_score is constant (lifelines missing or too few events); its coefficient is not interpretable
