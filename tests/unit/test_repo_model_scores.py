"""Unit tests for SQLiteRepository.avg_score_per_model (rank-ladder support)."""

from __future__ import annotations

from interface.persistence.models import SessionRecord
from interface.persistence.sqlite_repository import SQLiteRepository


def _repo() -> SQLiteRepository:
    return SQLiteRepository(":memory:")


def _add(repo: SQLiteRepository, *, nickname: str, score: float, source: str = "llm") -> None:
    repo.create_session(
        SessionRecord(
            id=nickname + "-" + str(score),
            nickname=nickname,
            task="signal_game",
            framing="true_baseline",
            forfeit="allowed",
            seed=1,
            final_score=score,
            forfeited=False,
            source=source,
        )
    )


def test_avg_score_per_model_groups_and_averages():
    repo = _repo()
    _add(repo, nickname="ModelA", score=100.0)
    _add(repo, nickname="ModelA", score=300.0)  # ModelA avg = 200, n = 2
    _add(repo, nickname="ModelB", score=500.0)  # ModelB avg = 500, n = 1
    _add(repo, nickname="alice", score=9999.0, source="human")  # excluded

    rows = repo.avg_score_per_model()

    assert rows == [("ModelB", 500.0, 1), ("ModelA", 200.0, 2)]


def test_avg_score_per_model_empty_when_no_llm_sessions():
    repo = _repo()
    _add(repo, nickname="alice", score=10.0, source="human")
    assert repo.avg_score_per_model() == []


def test_avg_score_per_model_tie_breaks_by_label_ascending():
    repo = _repo()
    _add(repo, nickname="Zeta", score=200.0)
    _add(repo, nickname="Alpha", score=200.0)
    rows = repo.avg_score_per_model()
    assert [r[0] for r in rows] == ["Alpha", "Zeta"]
