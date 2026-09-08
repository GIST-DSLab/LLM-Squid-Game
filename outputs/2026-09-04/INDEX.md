# outputs/2026-09-04

5 experiments. Times are UTC, from each run's `experiment_result.json`.

| experiment | runs | seasons | UTC span | model | config | reports |
|---|--:|--:|---|---|---|--:|
| `survival_drive_signal_deepseekv4pro` | 1 | - | - | deepseek-v4-pro-0813 | `survival_drive_signal_deepseekv4pro_n5.yaml` | 1 |
| `survival_drive_signal_gemma4` | 1 | - | - | gemma4-31b | `survival_drive_signal_gemma4_n5.yaml` | 1 |
| `survival_drive_signal_glm53` | 2 | - | - | glm-5.3 | `survival_drive_signal_glm53_n10.yaml, survival_drive_signal_glm53_n5.yaml` | 1 |
| `survival_drive_signal_gptoss` | 1 | 50 | 14:42-15:32 | gpt-oss-120b-cloud | `survival_drive_signal_gptoss_n10.yaml` | 0 |
| `survival_drive_smoke` | 1 | 5 | 14:31-14:35 | gpt-oss-120b-cloud | `survival_drive_smoke.yaml` | 1 |

Each experiment folder holds its run directories untouched, a `config/` copy of the YAML it was launched from, a `reports/` copy of the write-ups specific to it, and a `README.md`. Reports covering several runs stay at their original path and are listed in the READMEs of every run they cite.
