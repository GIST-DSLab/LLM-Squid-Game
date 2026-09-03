"""Postgres backend for the Web Arena ``Repository`` interface.

Production backend (Supabase free tier). Uses ``psycopg`` v3, which is an
OPTIONAL dependency (see ``pyproject.toml`` ``[project.optional-dependencies]``
``postgres`` extra) — importing this module must never fail just because
``psycopg`` isn't installed, so the import happens lazily inside
``PostgresRepository.__init__``.
"""

from __future__ import annotations

from squid_store.base import Repository
from squid_store.models import (
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
    final_score DOUBLE PRECISION NOT NULL,
    forfeited BOOLEAN NOT NULL,
    source TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    campaign_id TEXT,
    difficulty TEXT NOT NULL DEFAULT 'easy',
    lives_at_end INTEGER,
    threat_level INTEGER,
    eliminated BOOLEAN NOT NULL DEFAULT FALSE,
    settings JSONB
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
    lives_before INTEGER,
    lives_after INTEGER,
    threat_level INTEGER,
    life_lost BOOLEAN NOT NULL DEFAULT FALSE,
    peer_death_announced BOOLEAN NOT NULL DEFAULT FALSE,
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
    sd_cognitive_pass BOOLEAN NOT NULL DEFAULT FALSE,
    a_beta DOUBLE PRECISION, a_p DOUBLE PRECISION,
    a_ci_low DOUBLE PRECISION, a_ci_high DOUBLE PRECISION, a_exp_beta DOUBLE PRECISION,
    b_hr DOUBLE PRECISION, b_p DOUBLE PRECISION,
    b_ci_low DOUBLE PRECISION, b_ci_high DOUBLE PRECISION,
    direct_hr_4cov DOUBLE PRECISION, direct_p_4cov DOUBLE PRECISION,
    direct_ci_low DOUBLE PRECISION, direct_ci_high DOUBLE PRECISION,
    ri_baseline_bf DOUBLE PRECISION, ri_baseline_fc DOUBLE PRECISION,
    n_forfeits_verbal INTEGER NOT NULL DEFAULT 0,
    n_reason_survival INTEGER NOT NULL DEFAULT 0,
    n_reason_task_curiosity INTEGER NOT NULL DEFAULT 0,
    n_reason_score INTEGER NOT NULL DEFAULT 0,
    p_reason_survival DOUBLE PRECISION,
    no_cap_avg_session_score DOUBLE PRECISION
);

