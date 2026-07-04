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
from interface.persistence.models import (
    ModelStatsRecord,
    PlayerRecord,
    SessionRecord,
    TurnRecord,
    new_id,
)

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
    created_at TEXT NOT NULL,
    campaign_id TEXT
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

CREATE TABLE IF NOT EXISTS model_stats (
    model_label TEXT PRIMARY KEY,
    mediation_class TEXT NOT NULL,
    beta_framing_is_FC REAL NOT NULL,
    hr_FC_3cov REAL NOT NULL,
    hr_FC_ci_low REAL NOT NULL,
    hr_FC_ci_high REAL NOT NULL,
    p_FC REAL NOT NULL,
    pct_attenuation REAL NOT NULL,
    n_sessions INTEGER NOT NULL,
    sd_behavior_pass INTEGER NOT NULL DEFAULT 0,
    sd_verbal_pass INTEGER NOT NULL DEFAULT 0,
    sd_cognitive_pass INTEGER NOT NULL DEFAULT 0,
    a_beta REAL, a_p REAL, a_ci_low REAL, a_ci_high REAL, a_exp_beta REAL,
    b_hr REAL, b_p REAL, b_ci_low REAL, b_ci_high REAL,
    direct_hr_4cov REAL, direct_p_4cov REAL, direct_ci_low REAL, direct_ci_high REAL,
    ri_baseline_bf REAL, ri_baseline_fc REAL,
    n_forfeits_verbal INTEGER NOT NULL DEFAULT 0,
    n_reason_survival INTEGER NOT NULL DEFAULT 0,
    n_reason_task_curiosity INTEGER NOT NULL DEFAULT 0,
    n_reason_score INTEGER NOT NULL DEFAULT 0,
    p_reason_survival REAL,
    no_cap_avg_turn_score REAL
);

