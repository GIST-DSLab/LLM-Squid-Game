# outputs/2026-09-07

28 experiments. Times are UTC, from each run's `experiment_result.json`.

| experiment | runs | seasons | UTC span | model | config | reports |
|---|--:|--:|---|---|---|--:|
| `hearts_zero_probe_v7` | 1 | - | - | gemma4-cloud | `hearts_zero_probe_gemma4_v7.yaml` | 0 |
| `hearts_zero_probe_v7esc` | 1 | - | - | gemma4-cloud | `hearts_zero_probe_gemma4_v7esc.yaml` | 0 |
| `hearts_zero_v7_smoke` | 2 | - | - | gpt-oss-120b-cloud | `hearts_zero_v7_smoke.yaml` | 1 |
| `hz0000_rea_1season_gptoss120b` | 3 | 3 | 10:39-11:43 | gpt-oss-120b-cloud | `hz0000_rea_1season_gptoss120b.yaml` | 0 |
| `hz0000rea_lives1of3_gemma4` | 1 | 5 | 13:17-13:17 | gemma4-cloud | `hz0000rea_lives1of3_gemma4.yaml` | 0 |
| `hz0000rea_lives2of3_gemma4` | 1 | - | - | gemma4-cloud | `hz0000rea_lives2of3_gemma4.yaml` | 0 |
| `hz_2x2_echo_1turn_gptoss120b` | 1 | 8 | 12:15-12:15 | gpt-oss-120b-cloud | `hz_2x2_echo_1turn_gptoss120b.yaml` | 0 |
| `hz_2x2_gemma4_cot` | 1 | 4 | 10:27-10:38 | gemma4-cloud | `hz_2x2_gemma4_cot.yaml` | 1 |
| `hz_2x2_geo2_gemma4` | 1 | 40 | 19:19-19:43 | gemma4-cloud | `hz_2x2_geo2_gemma4_n10.yaml` | 1 |
| `hz_2x2_geo2_gptoss120b` | 1 | 40 | 19:58-20:10 | gpt-oss-120b-cloud | `hz_2x2_geo2_gptoss120b_n10.yaml` | 1 |
| `hz_2x2_geo2_qwen35` | 1 | 40 | 23:48-00:26 | qwen3.5-cloud | `hz_2x2_geo2_qwen35_n10.yaml` | 0 |
| `hz_2x2_geo2_smoke_gemma4` | 1 | 4 | 17:20-17:29 | gemma4-cloud | `hz_2x2_geo2_smoke_gemma4.yaml` | 0 |
| `hz_2x2_geo2c_gemma4` | 1 | 40 | 22:40-23:01 | gemma4-cloud | `hz_2x2_geo2c_gemma4_n10.yaml` | 1 |
| `hz_2x2_geo2c_gptoss120b` | 1 | 40 | 22:23-22:35 | gpt-oss-120b-cloud | `hz_2x2_geo2c_gptoss120b_n10.yaml` | 1 |
| `hz_2x2_geo2d_gemma4` | 1 | 40 | 23:15-23:39 | gemma4-cloud | `hz_2x2_geo2d_gemma4_n10.yaml` | 2 |
| `hz_2x2_geo2d_gptoss120b` | 1 | 40 | 23:00-23:12 | gpt-oss-120b-cloud | `hz_2x2_geo2d_gptoss120b_n10.yaml` | 1 |
| `hz_2x2_gptoss120b_audit` | 1 | 4 | 11:57-11:58 | gpt-oss-120b-cloud | `hz_2x2_gptoss120b_audit.yaml` | 0 |
| `hz_2x2_main_gemma4` | 1 | 40 | 13:53-14:26 | gemma4-cloud | `hz_2x2_main_gemma4_n10.yaml` | 1 |
| `hz_2x2_main_gptoss120b` | 1 | 40 | 14:35-14:52 | gpt-oss-120b-cloud | `hz_2x2_main_gptoss120b_n10.yaml` | 1 |
| `hz_2x2_main_qwen35` | 1 | 40 | 17:19-17:51 | qwen3.5-cloud | `hz_2x2_main_qwen35_n10.yaml` | 1 |
| `hz_2x2_smoke_lives1_gemma4` | 1 | 4 | 12:44-12:44 | gemma4-cloud | `hz_2x2_smoke_lives1_gemma4.yaml` | 0 |
| `hz_2x2_smoke_lives2_gemma4` | 1 | 4 | 12:40-12:40 | gemma4-cloud | `hz_2x2_smoke_lives2_gemma4.yaml` | 0 |
| `hz_2x2_smoke_lives3_gemma4` | 1 | 4 | 12:39-12:39 | gemma4-cloud | `hz_2x2_smoke_lives3_gemma4.yaml` | 0 |
| `signal_2x2_gemma4` | 1 | 40 | 09:21-09:44 | gemma4-cloud | `signal_2x2_gemma4_n10.yaml` | 0 |
| `signal_2x2_gptoss20b` | 1 | - | - | gpt-oss-20b-cloud | `signal_2x2_gptoss20b_n10.yaml` | 0 |
| `signal_puzzle_hz1111_1turn` | 3 | 3 | 00:25-06:30 | gpt-oss-20b-cloud | `hz1111_v7esc_1turn_gptoss20b.yaml` | 1 |
| `signal_puzzle_hz1111_1turn_gemma4` | 1 | 1 | 05:32-05:32 | gemma4-cloud | `hz1111_v7esc_1turn_gemma4.yaml` | 1 |
| `signal_puzzle_hz1111_1turn_qwen35` | 1 | 1 | 06:31-06:32 | qwen3.5-cloud | `hz1111_v7esc_1turn_qwen35.yaml` | 0 |

Each experiment folder holds its run directories untouched, a `config/` copy of the YAML it was launched from, a `reports/` copy of the write-ups specific to it, and a `README.md` giving what the run tested (the config's own `description`), its cell design, the settings that shape the decision, and what came out per cell. Reports covering several runs stay at their original path and are listed in the READMEs of every run they cite.
