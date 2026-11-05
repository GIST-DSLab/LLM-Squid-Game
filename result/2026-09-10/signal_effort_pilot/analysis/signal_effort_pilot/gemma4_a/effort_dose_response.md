# Effort dose-response

## Acceptance gates

| gate | value | passed |
|---|---|:-:|
| effort_gain | -0.05833333333333335 | FAIL |
| no_floor_or_ceiling |  | PASS |
| item_non_determinism | 0.175 | FAIL |
| shallow_solvers | 0.0 | PASS |
| cot_predicts_correct | 19.643790849673206 | PASS |
| effort_moves_tokens | {'low': 2899.0, 'medium': 3196.5, 'high': 3080.5} | FAIL |

## Per profile x effort

| profile | effort | n | accuracy | action accuracy | median ri_task |
|---|---|--:|--:|--:|--:|
| easy | high | 40 | 1.00 | 1.00 | 942 |
| easy | low | 40 | 1.00 | 1.00 | 1088 |
| easy | medium | 40 | 1.00 | 1.00 | 1034 |
| hard | high | 40 | 0.47 | 0.55 | 5078 |
| hard | low | 40 | 0.53 | 0.62 | 4348 |
| hard | medium | 40 | 0.55 | 0.65 | 4782 |
| medium | high | 40 | 0.78 | 0.82 | 3253 |
| medium | low | 40 | 0.90 | 0.93 | 3020 |
| medium | medium | 40 | 0.88 | 0.93 | 3208 |
