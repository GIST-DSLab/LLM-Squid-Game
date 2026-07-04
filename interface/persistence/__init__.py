"""Web Arena persistence layer.

Driver-agnostic repository interface (:class:`Repository`) with a SQLite
backend (local dev / tests, stdlib-only) and a Postgres backend
(production, requires the optional ``psycopg`` dependency). WP2 (API) and
WP3 (seed script) should import only from this package, never from
``sqlite_repository`` / ``postgres_repository`` directly.

Usage::

    from interface.persistence import get_repository, SessionRecord

    repo = get_repository()  # reads WEB_ARENA_DSN, falls back to SQLite
    repo.create_session(SessionRecord(...))
"""

from interface.persistence.base import Repository
from interface.persistence.factory import get_repository
from interface.persistence.models import (
    ModelStatsRecord,
    PlayerRecord,
    SessionRecord,
    TurnRecord,
)

__all__ = [
    "Repository",
    "SessionRecord",
    "TurnRecord",
    "ModelStatsRecord",
    "PlayerRecord",
    "get_repository",
]
