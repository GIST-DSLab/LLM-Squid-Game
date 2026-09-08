# outputs/2026-09-06

11 experiments. Times are UTC, from each run's `experiment_result.json`.

| experiment | runs | seasons | UTC span | model | config | reports |
|---|--:|--:|---|---|---|--:|
| `benchmark_promptflow_smoke_gemma4_omni_l2` | 1 | 1 | 10:39-10:40 | gemma4-cloud | `promptflow_smoke_gemma4_omni_l2.yaml` | 0 |
| `benchmark_survival_drive_omni_gemma4_hard9` | 1 | 220 | 02:31-04:49 | gemma4-31b | `survival_drive_omni_gemma4_hard9_n10.yaml` | 3 |
| `benchmark_survival_drive_omni_qwen35_hard9` | 1 | - | - | qwen3.5-397b | `survival_drive_omni_qwen35_hard9_n10.yaml` | 0 |
| `hearts_zero_probe` | 1 | - | - | gemma4-cloud | `hearts_zero_probe_gemma4.yaml` | 1 |
| `hearts_zero_probe_deploy` | 1 | - | - | gemma4-cloud | `hearts_zero_probe_gemma4_deploy.yaml` | 1 |
| `hearts_zero_probe_notitle` | 1 | - | - | gemma4-cloud | `hearts_zero_probe_gemma4_notitle.yaml` | 1 |
| `hearts_zero_probe_smoke` | 1 | - | - | gemma4-cloud | `hearts_zero_probe_smoke.yaml` | 0 |
| `promptflow_smoke_gemma4_signal_l2` | 1 | 1 | 10:39-10:41 | gemma4-cloud | `promptflow_smoke_gemma4_signal_l2.yaml` | 0 |
| `promptflow_smoke_gptoss20b_signal_l2_elimkeeps` | 1 | 1 | 11:14-11:16 | gpt-oss-20b-cloud | `promptflow_smoke_gptoss20b_signal_l2_elimkeeps.yaml` | 0 |
| `score_policy_smoke_gptoss20b` | 1 | 5 | 11:10-11:14 | gpt-oss-20b-cloud | `score_policy_smoke_gptoss20b.yaml` | 0 |
| `signal_puzzle_v7esc_smoke` | 3 | 2 | 21:25-21:34 | gemma4-cloud | `signal_puzzle_v7esc_smoke.yaml` | 3 |

Each experiment folder holds its run directories untouched, a `config/` copy of the YAML it was launched from, a `reports/` copy of the write-ups specific to it, and a `README.md`. Reports covering several runs stay at their original path and are listed in the READMEs of every run they cite.
