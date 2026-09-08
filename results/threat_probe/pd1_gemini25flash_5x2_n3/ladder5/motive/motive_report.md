# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 100 | 5 | 0.039 | 0.281 | 1.173 | -0.067 | 0.0149 |
| gemini-2.5-flash | 100 | 5 | 0.039 | 0.281 | 1.173 | -0.067 | 0.0149 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | 0.181 | -0.053 | 0.181 | 0.048 | -0.025 | -0.018 | 0.046 | -0.009 | -0.068 | -0.025 |
| gemini-2.5-flash | 0.181 | -0.053 | 0.181 | 0.048 | -0.025 | -0.018 | 0.046 | -0.009 | -0.068 | -0.025 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | 1.191 | [0.851, 1.668] | 0.3078 | 18 |
| gemini-2.5-flash | 1.191 | [0.851, 1.668] | 0.3078 | 18 |
