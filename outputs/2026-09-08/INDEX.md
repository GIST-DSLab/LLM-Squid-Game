# outputs/2026-09-08

3 experiments. Times are UTC, from each run's `experiment_result.json`.

| experiment | runs | seasons | UTC span | model | config | reports |
|---|--:|--:|---|---|---|--:|
| `hz_2x2_carrot_benchmark_gptoss120b` | 1 | 40 | 00:42-00:59 | gpt-oss-120b-cloud | `hz_2x2_carrot_benchmark_gptoss120b_n10.yaml` | 0 |
| `hz_2x2_carrot_beneficiary_gemma4` | 1 | 40 | 01:03-01:35 | gemma4-cloud | `hz_2x2_carrot_beneficiary_gemma4_n10.yaml` | 0 |
| `hz_2x2_carrot_beneficiary_gptoss120b` | 1 | 40 | 00:22-00:37 | gpt-oss-120b-cloud | `hz_2x2_carrot_beneficiary_gptoss120b_n10.yaml` | 1 |

Each experiment folder holds its run directories untouched, a `config/` copy of the YAML it was launched from, a `reports/` copy of the write-ups specific to it, and a `README.md`. Reports covering several runs stay at their original path and are listed in the READMEs of every run they cite.
