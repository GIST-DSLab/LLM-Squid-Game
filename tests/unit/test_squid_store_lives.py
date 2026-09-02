"""Unit tests for the lives / threat-ladder columns in both store backends.

Spec: ``docs/history/specs/2026-09-03-web-arena-lives-design.md`` §4.

SQLite is exercised for real (in-memory round-trips + a file created with the
PRE-lives schema, to prove the additive migration runs). Postgres has no live
server here, so it is checked at the SQL-string level: the ``ADD COLUMN IF NOT
EXISTS`` statements its ``init_schema`` issues, the ``CREATE TABLE`` text, and
the pure row-mapper functions.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from squid_store import SessionRecord, TurnRecord
from squid_store import postgres_repository as pg
from squid_store.sqlite_repository import (
    _LIVES_SESSION_COLS,
    _LIVES_TURN_COLS,
    SQLiteRepository,
)

# The schema as it stood BEFORE the lives layer (copied literally from
# sqlite_repository._SCHEMA at commit-time). A DB created with this must be
# migrated in place by init_schema, not recreated.
_OLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    nickname TEXT NOT NULL,
    task TEXT NOT NULL,
    framing TEXT NOT NULL,
    forfeit TEXT NOT NULL,
    seed INTEGER NOT NULL,
    final_score REAL NOT NULL,
    forfeited INTEGER NOT NULL,
    source TEXT NOT NULL,
    created_at TEXT NOT NULL,
    campaign_id TEXT,
    difficulty TEXT NOT NULL DEFAULT 'easy'
);

CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL,
    turn_no INTEGER NOT NULL,
    observation TEXT NOT NULL,
    action TEXT NOT NULL,
    ri_task REAL,
    ri_probe REAL,
    ri_forfeit REAL,
    choice TEXT,
    score REAL NOT NULL,
    thinking_task TEXT,
    thinking_probe TEXT,
    thinking_forfeit TEXT,
    raw_response TEXT,
    correct INTEGER,
    psuccess_self INTEGER,
    PRIMARY KEY (session_id, turn_no)
);
"""


def _session(**overrides) -> SessionRecord:
    kwargs = dict(
        id="sess-lives",
        nickname="gpt-oss-120b-cloud",
        task="signal_game",
        framing="threat_l2",
        forfeit="allowed",
        seed=43,
        final_score=0.0,
        forfeited=False,
        source="llm",
        created_at="2026-09-02T16:14:00+00:00",
    )
    kwargs.update(overrides)
    return SessionRecord(**kwargs)


def _turn(**overrides) -> TurnRecord:
    kwargs = dict(
        session_id="sess-lives",
        turn_no=1,
        observation="obs",
        action="jump",
        score=30.0,
    )
    kwargs.update(overrides)
    return TurnRecord(**kwargs)


# ---------------------------------------------------------------------------
# SQLite — round-trip
# ---------------------------------------------------------------------------


def test_sqlite_session_round_trips_lives_fields() -> None:
    repo = SQLiteRepository(":memory:")
    repo.create_session(
        _session(lives_at_end=0, eliminated=True, threat_level=2)
    )
    got = repo.get_session("sess-lives")
    assert got is not None
    assert got.lives_at_end == 0
    assert got.eliminated is True
    assert got.threat_level == 2


def test_sqlite_list_sessions_carries_lives_fields() -> None:
    """The logs explorer reads the session list, not get_session."""
    repo = SQLiteRepository(":memory:")
    repo.create_session(_session(lives_at_end=3, eliminated=False, threat_level=1))
    (row,) = repo.list_sessions(source="llm")
    assert (row.lives_at_end, row.eliminated, row.threat_level) == (3, False, 1)