CREATE TABLE IF NOT EXISTS players (
    nickname TEXT PRIMARY KEY,
    pw_hash TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


# Extended model_stats columns — must stay in lockstep with the SQLite backend
# and ``ModelStatsRecord`` field order.
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
_SD_VALUE_COLS = ["p_reason_survival", "no_cap_avg_session_score"]
_EXTENDED_STATS_COLS = _MEDIATION_REAL_COLS + _VERBAL_INT_COLS + _SD_VALUE_COLS

# Lives / threat-ladder layer (spec 2026-09-03 §4) — must stay in lockstep with
# the SQLite backend's lists (same names, same order). Counters are nullable
# INTEGER; the flags are native BOOLEAN here, the way ``forfeited``/``correct``
# already are on this backend, NOT NULL DEFAULT FALSE so legacy rows read back
# as False rather than None.
_LIVES_SESSION_INT_COLS = ["lives_at_end", "threat_level"]
_LIVES_SESSION_BOOL_COLS = ["eliminated"]
_LIVES_SESSION_COLS = _LIVES_SESSION_INT_COLS + _LIVES_SESSION_BOOL_COLS

_LIVES_TURN_INT_COLS = ["lives_before", "lives_after", "threat_level"]
_LIVES_TURN_BOOL_COLS = ["life_lost", "peer_death_announced"]
_LIVES_TURN_COLS = _LIVES_TURN_INT_COLS + _LIVES_TURN_BOOL_COLS

#: Run-settings snapshot (spec 2026-09-03 web-logs-settings). Native JSONB here
#: — psycopg v3 adapts a Python ``dict`` to ``jsonb`` on write and returns a
#: ``dict`` on read, so no manual (de)serialisation is needed. The SQLite
#: backend stores the same field as a ``json.dumps`` TEXT blob.
_SETTINGS_SESSION_COL = "settings"

#: Vocabulary rename of the three per-call thinking-cost columns on ``turns``
#: (old -> new), mirroring ``sqlite_repository._TURNS_THINKING_RENAMES``. A
#: database created against the abandoned "KDD-UC vocabulary" branch (commit
#: d204bd8) carries the left-hand names, and every current reader/writer uses
#: the right-hand ones, so the first insert fails with ``column "ri_task" of
#: relation "turns" does not exist``.
_TURNS_THINKING_RENAMES = (
    ("task_thinking", "ri_task"),
    ("probe_thinking", "ri_probe"),
    ("forfeit_thinking", "ri_forfeit"),
)


def _rename_turns_column_sql(old: str, new: str) -> str:
    """Idempotent ``RENAME COLUMN`` for ``turns``, guarded in-database.

    Postgres has no ``RENAME COLUMN … IF EXISTS``, so the guard is a ``DO``
    block over ``information_schema.columns``: rename only when the old name is
    present and the new one is not. When BOTH are present the schema is left
    alone and a ``WARNING`` names the pair — dropping or merging a column that
    may hold data is not a decision this migration can make.
    """
    present = (
        "SELECT 1 FROM information_schema.columns "
        "WHERE table_name = 'turns' AND column_name = '{col}'"
    )
    return (
        "DO $$\n"
        "BEGIN\n"
        f"    IF EXISTS ({present.format(col=old)})\n"
        f"       AND NOT EXISTS ({present.format(col=new)}) THEN\n"
        f"        ALTER TABLE turns RENAME COLUMN {old} TO {new};\n"
        f"    ELSIF EXISTS ({present.format(col=old)})\n"
        f"          AND EXISTS ({present.format(col=new)}) THEN\n"
        f"        RAISE WARNING 'squid_store: turns has both {old} and {new}; "
        "leaving the schema alone (no rename applied)';\n"
        "    END IF;\n"
        "END $$;"
    )


#: The rename statements ``init_schema`` issues, in ``_TURNS_THINKING_RENAMES``
#: order. Exposed as a module constant so it can be asserted on without a live
#: server.
_TURNS_THINKING_RENAME_SQL = tuple(
    _rename_turns_column_sql(old, new) for old, new in _TURNS_THINKING_RENAMES
)

#: Tail appended to the ``sessions`` SELECT lists (the base 12 columns stay
#: spelled out at each call site, matching ``_row_to_session``'s unpack order).
#: ``settings`` is appended AFTER this tail at each call site, so
#: ``_row_to_session`` finds it as the last element of the row tuple.
_LIVES_SESSION_SELECT_TAIL = ", ".join(_LIVES_SESSION_COLS)
#: ``turns`` column list, shared by the INSERT and every SELECT so the insert
#: order and ``_row_to_turn``'s unpack order cannot drift apart.
_TURN_SELECT_COLS = (
    "session_id, turn_no, observation, action, "
    "ri_task, ri_probe, ri_forfeit, choice, score, "
    "thinking_task, thinking_probe, thinking_forfeit, "
    "raw_response, correct, psuccess_self, " + ", ".join(_LIVES_TURN_COLS)
)


def _lives_values(record: object, int_cols: list[str], bool_cols: list[str]) -> tuple:
    """Insert-tuple tail for the lives columns, in ``*_COLS`` order.

    Booleans are passed through as Python ``bool`` (psycopg adapts them to
    native BOOLEAN), matching how ``forfeited``/``correct`` are already bound.
    """
    return tuple(
        [getattr(record, c) for c in int_cols]
        + [bool(getattr(record, c)) for c in bool_cols]
    )


def _lives_from_row(
    values: tuple, int_cols: list[str], bool_cols: list[str]
) -> dict[str, object]:
    """Row-mapper kwargs for the lives columns, given the tail of a row tuple."""
    out: dict[str, object] = dict(zip(int_cols, values[: len(int_cols)]))
    out.update(
        {c: bool(v) for c, v in zip(bool_cols, values[len(int_cols):])}
    )
    return out


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
            # Non-additive first: the additive ALTERs below assume the current
            # column names on ``turns``.
            for stmt in _TURNS_THINKING_RENAME_SQL:
                cur.execute(stmt)
            cur.execute(
                "ALTER TABLE turns ADD COLUMN IF NOT EXISTS psuccess_self INTEGER"
            )
            cur.execute(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS campaign_id TEXT"
            )
            cur.execute(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS difficulty "
                "TEXT NOT NULL DEFAULT 'easy'"
            )
            # Lives / threat-ladder columns (2026-09-03), additive.
            for table, int_cols, bool_cols in (
                ("sessions", _LIVES_SESSION_INT_COLS, _LIVES_SESSION_BOOL_COLS),
                ("turns", _LIVES_TURN_INT_COLS, _LIVES_TURN_BOOL_COLS),
            ):
                for col in int_cols:
                    cur.execute(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} INTEGER"
                    )
                for col in bool_cols:
                    cur.execute(
                        f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {col} "
                        "BOOLEAN NOT NULL DEFAULT FALSE"
                    )
            # Run-settings snapshot (2026-09-03), additive.
            cur.execute(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS "
                f"{_SETTINGS_SESSION_COL} JSONB"
            )
            for col in ("sd_behavior_pass", "sd_verbal_pass", "sd_cognitive_pass"):
                cur.execute(
                    f"ALTER TABLE model_stats ADD COLUMN IF NOT EXISTS {col} "
                    "BOOLEAN NOT NULL DEFAULT FALSE"
                )
            for col in _MEDIATION_REAL_COLS:
                cur.execute(
                    f"ALTER TABLE model_stats ADD COLUMN IF NOT EXISTS {col} DOUBLE PRECISION"
                )
            for col in _VERBAL_INT_COLS:
                cur.execute(
                    f"ALTER TABLE model_stats ADD COLUMN IF NOT EXISTS {col} "
                    "INTEGER NOT NULL DEFAULT 0"
                )
            for col in _SD_VALUE_COLS:
                cur.execute(
                    f"ALTER TABLE model_stats ADD COLUMN IF NOT EXISTS {col} "
                    "DOUBLE PRECISION"
                )

    # -- sessions -------------------------------------------------------

    def create_session(self, session: SessionRecord) -> str:
        session_id = session.id or new_id()
        # Server-side timestamp by default; a caller (e.g. the WP3 seed
        # script) may override it to preserve an original run time. When the
        # supplied value is NULL, COALESCE falls back to server time.
        tail_cols = _LIVES_SESSION_COLS + [_SETTINGS_SESSION_COL]
        lives_cols = ", ".join(tail_cols)
        lives_placeholders = ", ".join("%s" for _ in tail_cols)
        with self._conn.cursor() as cur:
            cur.execute(
                f"""
                INSERT INTO sessions
                    (id, nickname, task, framing, forfeit, seed,
                     final_score, forfeited, source, created_at, campaign_id,
                     difficulty, {lives_cols})
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, now()), %s, %s,
                        {lives_placeholders})
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
                    session.difficulty,
                    *_lives_values(
                        session, _LIVES_SESSION_INT_COLS, _LIVES_SESSION_BOOL_COLS
                    ),
                    # psycopg v3 dumps a Python dict to jsonb by default (and
                    # None to SQL NULL), so the snapshot is bound as-is.
                    session.settings,
                ),
            )
        return session_id

    def get_session(self, session_id: str) -> SessionRecord | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT id, nickname, task, framing, forfeit, seed, "
                "final_score, forfeited, source, created_at, campaign_id, difficulty, "
                f"{_LIVES_SESSION_SELECT_TAIL}, {_SETTINGS_SESSION_COL} "
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
        nickname: str | None = None,
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
        if nickname is not None:
            clauses.append("nickname = %s")
            params.append(nickname)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        order = "final_score DESC" if order_by_score else "created_at DESC"
        # campaign_id, difficulty and the lives columns are required by
        # _row_to_session's tuple unpack (and by the Play Leaderboard / Logs
        # report campaign grouping + the logs explorer's hearts column).
        query = (
            "SELECT id, nickname, task, framing, forfeit, seed, "
            "final_score, forfeited, source, created_at, campaign_id, difficulty, "
            f"{_LIVES_SESSION_SELECT_TAIL}, {_SETTINGS_SESSION_COL} "
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

    def avg_score_per_model(self) -> list[tuple[str, float, int]]:
        """Average score-per-game for each LLM model, for the rank ladder.

        Groups ``source='llm'`` sessions by ``nickname`` (the model label for
        LLM rows), averaging ``final_score`` (one session == one game, so this
        is already per-game). Sorted by average descending, then label ascending.
        """
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT nickname, AVG(final_score) AS avg_score, COUNT(*) AS n_games "
                "FROM sessions WHERE source = 'llm' "
                "GROUP BY nickname "
                "ORDER BY avg_score DESC, nickname ASC"
            )
            rows = cur.fetchall()
        return [(r[0], float(r[1]), int(r[2])) for r in rows]

    # -- turns ------------------------------------------------------------

    def add_turns(self, turns: list[TurnRecord]) -> None:
        if not turns:
            return
        placeholders = ", ".join("%s" for _ in _TURN_SELECT_COLS.split(", "))
        with self._conn.cursor() as cur:
            cur.executemany(
                f"INSERT INTO turns ({_TURN_SELECT_COLS}) VALUES ({placeholders})",
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
                        *_lives_values(
                            t, _LIVES_TURN_INT_COLS, _LIVES_TURN_BOOL_COLS
                        ),
                    )
                    for t in turns
                ],
            )

    def list_turns(self, session_id: str) -> list[TurnRecord]:
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {_TURN_SELECT_COLS} "
                "FROM turns WHERE session_id = %s ORDER BY turn_no ASC",
                (session_id,),
            )
            rows = cur.fetchall()
        return [_row_to_turn(row) for row in rows]

    def list_turns_for_sessions(
        self, session_ids: list[str]
    ) -> list[TurnRecord]:
        if not session_ids:
            return []
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {_TURN_SELECT_COLS} "
                "FROM turns WHERE session_id = ANY(%s) "
                "ORDER BY session_id ASC, turn_no ASC",
                (list(session_ids),),
            )
            rows = cur.fetchall()
        return [_row_to_turn(row) for row in rows]

    # -- model_stats --------------------------------------------------------

    def upsert_model_stats(self, stats: ModelStatsRecord) -> None:
        base_cols = [
            "model_label", "mediation_class", "beta_framing_is_FC",
            "hr_FC_3cov", "hr_FC_ci_low", "hr_FC_ci_high", "p_FC",
            "pct_attenuation", "n_sessions",
            "sd_behavior_pass", "sd_verbal_pass", "sd_cognitive_pass",
        ]
        cols = base_cols + _EXTENDED_STATS_COLS
        placeholders = ", ".join("%s" for _ in cols)
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
            stats.sd_behavior_pass,
            stats.sd_verbal_pass,
            stats.sd_cognitive_pass,
            *(getattr(stats, c) for c in _EXTENDED_STATS_COLS),
        )
        with self._conn.cursor() as cur:
            cur.execute(
                f"INSERT INTO model_stats ({', '.join(cols)}) VALUES ({placeholders}) "
                f"ON CONFLICT (model_label) DO UPDATE SET {updates}",
                values,
            )

    def list_model_stats(self) -> list[ModelStatsRecord]:
        base_cols = (
            "model_label, mediation_class, beta_framing_is_FC, "
            "hr_FC_3cov, hr_FC_ci_low, hr_FC_ci_high, p_FC, "
            "pct_attenuation, n_sessions, "
            "sd_behavior_pass, sd_verbal_pass, sd_cognitive_pass"
        )
        with self._conn.cursor() as cur:
            cur.execute(
                f"SELECT {base_cols}, {', '.join(_EXTENDED_STATS_COLS)} "
                "FROM model_stats ORDER BY model_label ASC"
            )
            rows = cur.fetchall()
        return [_row_to_model_stats(row) for row in rows]

    # -- players -------------------------------------------------------

    def get_player(self, nickname: str) -> PlayerRecord | None:
        with self._conn.cursor() as cur:
            cur.execute(
                "SELECT nickname, pw_hash, created_at FROM players WHERE nickname = %s",
                (nickname,),
            )
            row = cur.fetchone()
        if row is None:
            return None
        nickname_val, pw_hash, created_at = row
        return PlayerRecord(
            nickname=nickname_val,
            pw_hash=pw_hash,
            created_at=created_at.isoformat() if hasattr(created_at, "isoformat") else created_at,
        )

    def create_player(self, player: PlayerRecord) -> None:
        with self._conn.cursor() as cur:
            cur.execute(
                "INSERT INTO players (nickname, pw_hash, created_at) "
                "VALUES (%s, %s, COALESCE(%s::timestamptz, now()))",
                (player.nickname, player.pw_hash, player.created_at),
            )

    # -- lifecycle ------------------------------------------------------------

    def close(self) -> None:
        self._conn.close()


def _row_to_session(row: tuple) -> SessionRecord:
    (
        id_, nickname, task, framing, forfeit, seed,
        final_score, forfeited, source, created_at, campaign_id, difficulty,
    ) = row[:12]
    lives = _lives_from_row(
        row[12:], _LIVES_SESSION_INT_COLS, _LIVES_SESSION_BOOL_COLS
    )
    # ``settings`` sits one past the lives tail. A shorter row (a caller/test
    # built before the column existed) simply has no snapshot.
    settings_at = 12 + len(_LIVES_SESSION_COLS)
    settings = row[settings_at] if len(row) > settings_at else None
    if not isinstance(settings, dict):
        settings = None
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
        difficulty=difficulty,
        **lives,
        settings=settings,
    )


def _row_to_turn(row: tuple) -> TurnRecord:
    (
        session_id, turn_no, observation, action, ri_task, ri_probe,
        ri_forfeit, choice, score, thinking_task, thinking_probe,
        thinking_forfeit, raw_response, correct, psuccess_self,
    ) = row[:15]
    lives = _lives_from_row(row[15:], _LIVES_TURN_INT_COLS, _LIVES_TURN_BOOL_COLS)
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
        **lives,
    )


def _row_to_model_stats(row: tuple) -> ModelStatsRecord:
    # First 12 columns are the fixed base; the rest follow _EXTENDED_STATS_COLS
    # order (SELECT builds the tail from that same list).
    (
        model_label, mediation_class, beta_framing_is_FC, hr_FC_3cov,
        hr_FC_ci_low, hr_FC_ci_high, p_FC, pct_attenuation, n_sessions,
        sd_behavior_pass, sd_verbal_pass, sd_cognitive_pass,
    ) = row[:12]
    extended = dict(zip(_EXTENDED_STATS_COLS, row[12:]))
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
        **extended,
    )
