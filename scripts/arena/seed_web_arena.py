"""Seed CLI for the Web Arena DB (WP3).

Thin command-line wrapper around ``squid_arena.seeding`` (the importable seed
core, which ``squid_arena.arena`` also reuses to persist live LLM Arena runs).
The reusable helpers live in ``web/squid_arena/seeding.py`` — shipped inside the
backend image — because ``scripts/`` is excluded from the Docker build; this
file re-exports them so the seed command and its tests keep importing from
``scripts.arena.seed_web_arena``.

Imports the existing LLM experiment outputs
(``outputs/final_results/<run_dir>/season_results.jsonl`` +
``cognitive_load_mediation.json`` + ``unified_cox_summary.json``) into the
Web Arena persistence layer. Depends ONLY on the WP1 repository interface, so
it works unmodified against both the local SQLite fallback and the Postgres
(Supabase) production backend. Idempotent (skip-existing sessions, upsert
model_stats) — safe to re-run. See ``web/squid_arena/seeding.py`` for the full
Closed/Open classification + idempotency notes.

Usage::

    uv run python scripts/arena/seed_web_arena.py
    uv run python scripts/arena/seed_web_arena.py --dsn outputs/web_arena/web_arena.db
    uv run python scripts/arena/seed_web_arena.py --root outputs/final_results --dsn /tmp/scratch.db

Spec: ``docs/superpowers/specs/2026-07-02-web-arena-design.md`` §5, §7, §8.
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from squid_store import get_repository

# Re-exported from the importable seed core so existing callers and tests can
# keep importing these from ``scripts.arena.seed_web_arena``.
from squid_arena.seeding import (  # noqa: F401
    MODEL_DIRS,
    build_session_record,
    build_turn_records,
    classify_mediation,
    extract_action,
    run_dir_timestamp,
    seed_model_stats,
    seed_sessions,
)

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO_ROOT / "outputs" / "final_results"

logger = logging.getLogger("seed_web_arena")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn",
        default=None,
        help="Target DB DSN/path (default: $WEB_ARENA_DSN, else outputs/web_arena/web_arena.db)",
    )
    parser.add_argument(
        "--root",
        default=None,
        help="outputs/final_results dir to import from (default: <repo_root>/outputs/final_results)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else DEFAULT_ROOT

    repo = get_repository(args.dsn)
    try:
        n_sessions, n_skipped, n_turns = seed_sessions(repo, root, MODEL_DIRS)
        n_models = seed_model_stats(repo, root, MODEL_DIRS.keys())
    finally:
        repo.close()

    logger.info(
        "seeded %d sessions (%d already present, skipped), %d turns, %d model_stats rows",
        n_sessions,
        n_skipped,
        n_turns,
        n_models,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    main()