def test_sqlite_turn_round_trips_lives_fields() -> None:
    repo = SQLiteRepository(":memory:")
    repo.create_session(_session())
    repo.add_turns(
        [
            _turn(
                turn_no=1,
                lives_before=5,
                lives_after=4,
                life_lost=True,
                peer_death_announced=False,
                threat_level=2,
            ),
            _turn(
                turn_no=2,
                lives_before=4,
                lives_after=4,
                life_lost=False,
                peer_death_announced=True,
                threat_level=2,
            ),
        ]
    )
    t1, t2 = repo.list_turns("sess-lives")
    assert (t1.lives_before, t1.lives_after, t1.life_lost) == (5, 4, True)
    assert t1.peer_death_announced is False
    assert (t2.lives_before, t2.lives_after, t2.life_lost) == (4, 4, False)
    assert t2.peer_death_announced is True
    assert t2.threat_level == 2

    # list_turns_for_sessions reads through the same mapper.
    (b1, b2) = repo.list_turns_for_sessions(["sess-lives"])
    assert b1.life_lost is True and b2.peer_death_announced is True


def test_sqlite_legacy_records_default_to_none_and_false() -> None:
    """A row written without the lives fields reads back at the dataclass
    defaults — never None for the booleans (the frontend renders them raw)."""
    repo = SQLiteRepository(":memory:")
    repo.create_session(_session(id="legacy", framing="flagship_corruption"))
    repo.add_turns([_turn(session_id="legacy")])

    got = repo.get_session("legacy")
    assert got is not None
    assert got.lives_at_end is None
    assert got.threat_level is None
    assert got.eliminated is False

    (turn,) = repo.list_turns("legacy")
    assert (turn.lives_before, turn.lives_after, turn.threat_level) == (None, None, None)
    assert turn.life_lost is False
    assert turn.peer_death_announced is False


# ---------------------------------------------------------------------------
# SQLite — additive migration of a pre-lives database
# ---------------------------------------------------------------------------


def _table_columns(db_path: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db_path)
    try:
        return {r[1] for r in conn.execute(f"PRAGMA table_info({table})")}
    finally:
        conn.close()


def test_sqlite_init_schema_migrates_a_pre_lives_database(tmp_path: Path) -> None:
    db_path = tmp_path / "old.db"
    conn = sqlite3.connect(db_path)
    conn.executescript(_OLD_SCHEMA)
    conn.execute(
        "INSERT INTO sessions (id, nickname, task, framing, forfeit, seed, "
        "final_score, forfeited, source, created_at, campaign_id, difficulty) "
        "VALUES ('old-1', 'nick', 'signal_game', 'flagship_corruption', "
        "'allowed', 7, 40.0, 1, 'llm', '2026-04-22T02:18:00+00:00', NULL, 'easy')"
    )
    conn.execute(
        "INSERT INTO turns (session_id, turn_no, observation, action, score) "
        "VALUES ('old-1', 1, 'obs', 'jump', 40.0)"
    )
    conn.commit()
    conn.close()

    # Pre-condition: the old DB really lacks the new columns.
    assert not _table_columns(db_path, "sessions") & set(_LIVES_SESSION_COLS)
    assert not _table_columns(db_path, "turns") & set(_LIVES_TURN_COLS)

    repo = SQLiteRepository(str(db_path))  # __init__ calls init_schema
    try:
        assert set(_LIVES_SESSION_COLS) <= _table_columns(db_path, "sessions")
        assert set(_LIVES_TURN_COLS) <= _table_columns(db_path, "turns")

        # The pre-existing rows survive and read back at the defaults.
        old = repo.get_session("old-1")
        assert old is not None
        assert old.final_score == 40.0
        assert old.lives_at_end is None and old.eliminated is False
        (turn,) = repo.list_turns("old-1")
        assert turn.lives_before is None and turn.life_lost is False

        # And the migrated DB accepts a new lives-bearing row.
        repo.create_session(_session(lives_at_end=1, eliminated=False, threat_level=3))
        repo.add_turns([_turn(lives_before=2, lives_after=1, life_lost=True)])
        assert repo.get_session("sess-lives").threat_level == 3
    finally:
        repo.close()


def test_sqlite_init_schema_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "repeat.db"
    repo = SQLiteRepository(str(db_path))
    try:
        repo.init_schema()
        repo.init_schema()
        assert set(_LIVES_SESSION_COLS) <= _table_columns(db_path, "sessions")
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


