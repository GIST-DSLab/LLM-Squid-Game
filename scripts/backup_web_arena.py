"""Mirror the live Web Arena DB (Supabase/Postgres) to a local SQLite file.

Inverse of scripts/seed_web_arena.py: reads sessions/turns/model_stats from a
source Repository and writes them to a destination Repository, both obtained
via interface.persistence.get_repository (so it works Postgres->SQLite,
SQLite->SQLite, etc). Idempotent: sessions already present in the destination
(by id) are skipped; model_stats are upserted. Only durable rows are copied —
this is a backup/analysis snapshot, not a live sync.

Usage::

    # Supabase -> dated local SQLite (default dest)
    uv run --no-sync python scripts/backup_web_arena.py \
        --source-dsn "$WEB_ARENA_DSN"

    # explicit destination
    uv run --no-sync python scripts/backup_web_arena.py \
        --source-dsn "postgresql://..." --dest outputs/web_arena/backup.db
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from interface.persistence import Repository, get_repository  # noqa: E402

logger = logging.getLogger("backup_web_arena")


def mirror_repository(source: Repository, dest: Repository) -> tuple[int, int, int]:
    """Copy all sessions+turns+model_stats from ``source`` into ``dest``.

    Returns ``(sessions_copied, turns_copied, model_stats_copied)``. Skips a
    session (and its turns) whose id already exists in ``dest`` so re-runs are
    safe; ``model_stats`` are upserted every run.
    """
    n_sessions = n_turns = n_stats = 0
    for session in source.list_sessions():
        if dest.get_session(session.id) is not None:
            continue
        dest.create_session(session)  # created_at preserved (non-None)
        turns = source.list_turns(session.id)
        if turns:
            dest.add_turns(turns)
            n_turns += len(turns)
        n_sessions += 1
    for stats in source.list_model_stats():
        dest.upsert_model_stats(stats)
        n_stats += 1
    return n_sessions, n_turns, n_stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dsn", default=None,
        help="Source DB DSN (default: $WEB_ARENA_DSN, else local SQLite fallback).",
    )
    parser.add_argument(
        "--dest", default=None,
        help="Destination SQLite path (default: outputs/web_arena/backup_<UTC-date>.db).",
    )
    args = parser.parse_args(argv)

    dest_path = args.dest
    if dest_path is None:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
        dest_dir = REPO_ROOT / "outputs" / "web_arena"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = str(dest_dir / f"backup_{stamp}.db")

    source = get_repository(args.source_dsn)
    dest = get_repository(dest_path)
    try:
        n_sessions, n_turns, n_stats = mirror_repository(source, dest)
    finally:
        source.close()
        dest.close()

    logger.info(
        "mirrored %d sessions, %d turns, %d model_stats -> %s",
        n_sessions, n_turns, n_stats, dest_path,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    main()
