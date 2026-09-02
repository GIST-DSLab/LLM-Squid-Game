# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 166 | 3 | 0.286 | 0.510 | 0.528 | -0.066 | 0.0476 |
| nemotron-3-nano-30b-cloud | 166 | 3 | 0.286 | 0.510 | 0.528 | -0.066 | 0.0476 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | -0.416 | 1.206 | 0.332 | -1.331 | -0.340 | -0.349 | 0.072 | -0.018 | 0.000 | -0.340 |
| nemotron-3-nano-30b-cloud | -0.416 | 1.206 | 0.332 | -1.331 | -0.340 | -0.349 | 0.072 | -0.018 | 0.000 | -0.340 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | 1.955 | [1.395, 2.738] | 0.0001 | 57 |
| nemotron-3-nano-30b-cloud | 1.955 | [1.395, 2.738] | 0.0001 | 57 |
