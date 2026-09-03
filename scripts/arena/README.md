# scripts/arena/

Web Arena database operations — run by hand against a live Repository,
often the production Supabase instance, not part of the experiment or
analysis pipelines.

- `seed_web_arena.py` — imports canonical `outputs/final_results/` run data
  into a Repository (SQLite or Postgres via `WEB_ARENA_DSN`).
- `backup_web_arena.py` — the inverse: mirrors sessions/turns/model_stats
  from a live Repository (e.g. production Supabase) back to a local SQLite
  snapshot.
- `purge_human_sessions.py` — deletes human-play sessions from a Repository.

## Seeding the lives / threat-ladder runs (2026-09-03)

`discover_run_dirs()` picks up `outputs/lives_threat_*/*_signal-game`
automatically — there is no `--lives-runs` flag and no `--root` to point at
them. Each session also carries a `settings` snapshot built from the run's
`experiment_config.json` (see `squid_arena.seeding.build_settings_snapshot`),
which is what the Logs trace header's "Run settings" panel renders.

**Production (Supabase).** Run only once `WEB_ARENA_DSN` is in hand (it lives
in the Render dashboard, not in this repo):

```bash
PYTHONPATH=.:game:db:web uv run --no-sync --extra postgres --extra analysis \
  python scripts/arena/seed_web_arena.py --dsn "$WEB_ARENA_DSN"
```

`--extra analysis` matters: without pandas/lifelines,
`_no_cap_avg_session_score` returns `None` and the Model Leaderboard's
`no_cap_avg_session_score` column is overwritten with NULL (renders as "—").

**Local rehearsal** against the gitignored dev SQLite DB — same command, local
DSN. Idempotent: a second run inserts 0 and skips everything.

```bash
cp outputs/web_arena/web_arena.db outputs/web_arena/web_arena.db.bak   # first
PYTHONPATH=.:game:db:web uv run --no-sync \
  python scripts/arena/seed_web_arena.py --dsn outputs/web_arena/web_arena.db
```

⚠️ **Never seed `outputs/benchmark_*`.** Those runs derive from datasets that
must not be republished (GPQA above all). `LIVES_RUN_GLOB` does not match them
and `MODEL_DIRS` does not name them — do not add a `--root` that would.