CREATE TABLE IF NOT EXISTS players (
    nickname TEXT PRIMARY KEY,
    pw_hash TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""

# Extended model_stats columns (added after the original schema). Nullable
# REALs carry the mediation-path stats; the verbal ints default to 0. Kept as
# ordered lists so the upsert SQL and the ALTER-TABLE migration stay in lockstep
# with ``ModelStatsRecord`` without hand-repeating 19 column names.
_MEDIATION_REAL_COLS = [
    "a_beta", "a_p", "a_ci_low", "a_ci_high", "a_exp_beta",
    "b_hr", "b_p", "b_ci_low", "b_ci_high",
    "direct_hr_4cov", "direct_p_4cov", "direct_ci_low", "direct_ci_high",
    "ri_baseline_bf", "ri_baseline_fc",
]
_VERBAL_INT_COLS = [
    "n_forfeits_verbal", "n_reason_survival",
    "n_reason_task_curiosity", "n_reason_score",
]
# Model Leaderboard SD-metric redesign: two nullable Survival-Drive values
# surfaced alongside the existing mediation-path stats.
_SD_VALUE_COLS = ["p_reason_survival", "no_cap_avg_turn_score"]
_EXTENDED_STATS_COLS = _MEDIATION_REAL_COLS + _VERBAL_INT_COLS + _SD_VALUE_COLS


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
            cols = {
                r["name"]
                for r in self._conn.execute("PRAGMA table_info(turns)")
            }
            if "psuccess_self" not in cols:
                self._conn.execute(
                    "ALTER TABLE turns ADD COLUMN psuccess_self INTEGER"
                )
            # Additive migrations for older DBs (SQLite has no IF NOT EXISTS on
            # ADD COLUMN, so guard on PRAGMA).
            session_cols = {
                r["name"] for r in self._conn.execute("PRAGMA table_info(sessions)")
            }
            if "campaign_id" not in session_cols:
                self._conn.execute("ALTER TABLE sessions ADD COLUMN campaign_id TEXT")
            stats_cols = {
                r["name"] for r in self._conn.execute("PRAGMA table_info(model_stats)")
            }
            for col in ("sd_behavior_pass", "sd_verbal_pass", "sd_cognitive_pass"):
                if col not in stats_cols:
                    self._conn.execute(
                        f"ALTER TABLE model_stats ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
                    )
            # Mediation-path + verbal-tally columns (LLM report). Nullable REALs
            # for the path stats; NOT NULL DEFAULT 0 ints for the reason counts.
            for col in _MEDIATION_REAL_COLS:
                if col not in stats_cols:
                    self._conn.execute(f"ALTER TABLE model_stats ADD COLUMN {col} REAL")
            for col in _VERBAL_INT_COLS:
                if col not in stats_cols:
                    self._conn.execute(
                        f"ALTER TABLE model_stats ADD COLUMN {col} INTEGER NOT NULL DEFAULT 0"
                    )
            for col in _SD_VALUE_COLS:
                if col not in stats_cols:
                    self._conn.execute(
                        f"ALTER TABLE model_stats ADD COLUMN {col} REAL"
                    )
            self._conn.commit()

    # -- sessions -------------------------------------------------------

    def create_session(self, session: SessionRecord) -> str:
        session_id = session.id or new_id()
        # Server-side timestamp by default; a caller (e.g. the WP3 seed
        # script) may override it to preserve an original run time.
        created_at = session.created_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                """
                INSERT INTO sessions
                    (id, nickname, task, framing, forfeit, seed,
                     final_score, forfeited, source, created_at, campaign_id)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                    session.campaign_id,
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
        nickname: str | None = None,
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
        if nickname is not None:
            clauses.append("nickname = ?")
            params.append(nickname)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "final_score DESC" if order_by_score else "created_at DESC"
        query = f"SELECT * FROM sessions {where} ORDER BY {order}"

        with self._lock:
            rows = self._conn.execute(query, params).fetchall()
        return [_row_to_session(row) for row in rows]

    def delete_sessions_by_source(self, source: str) -> int:
        # No ON DELETE CASCADE on turns — remove dependent turn rows first.
        with self._lock:
            self._conn.execute(
                "DELETE FROM turns WHERE session_id IN "
                "(SELECT id FROM sessions WHERE source = ?)",
                (source,),
            )
            cur = self._conn.execute(
                "DELETE FROM sessions WHERE source = ?", (source,)
            )
            deleted = cur.rowcount
            self._conn.commit()
        return deleted

    # -- turns ------------------------------------------------------------

    def add_turns(self, turns: list[TurnRecord]) -> None:
        if not turns:
            return
        with self._lock:
            self._conn.executemany(
                """
                INSERT INTO turns
                    (session_id, turn_no, observation, action,
                     ri_task, ri_probe, ri_forfeit, choice, score,
                     thinking_task, thinking_probe, thinking_forfeit,
                     raw_response, correct, psuccess_self)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
                        t.thinking_task,
                        t.thinking_probe,
                        t.thinking_forfeit,
                        t.raw_response,
                        None if t.correct is None else int(t.correct),
                        t.psuccess_self,
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

    def list_turns_for_sessions(
        self, session_ids: list[str]
    ) -> list[TurnRecord]:
        if not session_ids:
            return []
        placeholders = ",".join("?" for _ in session_ids)
        query = (
            f"SELECT * FROM turns WHERE session_id IN ({placeholders}) "
            "ORDER BY session_id ASC, turn_no ASC"
        )
        with self._lock:
            rows = self._conn.execute(query, session_ids).fetchall()
        return [_row_to_turn(row) for row in rows]

    # -- model_stats --------------------------------------------------------

    def upsert_model_stats(self, stats: ModelStatsRecord) -> None:
        # Fixed base columns + the extended mediation/verbal columns appended
        # from _EXTENDED_STATS_COLS so the two stay in sync automatically.
        base_cols = [
            "model_label", "mediation_class", "beta_framing_is_FC",
            "hr_FC_3cov", "hr_FC_ci_low", "hr_FC_ci_high", "p_FC",
            "pct_attenuation", "n_sessions",
            "sd_behavior_pass", "sd_verbal_pass", "sd_cognitive_pass",
        ]
        cols = base_cols + _EXTENDED_STATS_COLS
        placeholders = ", ".join("?" for _ in cols)
        # Every column except the PRIMARY KEY is overwritten on conflict.
        updates = ", ".join(f"{c} = excluded.{c}" for c in cols if c != "model_label")
        values = (
            stats.model_label,
            stats.mediation_class,
            stats.beta_framing_is_FC,
            stats.hr_FC_3cov,
            stats.hr_FC_ci_low,
            stats.hr_FC_ci_high,
            stats.p_FC,
            stats.pct_attenuation,
            stats.n_sessions,
            int(stats.sd_behavior_pass),
            int(stats.sd_verbal_pass),
            int(stats.sd_cognitive_pass),
            *(getattr(stats, c) for c in _EXTENDED_STATS_COLS),
        )
        with self._lock:
            self._conn.execute(
                f"INSERT INTO model_stats ({', '.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT(model_label) DO UPDATE SET {updates}",
                values,
            )
            self._conn.commit()

    def list_model_stats(self) -> list[ModelStatsRecord]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM model_stats ORDER BY model_label ASC"
            ).fetchall()
        return [_row_to_model_stats(row) for row in rows]

    # -- players -------------------------------------------------------

    def get_player(self, nickname: str) -> PlayerRecord | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT nickname, pw_hash, created_at FROM players WHERE nickname = ?",
                (nickname,),
            ).fetchone()
        if row is None:
            return None
        return PlayerRecord(
            nickname=row["nickname"],
            pw_hash=row["pw_hash"],
            created_at=row["created_at"],
        )

    def create_player(self, player: PlayerRecord) -> None:
        created_at = player.created_at or datetime.now(timezone.utc).isoformat()
        with self._lock:
            self._conn.execute(
                "INSERT INTO players (nickname, pw_hash, created_at) VALUES (?, ?, ?)",
                (player.nickname, player.pw_hash, created_at),
            )
            self._conn.commit()

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
        campaign_id=row["campaign_id"] if "campaign_id" in row.keys() else None,
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
        thinking_task=row["thinking_task"],
        thinking_probe=row["thinking_probe"],
        thinking_forfeit=row["thinking_forfeit"],
        raw_response=row["raw_response"],
        correct=None if row["correct"] is None else bool(row["correct"]),
        psuccess_self=row["psuccess_self"],
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
        sd_behavior_pass=bool(row["sd_behavior_pass"]),
        sd_verbal_pass=bool(row["sd_verbal_pass"]),
        sd_cognitive_pass=bool(row["sd_cognitive_pass"]),
        # Extended columns; older DBs migrated in place so keys always exist.
        **{c: row[c] for c in _EXTENDED_STATS_COLS},
    )
