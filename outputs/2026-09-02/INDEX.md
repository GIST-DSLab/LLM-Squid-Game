# outputs/2026-09-02

3 experiments. Times are UTC, from each run's `experiment_result.json`.

| experiment | runs | seasons | UTC span | model | config | reports |
|---|--:|--:|---|---|---|--:|
| `benchmark_lives_gpqa_smoke` | 1 | 5 | 21:26-21:32 | gpt-oss-120b-cloud | `lives_threat_gpqa_smoke.yaml` | 0 |
| `benchmark_lives_omni_math_smoke` | 1 | 5 | 21:13-21:25 | gpt-oss-120b-cloud | `lives_threat_omni_math_smoke.yaml` | 0 |
| `lives_threat_smoke` | 1 | 5 | 16:14-16:17 | gpt-oss-120b-cloud | `lives_threat_smoke.yaml` | 1 |

Each experiment folder holds its run directories untouched, a `config/` copy of the YAML it was launched from, a `reports/` copy of the write-ups specific to it, and a `README.md` giving what the run tested (the config's own `description`), its cell design, the settings that shape the decision, and what came out per cell. Reports covering several runs stay at their original path and are listed in the READMEs of every run they cite.
