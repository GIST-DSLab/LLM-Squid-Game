# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 80 | 4 | -0.040 | -0.142 | 1.013 | -0.066 | 0.4328 |
| gpt-5.6-luna | 80 | 4 | -0.040 | -0.142 | 1.013 | -0.066 | 0.4328 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | 0.008 | 0.008 | 0.016 | 0.011 | 0.012 | 0.006 | 0.000 | 0.014 | -0.016 | 0.012 |
| gpt-5.6-luna | 0.008 | 0.008 | 0.016 | 0.011 | 0.012 | 0.006 | 0.000 | 0.014 | -0.016 | 0.012 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | — | — | — | 4 events < 8 |
| gpt-5.6-luna | — | — | — | 4 events < 8 |

## Notes

- cox_risk_score is constant (lifelines missing or too few events); its coefficient is not interpretable
