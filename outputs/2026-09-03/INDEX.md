# outputs/2026-09-03

18 experiments. Times are UTC, from each run's `experiment_result.json`.

| experiment | runs | seasons | UTC span | model | config | reports |
|---|--:|--:|---|---|---|--:|
| `benchmark_threat3_gpqa_codex56luna` | 1 | 9 | 22:32-00:20 | gpt-5.6-luna | `bench_threat3_gpqa_codex56luna_n3.yaml` | 0 |
| `benchmark_threat3_gpqa_gemini25flash` | 1 | 9 | 14:59-15:13 | gemini-2.5-flash | `bench_threat3_gpqa_gemini25flash_n3.yaml` | 0 |
| `benchmark_threat3_gpqa_glm53flash` | 1 | 9 | 20:50-00:30 | glm-5.3-flash | `bench_threat3_gpqa_glm53flash_n3.yaml` | 0 |
| `benchmark_threat3_gpqa_gptoss` | 1 | 9 | 15:13-15:46 | gpt-oss-120b-cloud | `bench_threat3_gpqa_gptoss_n3.yaml` | 0 |
| `benchmark_threat3_omni_math_codex56luna` | 1 | 9 | 21:58-22:32 | gpt-5.6-luna | `bench_threat3_omni_math_codex56luna_n3.yaml` | 0 |
| `benchmark_threat3_omni_math_gemini25flash` | 1 | 9 | 14:39-14:59 | gemini-2.5-flash | `bench_threat3_omni_math_gemini25flash_n3.yaml` | 0 |
| `benchmark_threat3_omni_math_glm53flash` | 1 | 9 | 16:49-20:50 | glm-5.3-flash | `bench_threat3_omni_math_glm53flash_n3.yaml` | 0 |
| `benchmark_threat3_omni_math_gptoss` | 1 | 9 | 14:39-15:13 | gpt-oss-120b-cloud | `bench_threat3_omni_math_gptoss_n3.yaml` | 0 |
| `lives_threat_5x2_gemini25flash` | 1 | - | - | gemini-2.5-flash | `lives_threat_5x2_gemini25flash_n3.yaml` | 0 |
| `lives_threat_5x2_glm53flash` | 1 | 30 | 05:03-07:38 | glm-5.3-flash | `lives_threat_5x2_glm53flash_n10.yaml` | 0 |
| `lives_threat_5x2_gptoss` | 1 | 100 | 11:09-11:38 | gpt-oss-120b-cloud | `lives_threat_5x2_gptoss_n10.yaml` | 0 |
| `lives_threat_5x2_pd1_codex56luna` | 1 | 100 | 15:22-16:31 | gpt-5.6-luna | `lives_threat_5x2_pd1_codex56luna_n10.yaml` | 0 |
| `lives_threat_5x2_pd1_gemini25flash` | 1 | 100 | 16:48-19:21 | gemini-2.5-flash | `lives_threat_5x2_pd1_gemini25flash_n10.yaml` | 0 |
| `lives_threat_5x2_pd1_glm53flash` | 1 | 100 | 19:21-01:32 | glm-5.3-flash | `lives_threat_5x2_pd1_glm53flash_n10.yaml` | 0 |
| `lives_threat_5x2_pd1_gptoss` | 1 | 100 | 13:02-13:38 | gpt-oss-120b-cloud | `lives_threat_5x2_pd1_gptoss_n10.yaml` | 0 |
| `lives_threat_5x2_pd1_opus5cc` | 1 | 30 | 12:30-12:57 | claude-opus-5 | `lives_threat_5x2_pd1_opus5cc_n10.yaml` | 0 |
| `lives_threat_5x2_pd1_opus5cchigh` | 1 | - | - | claude-opus-5 | `lives_threat_5x2_pd1_opus5cchigh_n3.yaml` | 0 |
| `lives_threat_docker_smoke` | 1 | 5 | 00:22-00:25 | gpt-oss-120b-cloud | `lives_threat_docker_smoke.yaml` | 0 |

Each experiment folder holds its run directories untouched, a `config/` copy of the YAML it was launched from, a `reports/` copy of the write-ups specific to it, and a `README.md` giving what the run tested (the config's own `description`), its cell design, the settings that shape the decision, and what came out per cell. Reports covering several runs stay at their original path and are listed in the READMEs of every run they cite.
