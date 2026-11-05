# outputs/2026-09-10

5 experiment folders, 5 run directories. Times are UTC — from each run's `experiment_result.json`
where present, else the min/max `timestamp` across its `*_turns.jsonl` files (marked `turn ts`).

| run folder | run dir | seasons | UTC span | model | config |
|---|---|--:|---|---|---|
| `ransom_r6_winnings_peer_gemma4` | `ransom_r6_winnings_peer_gemma4/20260910_0013_gemma4-cloud_signal-game` | 72 | 00:13-00:31 | gemma4-cloud | `ransom_r6_winnings_peer_gemma4.yaml` |
| `ransom_r6_winnings_gemma4` | `ransom_r6_winnings_gemma4/20260910_0031_gemma4-cloud_signal-game` | 52 (of 72 planned; stopped by the owner at 09:40 KST) | 00:31-00:40 | gemma4-cloud | `ransom_r6_winnings_gemma4.yaml` |
| `ransom_r10_gptoss120b` | `ransom_r10_gptoss120b/20260909_1526_gpt-oss-120b-cloud_signal-game` | 12 | 15:26-15:39 (turn ts) | gpt-oss-120b-cloud | `ransom_r10_gptoss120b.yaml` |
| `ransom_r10_gemma4` | `ransom_r10_gemma4/20260909_1539_gemma4-cloud_signal-game` | 12 | 15:39-15:51 (turn ts) | gemma4-cloud | `ransom_r10_gemma4.yaml` |
| `ransom_r10_glm53flash` | `ransom_r10_glm53flash/20260909_1551_glm-5.3-flash_signal-game` | 3 | 16:09-17:08 (turn ts) | glm-5.3-flash | `ransom_r10_glm53flash.yaml` |

`ransom_r6_winnings_peer_gemma4` and `ransom_r6_winnings_gemma4` are two of the five carrot-variant
gpt-oss-120b/gemma4 runs filed 2026-09-10 (see `outputs/2026-09-09/INDEX.md` for the three
gpt-oss-120b siblings filed under that date); each has its own `README.md` and `config/` copy of
the launching YAML, and is also cited by `docs/reports/2026-09-10-ransom-r6-pilot-eli5.html`.
`ransom_r6_winnings_gemma4` is **incomplete** — stopped mid-run — and has no `results/ransom_r6/`
judge directory; `ransom_r6_winnings_peer_gemma4` is cited by
`results/ransom_r6/main_wp_gemma4/registration.md`.

`ransom_r10_gptoss120b`, `ransom_r10_gemma4` and `ransom_r10_glm53flash` were run earlier the same
day (config `output_dir` already points at this date, so no filing move is needed for them); they
are a separate 10-round ransom design and are not part of this task's filing scope. Their run-dir
timestamps (`20260909_15xx`) predate midnight UTC — they are grouped here because their configs'
`output_dir` already names `outputs/2026-09-10/`, not by the run-directory-timestamp convention
used elsewhere in this file. `ransom_r10_glm53flash` recorded only 3 of 12 seasons (interrupted);
a fourth sibling config, `ransom_r10_forced_gptoss120b.yaml`, has no output on disk yet, and
`ransom_r10_qwen35.yaml.skip` is disabled and unrun. None of the three `ransom_r10_*` runs has a
`README.md` or `config/` copy yet — filing them is out of scope for this pass.
