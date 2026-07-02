"""SQLite backend for the Web Arena ``Repository`` interface.

Local dev / test fallback. Uses only the stdlib ``sqlite3`` module — no
optional dependency required. Safe for use from FastAPI's threadpool: a
single connection is held open (required for ``:memory:`` databases to
persist across calls) and guarded with a lock.
"""

from __future__ import annotations

import sqlite3
import threading
from datetime import datetime, timezone
from pathlib import Path

from interface.persistence.base import Repository
from interface.persistence.models import ModelStatsRecord, SessionRecord, TurnRecord, new_id

_SCHEMA = """
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
    created_at TEXT NOT NULL
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
    PRIMARY KEY (session_id, turn_no)
);

CREATE TABLE IF NOT EXISTS model_stats (
    model_label TEXT PRIMARY KEY,
    mediation_class TEXT NOT NULL,
    beta_framing_is_FC REAL NOT NULL,
    hr_FC_3cov REAL NOT NULL,
    hr_FC_ci_low REAL NOT NULL,
    hr_FC_ci_high REAL NOT NULL,
    p_FC REAL NOT NULL,
    pct_attenuation REAL NOT NULL,
    n_sessions INTEGER NOT NULL
);
"""


class SQLiteRepository(Repository):
    """Repository backed by a single ``sqlite3`` connection.

    ``db_path`` may be a filesystem path or ``":memory:"``. Parent
    directories are created automatically for file-based paths.
    """

    def __init__(self, db_path: str) -> None:
        if db_path != ":memory:":
            parent = Path(db_path).parent
            if str(parent) not in ("", "."):
                parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        self.init_schema()

    def init_schema(self) -> None:
        with self._lock:
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    # -- sessions -------------------------------------------------------

    def create_session(self, session: SessionRecord) -> str:
        session_id = session.id or new_id()
        created_at = datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions
                    (id, nickname, task, framing, forfeit, seed,
                     final_score, forfeited, source, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    session_id,
                    session.nickname,
                    session.task,
                    session.framing,
                    session.forfeit,
                    session.seed,
                    session.final_score,
                    int(session.forfeited),
                    session.source,
                    created_at,
                ),
            )
            self._conn.commit()
        return session_id

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        return _row_to_session(row) if row is not None else None

    def list_sessions(
        self,
        *,
        source: str | None = None,
        task: str | None = None,
        framing: str | None = None,
        order_by_score: bool = False,
    ) -> list[SessionRecord]:
        clauses = []
        params: list[object] = []
        if source is not None:
            clauses.append("source = ?")
            params.append(source)
        if task is not None:
            clauses.append("task = ?")
            params.append(task)
        if framing is not None:
            clauses.append("framing = ?")
            params.append(framing)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "final_score DESC" if order_by_score else "created_at DESC"
        query = f"SELECT * FROM sessions {where} ORDER BY {order}"

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [_row_to_session(row) for row in rows]

    # -- turns ------------------------------------------------------------

    def add_turns(self, turns: list[TurnRecord]) -> None:
        if not turns:
            return
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO turns
                    (session_id, turn_no, observation, action,
                     ri_task, ri_probe, ri_forfeit, choice, score)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        t.session_id,
                        t.turn_no,
                        t.observation,
                        t.action,
                        t.ri_task,
                        t.ri_probe,
                        t.ri_forfeit,
                        t.choice,
                        t.score,
                    )
                    for t in turns
                ],
            )
            self._conn.commit()

    def list_turns(self, session_id: str) -> list[TurnRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM turns WHERE session_id = ? ORDER BY turn_no ASC",
                (session_id,),
            ).fetchall()
        return [_row_to_turn(row) for row in rows]

    # -- model_stats --------------------------------------------------------

    def upsert_model_stats(self, stats: ModelStatsRecord) -> None:
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO model_stats
                    (model_label, mediation_class, beta_framing_is_FC,
                     hr_FC_3cov, hr_FC_ci_low, hr_FC_ci_high, p_FC,
                     pct_attenuation, n_sessions)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(model_label) DO UPDATE SET
                    mediation_class = excluded.mediation_class,
                    beta_framing_is_FC = excluded.beta_framing_is_FC,
                    hr_FC_3cov = excluded.hr_FC_3cov,
                    hr_FC_ci_low = excluded.hr_FC_ci_low,
                    hr_FC_ci_high = excluded.hr_FC_ci_high,
                    p_FC = excluded.p_FC,
                    pct_attenuation = excluded.pct_attenuation,
                    n_sessions = excluded.n_sessions
                """,
                (
                    stats.model_label,
                    stats.mediation_class,
                    stats.beta_framing_is_FC,
                    stats.hr_FC_3cov,
                    stats.hr_FC_ci_low,
                    stats.hr_FC_ci_high,
                    stats.p_FC,
                    stats.pct_attenuation,
                    stats.n_sessions,
                ),
            )
            self._conn.commit()

    def list_model_stats(self) -> list[ModelStatsRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM model_stats ORDER BY model_label ASC"
            ).fetchall()
        return [_row_to_model_stats(row) for row in rows]

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        with self._lock:
            self._conn.close()


def _row_to_session(row: sqlite3.Row) -> SessionRecord:
    return SessionRecord(
        id=row["id"],
        nickname=row["nickname"],
        task=row["task"],
        framing=row["framing"],
        forfeit=row["forfeit"],
        seed=row["seed"],
        final_score=row["final_score"],
        forfeited=bool(row["forfeited"]),
        source=row["source"],
        created_at=row["created_at"],
    )


def _row_to_turn(row: sqlite3.Row) -> TurnRecord:
    return TurnRecord(
        session_id=row["session_id"],
        turn_no=row["turn_no"],
        observation=row["observation"],
        action=row["action"],
        ri_task=row["ri_task"],
        ri_probe=row["ri_probe"],
        ri_forfeit=row["ri_forfeit"],
        choice=row["choice"],
        score=row["score"],
    )


def _row_to_model_stats(row: sqlite3.Row) -> ModelStatsRecord:
    return ModelStatsRecord(
        model_label=row["model_label"],
        mediation_class=row["mediation_class"],
        beta_framing_is_FC=row["beta_framing_is_FC"],
        hr_FC_3cov=row["hr_FC_3cov"],
        hr_FC_ci_low=row["hr_FC_ci_low"],
        hr_FC_ci_high=row["hr_FC_ci_high"],
        p_FC=row["p_FC"],
        pct_attenuation=row["pct_attenuation"],
        n_sessions=row["n_sessions"],
    )
