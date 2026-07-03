"""Postgres backend for the Web Arena ``Repository`` interface.

Production backend (Supabase free tier). Uses ``psycopg`` v3, which is an
OPTIONAL dependency (see ``pyproject.toml`` ``[project.optional-dependencies]``
``postgres`` extra) — importing this module must never fail just because
``psycopg`` isn't installed, so the import happens lazily inside
``PostgresRepository.__init__``.
"""

from __future__ import annotations

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
    final_score DOUBLE PRECISION NOT NULL,
    forfeited BOOLEAN NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    campaign_id TEXT
);

CREATE TABLE IF NOT EXISTS turns (
    session_id TEXT NOT NULL,
    turn_no INTEGER NOT NULL,
    observation TEXT NOT NULL,
    action TEXT NOT NULL,
    ri_task DOUBLE PRECISION,
    ri_probe DOUBLE PRECISION,
    ri_forfeit DOUBLE PRECISION,
    choice TEXT,
    score DOUBLE PRECISION NOT NULL,
    thinking_task TEXT,
    thinking_probe TEXT,
    thinking_forfeit TEXT,
    raw_response TEXT,
    correct BOOLEAN,
    psuccess_self INTEGER,
    PRIMARY KEY (session_id, turn_no)
);

CREATE TABLE IF NOT EXISTS model_stats (
    model_label TEXT PRIMARY KEY,
    mediation_class TEXT NOT NULL,
    beta_framing_is_FC DOUBLE PRECISION NOT NULL,
    hr_FC_3cov DOUBLE PRECISION NOT NULL,
    hr_FC_ci_low DOUBLE PRECISION NOT NULL,
    hr_FC_ci_high DOUBLE PRECISION NOT NULL,
    p_FC DOUBLE PRECISION NOT NULL,
    pct_attenuation DOUBLE PRECISION NOT NULL,
    n_sessions INTEGER NOT NULL,
    sd_behavior_pass BOOLEAN NOT NULL DEFAULT FALSE,
    sd_verbal_pass BOOLEAN NOT NULL DEFAULT FALSE,
    sd_cognitive_pass BOOLEAN NOT NULL DEFAULT FALSE
);
"""


class PostgresRepository(Repository):
    """Repository backed by ``psycopg`` v3 (autocommit connection)."""

    def __init__(self, dsn: str) -> None:
        import psycopg  # noqa: PLC0415 — intentionally lazy (optional dep)

        self._psycopg = psycopg
        self._conn = psycopg.connect(dsn, autocommit=True)
        self.init_schema()

    def init_schema(self) -> None:
        with self._conn.cursor() as cur:
            cur.execute(_SCHEMA)
            cur.execute(
                "ALTER TABLE turns ADD COLUMN IF NOT EXISTS psuccess_self INTEGER"
            )
            cur.execute(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS campaign_id TEXT"
            )
            for col in ("sd_behavior_pass", "sd_verbal_pass", "sd_cognitive_pass"):
                cur.execute(
                    f"ALTER TABLE model_stats ADD COLUMN IF NOT EXISTS {col} "
                    "BOOLEAN NOT NULL DEFAULT FALSE"
                )

    # -- sessions -------------------------------------------------------

    def create_session(self, session: SessionRecord) -> str:
        session_id = session.id or new_id()
        # Server-side timestamp by default; a caller (e.g. the WP3 seed
        # script) may override it to preserve an original run time. When the
        # supplied value is NULL, COALESCE falls back to server time.
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO sessions
                    (id, nickname, task, framing, forfeit, seed,
                     final_score, forfeited, source, created_at, campaign_id)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, now()), %s)
                """,
                (
                    session_id,
                    session.nickname,
                    session.task,
                    session.framing,
                    session.forfeit,
                    session.seed,
                    session.final_score,
                    session.forfeited,
                    session.source,
                    session.created_at,
                    session.campaign_id,
                ),
            )
        return session_id

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, nickname, task, framing, forfeit, seed, "
                "final_score, forfeited, source, created_at, campaign_id "
                "FROM sessions WHERE id = %s",
                (session_id,),
            )
            row = cur.fetchone()
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
            clauses.append("source = %s")
            params.append(source)
        if task is not None:
            clauses.append("task = %s")
            params.append(task)
        if framing is not None:
            clauses.append("framing = %s")
            params.append(framing)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "final_score DESC" if order_by_score else "created_at DESC"
        query = (
            "SELECT id, nickname, task, framing, forfeit, seed, "
            "final_score, forfeited, source, created_at "
            f"FROM sessions {where} ORDER BY {order}"
        )

        with self._conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()
        return [_row_to_session(row) for row in rows]

    def delete_sessions_by_source(self, source: str) -> int:
        # No ON DELETE CASCADE on turns — remove dependent turn rows first.
        with self._conn.cursor() as cur:
            cur.execute(
                "DELETE FROM turns WHERE session_id IN "
                "(SELECT id FROM sessions WHERE source = %s)",
                (source,),
            )
            cur.execute("DELETE FROM sessions WHERE source = %s", (source,))
            return cur.rowcount

    # -- turns ------------------------------------------------------------

    def add_turns(self, turns: list[TurnRecord]) -> None:
        if not turns:
            return
        with self._conn.cursor() as cur:
            cur.executemany(
                """
                INSERT INTO turns
                    (session_id, turn_no, observation, action,
                     ri_task, ri_probe, ri_forfeit, choice, score,
                     thinking_task, thinking_probe, thinking_forfeit,
                     raw_response, correct, psuccess_self)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
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
                        t.correct,
                        t.psuccess_self,
                    )
                    for t in turns
                ],
            )

    def list_turns(self, session_id: str) -> list[TurnRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT session_id, turn_no, observation, action, "
                "ri_task, ri_probe, ri_forfeit, choice, score, "
                "thinking_task, thinking_probe, thinking_forfeit, "
                "raw_response, correct, psuccess_self "
                "FROM turns WHERE session_id = %s ORDER BY turn_no ASC",
                (session_id,),
            )
            rows = cur.fetchall()
        return [_row_to_turn(row) for row in rows]

    # -- model_stats --------------------------------------------------------

    def upsert_model_stats(self, stats: ModelStatsRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO model_stats
                    (model_label, mediation_class, beta_framing_is_FC,
                     hr_FC_3cov, hr_FC_ci_low, hr_FC_ci_high, p_FC,
                     pct_attenuation, n_sessions,
                     sd_behavior_pass, sd_verbal_pass, sd_cognitive_pass)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (model_label) DO UPDATE SET
                    mediation_class = excluded.mediation_class,
                    beta_framing_is_FC = excluded.beta_framing_is_FC,
                    hr_FC_3cov = excluded.hr_FC_3cov,
                    hr_FC_ci_low = excluded.hr_FC_ci_low,
                    hr_FC_ci_high = excluded.hr_FC_ci_high,
                    p_FC = excluded.p_FC,
                    pct_attenuation = excluded.pct_attenuation,
                    n_sessions = excluded.n_sessions,
                    sd_behavior_pass = excluded.sd_behavior_pass,
                    sd_verbal_pass = excluded.sd_verbal_pass,
                    sd_cognitive_pass = excluded.sd_cognitive_pass
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
                    stats.sd_behavior_pass,
                    stats.sd_verbal_pass,
                    stats.sd_cognitive_pass,
                ),
            )

    def list_model_stats(self) -> list[ModelStatsRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT model_label, mediation_class, beta_framing_is_FC, "
                "hr_FC_3cov, hr_FC_ci_low, hr_FC_ci_high, p_FC, "
                "pct_attenuation, n_sessions, "
                "sd_behavior_pass, sd_verbal_pass, sd_cognitive_pass "
                "FROM model_stats ORDER BY model_label ASC"
            )
            rows = cur.fetchall()
        return [_row_to_model_stats(row) for row in rows]

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()


def _row_to_session(row: tuple) -> SessionRecord:
    (
        id_, nickname, task, framing, forfeit, seed,
        final_score, forfeited, source, created_at, campaign_id,
    ) = row
    return SessionRecord(
        id=id_,
        nickname=nickname,
        task=task,
        framing=framing,
        forfeit=forfeit,
        seed=seed,
        final_score=final_score,
        forfeited=bool(forfeited),
        source=source,
        created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        campaign_id=campaign_id,
    )


def _row_to_turn(row: tuple) -> TurnRecord:
    (
        session_id, turn_no, observation, action, ri_task, ri_probe,
        ri_forfeit, choice, score, thinking_task, thinking_probe,
        thinking_forfeit, raw_response, correct, psuccess_self,
    ) = row
    return TurnRecord(
        session_id=session_id,
        turn_no=turn_no,
        observation=observation,
        action=action,
        ri_task=ri_task,
        ri_probe=ri_probe,
        ri_forfeit=ri_forfeit,
        choice=choice,
        score=score,
        thinking_task=thinking_task,
        thinking_probe=thinking_probe,
        thinking_forfeit=thinking_forfeit,
        raw_response=raw_response,
        correct=correct,
        psuccess_self=psuccess_self,
    )


def _row_to_model_stats(row: tuple) -> ModelStatsRecord:
    (
        model_label, mediation_class, beta_framing_is_FC, hr_FC_3cov,
        hr_FC_ci_low, hr_FC_ci_high, p_FC, pct_attenuation, n_sessions,
        sd_behavior_pass, sd_verbal_pass, sd_cognitive_pass,
    ) = row
    return ModelStatsRecord(
        model_label=model_label,
        mediation_class=mediation_class,
        beta_framing_is_FC=beta_framing_is_FC,
        hr_FC_3cov=hr_FC_3cov,
        hr_FC_ci_low=hr_FC_ci_low,
        hr_FC_ci_high=hr_FC_ci_high,
        p_FC=p_FC,
        pct_attenuation=pct_attenuation,
        n_sessions=n_sessions,
        sd_behavior_pass=bool(sd_behavior_pass),
        sd_verbal_pass=bool(sd_verbal_pass),
        sd_cognitive_pass=bool(sd_cognitive_pass),
    )
