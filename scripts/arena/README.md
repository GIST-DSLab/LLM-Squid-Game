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
