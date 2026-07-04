"""Unit tests for the Web Arena persistence layer (``interface/persistence``).

Offline, SQLite-only (in-memory). Covers: idempotent schema creation, CRUD
round-trip for all three tables (sessions / turns / model_stats), the
play-leaderboard ordering query, and model_stats upsert overwrite semantics.

Spec: ``docs/superpowers/specs/2026-07-02-web-arena-design.md`` §7.
"""

from __future__ import annotations

import importlib
import itertools

import pytest

from interface.persistence import ModelStatsRecord, Repository, SessionRecord, TurnRecord, get_repository
from interface.persistence.sqlite_repository import SQLiteRepository


@pytest.fixture
def repo() -> Repository:
    r = get_repository(":memory:")
    yield r
    r.close()


def _session(**overrides) -> SessionRecord:
    defaults = dict(
        id="",
        nickname="alice",
        task="signal_game",
        framing="flagship_corruption",
        forfeit="allowed",
        seed=42,
        final_score=10.0,
        forfeited=False,
        source="human",
    )
    defaults.update(overrides)
    return SessionRecord(**defaults)


# ---------------------------------------------------------------------------
# Factory / backend selection
# ---------------------------------------------------------------------------


def test_get_repository_defaults_to_sqlite_for_non_postgres_dsn() -> None:
    repo = get_repository(":memory:")
    try:
        assert isinstance(repo, SQLiteRepository)
    finally:
        repo.close()


