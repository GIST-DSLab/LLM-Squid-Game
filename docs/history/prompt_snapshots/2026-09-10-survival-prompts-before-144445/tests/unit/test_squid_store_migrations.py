"""Unit tests for the ``turns`` thinking-cost column rename migration.

A Web Arena database created against the abandoned "KDD-UC vocabulary" branch
(commit ``d204bd8``) spells the three per-call thinking-cost columns
``task_thinking`` / ``probe_thinking`` / ``forfeit_thinking``. Every current
reader and writer uses ``ri_task`` / ``ri_probe`` / ``ri_forfeit``, so the
first insert against such a DB fails with ``table turns has no column named
ri_task``. ``init_schema()`` must rename them in place.

SQLite is exercised for real against a file created with the old DDL (copied
literally from ``outputs/web_arena/web_arena.db.pre-settings.bak``). Postgres
has no live server here, so its migration is checked at the SQL-string level,
the same way ``test_squid_store_lives.py`` does.
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from squid_store import postgres_repository as pg
from squid_store.sqlite_repository import (
    _TURNS_THINKING_RENAMES,
    SQLiteRepository,
)

# The ``sessions``/``turns`` DDL exactly as an old dev DB carries it: the
# pre-rename column names, and none of the later lives / settings columns.
_OLD_SCHEMA = """
CREATE TABLE sessions (
    id TEXT PRIMARY KEY,
    nickname TEXT NOT NULL,
    task TEXT NOT NULL,
    framing TEXT NOT NULL,
    forfeit TEXT NOT NULL,
    seed INTEGER NOT NULL,
    final_score REAL NOT NULL,
    forfeited INTEGER NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL
, campaign_id TEXT, difficulty TEXT NOT NULL DEFAULT 'easy');

