# Effort dose-response

## Acceptance gates

| gate | value | passed |
|---|---|:-:|
| effort_gain | 0.15833333333333333 | FAIL |
| no_floor_or_ceiling |  | PASS |
| item_non_determinism | 0.525 | PASS |
| shallow_solvers | 0.0 | PASS |
| cot_predicts_correct | 1292.375 | PASS |
| effort_moves_tokens | {'low': 419.0, 'medium': 5585.0, 'high': 1171.5} | FAIL |

## Per profile x effort

| profile | effort | n | accuracy | action accuracy | median ri_task |
|---|---|--:|--:|--:|--:|
| easy | high | 40 | 0.90 | 0.95 | 193 |
| easy | low | 40 | 0.80 | 0.93 | 96 |
| easy | medium | 40 | 1.00 | 1.00 | 466 |
| hard | high | 40 | 0.72 | 0.82 | 7157 |
| hard | low | 40 | 0.40 | 0.75 | 1610 |
| hard | medium | 40 | 0.68 | 0.68 | 19272 |
| medium | high | 40 | 0.75 | 0.82 | 1425 |
| medium | low | 40 | 0.70 | 0.85 | 511 |
| medium | medium | 40 | 0.95 | 0.95 | 7828 |
