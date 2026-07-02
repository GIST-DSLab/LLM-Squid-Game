"""Seed CLI for the Web Arena DB (WP3).

Thin command-line wrapper around ``interface.seeding`` (the importable seed
core, which ``interface.arena`` also reuses to persist live LLM Arena runs).
The reusable helpers live in ``interface/seeding.py`` — shipped inside the
backend image — because ``scripts/`` is excluded from the Docker build; this
file re-exports them so the seed command and its tests keep importing from
``scripts.seed_web_arena``.

Imports the existing LLM experiment outputs
(``outputs/final_results/<run_dir>/season_results.jsonl`` +
``cognitive_load_mediation.json`` + ``unified_cox_summary.json``) into the
Web Arena persistence layer. Depends ONLY on the WP1 repository interface, so
it works unmodified against both the local SQLite fallback and the Postgres
(Supabase) production backend. Idempotent (skip-existing sessions, upsert
model_stats) — safe to re-run. See ``interface/seeding.py`` for the full
Closed/Open classification + idempotency notes.

Usage::

    uv run python scripts/seed_web_arena.py
    uv run python scripts/seed_web_arena.py --dsn outputs/web_arena/web_arena.db
    uv run python scripts/seed_web_arena.py --root outputs/final_results --dsn /tmp/scratch.db

Spec: ``docs/superpowers/specs/2026-07-02-web-arena-design.md`` §5, §7, §8.
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_ROOT = REPO_ROOT / "outputs" / "final_results"

# `interface` is a plain top-level package (not pip-installed), so running
# this script directly (`uv run python scripts/seed_web_arena.py`, per the
# project convention -- see interface/api.py, interface/app.py) needs the
# repo root on sys.path. Not needed when imported as `scripts.seed_web_arena`
# (e.g. from tests), where pytest's rootdir is already on sys.path.
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from interface.persistence import get_repository  # noqa: E402

# Re-exported from the importable seed core so existing callers and tests can
# keep importing these from ``scripts.seed_web_arena``.
from interface.seeding import (  # noqa: E402,F401
    MODEL_DIRS,
    build_session_record,
    build_turn_records,
    classify_mediation,
    extract_action,
    run_dir_timestamp,
    seed_model_stats,
    seed_sessions,
)

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