CREATE TABLE turns (
    session_id TEXT NOT NULL,
    turn_no INTEGER NOT NULL,
    observation TEXT NOT NULL,
    action TEXT NOT NULL,
    task_thinking REAL,
    probe_thinking REAL,
    forfeit_thinking REAL,
    choice TEXT,
    score REAL NOT NULL,
    thinking_task TEXT,
    thinking_probe TEXT,
    thinking_forfeit TEXT,
    raw_response TEXT,
    correct INTEGER, psuccess_self INTEGER,
    PRIMARY KEY (session_id, turn_no)
);
"""

_OLD_NAMES = [old for old, _ in _TURNS_THINKING_RENAMES]
_NEW_NAMES = [new for _, new in _TURNS_THINKING_RENAMES]


def _table_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def _make_old_db(db_path: Path) -> None:
    conn = sqlite3.connect(db_path)
    conn.executescript(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO sessions (id, nickname, task, framing, forfeit, seed, "
        "final_score, forfeited, source, created_at, campaign_id, difficulty) "
        "VALUES ('old-1', 'nick', 'signal_game', 'flagship_corruption', "
        "'allowed', 7, 40.0, 0, 'llm', '2026-04-22T02:18:00+00:00', NULL, 'easy')"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_no, observation, action, "
        "task_thinking, probe_thinking, forfeit_thinking, choice, score, "
        "thinking_task, thinking_probe, thinking_forfeit, raw_response, "
        "correct, psuccess_self) "
        "VALUES ('old-1', 1, 'obs', 'jump', 111.0, 22.0, 333.0, 'CONTINUE', "
        "40.0, '<think>t</think>', '<think>p</think>', '<think>f</think>', "
        "'raw', 1, 33)"
    )
    conn.commit()
    conn.close()


# ---------------------------------------------------------------------------
# SQLite — real migration
# ---------------------------------------------------------------------------


def test_sqlite_renames_the_old_thinking_columns(tmp_path: Path) -> None:
    db_path = tmp_path / "old-vocab.db"
    _make_old_db(db_path)

    # Pre-condition: the old DB really carries the old names and not the new.
    cols = _table_columns(db_path, "turns")
    assert set(_OLD_NAMES) <= cols
    assert not set(_NEW_NAMES) & cols

    repo = SQLiteRepository(str(db_path))  # __init__ calls init_schema
    try:
        cols = _table_columns(db_path, "turns")
        assert set(_NEW_NAMES) <= cols
        assert not set(_OLD_NAMES) & cols
    finally:
        repo.close()


def test_sqlite_rename_preserves_the_stored_values(tmp_path: Path) -> None:
    db_path = tmp_path / "old-vocab-values.db"
    _make_old_db(db_path)

    repo = SQLiteRepository(str(db_path))
    try:
        (turn,) = repo.list_turns("old-1")
        assert (turn.ri_task, turn.ri_probe, turn.ri_forfeit) == (111.0, 22.0, 333.0)
        assert turn.thinking_task == "<think>t</think>"
        assert turn.thinking_forfeit == "<think>f</think>"
        assert turn.choice == "CONTINUE"
        assert turn.psuccess_self == 33
        assert turn.correct is True
    finally:
        repo.close()


def test_sqlite_migrated_db_accepts_a_new_insert(tmp_path: Path) -> None:
    """The bug this migration fixes: the first insert used to raise
    ``table turns has no column named ri_task``."""
    from squid_store import TurnRecord

    db_path = tmp_path / "old-vocab-insert.db"
    _make_old_db(db_path)

    repo = SQLiteRepository(str(db_path))
    try:
        repo.add_turns(
            [
                TurnRecord(
                    session_id="old-1",
                    turn_no=2,
                    observation="obs2",
                    action="stay",
                    ri_task=5.0,
                    ri_probe=6.0,
                    ri_forfeit=7.0,
                    score=50.0,
                )
            ]
        )
        turns = {t.turn_no: t for t in repo.list_turns("old-1")}
        assert turns[2].ri_task == 5.0
        assert turns[1].ri_task == 111.0
    finally:
        repo.close()


def test_sqlite_rename_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "old-vocab-idempotent.db"
    _make_old_db(db_path)

    repo = SQLiteRepository(str(db_path))
    try:
        repo.init_schema()
        repo.init_schema()
        cols = _table_columns(db_path, "turns")
        assert set(_NEW_NAMES) <= cols
        assert not set(_OLD_NAMES) & cols
    finally:
        repo.close()


def test_sqlite_fresh_db_is_untouched_by_the_rename(tmp_path: Path) -> None:
    db_path = tmp_path / "fresh.db"
    repo = SQLiteRepository(str(db_path))
    try:
        cols = _table_columns(db_path, "turns")
        assert set(_NEW_NAMES) <= cols
        assert not set(_OLD_NAMES) & cols
    finally:
        repo.close()


def test_sqlite_leaves_schema_alone_when_both_names_exist(
    tmp_path: Path, caplog
) -> None:
    """Someone added the new column alongside the old: no rename, one warning
    per colliding pair, and both columns keep their values."""
    db_path = tmp_path / "both.db"
    _make_old_db(db_path)
    conn = sqlite3.connect(db_path)
    for _, new in _TURNS_THINKING_RENAMES:
        conn.execute(f"ALTER TABLE turns ADD COLUMN {new} REAL")
    conn.execute("UPDATE turns SET ri_task = 999.0 WHERE turn_no = 1")
    conn.commit()
    conn.close()

    with caplog.at_level(logging.WARNING, logger="squid_store.sqlite_repository"):
        repo = SQLiteRepository(str(db_path))
    try:
        cols = _table_columns(db_path, "turns")
        assert set(_OLD_NAMES) <= cols  # old columns survive untouched
        assert set(_NEW_NAMES) <= cols

        warnings = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
        assert len(warnings) == len(_TURNS_THINKING_RENAMES)
        for old, new in _TURNS_THINKING_RENAMES:
            assert any(old in m and new in m for m in warnings), (old, new)

        # The pre-existing new-column value is not clobbered by a rename.
        (turn,) = repo.list_turns("old-1")
        assert turn.ri_task == 999.0
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# Postgres — SQL-string level (no live server)
# ---------------------------------------------------------------------------


class _RecordingCursor:
    def __init__(self, sink: list[str]) -> None:
        self._sink = sink

    def __enter__(self) -> "_RecordingCursor":
        return self

    def __exit__(self, *exc: object) -> bool:
        return False

    def execute(self, sql: str, params: object = None) -> None:
        self._sink.append(sql)


class _RecordingConn:
    def __init__(self) -> None:
        self.statements: list[str] = []

    def cursor(self) -> _RecordingCursor:
        return _RecordingCursor(self.statements)


class _StubPostgresRepository:
    """Just enough of the repo for the unbound ``init_schema`` to run."""

    def __init__(self) -> None:
        self._conn = _RecordingConn()


def test_postgres_rename_pairs_match_sqlite() -> None:
    assert pg._TURNS_THINKING_RENAMES == _TURNS_THINKING_RENAMES


def test_postgres_init_schema_issues_a_guarded_rename_per_pair() -> None:
    stub = _StubPostgresRepository()
    pg.PostgresRepository.init_schema(stub)
    sql = "\n".join(stub._conn.statements)

    for old, new in _TURNS_THINKING_RENAMES:
        assert f"ALTER TABLE turns RENAME COLUMN {old} TO {new};" in sql, (old, new)
        # Guarded both ways: rename only when old exists and new does not.
        assert f"column_name = '{old}'" in sql, old
        assert f"column_name = '{new}'" in sql, new
        # Both-present case warns instead of touching the schema.
        assert f"RAISE WARNING 'squid_store: turns has both {old} and {new}" in sql


def test_postgres_rename_runs_before_the_additive_alters() -> None:
    """The ADD COLUMN guards below assume the current column names."""
    stub = _StubPostgresRepository()
    pg.PostgresRepository.init_schema(stub)
    statements = stub._conn.statements

    last_rename = max(
        i for i, s in enumerate(statements) if "RENAME COLUMN" in s
    )
    first_add = min(
        i for i, s in enumerate(statements) if "ADD COLUMN IF NOT EXISTS" in s
    )
    assert last_rename < first_add


def test_postgres_rename_sql_is_a_single_guarded_do_block() -> None:
    for stmt, (old, new) in zip(
        pg._TURNS_THINKING_RENAME_SQL, _TURNS_THINKING_RENAMES
    ):
        assert stmt.startswith("DO $$")
        assert stmt.endswith("END $$;")
        assert "information_schema.columns" in stmt
        assert f"RENAME COLUMN {old} TO {new}" in stmt


def test_postgres_schema_declares_the_new_column_names() -> None:
    for col in _NEW_NAMES:
        assert f"{col} DOUBLE PRECISION" in pg._SCHEMA, col
    for col in _OLD_NAMES:
        assert col not in pg._SCHEMA, col
    assert "ri_task, ri_probe, ri_forfeit" in pg._TURN_SELECT_COLS
