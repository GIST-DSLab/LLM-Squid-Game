"""Abstract repository interface for the Web Arena persistence layer.

WP2 (backend API) and WP3 (seed script) must depend only on this interface,
never on a concrete DB driver. Two backends implement it:
``SQLiteRepository`` (stdlib ``sqlite3``, local dev / tests) and
``PostgresRepository`` (``psycopg`` v3, production — Supabase free tier).

Spec: ``docs/superpowers/specs/2026-07-02-web-arena-design.md`` §6, §7, §8.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from interface.persistence.models import ModelStatsRecord, SessionRecord, TurnRecord


class Repository(ABC):
    """CRUD + the read queries WP2/WP3 need, nothing more (YAGNI: no
    pagination, no auth, no migration framework)."""

    @abstractmethod
    def init_schema(self) -> None:
        """Create tables if they do not already exist. Idempotent."""

    # -- sessions ---------------------------------------------------------

    @abstractmethod
    def create_session(self, session: SessionRecord) -> str:
        """Insert a session row. Returns the (possibly generated) id.

        ``created_at`` is assigned server-side by DEFAULT (when
        ``session.created_at`` is ``None``). A caller may override it by
        passing a non-``None`` value, which is stored verbatim — used by the
        seed script to preserve original historical run timestamps.
        """

    @abstractmethod
    def get_session(self, session_id: str) -> SessionRecord | None:
        """Fetch one session by id, or ``None`` if it does not exist."""

    @abstractmethod
    def list_sessions(
        self,
        *,
        source: str | None = None,
        task: str | None = None,
        framing: str | None = None,
        order_by_score: bool = False,
    ) -> list[SessionRecord]:
        """List sessions, optionally filtered by source/task/framing.

        ``order_by_score=True`` sorts by ``final_score`` descending (Play
        Leaderboard); otherwise sorts by ``created_at`` descending (Logs).
        """

    # -- turns --------------------------------------------------------------

    @abstractmethod
    def add_turns(self, turns: list[TurnRecord]) -> None:
        """Bulk-insert turn rows (each carries its own ``session_id``)."""

    @abstractmethod
    def list_turns(self, session_id: str) -> list[TurnRecord]:
        """List turns for one session, ordered by ``turn_no`` ascending."""

    # -- model_stats --------------------------------------------------------

    @abstractmethod
    def upsert_model_stats(self, stats: ModelStatsRecord) -> None:
        """Insert or overwrite the row for ``stats.model_label``."""

    @abstractmethod
    def list_model_stats(self) -> list[ModelStatsRecord]:
        """List all model_stats rows (Model Leaderboard)."""

    # -- lifecycle ------------------------------------------------------------

    @abstractmethod
    def close(self) -> None:
        """Release the underlying connection."""

    def __enter__(self) -> "Repository":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()
