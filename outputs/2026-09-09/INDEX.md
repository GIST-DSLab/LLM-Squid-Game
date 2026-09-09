# outputs/2026-09-09

17 experiment folders, 24 run directories. Times are UTC — from each run's `experiment_result.json` where present, else the min/max `timestamp` across its `*_turns.jsonl` files (marked `turn ts`).

| run folder | run dir | seasons | UTC span | model | config |
|---|---|--:|---|---|---|
| `ransom_r6_pilot_gptoss120b` | `ransom_r6_pilot_gptoss120b/20260909_1841_gpt-oss-120b-cloud_signal-game` | 24 | 18:41-18:48 | gpt-oss-120b-cloud | `ransom_r6_pilot_gptoss120b.yaml` |
| `ransom_r6_pilot_gemma4` | `ransom_r6_pilot_gemma4/20260909_1848_gemma4-cloud_signal-game` | 24 | 18:48-18:57 | gemma4-cloud | `ransom_r6_pilot_gemma4.yaml` |
| `ransom_r6_pilot_glm53flash` | `ransom_r6_pilot_glm53flash/20260909_1857_glm-5.3-flash_signal-game` | 24 | 18:57-19:34 | glm-5.3-flash | `ransom_r6_pilot_glm53flash.yaml` |
| `ransom_r6_gptoss120b` | `ransom_r6_gptoss120b/20260909_1934_gpt-oss-120b-cloud_signal-game` | 72 | 19:34-19:52 | gpt-oss-120b-cloud | `ransom_r6_gptoss120b.yaml` |
| `ransom_r6_gemma4` | `ransom_r6_gemma4/20260909_1952_gemma4-cloud_signal-game` | 72 | 19:52-20:09 | gemma4-cloud | `ransom_r6_gemma4.yaml` |
| `ransom_r6_glm53flash` | `ransom_r6_glm53flash/20260909_2009_glm-5.3-flash_signal-game` | 72 | 20:09-22:01 | glm-5.3-flash | `ransom_r6_glm53flash.yaml` |
| `_ransom_haiku_n10_shortladder` | `_ransom_haiku_n10_shortladder/20260909_1108_haiku_signal-game` | 28 | 11:08-14:14 (turn ts) | haiku | `ransom_haiku_n10.yaml` |
| `ransom_smoke` | `ransom_smoke/20260909_1056_haiku_signal-game` | 12 | 10:56-11:10 | haiku | `ransom_smoke.yaml` |
| `ransom_smoke_gemma4` | `ransom_smoke_gemma4/20260909_1405_gemma4-cloud_signal-game` | 12 | 14:05-14:08 | gemma4-cloud | `ransom_smoke_gemma4.yaml` |
| `ransom_smoke_gemma4` | `ransom_smoke_gemma4/20260909_1413_gemma4-cloud_signal-game` | 12 | 14:13-14:16 | gemma4-cloud | `ransom_smoke_gemma4.yaml` |
| `ransom_smoke_glm53flash` | `ransom_smoke_glm53flash/20260909_1426_glm-5.3-flash_signal-game` | 12 | 14:26-14:33 | glm-5.3-flash | `ransom_smoke_glm53flash.yaml` |
| `ransom_smoke_gptoss120b` | `ransom_smoke_gptoss120b/20260909_1333_gpt-oss-120b-cloud_signal-game` | 12 | 13:33-13:38 | gpt-oss-120b-cloud | `ransom_smoke_gptoss120b.yaml` |
| `ransom_smoke_gptoss20b` | `ransom_smoke_gptoss20b/20260909_1308_gpt-oss-20b-cloud_signal-game` | 12 | 13:08-13:11 | gpt-oss-20b-cloud | `— (not on disk)` |
| `ransom_smoke_qwen35` | `ransom_smoke_qwen35/20260909_1416_qwen3.5-cloud_signal-game` | 12 | 14:16-14:26 | qwen3.5-cloud | `ransom_smoke_qwen35.yaml` |
| `ransom_smoke10_gptoss120b` | `ransom_smoke10_gptoss120b/20260909_1347_gpt-oss-120b-cloud_signal-game` | 0 | 13:47-13:47 (turn ts) | gpt-oss-120b-cloud | `ransom_smoke10_gptoss120b.yaml` |
| `score_equiv_probe_haiku` | `score_equiv_probe_haiku/lives1/20260908_1907_haiku_signal-game` | 18 | 19:07-19:17 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku` | `score_equiv_probe_haiku/lives2/20260908_1712_haiku_signal-game` | 18 | 17:12-17:23 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku` | `score_equiv_probe_haiku/lives3/20260908_1659_haiku_signal-game` | 18 | 16:59-17:12 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku_v2` | `score_equiv_probe_haiku_v2/lives1/20260908_2328_haiku_signal-game` | 3 | 23:29-23:30 (turn ts) | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku_v2` | `score_equiv_probe_haiku_v2/lives2/20260908_2058_haiku_signal-game` | 21 | 20:58-21:13 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku_v2` | `score_equiv_probe_haiku_v2/lives3/20260908_1911_haiku_signal-game` | 21 | 19:11-19:26 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku_v3` | `score_equiv_probe_haiku_v3/lives1/20260909_0034_haiku_signal-game` | 21 | 00:34-00:37 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku_v3` | `score_equiv_probe_haiku_v3/lives2/20260908_2358_haiku_signal-game` | 21 | 23:58-00:02 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |
| `score_equiv_probe_haiku_v3` | `score_equiv_probe_haiku_v3/lives3/20260908_2332_haiku_signal-game` | 21 | 23:32-23:35 | haiku | `— (deleted, score_equiv_*.yaml removed 2026-09-09)` |

Six of these (`ransom_r6_pilot_*`, `ransom_r6_*`) are the r6-pilot / r6-main release-gate runs filed 2026-09-10; each has its own `README.md`, `config/` copy of the launching YAML, and is also cited by `docs/reports/2026-09-10-ransom-r6-pilot-eli5.html` and `results/ransom_r6/<pilot_|main_><model>/registration.md`. `ransom_smoke10_gptoss120b` recorded turns but no `season_results.jsonl` (aborted before any season completed). `score_equiv_probe_haiku*` are frozen-state probes (per-`lives` run dirs, not a single 12-cell design); their configs no longer exist on disk (`score_equiv_*.yaml` was deleted 2026-09-09, see CLAUDE.md "등가 점수 지표").
