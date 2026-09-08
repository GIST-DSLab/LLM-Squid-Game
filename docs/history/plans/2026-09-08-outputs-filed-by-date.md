# outputs/ filed by date (2026-09-08)

## What changed

`outputs/` had grown 78 flat experiment directories. Every run directory
carries its date in its own name (`20260907_2315_gemma4-cloud_signal-game`),
and every experiment directory turned out to hold runs from exactly one date,
so the runs were regrouped without splitting any run set:

```
outputs/2026-09-07/hz_2x2_main_gemma4/
    20260907_1353_gemma4-cloud_signal-game/   the run, byte-for-byte as written
    config/hz_2x2_main_gemma4_n10.yaml        copy of the YAML it was launched from
    reports/2026-09-07-hz-2x2-gemma4-report.html
    README.md                                 runs, seasons, UTC span, config, reports
outputs/2026-09-07/INDEX.md                   one table over that day
```

74 experiments across 2026-09-02 … 2026-09-08. 2915 `*_turns.jsonl` before and
after; no run directory's contents were touched.

Not filed by date, and why:

- `final_results/` — the golden-snapshot harness and the paper both resolve
  runs at `outputs/final_results/`.
- `web_arena/` — the live arena's database.
- `_aborted/` — spans several dates by construction.
- `_sdi_logs/`, `_trace/` — driver logs and prompt-trace dumps, not runs.

## Configs

Each experiment folder gets a copy of the YAML it was launched from, matched by
the `name` field recorded in the run's own `experiment_config.json` — not by
directory name, which is not always the config's. Two runs needed the
`output_dir` fallback: the six `hearts_zero_probe*` prompt probes write no
`experiment_config.json`, and `survival_drive_smoke` recorded the name
`survival_drive_smoke8`, which no YAML carries. Both are flagged in the folder's
`README.md`.

262 references to `outputs/<name>` across 130 files were repointed: configs
(`output_dir`), scripts, tests, `results/**` provenance, `CLAUDE.md`,
`docker-compose.runner.yml`. Deliberately **not** repointed: `docs/history/`,
`docs/reports/`, `weekly-report/` and the run artefacts themselves — those are
records of what was true when written, and a path inside them is part of the
record. `.claude/worktrees/` is a separate checkout and was left alone.

A config for a run that has not happened yet keeps a flat `outputs/<name>`,
because its date is not known until it runs. Filing is a post-run step; see
`outputs/README.md`.

## Reports

A report documenting one run moved next to that run. A report covering several
runs stayed where it was and is listed under "Also cited by" in the `README.md`
of every run it cites. Assignment came from which `outputs/<name>` paths a
report's text contains; where several appeared, the filename had to name one of
them unambiguously, with the token-length tiebreak that separates
`hz_2x2_geo2d_*` from `hz_2x2_geo2_*`. 36 reports moved, 10 joint ones stayed.
`docs/reports/traces/` emptied and was removed.

Moving did not edit any report, so paths written inside them still name the
pre-2026-09-08 flat location. That is intended.

## The `.gitignore` hazard this created

`outputs/benchmark_*/`, `outputs/lives_threat_*/` and `outputs/signal_puzzle_*/`
stop matching at `outputs/<date>/<name>/`. Left alone, a benchmark run's GPQA
question text would have become committable — the exact thing those rules
exist to prevent.

Each rule now has an `outputs/*/<name>/**` twin. The twin ignores the
directory's *contents* rather than the directory, so `README.md`, `config/` and
`reports/` can be re-included by negation: what these rules keep out is the raw
per-turn trace, not the write-up. Without those negations the 10 reports that
were tracked at `docs/reports/` and `weekly-report/` and moved into such a
directory would have silently dropped out of the repository.

`.gitattributes` matches `outputs/**/*.jsonl`, so LFS is unaffected by the
extra level; 0 files smudged to empty.

## Tests

Three assertions pinned the flat prefix and now accept an optional
`outputs/<YYYY-MM-DD>/` segment:
`test_geometric_reward.py::TestShippedConfigs::test_output_dir_is_its_own`,
`test_flagship_pull.py::TestTheGeo2dConfigs::test_the_output_dir_is_its_own`,
`test_lives_threat_configs.py::TestRunSizes::test_output_lands_under_the_gitignored_prefix`.

The remaining suite failures are unrelated to this change (missing
`OLLAMA_API_KEY`, a sixth plot script the count guard has not been updated for,
a pandas `StringDtype` change, the pre-existing Web Arena baseline, and
`configs/experiment/phase3_null_risk.yaml`, which has never been committed).
