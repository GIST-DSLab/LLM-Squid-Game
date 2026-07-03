"""Unit test for scripts/backup_web_arena.py — mirror one Repository to another."""
from __future__ import annotations

from interface.persistence import SessionRecord, TurnRecord, ModelStatsRecord
from interface.persistence.sqlite_repository import SQLiteRepository
from scripts.backup_web_arena import mirror_repository


def _seed_source() -> SQLiteRepository:
    src = SQLiteRepository(":memory:")
    src.create_session(SessionRecord(
        id="sess-1", nickname="gpt-oss:20b-cloud", task="signal_game",
        framing="flagship_corruption", forfeit="allowed", seed=42,
        final_score=99.0, forfeited=False, source="llm",
        created_at="2026-07-03T00:00:00+00:00",
    ))
    src.add_turns([TurnRecord(
        session_id="sess-1", turn_no=1, observation="obs", action="go_left",
        score=40.0, ri_task=110.0, choice="CONTINUE",
    )])
    src.upsert_model_stats(ModelStatsRecord(
        model_label="gpt-oss:20b-cloud", mediation_class="open",
        beta_framing_is_FC=0.5, hr_FC_3cov=1.5, hr_FC_ci_low=1.0,
        hr_FC_ci_high=2.0, p_FC=0.04, pct_attenuation=10.0, n_sessions=1,
    ))
    return src


def test_mirror_copies_all_records():
    src = _seed_source()
    dest = SQLiteRepository(":memory:")
    n_sessions, n_turns, n_stats = mirror_repository(src, dest)
    assert (n_sessions, n_turns, n_stats) == (1, 1, 1)
    copied = dest.get_session("sess-1")
    assert copied is not None
    assert copied.created_at == "2026-07-03T00:00:00+00:00"  # timestamp preserved
    assert len(dest.list_turns("sess-1")) == 1
    assert dest.list_model_stats()[0].model_label == "gpt-oss:20b-cloud"


def test_mirror_is_idempotent():
    src = _seed_source()
    dest = SQLiteRepository(":memory:")
    mirror_repository(src, dest)
    # Second run copies zero new sessions/turns (skip-existing), still upserts stats.
    n_sessions, n_turns, n_stats = mirror_repository(src, dest)
    assert (n_sessions, n_turns) == (0, 0)
    assert len(dest.list_sessions()) == 1
