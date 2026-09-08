# outputs/2026-09-05

6 experiments. Times are UTC, from each run's `experiment_result.json`.

| experiment | runs | seasons | UTC span | model | config | reports |
|---|--:|--:|---|---|---|--:|
| `benchmark_survival_drive_omni_codex56luna` | 1 | - | - | gpt-5.6-luna | `survival_drive_omni_codex56luna_n10.yaml` | 0 |
| `benchmark_survival_drive_omni_gemma4_hard10` | 1 | 220 | 16:45-20:55 | gemma4-31b | `survival_drive_omni_gemma4_hard10_n10.yaml` | 2 |
| `benchmark_survival_drive_omni_gptoss` | 1 | 50 | 06:29-07:11 | gpt-oss-120b-cloud | `survival_drive_omni_gptoss_n10.yaml` | 2 |
| `benchmark_survival_drive_omni_gptoss_bf` | 1 | 20 | 08:34-08:49 | gpt-oss-120b-cloud | `survival_drive_omni_gptoss_bf_n10.yaml` | 2 |
| `benchmark_survival_drive_omni_gptoss_grid` | 1 | 120 | 14:09-15:34 | gpt-oss-120b-cloud | `survival_drive_omni_gptoss_grid_n10.yaml` | 1 |
| `benchmark_survival_drive_omni_gptoss_threat_na` | 1 | 30 | 11:51-12:17 | gpt-oss-120b-cloud | `survival_drive_omni_gptoss_threat_na_n10.yaml` | 0 |

Each experiment folder holds its run directories untouched, a `config/` copy of the YAML it was launched from, a `reports/` copy of the write-ups specific to it, and a `README.md`. Reports covering several runs stay at their original path and are listed in the READMEs of every run they cite.
