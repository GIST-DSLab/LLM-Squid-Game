"""Backend-selection factory for the Web Arena ``Repository``.

Selection rule (see design guidance in the WP1 brief): if the DSN starts
with ``postgres://`` or ``postgresql://``, use the Postgres backend;
otherwise treat it as a SQLite file path (or ``:memory:``) and fall back to
the SQLite backend. The DSN is read from the ``WEB_ARENA_DSN`` environment
variable unless passed explicitly.
"""

from __future__ import annotations

import os

from interface.persistence.base import Repository

DEFAULT_SQLITE_PATH = "outputs/web_arena/web_arena.db"


def get_repository(dsn: str | None = None) -> Repository:
    """Return the ``Repository`` backend selected by ``dsn`` (or
    ``WEB_ARENA_DSN`` if ``dsn`` is not given)."""
    if dsn is None:
        dsn = os.environ.get("WEB_ARENA_DSN")

    if dsn and dsn.startswith(("postgres://", "postgresql://")):
        from interface.persistence.postgres_repository import PostgresRepository

        return PostgresRepository(dsn)

    from interface.persistence.sqlite_repository import SQLiteRepository

    return SQLiteRepository(dsn or DEFAULT_SQLITE_PATH)
