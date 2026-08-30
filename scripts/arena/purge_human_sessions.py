"""Delete all human plays from the Web Arena DB (sessions + their turns).

Human records are no longer surfaced anywhere (the Logs explorer is LLM-only
and the Play Leaderboard was removed), and new human plays are no longer
persisted (see ``PERSIST_HUMAN_SESSIONS`` in web/squid_arena/api.py). This one-off
cleanup drops the human rows that were written before that change.

Works against whatever backend ``WEB_ARENA_DSN`` selects (local SQLite or
production Postgres) via squid_store.get_repository. The ``turns``
table has no ON DELETE CASCADE, so the repository method removes dependent
turn rows first.

Usage::

    # dry-run against the live DB (reports the count, deletes nothing)
    uv run --no-sync python scripts/purge_human_sessions.py \
        --dsn "$WEB_ARENA_DSN" --dry-run

    # actually delete
    uv run --no-sync python scripts/purge_human_sessions.py --dsn "$WEB_ARENA_DSN"

    # no --dsn -> local SQLite fallback (outputs/web_arena/web_arena.db)
    uv run --no-sync python scripts/purge_human_sessions.py
"""
from __future__ import annotations

import argparse
import logging

from squid_store import get_repository

logger = logging.getLogger("purge_human_sessions")

SOURCE = "human"


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dsn", default=None,
        help="DB DSN (default: $WEB_ARENA_DSN, else local SQLite fallback).",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Report how many human sessions exist without deleting anything.",
    )
    args = parser.parse_args(argv)

    repo = get_repository(args.dsn)
    try:
        existing = repo.list_sessions(source=SOURCE)
        if args.dry_run:
            logger.info("[dry-run] %d human session(s) would be deleted", len(existing))
            return
        deleted = repo.delete_sessions_by_source(SOURCE)
        logger.info("deleted %d human session(s) and their turns", deleted)
    finally:
        repo.close()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    main()