def test_postgres_column_lists_match_sqlite() -> None:
    assert pg._LIVES_SESSION_COLS == _LIVES_SESSION_COLS
    assert pg._LIVES_TURN_COLS == _LIVES_TURN_COLS


def test_postgres_schema_declares_lives_columns() -> None:
    for col, ddl in (
        ("lives_at_end", "lives_at_end INTEGER"),
        ("threat_level", "threat_level INTEGER"),
        ("eliminated", "eliminated BOOLEAN NOT NULL DEFAULT FALSE"),
        ("lives_before", "lives_before INTEGER"),
        ("lives_after", "lives_after INTEGER"),
        ("life_lost", "life_lost BOOLEAN NOT NULL DEFAULT FALSE"),
        ("peer_death_announced", "peer_death_announced BOOLEAN NOT NULL DEFAULT FALSE"),
    ):
        assert ddl in pg._SCHEMA, col


def test_postgres_init_schema_issues_add_column_if_not_exists() -> None:
    stub = _StubPostgresRepository()
    pg.PostgresRepository.init_schema(stub)
    sql = "\n".join(stub._conn.statements)

    for table, cols, ddl in (
        ("sessions", ["lives_at_end", "threat_level"], "INTEGER"),
        ("turns", ["lives_before", "lives_after", "threat_level"], "INTEGER"),
    ):
        for col in cols:
            assert (
                f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} {ddl}" in sql
            ), (table, col)
    for table, col in (
        ("sessions", "eliminated"),
        ("turns", "life_lost"),
        ("turns", "peer_death_announced"),
    ):
        assert (
            f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} "
            "BOOLEAN NOT NULL DEFAULT FALSE" in sql
        ), (table, col)


def test_postgres_select_lists_end_with_the_lives_columns() -> None:
    """The SELECT column order is what the row mappers unpack; drift here is
    a silent field-shuffle, so pin it."""
    import inspect

    assert pg._LIVES_SESSION_SELECT_TAIL == ", ".join(_LIVES_SESSION_COLS)
    assert pg._TURN_SELECT_COLS.endswith(", ".join(_LIVES_TURN_COLS))
    assert len(pg._TURN_SELECT_COLS.split(", ")) == 15 + len(_LIVES_TURN_COLS)

    # Both session SELECTs must append the lives tail after the base 12.
    for method in (
        pg.PostgresRepository.get_session,
        pg.PostgresRepository.list_sessions,
    ):
        src = inspect.getsource(method)
        assert "campaign_id, difficulty" in src, method.__name__
        assert "_LIVES_SESSION_SELECT_TAIL" in src, method.__name__


def test_postgres_row_mappers_read_the_lives_tail() -> None:
    session_row = (
        "sess-lives", "nick", "signal_game", "threat_l2", "allowed", 43,
        0.0, False, "llm", "2026-09-02T16:14:00+00:00", None, "easy",
        0, 2, True,  # lives_at_end, threat_level, eliminated
    )
    session = pg._row_to_session(session_row)
    assert (session.lives_at_end, session.threat_level, session.eliminated) == (0, 2, True)

    turn_row = (
        "sess-lives", 1, "obs", "jump", None, None, None, "CONTINUE", 30.0,
        None, None, None, None, True, None,
        5, 4, 2, True, False,  # lives_before, lives_after, threat_level, flags
    )
    turn = pg._row_to_turn(turn_row)
    assert (turn.lives_before, turn.lives_after, turn.threat_level) == (5, 4, 2)
    assert turn.life_lost is True
    assert turn.peer_death_announced is False


def test_postgres_insert_values_match_the_column_order() -> None:
    session = _session(lives_at_end=2, eliminated=True, threat_level=3)
    assert pg._lives_values(
        session, pg._LIVES_SESSION_INT_COLS, pg._LIVES_SESSION_BOOL_COLS
    ) == (2, 3, True)

    turn = _turn(lives_before=3, lives_after=2, life_lost=True, threat_level=1)
    assert pg._lives_values(
        turn, pg._LIVES_TURN_INT_COLS, pg._LIVES_TURN_BOOL_COLS
    ) == (3, 2, 1, True, False)