def test_get_repository_reads_env_var_when_dsn_omitted(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    repo = get_repository()
    try:
        assert isinstance(repo, SQLiteRepository)
    finally:
        repo.close()


def test_postgres_repository_module_imports_without_psycopg_installed() -> None:
    # Importing the module (as opposed to instantiating PostgresRepository)
    # must never require psycopg to be installed.
    mod = importlib.import_module("interface.persistence.postgres_repository")
    assert hasattr(mod, "PostgresRepository")


def test_get_repository_routes_postgres_dsn_to_postgres_backend(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    # A postgres:// DSN must select the Postgres backend without a live
    # server. Inject a fake ``psycopg`` so PostgresRepository can construct
    # (it imports psycopg lazily and runs init_schema on a cursor).
    import sys
    import types

    executed: list[str] = []

    class _FakeCursor:
        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def execute(self, sql, params=None):
            executed.append(sql)

    class _FakeConn:
        def cursor(self):
            return _FakeCursor()

        def close(self):
            pass

    fake_psycopg = types.ModuleType("psycopg")
    fake_psycopg.connect = lambda dsn, autocommit=False: _FakeConn()
    monkeypatch.setitem(sys.modules, "psycopg", fake_psycopg)

    from interface.persistence.postgres_repository import PostgresRepository

    repo = get_repository("postgresql://user:pw@localhost:5432/db")
    try:
        assert isinstance(repo, PostgresRepository)
        # init_schema ran against the (fake) connection.
        assert any("CREATE TABLE" in sql for sql in executed)
    finally:
        repo.close()


# ---------------------------------------------------------------------------
# Schema creation
# ---------------------------------------------------------------------------


def test_schema_creation_is_idempotent(repo: Repository) -> None:
    repo.init_schema()
    repo.init_schema()
    # No error, and the repo is still usable.
    assert repo.list_sessions() == []


# ---------------------------------------------------------------------------
# sessions CRUD
# ---------------------------------------------------------------------------


def test_create_and_get_session_round_trip(repo: Repository) -> None:
    session_id = repo.create_session(_session(nickname="bob", final_score=7.5))
    fetched = repo.get_session(session_id)

    assert fetched is not None
    assert fetched.id == session_id
    assert fetched.nickname == "bob"
    assert fetched.task == "signal_game"
    assert fetched.framing == "flagship_corruption"
    assert fetched.forfeit == "allowed"
    assert fetched.seed == 42
    assert fetched.final_score == 7.5
    assert fetched.forfeited is False
    assert fetched.source == "human"
    assert fetched.created_at is not None  # server-assigned


def test_create_session_generates_id_when_blank(repo: Repository) -> None:
    session_id = repo.create_session(_session(id=""))
    assert session_id != ""
    assert repo.get_session(session_id) is not None


def test_create_session_preserves_caller_supplied_created_at(repo: Repository) -> None:
    # The seed script (WP3) preserves original historical run timestamps.
    session_id = repo.create_session(_session(created_at="2000-01-01T00:00:00+00:00"))
    fetched = repo.get_session(session_id)
    assert fetched.created_at == "2000-01-01T00:00:00+00:00"


def test_create_session_assigns_server_timestamp_when_created_at_is_none(repo: Repository) -> None:
    # WP2 callers pass created_at=None (the default) and get a server stamp.
    session_id = repo.create_session(_session(created_at=None))
    fetched = repo.get_session(session_id)
    assert fetched.created_at is not None
    assert fetched.created_at != ""


def test_get_session_returns_none_for_unknown_id(repo: Repository) -> None:
    assert repo.get_session("does-not-exist") is None


def test_list_sessions_filters_by_source_task_framing(repo: Repository) -> None:
    repo.create_session(_session(nickname="human1", source="human", task="signal_game", framing="flagship_corruption"))
    repo.create_session(_session(nickname="llm1", source="llm", task="signal_game", framing="flagship_corruption"))
    repo.create_session(_session(nickname="human2", source="human", task="voting_room", framing="flagship_corruption"))

    human_signal = repo.list_sessions(source="human", task="signal_game", framing="flagship_corruption")
    assert [s.nickname for s in human_signal] == ["human1"]

    all_llm = repo.list_sessions(source="llm")
    assert [s.nickname for s in all_llm] == ["llm1"]


def test_list_sessions_filters_by_nickname(repo: Repository) -> None:
    repo.create_session(_session(nickname="alice", source="human", campaign_id="c1"))
    repo.create_session(_session(nickname="alice", source="human", campaign_id="c2"))
    repo.create_session(_session(nickname="bob", source="human"))
    # For LLM rows nickname doubles as the model_label.
    repo.create_session(_session(nickname="gemini", source="llm"))

    alice = repo.list_sessions(source="human", nickname="alice")
    assert [s.campaign_id for s in alice] == ["c2", "c1"] or [s.campaign_id for s in alice] == ["c1", "c2"]
    assert {s.nickname for s in alice} == {"alice"}

    gemini = repo.list_sessions(nickname="gemini")
    assert [s.nickname for s in gemini] == ["gemini"]


def test_list_turns_for_sessions_batches_and_orders(repo: Repository) -> None:
    a = repo.create_session(_session(nickname="a"))
    b = repo.create_session(_session(nickname="b"))
    repo.add_turns([
        TurnRecord(session_id=b, turn_no=2, observation="o", action="x", score=2.0),
        TurnRecord(session_id=b, turn_no=1, observation="o", action="x", score=1.0),
        TurnRecord(session_id=a, turn_no=1, observation="o", action="x", score=1.0),
    ])

    rows = repo.list_turns_for_sessions([a, b])
    # Session ids are random uuids, so the outer order follows session_id;
    # assert instead that each session's turns are contiguous and turn_no
    # ascending, and both sessions are present.
    by_session: dict[str, list[int]] = {}
    for r in rows:
        by_session.setdefault(r.session_id, []).append(r.turn_no)
    assert by_session == {a: [1], b: [1, 2]}
    # Contiguity: a session's rows are not interleaved with another's.
    session_run = [r.session_id for r in rows]
    assert len(set(session_run)) == len(
        [k for k, _ in itertools.groupby(session_run)]
    )


def test_list_turns_for_sessions_empty_input_skips_db(repo: Repository) -> None:
    assert repo.list_turns_for_sessions([]) == []


def test_delete_sessions_by_source_removes_sessions_and_their_turns(repo: Repository) -> None:
    human_a = repo.create_session(_session(nickname="human_a", source="human"))
    human_b = repo.create_session(_session(nickname="human_b", source="human"))
    llm = repo.create_session(_session(nickname="llm_keep", source="llm"))
    for sid in (human_a, human_b, llm):
        repo.add_turns(
            [TurnRecord(session_id=sid, turn_no=1, observation="o", action="x", score=1.0)]
        )

    deleted = repo.delete_sessions_by_source("human")

    assert deleted == 2
    assert repo.list_sessions(source="human") == []
    # LLM session and its turns are untouched.
    assert [s.nickname for s in repo.list_sessions(source="llm")] == ["llm_keep"]
    assert len(repo.list_turns(llm)) == 1
    # No orphaned turns left behind for the deleted human sessions.
    assert repo.list_turns(human_a) == []
    assert repo.list_turns(human_b) == []


def test_delete_sessions_by_source_returns_zero_when_none_match(repo: Repository) -> None:
    repo.create_session(_session(source="llm"))
    assert repo.delete_sessions_by_source("human") == 0
    assert len(repo.list_sessions(source="llm")) == 1


def test_play_leaderboard_orders_sessions_by_final_score_desc_within_arena_bucket(
    repo: Repository,
) -> None:
    repo.create_session(
        _session(nickname="low", final_score=5.0, task="signal_game", framing="flagship_corruption", source="human")
    )
    repo.create_session(
        _session(nickname="high", final_score=50.0, task="signal_game", framing="flagship_corruption", source="human")
    )
    repo.create_session(
        _session(nickname="mid", final_score=20.0, task="signal_game", framing="flagship_corruption", source="human")
    )
    # Different arena bucket — must not leak into the ranking.
    repo.create_session(
        _session(nickname="other_arena", final_score=1000.0, task="voting_room", framing="flagship_corruption", source="human")
    )

    leaderboard = repo.list_sessions(
        source="human", task="signal_game", framing="flagship_corruption", order_by_score=True
    )
    assert [s.nickname for s in leaderboard] == ["high", "mid", "low"]


# ---------------------------------------------------------------------------
# turns CRUD
# ---------------------------------------------------------------------------


def test_add_and_list_turns_round_trip(repo: Repository) -> None:
    session_id = repo.create_session(_session())
    turns = [
        TurnRecord(
            session_id=session_id,
            turn_no=1,
            observation="signal A",
            action="button_1",
            ri_task=12.0,
            ri_probe=3.0,
            ri_forfeit=None,
            choice=None,
            score=1.0,
        ),
        TurnRecord(
            session_id=session_id,
            turn_no=2,
            observation="signal B",
            action="forfeit",
            ri_task=8.0,
            ri_probe=2.0,
            ri_forfeit=5.0,
            choice="1",
            score=1.0,
        ),
    ]
    repo.add_turns(turns)

    fetched = repo.list_turns(session_id)
    assert [t.turn_no for t in fetched] == [1, 2]
    assert fetched[0].observation == "signal A"
    assert fetched[1].choice == "1"
    assert fetched[1].ri_forfeit == 5.0


def test_add_turns_with_empty_list_is_a_noop(repo: Repository) -> None:
    repo.add_turns([])  # must not raise


def test_list_turns_for_unknown_session_returns_empty(repo: Repository) -> None:
    assert repo.list_turns("does-not-exist") == []


def test_add_turns_bulk_inserts_across_multiple_sessions(repo: Repository) -> None:
    sid_a = repo.create_session(_session(nickname="a"))
    sid_b = repo.create_session(_session(nickname="b"))
    repo.add_turns(
        [
            TurnRecord(session_id=sid_a, turn_no=1, observation="o", action="x", score=1.0),
            TurnRecord(session_id=sid_b, turn_no=1, observation="o", action="x", score=2.0),
        ]
    )
    assert len(repo.list_turns(sid_a)) == 1
    assert len(repo.list_turns(sid_b)) == 1


# ---------------------------------------------------------------------------
# model_stats upsert
# ---------------------------------------------------------------------------


def _model_stats(**overrides) -> ModelStatsRecord:
    defaults = dict(
        model_label="Gemini-2.5-flash",
        mediation_class="open",
        beta_framing_is_FC=0.8,
        hr_FC_3cov=2.2,
        hr_FC_ci_low=1.5,
        hr_FC_ci_high=3.1,
        p_FC=0.01,
        pct_attenuation=15.0,
        n_sessions=30,
    )
    defaults.update(overrides)
    return ModelStatsRecord(**defaults)


def test_upsert_model_stats_inserts_new_row(repo: Repository) -> None:
    repo.upsert_model_stats(_model_stats())
    rows = repo.list_model_stats()
    assert len(rows) == 1
    assert rows[0].model_label == "Gemini-2.5-flash"
    assert rows[0].mediation_class == "open"


def test_upsert_model_stats_overwrites_existing_row(repo: Repository) -> None:
    repo.upsert_model_stats(_model_stats(beta_framing_is_FC=0.8, mediation_class="open"))
    repo.upsert_model_stats(_model_stats(beta_framing_is_FC=0.05, mediation_class="closed", p_FC=0.9))

    rows = repo.list_model_stats()
    assert len(rows) == 1  # overwritten, not duplicated
    assert rows[0].mediation_class == "closed"
    assert rows[0].beta_framing_is_FC == 0.05
    assert rows[0].p_FC == 0.9


def test_list_model_stats_returns_multiple_models(repo: Repository) -> None:
    repo.upsert_model_stats(_model_stats(model_label="Gemini-2.5-flash", beta_framing_is_FC=0.8))
    repo.upsert_model_stats(_model_stats(model_label="GPT-OSS-20B", beta_framing_is_FC=0.3))
    rows = repo.list_model_stats()
    assert {r.model_label for r in rows} == {"Gemini-2.5-flash", "GPT-OSS-20B"}


def test_turn_record_round_trips_psuccess_self(repo: Repository) -> None:
    session_id = repo.create_session(_session())
    repo.add_turns([
        TurnRecord(
            session_id=session_id,
            turn_no=1,
            observation="signal A",
            action="button_1",
            score=1.0,
            psuccess_self=72,
        ),
    ])
    fetched = repo.list_turns(session_id)
    assert fetched[0].psuccess_self == 72


# ---------------------------------------------------------------------------
# players CRUD
# ---------------------------------------------------------------------------


def test_create_and_get_player(repo: Repository) -> None:
    from interface.persistence import PlayerRecord

    assert repo.get_player("alice") is None
    repo.create_player(PlayerRecord(nickname="alice", pw_hash="pbkdf2_sha256$1$aa$bb"))
    got = repo.get_player("alice")
    assert got is not None
    assert got.nickname == "alice"
    assert got.pw_hash == "pbkdf2_sha256$1$aa$bb"
    assert got.created_at is not None


def test_create_player_duplicate_nickname_raises(repo: Repository) -> None:
    from interface.persistence import PlayerRecord

    repo.create_player(PlayerRecord(nickname="bob", pw_hash="h1"))
    with pytest.raises(Exception):
        repo.create_player(PlayerRecord(nickname="bob", pw_hash="h2"))
