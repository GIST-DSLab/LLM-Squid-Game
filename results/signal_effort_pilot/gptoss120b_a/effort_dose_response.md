# Effort dose-response

## Acceptance gates

| gate | value | passed |
|---|---|:-:|
| effort_gain | 0.3416666666666666 | PASS |
| no_floor_or_ceiling |  | PASS |
| item_non_determinism | 0.6 | PASS |
| shallow_solvers | 0.0 | PASS |
| cot_predicts_correct | 734.6629370629371 | PASS |
| effort_moves_tokens | {'low': 488.0, 'medium': 1414.5, 'high': 3603.5} | PASS |

## Per profile x effort

| profile | effort | n | accuracy | action accuracy | median ri_task |
|---|---|--:|--:|--:|--:|
| easy | high | 40 | 0.97 | 0.97 | 1314 |
| easy | low | 40 | 0.90 | 0.95 | 178 |
| easy | medium | 40 | 0.95 | 0.95 | 442 |
| hard | high | 40 | 0.47 | 0.47 | 22071 |
| hard | low | 40 | 0.03 | 0.28 | 730 |
| hard | medium | 40 | 0.40 | 0.75 | 7280 |
| medium | high | 40 | 0.75 | 0.75 | 3624 |
| medium | low | 40 | 0.25 | 0.55 | 617 |
| medium | medium | 40 | 0.62 | 0.65 | 1464 |
