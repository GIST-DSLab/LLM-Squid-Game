# Survival-motive metric probe (P2)

Session-level RidgeCV from the motive indicators onto the ordinal `threat_level`. `delta_ri_*` is the lift over the *same model's* turn-matched level-0 cells, so a model that simply thinks a lot scores 0 there.

Read `mean_ri_*` and its `delta_ri_*` twin **as a pair**: the delta is the mean minus a turn-matched constant, so the two are close to collinear and ridge splits the weight into a large opposing pair. The sum of the pair is the interpretable quantity, not either coefficient alone.

| model | sessions | levels | R² | ρ | MAE | null R² | p |
|---|---:|---:|---:|---:|---:|---:|---:|
| POOLED | 100 | 5 | -0.117 | -0.302 | 1.281 | -0.045 | 0.9303 |
| gpt-oss-120b-cloud | 100 | 5 | -0.117 | -0.302 | 1.281 | -0.045 | 0.9303 |

## Coefficients (standardised, mean over folds)

| model | mean_ri_task | mean_ri_forfeit | delta_ri_task | delta_ri_forfeit | forfeit_time | forfeited | cox_risk_score | accuracy | lives_lost | n_turns |
|---|---|---|---|---|---|---|---|---|---|---|
| POOLED | -0.014 | -0.020 | -0.023 | 0.027 | -0.017 | 0.024 | 0.042 | -0.012 | -0.021 | -0.017 |
| gpt-oss-120b-cloud | -0.014 | -0.020 | -0.023 | 0.027 | -0.017 | 0.024 | 0.042 | -0.012 | -0.021 | -0.017 |

## Forfeit hazard per threat level (Cox, side-table)

| model | HR | 95% CI | p | events |
|---|---:|---|---:|---:|
| POOLED | 1.203 | [0.845, 1.713] | 0.3049 | 16 |
| gpt-oss-120b-cloud | 1.203 | [0.845, 1.713] | 0.3049 | 16 |
