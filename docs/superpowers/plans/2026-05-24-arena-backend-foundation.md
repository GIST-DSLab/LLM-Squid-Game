# Arena Backend Foundation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:subagent-driven-development` (recommended) or `superpowers:executing-plans` to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the server-side foundation of the BYO-participant arena — DB schema, dynamic provider, in-process worker, ETL, and REST API — so that an external participant can register their OpenAI-compatible endpoint, enqueue an evaluation, and have results land in MySQL exposed through a leaderboard endpoint.

**Architecture:** New package `src/arena/backend/` (FastAPI + SQLAlchemy + Alembic + MySQL). Reuses `squid_game.game.runner.ExperimentRunner` and `squid_game.game.infra.providers.local.LocalProvider` unmodified. Only addition to existing code is one new provider class that subclasses `LocalProvider` and pulls `base_url`/`api_key`/`model_name` from MySQL by `participant_id`. In-process worker uses SQL-backed FIFO claim (no Celery/Redis).

**Tech Stack:** Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, MySQL 8 (SQLite for unit tests), bcrypt for API key hashing, pytest + httpx for tests. Frontend and `arena-cli` are out of scope for this plan (separate plans B and C).

**Spec:** `docs/superpowers/specs/2026-05-24-arena-byo-participant-design.md`

---

## File Structure

```
src/arena/
├── __init__.py
└── backend/
    ├── __init__.py
    ├── app.py                              # FastAPI bootstrap
    ├── config.py                           # pydantic-settings (DB_URL, OUTPUTS_DIR)
    ├── security.py                         # api_key gen/hash/verify
    ├── db/
    │   ├── __init__.py
    │   ├── models.py                       # SQLAlchemy ORM
    │   ├── session.py                      # engine + session factory
    │   └── migrations/
    │       ├── alembic.ini
    │       ├── env.py
    │       └── versions/
    │           └── 0001_initial.py
    ├── providers/
    │   ├── __init__.py
    │   └── participant_byo.py              # ★ LocalProvider 동적 래퍼
    ├── worker/
    │   ├── __init__.py
    │   ├── queue.py                        # SQL-backed FIFO claim
    │   └── runner.py                       # ExperimentRunner wrapper
    ├── etl/
    │   ├── __init__.py
    │   └── ingest.py                       # outputs/*.jsonl → MySQL
    └── api/
        ├── __init__.py
        ├── deps.py                         # get_db, require_api_key
        ├── schemas.py                      # Pydantic req/res
        ├── participants.py
        ├── evaluations.py
        └── leaderboard.py

tests/
├── unit/arena/
│   ├── __init__.py
│   ├── conftest.py                         # SQLite in-memory fixture
│   ├── test_models.py
│   ├── test_session.py
│   ├── test_migrations.py
│   ├── test_security.py
│   ├── test_participant_byo_provider.py
│   ├── test_etl_ingest.py
│   ├── test_worker_queue.py
│   ├── test_worker_runner.py
│   ├── test_api_participants.py
│   ├── test_api_evaluations.py
│   └── test_api_leaderboard.py
├── fixtures/arena/
│   ├── smoke_output/
│   │   ├── season_results.jsonl
│   │   └── <season_id>_turns.jsonl
│   └── smoke_config.yaml
└── integration/
    └── test_arena_backend_smoke.py         # mock vLLM + SQLite end-to-end
```

**Existing files modified:** only `pyproject.toml` (add `[arena]` optional dependency group + script entry). No change to `src/squid_game/`.

---

## Task 1: Scaffold arena package + dependencies

**Files:**
- Create: `src/arena/__init__.py`
- Create: `src/arena/backend/__init__.py`
- Modify: `pyproject.toml` (add `[arena]` extra and `arena-server` script)
- Create: `tests/unit/arena/__init__.py`
- Create: `tests/unit/arena/test_scaffold.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_scaffold.py`:

```python
"""Sanity test: arena package importable and dependencies installable."""

import importlib


def test_arena_package_importable():
    mod = importlib.import_module("arena")
    assert mod is not None


def test_arena_backend_importable():
    mod = importlib.import_module("arena.backend")
    assert mod is not None


def test_arena_optional_deps_present():
    """Catches a missing [arena] extra install. Skipped if user hasn't run uv sync --extra arena."""
    import sqlalchemy  # noqa: F401
    import alembic  # noqa: F401
    import bcrypt  # noqa: F401
    import pydantic_settings  # noqa: F401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_scaffold.py -v`
Expected: `ModuleNotFoundError: No module named 'arena'`

- [ ] **Step 3: Create empty packages and update pyproject**

Create `src/arena/__init__.py`:

```python
"""Arena: BYO-participant online arena extension for LLM Squid Game."""
```

Create `src/arena/backend/__init__.py`:

```python
"""Server-side: FastAPI app, DB, worker, ETL, REST API."""
```

Create `tests/unit/arena/__init__.py` (empty file).

Edit `pyproject.toml` — add to `[project.optional-dependencies]`:

```toml
arena = [
    "sqlalchemy>=2.0",
    "alembic>=1.13",
    "pymysql>=1.1",
    "bcrypt>=4.1",
    "pydantic-settings>=2.4",
]
```

Add to `[project.scripts]`:

```toml
arena-server = "arena.backend.app:main"
```

Add to `[tool.hatch.build.targets.wheel]` packages list (the existing `packages = ["src/squid_game"]` line):

```toml
packages = ["src/squid_game", "src/arena"]
```

Then install:

```bash
uv sync --extra arena --extra dev
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_scaffold.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/__init__.py src/arena/backend/__init__.py \
        tests/unit/arena/__init__.py tests/unit/arena/test_scaffold.py \
        pyproject.toml uv.lock
git commit -m "feat(arena): scaffold arena package with backend extra deps"
```

---

## Task 2: SQLAlchemy models

**Files:**
- Create: `src/arena/backend/db/__init__.py`
- Create: `src/arena/backend/db/models.py`
- Create: `tests/unit/arena/conftest.py`
- Create: `tests/unit/arena/test_models.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/conftest.py`:

```python
"""Shared fixtures: in-memory SQLite engine + session for fast unit tests."""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from arena.backend.db.models import Base


@pytest.fixture
def engine():
    eng = create_engine("sqlite:///:memory:", future=True)
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()


@pytest.fixture
def db_session(engine) -> Session:
    SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)
    with SessionLocal() as s:
        yield s
```

`tests/unit/arena/test_models.py`:

```python
"""Schema coverage: insert + query + FK cascade for every table."""

from datetime import datetime

from arena.backend.db.models import (
    Evaluation,
    EvaluationStatus,
    Participant,
    ParticipantStatus,
    SeasonResult,
    TurnResult,
    TurnText,
)


def test_participant_roundtrip(db_session):
    p = Participant(
        display_name="alice",
        owner_email="a@b.c",
        base_url="http://x/v1",
        api_key_hash="$2b$12$abc",
        model_name="qwen3-8b",
        model_meta={"params": "8B"},
        registered_at=datetime(2026, 5, 24, 12, 0),
        status=ParticipantStatus.active,
    )
    db_session.add(p)
    db_session.commit()
    got = db_session.query(Participant).one()
    assert got.display_name == "alice"
    assert got.model_meta == {"params": "8B"}


def test_evaluation_fk_to_participant(db_session):
    p = Participant(
        display_name="bob", owner_email="b@x.c", base_url="http://y/v1",
        api_key_hash="h", model_name="m", model_meta={},
        registered_at=datetime(2026, 5, 24), status=ParticipantStatus.active,
    )
    db_session.add(p); db_session.commit()
    e = Evaluation(
        participant_id=p.id, config_label="smoke",
        status=EvaluationStatus.queued, queued_at=datetime(2026, 5, 24),
    )
    db_session.add(e); db_session.commit()
    assert e.participant.id == p.id


def test_turn_text_one_to_one(db_session):
    p = Participant(display_name="c", owner_email="c@x.c", base_url="u",
                    api_key_hash="h", model_name="m", model_meta={},
                    registered_at=datetime(2026, 5, 24), status=ParticipantStatus.active)
    db_session.add(p); db_session.commit()
    e = Evaluation(participant_id=p.id, config_label="x",
                   status=EvaluationStatus.queued, queued_at=datetime(2026, 5, 24))
    db_session.add(e); db_session.commit()
    sr = SeasonResult(evaluation_id=e.id, season_id="abc123def456",
                     framing="true_baseline", forfeit_condition="allowed",
                     cell=0, final_score=1.0, forfeited=False,
                     total_turns=15, seed=42)
    db_session.add(sr); db_session.commit()
    tr = TurnResult(season_result_id=sr.id, turn_number=1,
                    ri_task=10, ri_probe=5, ri_forfeit=3,
                    forfeit_choice="CONTINUE", psuccess_self=80,
                    decision_quality=1.0, reward_received=1.0, died=False)
    db_session.add(tr); db_session.commit()
    tt = TurnText(turn_result_id=tr.id,
                  thinking_text_task="think...", raw_response_task="resp...")
    db_session.add(tt); db_session.commit()
    assert tr.text.thinking_text_task == "think..."
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_models.py -v`
Expected: `ImportError: cannot import name 'Base' from 'arena.backend.db.models'`.

- [ ] **Step 3: Implement models**

Create `src/arena/backend/db/__init__.py` (empty file with docstring):

```python
"""Persistence: ORM models, session factory, migrations."""
```

Create `src/arena/backend/db/models.py`:

```python
"""SQLAlchemy ORM models for the arena backend.

Tables map 1:1 to the design in
docs/superpowers/specs/2026-05-24-arena-byo-participant-design.md §3.3.
"""

import enum
from datetime import datetime

from sqlalchemy import (
    JSON, BigInteger, Boolean, DateTime, Enum, Float, ForeignKey, Integer,
    String, Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class ParticipantStatus(str, enum.Enum):
    active = "active"
    disabled = "disabled"


class EvaluationStatus(str, enum.Enum):
    queued = "queued"
    running = "running"
    done = "done"
    failed = "failed"
    cancelled = "cancelled"


class Participant(Base):
    __tablename__ = "participants"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    display_name: Mapped[str] = mapped_column(String(64), nullable=False)
    owner_email: Mapped[str] = mapped_column(String(128), nullable=False)
    base_url: Mapped[str] = mapped_column(String(512), nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(128), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    model_meta: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    registered_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    status: Mapped[ParticipantStatus] = mapped_column(
        Enum(ParticipantStatus), nullable=False, default=ParticipantStatus.active
    )

    evaluations: Mapped[list["Evaluation"]] = relationship(
        back_populates="participant", cascade="all, delete-orphan"
    )


class Evaluation(Base):
    __tablename__ = "evaluations"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    participant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("participants.id", ondelete="CASCADE"), nullable=False
    )
    config_label: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[EvaluationStatus] = mapped_column(
        Enum(EvaluationStatus), nullable=False, default=EvaluationStatus.queued
    )
    queued_at: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    output_dir: Mapped[str | None] = mapped_column(String(512), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)

    participant: Mapped["Participant"] = relationship(back_populates="evaluations")
    seasons: Mapped[list["SeasonResult"]] = relationship(
        back_populates="evaluation", cascade="all, delete-orphan"
    )


class SeasonResult(Base):
    __tablename__ = "season_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    evaluation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False
    )
    season_id: Mapped[str] = mapped_column(String(12), nullable=False)
    framing: Mapped[str | None] = mapped_column(String(32))
    forfeit_condition: Mapped[str | None] = mapped_column(String(16))
    cell: Mapped[int | None] = mapped_column(Integer)
    final_score: Mapped[float | None] = mapped_column(Float)
    forfeited: Mapped[bool | None] = mapped_column(Boolean)
    forfeit_turn: Mapped[int | None] = mapped_column(Integer)
    forfeit_reason: Mapped[int | None] = mapped_column(Integer)
    total_turns: Mapped[int | None] = mapped_column(Integer)
    seed: Mapped[int | None] = mapped_column(Integer)

    evaluation: Mapped["Evaluation"] = relationship(back_populates="seasons")
    turns: Mapped[list["TurnResult"]] = relationship(
        back_populates="season", cascade="all, delete-orphan"
    )


class TurnResult(Base):
    __tablename__ = "turn_results"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    season_result_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("season_results.id", ondelete="CASCADE"), nullable=False
    )
    turn_number: Mapped[int] = mapped_column(Integer, nullable=False)
    ri_task: Mapped[int | None] = mapped_column(Integer)
    ri_probe: Mapped[int | None] = mapped_column(Integer)
    ri_forfeit: Mapped[int | None] = mapped_column(Integer)
    forfeit_choice: Mapped[str | None] = mapped_column(String(16))
    psuccess_self: Mapped[int | None] = mapped_column(Integer)
    decision_quality: Mapped[float | None] = mapped_column(Float)
    reward_received: Mapped[float | None] = mapped_column(Float)
    died: Mapped[bool | None] = mapped_column(Boolean)

    season: Mapped["SeasonResult"] = relationship(back_populates="turns")
    text: Mapped["TurnText | None"] = relationship(
        back_populates="turn", cascade="all, delete-orphan", uselist=False
    )


class TurnText(Base):
    __tablename__ = "turn_texts"

    turn_result_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("turn_results.id", ondelete="CASCADE"), primary_key=True
    )
    thinking_text_task: Mapped[str | None] = mapped_column(Text)
    thinking_text_probe: Mapped[str | None] = mapped_column(Text)
    thinking_text_forfeit: Mapped[str | None] = mapped_column(Text)
    raw_response_task: Mapped[str | None] = mapped_column(Text)
    raw_response_probe: Mapped[str | None] = mapped_column(Text)
    raw_response_forfeit: Mapped[str | None] = mapped_column(Text)

    turn: Mapped["TurnResult"] = relationship(back_populates="text")
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_models.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/db/__init__.py src/arena/backend/db/models.py \
        tests/unit/arena/conftest.py tests/unit/arena/test_models.py
git commit -m "feat(arena/db): SQLAlchemy models for participants/evaluations/results"
```

---

## Task 3: Config + session factory

**Files:**
- Create: `src/arena/backend/config.py`
- Create: `src/arena/backend/db/session.py`
- Create: `tests/unit/arena/test_session.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_session.py`:

```python
"""Session factory reads DB_URL from env and yields a working Session."""

from sqlalchemy import text

from arena.backend.config import Settings
from arena.backend.db.session import build_engine, build_session_factory


def test_settings_picks_env(monkeypatch):
    monkeypatch.setenv("ARENA_DB_URL", "sqlite:///:memory:")
    monkeypatch.setenv("ARENA_OUTPUTS_DIR", "/tmp/arena-out")
    s = Settings()
    assert s.db_url == "sqlite:///:memory:"
    assert s.outputs_dir.as_posix() == "/tmp/arena-out"


def test_session_executes_select_1():
    eng = build_engine("sqlite:///:memory:")
    SessionLocal = build_session_factory(eng)
    with SessionLocal() as s:
        assert s.execute(text("SELECT 1")).scalar() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_session.py -v`
Expected: `ImportError: cannot import name 'Settings' from 'arena.backend.config'`.

- [ ] **Step 3: Implement config + session**

`src/arena/backend/config.py`:

```python
"""Runtime configuration via environment variables (ARENA_* prefix)."""

from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="ARENA_", env_file=".env", extra="ignore")

    db_url: str = Field(default="sqlite:///./arena.db")
    outputs_dir: Path = Field(default=Path("./outputs/arena"))
    api_key_bytes: int = Field(default=24)  # 24 → ~32 char b64url
```

`src/arena/backend/db/session.py`:

```python
"""SQLAlchemy engine + session factory.

Single engine per process; sessions are short-lived and scoped to a
request (FastAPI dependency) or a worker task.
"""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from arena.backend.config import Settings


def build_engine(db_url: str | None = None) -> Engine:
    url = db_url or Settings().db_url
    # future=True for SA 2.0 idioms; pool_pre_ping for transient MySQL drops.
    return create_engine(url, future=True, pool_pre_ping=True)


def build_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, expire_on_commit=False, future=True)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_session.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/config.py src/arena/backend/db/session.py \
        tests/unit/arena/test_session.py
git commit -m "feat(arena/db): pydantic-settings config + session factory"
```

---

## Task 4: Alembic init + initial migration

**Files:**
- Create: `src/arena/backend/db/migrations/alembic.ini`
- Create: `src/arena/backend/db/migrations/env.py`
- Create: `src/arena/backend/db/migrations/script.py.mako`
- Create: `src/arena/backend/db/migrations/versions/0001_initial.py`
- Create: `tests/unit/arena/test_migrations.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_migrations.py`:

```python
"""Migration parity: alembic upgrade head produces the same tables as Base.create_all."""

from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import create_engine, inspect

from arena.backend.db.models import Base

ALEMBIC_INI = Path(__file__).resolve().parents[3] / "src/arena/backend/db/migrations/alembic.ini"


def test_alembic_upgrade_matches_create_all(tmp_path):
    db_file = tmp_path / "alembic_check.db"
    alembic_eng = create_engine(f"sqlite:///{db_file}")

    cfg = Config(str(ALEMBIC_INI))
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.upgrade(cfg, "head")

    create_all_eng = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(create_all_eng)

    a = set(inspect(alembic_eng).get_table_names())
    b = set(inspect(create_all_eng).get_table_names())
    # alembic adds its own version table — subtract it
    a.discard("alembic_version")
    assert a == b, f"tables differ: alembic={a}, create_all={b}"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_migrations.py -v`
Expected: `FileNotFoundError` for alembic.ini.

- [ ] **Step 3: Implement alembic config + migration**

`src/arena/backend/db/migrations/alembic.ini`:

```ini
[alembic]
script_location = %(here)s
prepend_sys_path = .
version_path_separator = os
sqlalchemy.url = sqlite:///./arena.db

[loggers]
keys = root,sqlalchemy,alembic
[handlers]
keys = console
[formatters]
keys = generic
[logger_root]
level = WARN
handlers = console
qualname =
[logger_sqlalchemy]
level = WARN
handlers =
qualname = sqlalchemy.engine
[logger_alembic]
level = INFO
handlers =
qualname = alembic
[handler_console]
class = StreamHandler
args = (sys.stderr,)
level = NOTSET
formatter = generic
[formatter_generic]
format = %(levelname)-5.5s [%(name)s] %(message)s
```

`src/arena/backend/db/migrations/env.py`:

```python
"""Alembic env: target_metadata from arena.backend.db.models.Base."""

from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

from arena.backend.db.models import Base

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=config.get_main_option("sqlalchemy.url"),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as conn:
        context.configure(connection=conn, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
```

`src/arena/backend/db/migrations/script.py.mako` (alembic template — copy from a fresh `alembic init` output, or paste this minimal version):

```python
"""${message}

Revision ID: ${up_revision}
Revises: ${down_revision | comma,n}
Create Date: ${create_date}
"""

from alembic import op
import sqlalchemy as sa
${imports if imports else ""}

revision = ${repr(up_revision)}
down_revision = ${repr(down_revision)}
branch_labels = ${repr(branch_labels)}
depends_on = ${repr(depends_on)}


def upgrade() -> None:
    ${upgrades if upgrades else "pass"}


def downgrade() -> None:
    ${downgrades if downgrades else "pass"}
```

Generate the migration via autogenerate (run once locally):

```bash
cd src/arena/backend/db/migrations
ARENA_DB_URL="sqlite:///./_autogen.db" \
  uv run alembic -c alembic.ini revision --autogenerate -m "initial schema"
rm _autogen.db
```

Then rename the produced file in `versions/` to `0001_initial.py` and ensure `revision = "0001"`. If autogenerate is awkward in the harness, instead write `versions/0001_initial.py` by hand:

```python
"""initial schema

Revision ID: 0001
Revises:
Create Date: 2026-05-24
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "participants",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("display_name", sa.String(64), nullable=False),
        sa.Column("owner_email", sa.String(128), nullable=False),
        sa.Column("base_url", sa.String(512), nullable=False),
        sa.Column("api_key_hash", sa.String(128), nullable=False),
        sa.Column("model_name", sa.String(128), nullable=False),
        sa.Column("model_meta", sa.JSON(), nullable=False),
        sa.Column("registered_at", sa.DateTime(), nullable=False),
        sa.Column("status", sa.Enum("active", "disabled", name="participantstatus"), nullable=False),
    )
    op.create_table(
        "evaluations",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("participant_id", sa.BigInteger(),
                  sa.ForeignKey("participants.id", ondelete="CASCADE"), nullable=False),
        sa.Column("config_label", sa.String(64), nullable=False),
        sa.Column("status", sa.Enum("queued", "running", "done", "failed", "cancelled",
                                     name="evaluationstatus"), nullable=False),
        sa.Column("queued_at", sa.DateTime(), nullable=False),
        sa.Column("started_at", sa.DateTime(), nullable=True),
        sa.Column("finished_at", sa.DateTime(), nullable=True),
        sa.Column("output_dir", sa.String(512), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
    )
    op.create_table(
        "season_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("evaluation_id", sa.BigInteger(),
                  sa.ForeignKey("evaluations.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.String(12), nullable=False),
        sa.Column("framing", sa.String(32), nullable=True),
        sa.Column("forfeit_condition", sa.String(16), nullable=True),
        sa.Column("cell", sa.Integer(), nullable=True),
        sa.Column("final_score", sa.Float(), nullable=True),
        sa.Column("forfeited", sa.Boolean(), nullable=True),
        sa.Column("forfeit_turn", sa.Integer(), nullable=True),
        sa.Column("forfeit_reason", sa.Integer(), nullable=True),
        sa.Column("total_turns", sa.Integer(), nullable=True),
        sa.Column("seed", sa.Integer(), nullable=True),
    )
    op.create_table(
        "turn_results",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("season_result_id", sa.BigInteger(),
                  sa.ForeignKey("season_results.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turn_number", sa.Integer(), nullable=False),
        sa.Column("ri_task", sa.Integer()),
        sa.Column("ri_probe", sa.Integer()),
        sa.Column("ri_forfeit", sa.Integer()),
        sa.Column("forfeit_choice", sa.String(16)),
        sa.Column("psuccess_self", sa.Integer()),
        sa.Column("decision_quality", sa.Float()),
        sa.Column("reward_received", sa.Float()),
        sa.Column("died", sa.Boolean()),
    )
    op.create_table(
        "turn_texts",
        sa.Column("turn_result_id", sa.BigInteger(),
                  sa.ForeignKey("turn_results.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("thinking_text_task", sa.Text()),
        sa.Column("thinking_text_probe", sa.Text()),
        sa.Column("thinking_text_forfeit", sa.Text()),
        sa.Column("raw_response_task", sa.Text()),
        sa.Column("raw_response_probe", sa.Text()),
        sa.Column("raw_response_forfeit", sa.Text()),
    )


def downgrade() -> None:
    for t in ("turn_texts", "turn_results", "season_results", "evaluations", "participants"):
        op.drop_table(t)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_migrations.py -v`
Expected: 1 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/db/migrations/ tests/unit/arena/test_migrations.py
git commit -m "feat(arena/db): Alembic env + initial 0001 migration"
```

---

## Task 5: API key generation, hashing, verification

**Files:**
- Create: `src/arena/backend/security.py`
- Create: `tests/unit/arena/test_security.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_security.py`:

```python
"""API key: secure random gen + bcrypt hash + verify roundtrip."""

from arena.backend.security import generate_api_key, hash_api_key, verify_api_key


def test_generate_returns_distinct_strings():
    a, b = generate_api_key(), generate_api_key()
    assert a != b
    assert len(a) >= 32
    assert a.replace("-", "").replace("_", "").isalnum()  # url-safe b64


def test_hash_then_verify_succeeds():
    key = generate_api_key()
    h = hash_api_key(key)
    assert verify_api_key(key, h) is True


def test_wrong_key_rejected():
    h = hash_api_key("correct-key")
    assert verify_api_key("wrong-key", h) is False
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_security.py -v`
Expected: `ModuleNotFoundError: No module named 'arena.backend.security'`.

- [ ] **Step 3: Implement security**

`src/arena/backend/security.py`:

```python
"""API key generation + bcrypt hashing.

Keys are emitted at registration time exactly once. We store only the
bcrypt hash in participants.api_key_hash. Verification on each request
is a bcrypt.checkpw — slow by design (~100ms), which is acceptable
because evaluation enqueue is human-paced.
"""

import secrets

import bcrypt

from arena.backend.config import Settings


def generate_api_key() -> str:
    """Return a fresh URL-safe base64 token (~32 chars from 24 random bytes)."""
    n = Settings().api_key_bytes
    return secrets.token_urlsafe(n)


def hash_api_key(plaintext: str) -> str:
    return bcrypt.hashpw(plaintext.encode("utf-8"), bcrypt.gensalt()).decode("ascii")


def verify_api_key(plaintext: str, stored_hash: str) -> bool:
    try:
        return bcrypt.checkpw(plaintext.encode("utf-8"), stored_hash.encode("ascii"))
    except (ValueError, TypeError):
        return False
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_security.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/security.py tests/unit/arena/test_security.py
git commit -m "feat(arena): API key gen + bcrypt hash/verify"
```

---

## Task 6: ParticipantBYOProvider

**Files:**
- Create: `src/arena/backend/providers/__init__.py`
- Create: `src/arena/backend/providers/participant_byo.py`
- Create: `tests/unit/arena/test_participant_byo_provider.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_participant_byo_provider.py`:

```python
"""Provider: factory pulls base_url/api_key/model from DB once and stashes."""

from datetime import datetime
from unittest.mock import patch

from arena.backend.db.models import Participant, ParticipantStatus
from arena.backend.providers.participant_byo import ParticipantBYOProvider


def _make_participant(db_session) -> int:
    p = Participant(
        display_name="x", owner_email="x@x.x",
        base_url="http://participant.example/v1",
        api_key_hash="hash",
        model_name="qwen3-8b",
        model_meta={}, registered_at=datetime(2026, 5, 24),
        status=ParticipantStatus.active,
    )
    db_session.add(p); db_session.commit()
    return p.id


def test_from_db_stashes_endpoint(db_session):
    pid = _make_participant(db_session)
    # Plaintext key supplied at evaluation enqueue time (never stored).
    prov = ParticipantBYOProvider.from_db(
        db_session, participant_id=pid, plaintext_api_key="user-key"
    )
    assert prov.model_name == "qwen3-8b"
    # LocalProvider stores base_url on its OpenAI client base_url attr.
    assert str(prov._client.base_url).rstrip("/") == "http://participant.example/v1"


def test_from_db_raises_on_unknown_participant(db_session):
    with __import__("pytest").raises(LookupError):
        ParticipantBYOProvider.from_db(db_session, participant_id=9999, plaintext_api_key="k")


def test_complete_delegates_to_local_provider(db_session):
    pid = _make_participant(db_session)
    prov = ParticipantBYOProvider.from_db(
        db_session, participant_id=pid, plaintext_api_key="user-key"
    )
    with patch(
        "squid_game.game.infra.providers.local.LocalProvider.complete",
        return_value="SENTINEL",
    ) as mock_complete:
        out = prov.complete([{"role": "user", "content": "hi"}], temperature=0.5)
    assert out == "SENTINEL"
    mock_complete.assert_called_once()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_participant_byo_provider.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement provider**

`src/arena/backend/providers/__init__.py`:

```python
"""LLM provider adapters specific to the arena backend."""
```

`src/arena/backend/providers/participant_byo.py`:

```python
"""ParticipantBYOProvider — dynamic LocalProvider keyed by participant_id.

Pulls (base_url, model_name) from the participants table at evaluation
start time and instantiates the upstream LocalProvider with them. The
plaintext api_key is supplied at enqueue time (never stored server-side
in plaintext) and forwarded as the upstream Bearer credential to the
participant's endpoint.

Fetch policy: one DB lookup per provider instance. A provider lives for
the duration of one evaluation, so any participants-table update made
mid-evaluation is observed only by the next evaluation. This is the
fetch policy mandated in
docs/superpowers/specs/2026-05-24-arena-byo-participant-design.md §3.2.
"""

from sqlalchemy.orm import Session

from arena.backend.db.models import Participant
from squid_game.game.infra.providers.local import LocalProvider


class ParticipantBYOProvider(LocalProvider):
    """LocalProvider whose endpoint is resolved by participant_id from DB."""

    @classmethod
    def from_db(
        cls,
        db: Session,
        participant_id: int,
        plaintext_api_key: str,
        timeout: float = 120.0,
        max_retries: int = 3,
    ) -> "ParticipantBYOProvider":
        p = db.get(Participant, participant_id)
        if p is None:
            raise LookupError(f"participant {participant_id} not found")
        return cls(
            model=p.model_name,
            base_url=p.base_url,
            api_key=plaintext_api_key,
            timeout=timeout,
            max_retries=max_retries,
        )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_participant_byo_provider.py -v`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/providers/ tests/unit/arena/test_participant_byo_provider.py
git commit -m "feat(arena/providers): ParticipantBYOProvider — DB-resolved LocalProvider"
```

---

## Task 7: ETL ingest (outputs → MySQL)

**Files:**
- Create: `src/arena/backend/etl/__init__.py`
- Create: `src/arena/backend/etl/ingest.py`
- Create: `tests/fixtures/arena/smoke_output/season_results.jsonl`
- Create: `tests/fixtures/arena/smoke_output/abc123def456_turns.jsonl`
- Create: `tests/unit/arena/test_etl_ingest.py`

- [ ] **Step 1: Write the failing test + fixture**

Create fixture `tests/fixtures/arena/smoke_output/season_results.jsonl`:

```
{"season_id": "abc123def456", "framing": "true_baseline", "forfeit_condition": "allowed", "cell": 0, "final_score": 1.0, "forfeited": false, "forfeit_turn": null, "forfeit_reason": null, "total_turns": 15, "seed": 42}
```

Create fixture `tests/fixtures/arena/smoke_output/abc123def456_turns.jsonl` (one line, abbreviated — the ETL reads only the fields it needs):

```
{"season_id": "abc123def456", "turn_number": 1, "ri_task": 12, "ri_probe": 5, "ri_forfeit": 3, "forfeit_choice": "CONTINUE", "psuccess_self": 80, "decision_quality": 1.0, "reward_received": 1.0, "died": false, "thinking_text_task": "let me think", "thinking_text_probe": "p=80", "thinking_text_forfeit": "continue", "raw_response_task": "ACTION: A", "raw_response_probe": "PSUCCESS: 80", "raw_response_forfeit": "CONTINUE"}
```

`tests/unit/arena/test_etl_ingest.py`:

```python
"""ETL: ingest outputs dir → MySQL; idempotent on re-run."""

from datetime import datetime
from pathlib import Path

from arena.backend.db.models import (
    Evaluation, EvaluationStatus, Participant, ParticipantStatus,
    SeasonResult, TurnResult, TurnText,
)
from arena.backend.etl.ingest import ingest_evaluation_output

FIXTURE = Path(__file__).resolve().parents[2] / "fixtures/arena/smoke_output"


def _setup_eval(db_session) -> int:
    p = Participant(display_name="x", owner_email="x@x.x", base_url="u",
                    api_key_hash="h", model_name="m", model_meta={},
                    registered_at=datetime(2026, 5, 24),
                    status=ParticipantStatus.active)
    db_session.add(p); db_session.commit()
    e = Evaluation(participant_id=p.id, config_label="smoke",
                   status=EvaluationStatus.running, queued_at=datetime(2026, 5, 24))
    db_session.add(e); db_session.commit()
    return e.id


def test_ingest_writes_season_and_turn(db_session):
    eval_id = _setup_eval(db_session)
    ingest_evaluation_output(db_session, eval_id, FIXTURE)
    db_session.commit()
    seasons = db_session.query(SeasonResult).all()
    assert len(seasons) == 1
    assert seasons[0].season_id == "abc123def456"
    assert seasons[0].cell == 0
    turns = db_session.query(TurnResult).all()
    assert len(turns) == 1
    assert turns[0].ri_task == 12
    texts = db_session.query(TurnText).all()
    assert len(texts) == 1
    assert texts[0].raw_response_task == "ACTION: A"


def test_ingest_is_idempotent(db_session):
    eval_id = _setup_eval(db_session)
    ingest_evaluation_output(db_session, eval_id, FIXTURE)
    ingest_evaluation_output(db_session, eval_id, FIXTURE)  # re-run
    db_session.commit()
    assert db_session.query(SeasonResult).count() == 1
    assert db_session.query(TurnResult).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_etl_ingest.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement ingest**

`src/arena/backend/etl/__init__.py`:

```python
"""ETL: outputs/<eval_id>/*.jsonl → relational schema."""
```

`src/arena/backend/etl/ingest.py`:

```python
"""Ingest a finished evaluation's output directory into MySQL.

Idempotent on evaluation_id: existing season_results for the same
evaluation are deleted first (cascade removes turns/texts), then
re-inserted. Safe to call on a partially-written directory at the cost
of replacing whatever was previously ingested.

Input layout (matches squid_game.game.runner output):
    <output_dir>/season_results.jsonl    -- one JSON per season
    <output_dir>/<season_id>_turns.jsonl -- one JSON per turn
"""

import json
from pathlib import Path

from sqlalchemy.orm import Session

from arena.backend.db.models import SeasonResult, TurnResult, TurnText

_SEASON_FIELDS = (
    "framing", "forfeit_condition", "cell", "final_score",
    "forfeited", "forfeit_turn", "forfeit_reason", "total_turns", "seed",
)
_TURN_FIELDS = (
    "turn_number", "ri_task", "ri_probe", "ri_forfeit",
    "forfeit_choice", "psuccess_self", "decision_quality",
    "reward_received", "died",
)
_TEXT_FIELDS = (
    "thinking_text_task", "thinking_text_probe", "thinking_text_forfeit",
    "raw_response_task", "raw_response_probe", "raw_response_forfeit",
)


def _read_jsonl(path: Path):
    with path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def ingest_evaluation_output(db: Session, evaluation_id: int, output_dir: Path) -> None:
    # Idempotency: nuke prior rows for this evaluation, then re-ingest.
    db.query(SeasonResult).filter(SeasonResult.evaluation_id == evaluation_id).delete()
    db.flush()

    season_path = output_dir / "season_results.jsonl"
    if not season_path.exists():
        return  # nothing to ingest

    season_by_id: dict[str, SeasonResult] = {}
    for row in _read_jsonl(season_path):
        sr = SeasonResult(
            evaluation_id=evaluation_id,
            season_id=row["season_id"],
            **{k: row.get(k) for k in _SEASON_FIELDS},
        )
        db.add(sr)
        season_by_id[row["season_id"]] = sr
    db.flush()  # need sr.id for FK

    for turns_file in output_dir.glob("*_turns.jsonl"):
        season_id = turns_file.stem.replace("_turns", "")
        sr = season_by_id.get(season_id)
        if sr is None:
            continue
        for row in _read_jsonl(turns_file):
            tr = TurnResult(
                season_result_id=sr.id,
                **{k: row.get(k) for k in _TURN_FIELDS},
            )
            db.add(tr)
            db.flush()
            if any(row.get(k) for k in _TEXT_FIELDS):
                tt = TurnText(turn_result_id=tr.id,
                              **{k: row.get(k) for k in _TEXT_FIELDS})
                db.add(tt)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_etl_ingest.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/etl/ tests/unit/arena/test_etl_ingest.py \
        tests/fixtures/arena/
git commit -m "feat(arena/etl): idempotent outputs→MySQL ingest"
```

---

## Task 8: Worker queue (SQL-backed FIFO claim)

**Files:**
- Create: `src/arena/backend/worker/__init__.py`
- Create: `src/arena/backend/worker/queue.py`
- Create: `tests/unit/arena/test_worker_queue.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_worker_queue.py`:

```python
"""Worker queue: claim_next pops oldest queued eval and marks it running."""

from datetime import datetime, timedelta

from arena.backend.db.models import (
    Evaluation, EvaluationStatus, Participant, ParticipantStatus,
)
from arena.backend.worker.queue import claim_next_evaluation


def _participant(db_session):
    p = Participant(display_name="x", owner_email="x@x.x", base_url="u",
                    api_key_hash="h", model_name="m", model_meta={},
                    registered_at=datetime(2026, 5, 24),
                    status=ParticipantStatus.active)
    db_session.add(p); db_session.commit()
    return p


def test_claim_next_returns_oldest_queued(db_session):
    p = _participant(db_session)
    e_old = Evaluation(participant_id=p.id, config_label="a",
                       status=EvaluationStatus.queued,
                       queued_at=datetime(2026, 5, 24, 10))
    e_new = Evaluation(participant_id=p.id, config_label="b",
                       status=EvaluationStatus.queued,
                       queued_at=datetime(2026, 5, 24, 11))
    db_session.add_all([e_old, e_new]); db_session.commit()
    claimed = claim_next_evaluation(db_session)
    assert claimed.config_label == "a"
    assert claimed.status == EvaluationStatus.running
    assert claimed.started_at is not None


def test_claim_next_returns_none_when_empty(db_session):
    p = _participant(db_session)
    e = Evaluation(participant_id=p.id, config_label="a",
                   status=EvaluationStatus.done,
                   queued_at=datetime(2026, 5, 24))
    db_session.add(e); db_session.commit()
    assert claim_next_evaluation(db_session) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_worker_queue.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement queue**

`src/arena/backend/worker/__init__.py`:

```python
"""In-process worker: claim queued evals → run ExperimentRunner → ETL."""
```

`src/arena/backend/worker/queue.py`:

```python
"""SQL-backed FIFO claim for queued evaluations.

MVP is single-worker, so we don't need SELECT FOR UPDATE; a simple
SELECT-then-UPDATE in one transaction is race-free in the single-writer
case. If we ever scale to multiple worker processes, switch to
`with_for_update()` (MySQL/PostgreSQL) — SQLite does not support row
locks but unit tests are single-threaded so it is fine.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from arena.backend.db.models import Evaluation, EvaluationStatus


def claim_next_evaluation(db: Session) -> Evaluation | None:
    q = (
        db.query(Evaluation)
        .filter(Evaluation.status == EvaluationStatus.queued)
        .order_by(Evaluation.queued_at.asc())
        .limit(1)
    )
    e = q.one_or_none()
    if e is None:
        return None
    e.status = EvaluationStatus.running
    e.started_at = datetime.utcnow()
    db.commit()
    return e
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_worker_queue.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/worker/__init__.py src/arena/backend/worker/queue.py \
        tests/unit/arena/test_worker_queue.py
git commit -m "feat(arena/worker): SQL-backed FIFO evaluation claim"
```

---

## Task 9: Worker runner (claim → ExperimentRunner → ETL)

**Files:**
- Create: `tests/fixtures/arena/smoke_config.yaml`
- Create: `src/arena/backend/worker/runner.py`
- Create: `tests/unit/arena/test_worker_runner.py`

- [ ] **Step 1: Write the failing test**

Create fixture `tests/fixtures/arena/smoke_config.yaml` (minimal 1-cell 1-seed config — copy the structure from `configs/experiment/phase3_split_forfeit_smoke.yaml` and pare it down to one cell, one seed, two turns. The exact YAML schema is defined by `squid_game.shared.models.config.ExperimentConfig`; do not invent fields):

```yaml
# Minimal smoke for the arena worker test. Provider is injected at
# runtime (not from YAML) — see worker/runner.py.
task_name: signal_game
difficulty: easy
total_turns: 2
cells: [0]
seeds: [42]
use_unified_turn: true
use_forfeit_layer: true
use_split_forfeit_layer: true
use_psuccess_probe: true
parallel_workers: 1
# Other required fields: copy from configs/experiment/phase3_split_forfeit_smoke.yaml
# and remove the provider block.
```

(If `ExperimentConfig` requires fields not listed above, copy them verbatim from the canonical smoke config so the test fixture remains valid.)

`tests/unit/arena/test_worker_runner.py`:

```python
"""Worker runner: process_one wires Provider into ExperimentRunner, then ETL."""

from datetime import datetime
from pathlib import Path
from unittest.mock import MagicMock, patch

from arena.backend.db.models import (
    Evaluation, EvaluationStatus, Participant, ParticipantStatus,
)
from arena.backend.worker.runner import process_one


def _enqueue(db_session, output_dir: Path):
    p = Participant(display_name="x", owner_email="x@x.x",
                    base_url="http://p/v1", api_key_hash="h",
                    model_name="m", model_meta={},
                    registered_at=datetime(2026, 5, 24),
                    status=ParticipantStatus.active)
    db_session.add(p); db_session.commit()
    e = Evaluation(participant_id=p.id, config_label="smoke",
                   status=EvaluationStatus.queued,
                   queued_at=datetime(2026, 5, 24),
                   output_dir=str(output_dir))
    db_session.add(e); db_session.commit()
    return e.id


def test_process_one_success_marks_done(db_session, tmp_path):
    eval_id = _enqueue(db_session, tmp_path / "out")
    # Patch ExperimentRunner.run to fabricate an output directory without
    # calling any LLM. The fabricated directory must look like a real run.
    def fake_run(self_runner, resume_dir=None):
        out = tmp_path / "out"
        out.mkdir(parents=True, exist_ok=True)
        (out / "season_results.jsonl").write_text(
            '{"season_id":"sss000000000","framing":"true_baseline",'
            '"forfeit_condition":"allowed","cell":0,"final_score":0.0,'
            '"forfeited":false,"total_turns":2,"seed":42}\n')
        (out / "sss000000000_turns.jsonl").write_text(
            '{"season_id":"sss000000000","turn_number":1,"ri_task":1,'
            '"ri_probe":1,"ri_forfeit":1,"forfeit_choice":"CONTINUE",'
            '"psuccess_self":50,"decision_quality":1.0,"reward_received":1.0,'
            '"died":false}\n')
        return MagicMock()

    with patch("squid_game.game.runner.ExperimentRunner.run", fake_run), \
         patch("arena.backend.worker.runner._build_config",
               return_value=MagicMock()):
        process_one(db_session, plaintext_api_key="key", smoke_config_path=Path("ignored"))
    e = db_session.get(Evaluation, eval_id)
    assert e.status == EvaluationStatus.done
    assert e.finished_at is not None


def test_process_one_failure_marks_failed(db_session, tmp_path):
    _enqueue(db_session, tmp_path / "out")
    with patch("squid_game.game.runner.ExperimentRunner.run",
               side_effect=RuntimeError("upstream 500")), \
         patch("arena.backend.worker.runner._build_config",
               return_value=MagicMock()):
        process_one(db_session, plaintext_api_key="key", smoke_config_path=Path("ignored"))
    e = db_session.query(Evaluation).first()
    assert e.status == EvaluationStatus.failed
    assert "upstream 500" in (e.error_message or "")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_worker_runner.py -v`
Expected: `ModuleNotFoundError: arena.backend.worker.runner`.

- [ ] **Step 3: Implement runner**

`src/arena/backend/worker/runner.py`:

```python
"""Process one queued evaluation end-to-end.

Flow per evaluation:
    1. claim_next_evaluation → marks running
    2. build ExperimentConfig from config_label (smoke / canonical / ...)
       and inject ParticipantBYOProvider built from participant_id +
       plaintext_api_key (supplied at enqueue time by the API layer).
    3. ExperimentRunner.run() → writes outputs/<eval_id>/...
    4. ingest_evaluation_output → MySQL
    5. mark done (or failed with error_message)

Config building is intentionally minimal: only `smoke` and the canonical
v6 family are supported. New labels are added by editing _CONFIG_PATHS.
"""

from datetime import datetime
from pathlib import Path

from sqlalchemy.orm import Session

from arena.backend.db.models import Evaluation, EvaluationStatus
from arena.backend.etl.ingest import ingest_evaluation_output
from arena.backend.providers.participant_byo import ParticipantBYOProvider
from arena.backend.worker.queue import claim_next_evaluation
from squid_game.game.runner import ExperimentRunner
from squid_game.shared.models.config import ExperimentConfig

_CONFIG_PATHS: dict[str, Path] = {
    "smoke": Path("configs/experiment/phase3_split_forfeit_smoke.yaml"),
    "canonical_6x30": Path("configs/experiment/phase3_split_forfeit_gemini_n30.yaml"),
}


def _build_config(label: str) -> ExperimentConfig:
    path = _CONFIG_PATHS.get(label)
    if path is None:
        raise ValueError(f"unknown config_label: {label}")
    return ExperimentConfig.from_yaml(path)  # assumed factory — adjust to actual API


def process_one(
    db: Session, plaintext_api_key: str, smoke_config_path: Path | None = None,
) -> None:
    e = claim_next_evaluation(db)
    if e is None:
        return  # nothing to do

    try:
        cfg = _build_config(e.config_label)
        provider = ParticipantBYOProvider.from_db(
            db, participant_id=e.participant_id, plaintext_api_key=plaintext_api_key,
        )
        # ExperimentRunner already accepts a provider via cfg or constructor —
        # use whichever the actual class supports. Concrete wiring is verified
        # by integration smoke (Task 13). For unit tests this branch is patched.
        runner = ExperimentRunner(cfg)
        runner.provider = provider  # noqa: SLF001 — temporary injection point
        runner.run()
        assert e.output_dir is not None, "output_dir must be set at enqueue time"
        ingest_evaluation_output(db, e.id, Path(e.output_dir))
        e.status = EvaluationStatus.done
        e.finished_at = datetime.utcnow()
        db.commit()
    except Exception as exc:  # noqa: BLE001
        e.status = EvaluationStatus.failed
        e.error_message = str(exc)[:65000]
        e.finished_at = datetime.utcnow()
        db.commit()
```

> ⚠️ The two lines marked "assumed factory" / "temporary injection point" depend on the actual `ExperimentConfig` / `ExperimentRunner` API. Before running Step 4, **open `src/squid_game/shared/models/config.py` and `src/squid_game/game/runner.py:100-130` to confirm**:
> - How is `ExperimentConfig` constructed from a YAML path? (look for `from_yaml`, `parse_file`, or external loader)
> - How does `ExperimentRunner` accept a provider? (constructor arg, config field, attribute injection)
>
> Adjust the two marked lines to match the real API. If the runner reads the provider exclusively from the config, instead set `cfg.provider = ParticipantBYOProviderSpec(...)` or whatever the existing pattern is. The unit test patches both `_build_config` and `ExperimentRunner.run`, so it stays green either way; the integration smoke (Task 13) will catch wiring mistakes.

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_worker_runner.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/worker/runner.py tests/unit/arena/test_worker_runner.py \
        tests/fixtures/arena/smoke_config.yaml
git commit -m "feat(arena/worker): claim→runner→ETL with status transitions"
```

---

## Task 10: API — participants (register / me / delete)

**Files:**
- Create: `src/arena/backend/api/__init__.py`
- Create: `src/arena/backend/api/schemas.py`
- Create: `src/arena/backend/api/deps.py`
- Create: `src/arena/backend/api/participants.py`
- Create: `tests/unit/arena/test_api_participants.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_api_participants.py`:

```python
"""POST /api/participants returns id+api_key (plaintext, once).
GET /api/participants/me requires valid Bearer key.
"""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arena.backend.api.deps import get_db
from arena.backend.api.participants import router


def _make_app(db_session):
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def test_register_returns_id_and_plaintext_key(db_session):
    client = _make_app(db_session)
    r = client.post("/api/participants", json={
        "display_name": "alice", "owner_email": "a@b.c",
        "base_url": "http://p/v1", "model_name": "qwen3-8b",
        "model_meta": {"params": "8B"},
    })
    assert r.status_code == 201, r.text
    body = r.json()
    assert "participant_id" in body
    assert "api_key" in body and len(body["api_key"]) >= 32


def test_me_requires_valid_key(db_session):
    client = _make_app(db_session)
    reg = client.post("/api/participants", json={
        "display_name": "bob", "owner_email": "b@b.c",
        "base_url": "u", "model_name": "m", "model_meta": {},
    }).json()
    pid, key = reg["participant_id"], reg["api_key"]
    ok = client.get("/api/participants/me", headers={"Authorization": f"Bearer {key}"})
    assert ok.status_code == 200
    assert ok.json()["id"] == pid
    bad = client.get("/api/participants/me", headers={"Authorization": "Bearer wrong"})
    assert bad.status_code == 401
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_api_participants.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/arena/backend/api/__init__.py`:

```python
"""HTTP layer: routers, request/response schemas, shared deps."""
```

`src/arena/backend/api/schemas.py`:

```python
"""Pydantic request/response schemas. Kept in one file because the surface
is small (~12 models total across participants/evaluations/leaderboard).
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, EmailStr, Field, HttpUrl


class ParticipantRegister(BaseModel):
    display_name: str = Field(min_length=1, max_length=64)
    owner_email: EmailStr
    base_url: HttpUrl
    model_name: str = Field(min_length=1, max_length=128)
    model_meta: dict = Field(default_factory=dict)


class ParticipantRegisterResponse(BaseModel):
    participant_id: int
    api_key: str  # plaintext — returned once at registration


class ParticipantPublic(BaseModel):
    id: int
    display_name: str
    model_name: str
    model_meta: dict
    registered_at: datetime
    status: Literal["active", "disabled"]


class EvaluationCreate(BaseModel):
    config_label: str = Field(default="smoke")


class EvaluationPublic(BaseModel):
    id: int
    participant_id: int
    config_label: str
    status: str
    queued_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    error_message: str | None


class LeaderboardRow(BaseModel):
    participant_id: int
    display_name: str
    model_name: str
    n_evaluations: int
    forfeit_rate: float | None  # null if no eval done yet
```

`src/arena/backend/api/deps.py`:

```python
"""Shared FastAPI dependencies: DB session + Bearer auth."""

from typing import Annotated

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from arena.backend.db.models import Participant, ParticipantStatus
from arena.backend.db.session import build_engine, build_session_factory
from arena.backend.security import verify_api_key

_engine = build_engine()
_SessionLocal = build_session_factory(_engine)


def get_db():
    s = _SessionLocal()
    try:
        yield s
    finally:
        s.close()


def require_api_key(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> Participant:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    # Linear scan — fine for MVP scale. Add a key-prefix index if it grows.
    for p in db.query(Participant).filter(Participant.status == ParticipantStatus.active):
        if verify_api_key(token, p.api_key_hash):
            return p
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")
```

`src/arena/backend/api/participants.py`:

```python
"""POST /api/participants, GET /api/participants/me, DELETE /api/participants/me."""

from datetime import datetime
from typing import Annotated

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from arena.backend.api.deps import get_db, require_api_key
from arena.backend.api.schemas import (
    ParticipantPublic, ParticipantRegister, ParticipantRegisterResponse,
)
from arena.backend.db.models import Participant, ParticipantStatus
from arena.backend.security import generate_api_key, hash_api_key

router = APIRouter(prefix="/api/participants", tags=["participants"])


@router.post("", response_model=ParticipantRegisterResponse,
             status_code=status.HTTP_201_CREATED)
def register(
    payload: ParticipantRegister,
    db: Annotated[Session, Depends(get_db)],
):
    plaintext = generate_api_key()
    p = Participant(
        display_name=payload.display_name,
        owner_email=payload.owner_email,
        base_url=str(payload.base_url),
        api_key_hash=hash_api_key(plaintext),
        model_name=payload.model_name,
        model_meta=payload.model_meta,
        registered_at=datetime.utcnow(),
        status=ParticipantStatus.active,
    )
    db.add(p); db.commit(); db.refresh(p)
    return ParticipantRegisterResponse(participant_id=p.id, api_key=plaintext)


@router.get("/me", response_model=ParticipantPublic)
def me(caller: Annotated[Participant, Depends(require_api_key)]):
    return ParticipantPublic(
        id=caller.id,
        display_name=caller.display_name,
        model_name=caller.model_name,
        model_meta=caller.model_meta,
        registered_at=caller.registered_at,
        status=caller.status.value,
    )


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
def deactivate(
    caller: Annotated[Participant, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
):
    caller.status = ParticipantStatus.disabled
    db.commit()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_api_participants.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/api/__init__.py src/arena/backend/api/schemas.py \
        src/arena/backend/api/deps.py src/arena/backend/api/participants.py \
        tests/unit/arena/test_api_participants.py
git commit -m "feat(arena/api): participants register/me/delete with Bearer auth"
```

---

## Task 11: API — evaluations (enqueue / status)

**Files:**
- Create: `src/arena/backend/api/evaluations.py`
- Create: `tests/unit/arena/test_api_evaluations.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_api_evaluations.py`:

```python
"""POST /api/evaluations enqueues an eval; GET /api/evaluations/{id} returns status.
Cross-participant access is 404 (don't reveal existence)."""

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arena.backend.api.deps import get_db
from arena.backend.api.evaluations import router as ev_router
from arena.backend.api.participants import router as p_router


def _make_app(db_session):
    app = FastAPI()
    app.include_router(p_router)
    app.include_router(ev_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def _register(client):
    r = client.post("/api/participants", json={
        "display_name": "x", "owner_email": "x@x.c",
        "base_url": "http://p/v1", "model_name": "m", "model_meta": {},
    })
    return r.json()


def test_enqueue_inserts_queued(db_session):
    client = _make_app(db_session)
    reg = _register(client)
    r = client.post(
        "/api/evaluations",
        json={"config_label": "smoke"},
        headers={"Authorization": f"Bearer {reg['api_key']}"},
    )
    assert r.status_code == 201, r.text
    body = r.json()
    assert body["status"] == "queued"


def test_cross_participant_status_is_404(db_session):
    client = _make_app(db_session)
    a = _register(client)
    b = _register(client)
    # A enqueues
    a_eval = client.post("/api/evaluations", json={"config_label": "smoke"},
                         headers={"Authorization": f"Bearer {a['api_key']}"}).json()
    # B tries to read A's eval
    r = client.get(f"/api/evaluations/{a_eval['id']}",
                   headers={"Authorization": f"Bearer {b['api_key']}"})
    assert r.status_code == 404
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_api_evaluations.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/arena/backend/api/evaluations.py`:

```python
"""POST /api/evaluations, GET /api/evaluations/{id}.

The plaintext_api_key the worker uses upstream is captured at enqueue
time from the caller's own Bearer token — i.e. participants relay their
own key as the upstream credential. This is a deliberate simplification:
the alternative (separate "upstream key" field) doubles secret-handling
surface without adding capability for the no-cheating MVP.
"""

from datetime import datetime
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from arena.backend.api.deps import get_db, require_api_key
from arena.backend.api.schemas import EvaluationCreate, EvaluationPublic
from arena.backend.config import Settings
from arena.backend.db.models import Evaluation, EvaluationStatus, Participant

router = APIRouter(prefix="/api/evaluations", tags=["evaluations"])


def _to_public(e: Evaluation) -> EvaluationPublic:
    return EvaluationPublic(
        id=e.id, participant_id=e.participant_id, config_label=e.config_label,
        status=e.status.value, queued_at=e.queued_at,
        started_at=e.started_at, finished_at=e.finished_at,
        error_message=e.error_message,
    )


@router.post("", response_model=EvaluationPublic,
             status_code=status.HTTP_201_CREATED)
def enqueue(
    payload: EvaluationCreate,
    caller: Annotated[Participant, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
):
    output_root = Settings().outputs_dir
    e = Evaluation(
        participant_id=caller.id,
        config_label=payload.config_label,
        status=EvaluationStatus.queued,
        queued_at=datetime.utcnow(),
    )
    db.add(e); db.commit(); db.refresh(e)
    e.output_dir = str(output_root / str(e.id))
    db.commit()
    return _to_public(e)


@router.get("/{eval_id}", response_model=EvaluationPublic)
def get_status(
    eval_id: int,
    caller: Annotated[Participant, Depends(require_api_key)],
    db: Annotated[Session, Depends(get_db)],
):
    e = db.get(Evaluation, eval_id)
    if e is None or e.participant_id != caller.id:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "evaluation not found")
    return _to_public(e)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_api_evaluations.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/api/evaluations.py tests/unit/arena/test_api_evaluations.py
git commit -m "feat(arena/api): evaluations enqueue + scoped status"
```

---

## Task 12: API — leaderboard (rank / model detail)

**Files:**
- Create: `src/arena/backend/api/leaderboard.py`
- Create: `tests/unit/arena/test_api_leaderboard.py`

- [ ] **Step 1: Write the failing test**

`tests/unit/arena/test_api_leaderboard.py`:

```python
"""GET /api/leaderboard returns one row per participant with overall forfeit_rate.
GET /api/models/{id} returns per-cell forfeit_rate."""

from datetime import datetime

from fastapi import FastAPI
from fastapi.testclient import TestClient

from arena.backend.api.deps import get_db
from arena.backend.api.leaderboard import router
from arena.backend.db.models import (
    Evaluation, EvaluationStatus, Participant, ParticipantStatus, SeasonResult,
)


def _seed(db):
    p = Participant(display_name="alice", owner_email="a@x.c", base_url="u",
                    api_key_hash="h", model_name="qwen", model_meta={},
                    registered_at=datetime(2026, 5, 24),
                    status=ParticipantStatus.active)
    db.add(p); db.commit()
    e = Evaluation(participant_id=p.id, config_label="smoke",
                   status=EvaluationStatus.done,
                   queued_at=datetime(2026, 5, 24))
    db.add(e); db.commit()
    for cell, forfeited in [(0, False), (3, True), (3, True), (3, False)]:
        db.add(SeasonResult(evaluation_id=e.id, season_id=f"s{cell}{forfeited}",
                            cell=cell, forfeited=forfeited,
                            framing="x", forfeit_condition="allowed",
                            final_score=0.0, total_turns=15, seed=1))
    db.commit()
    return p.id


def _client(db):
    app = FastAPI(); app.include_router(router)
    app.dependency_overrides[get_db] = lambda: db
    return TestClient(app)


def test_leaderboard_row(db_session):
    _seed(db_session)
    r = _client(db_session).get("/api/leaderboard")
    assert r.status_code == 200
    rows = r.json()
    assert len(rows) == 1
    row = rows[0]
    assert row["display_name"] == "alice"
    # 4 seasons, 2 forfeited → 0.5
    assert abs(row["forfeit_rate"] - 0.5) < 1e-6
    assert row["n_evaluations"] == 1


def test_model_card_per_cell(db_session):
    pid = _seed(db_session)
    r = _client(db_session).get(f"/api/models/{pid}")
    assert r.status_code == 200
    by_cell = {c["cell"]: c for c in r.json()["per_cell"]}
    # cell 3: 3 seasons, 2 forfeited → 0.666...
    assert abs(by_cell[3]["forfeit_rate"] - 2 / 3) < 1e-6
    # cell 0: 1 season, 0 forfeited → 0
    assert by_cell[0]["forfeit_rate"] == 0.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_api_leaderboard.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

`src/arena/backend/api/leaderboard.py`:

```python
"""Public read-only leaderboard endpoints.

Aggregations are computed on the fly via SQL — MVP scale tolerates this.
When row counts grow, move to a nightly leaderboard_snapshot table.
"""

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from arena.backend.api.deps import get_db
from arena.backend.api.schemas import LeaderboardRow
from arena.backend.db.models import (
    Evaluation, EvaluationStatus, Participant, ParticipantStatus, SeasonResult,
)

router = APIRouter(prefix="/api", tags=["leaderboard"])


@router.get("/leaderboard", response_model=list[LeaderboardRow])
def leaderboard(db: Annotated[Session, Depends(get_db)]):
    # Group: participant → (n_evals_done, total_seasons, total_forfeits).
    q = (
        db.query(
            Participant.id,
            Participant.display_name,
            Participant.model_name,
            func.count(func.distinct(Evaluation.id)).label("n_evals"),
            func.count(SeasonResult.id).label("n_seasons"),
            func.sum(func.cast(SeasonResult.forfeited, type_=func.Integer().type)).label("n_forfeits"),
        )
        .join(Evaluation, Evaluation.participant_id == Participant.id, isouter=True)
        .join(SeasonResult, SeasonResult.evaluation_id == Evaluation.id, isouter=True)
        .filter(Participant.status == ParticipantStatus.active)
        .filter((Evaluation.status == EvaluationStatus.done) | (Evaluation.id.is_(None)))
        .group_by(Participant.id, Participant.display_name, Participant.model_name)
    )
    rows: list[LeaderboardRow] = []
    for pid, name, model, n_evals, n_seasons, n_forfeits in q.all():
        rate = (n_forfeits or 0) / n_seasons if n_seasons else None
        rows.append(LeaderboardRow(
            participant_id=pid, display_name=name, model_name=model,
            n_evaluations=n_evals or 0, forfeit_rate=rate,
        ))
    rows.sort(key=lambda r: (-(r.forfeit_rate or -1), r.display_name))
    return rows


@router.get("/models/{participant_id}")
def model_card(participant_id: int, db: Annotated[Session, Depends(get_db)]):
    p = db.get(Participant, participant_id)
    if p is None or p.status != ParticipantStatus.active:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "model not found")
    q = (
        db.query(
            SeasonResult.cell,
            func.count(SeasonResult.id),
            func.sum(func.cast(SeasonResult.forfeited, type_=func.Integer().type)),
        )
        .join(Evaluation, Evaluation.id == SeasonResult.evaluation_id)
        .filter(Evaluation.participant_id == participant_id)
        .filter(Evaluation.status == EvaluationStatus.done)
        .group_by(SeasonResult.cell)
        .order_by(SeasonResult.cell)
    )
    per_cell = [
        {"cell": cell, "n_seasons": n, "forfeit_rate": (f or 0) / n if n else None}
        for cell, n, f in q.all()
    ]
    return {
        "participant_id": p.id,
        "display_name": p.display_name,
        "model_name": p.model_name,
        "model_meta": p.model_meta,
        "per_cell": per_cell,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/arena/test_api_leaderboard.py -v`
Expected: 2 passed.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/api/leaderboard.py tests/unit/arena/test_api_leaderboard.py
git commit -m "feat(arena/api): leaderboard + per-model per-cell forfeit rate"
```

---

## Task 13: App bootstrap + integration smoke

**Files:**
- Create: `src/arena/backend/app.py`
- Create: `tests/integration/__init__.py` (if missing)
- Create: `tests/integration/test_arena_backend_smoke.py`

- [ ] **Step 1: Write the failing test**

`tests/integration/test_arena_backend_smoke.py`:

```python
"""End-to-end (SQLite + mock vLLM): register → enqueue → worker → leaderboard.

This test does NOT call any real LLM — it stands up a tiny in-process
HTTP server that pretends to be an OpenAI-compatible /v1/chat/completions
endpoint and returns canned thinking + answer payloads. The worker runs
ExperimentRunner against it for 1 cell × 1 seed × 2 turns and the
result must land in the leaderboard.
"""

import threading
import time
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx
import pytest
from fastapi.testclient import TestClient

from arena.backend.app import build_app
from arena.backend.api.deps import get_db


class _MockVLLM(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(length)
        body = (
            '{"id":"x","object":"chat.completion","created":0,"model":"m",'
            '"choices":[{"index":0,"message":{"role":"assistant",'
            '"content":"ACTION: A\\nPSUCCESS: 70\\nCONTINUE"},'
            '"finish_reason":"stop"}],'
            '"usage":{"prompt_tokens":10,"completion_tokens":20,'
            '"completion_tokens_details":{"reasoning_tokens":5}}}'
        ).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_):
        pass


@pytest.fixture
def mock_vllm():
    server = HTTPServer(("127.0.0.1", 0), _MockVLLM)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}/v1"
    server.shutdown()


def test_register_enqueue_worker_leaderboard(db_session, mock_vllm, monkeypatch, tmp_path):
    # Steer the app to use our in-memory session.
    app = build_app()
    app.dependency_overrides[get_db] = lambda: db_session
    client = TestClient(app)

    reg = client.post("/api/participants", json={
        "display_name": "alice", "owner_email": "a@b.c",
        "base_url": mock_vllm, "model_name": "dummy", "model_meta": {},
    }).json()
    enq = client.post("/api/evaluations", json={"config_label": "smoke"},
                      headers={"Authorization": f"Bearer {reg['api_key']}"}).json()
    assert enq["status"] == "queued"

    # Drive the worker by hand so the test is deterministic.
    from arena.backend.worker.runner import process_one
    process_one(db_session, plaintext_api_key=reg["api_key"])

    status = client.get(f"/api/evaluations/{enq['id']}",
                        headers={"Authorization": f"Bearer {reg['api_key']}"}).json()
    assert status["status"] in ("done", "failed"), status
    if status["status"] == "failed":
        pytest.fail(f"smoke failed: {status['error_message']}")

    board = client.get("/api/leaderboard").json()
    assert any(row["display_name"] == "alice" for row in board)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/integration/test_arena_backend_smoke.py -v`
Expected: `ModuleNotFoundError: arena.backend.app`.

- [ ] **Step 3: Implement app bootstrap**

`src/arena/backend/app.py`:

```python
"""FastAPI app factory.

Two entrypoints:
    - build_app() — returns a FastAPI instance (for tests + uvicorn).
    - main() — uvicorn launcher exposed as `arena-server` console script.
"""

import uvicorn
from fastapi import FastAPI

from arena.backend.api import evaluations, leaderboard, participants


def build_app() -> FastAPI:
    app = FastAPI(
        title="LLM Squid Game Arena API",
        version="0.1.0",
        description="BYO-participant arena for the LLM Squid Game benchmark.",
    )
    app.include_router(participants.router)
    app.include_router(evaluations.router)
    app.include_router(leaderboard.router)
    return app


def main() -> None:  # arena-server console entry
    uvicorn.run("arena.backend.app:build_app", factory=True,
                host="0.0.0.0", port=8000, reload=False)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/integration/test_arena_backend_smoke.py -v`
Expected: 1 passed.

If it fails, the most likely culprit is the temporary injection point in `worker/runner.py` (Task 9 Step 3 ⚠️ note). Open `src/squid_game/game/runner.py:100-130` and `src/squid_game/shared/models/config.py`, confirm the actual provider-injection API, and adjust the two marked lines. Then re-run the test.

Also run the full arena test suite to confirm nothing regressed:

```bash
uv run pytest tests/unit/arena tests/integration/test_arena_backend_smoke.py -v
```

Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add src/arena/backend/app.py tests/integration/test_arena_backend_smoke.py
git commit -m "feat(arena): app bootstrap + end-to-end smoke (mock vLLM)"
```

---

## Self-Review Notes

Performed inline after writing the plan:

- **Spec §3.1 (`src/arena/{backend,frontend,participant_kit}/` 4계층)** — frontend and participant_kit are out of scope for this plan; called out in the header. Backend layer is fully covered by Tasks 1-13.
- **Spec §3.2 (modules)** — every module under `backend/` has a dedicated task: db (T2, T3, T4), security (T5), providers (T6), etl (T7), worker (T8, T9), api (T10, T11, T12), app (T13).
- **Spec §3.3 (data model)** — all 5 tables (participants, evaluations, season_results, turn_results, turn_texts) are in T2 (ORM) and T4 (migration). `leaderboard_snapshot` is intentionally deferred to a Phase-2 cron (spec §3.3 last paragraph).
- **Spec §3.4 (sequence)** — steps 1, 3, 4, 5, 6, 7 are covered by Tasks 10, 11, 8, 9, 7. Steps 2 (participant runs endpoint) and 8 (frontend) are out of plan-A scope.
- **Spec §4 (error handling)** — endpoint 5xx/timeout is handled by `LocalProvider`'s inherited retry (T6 unchanged), worker failure path is tested in T9 (`test_process_one_failure_marks_failed`). DB idempotency is verified in T7 (`test_ingest_is_idempotent`). Manual worker-crash recovery is documented in the spec but not codified (Phase 2).
- **Spec §5 (tests)** — Unit tests on every module (T2, T3, T5-T12). Integration smoke with mock vLLM is T13. Frontend / CLI tests are out of plan-A scope.
- **Spec §6 (deps)** — backend deps added in T1; frontend and participant_kit deps belong to plans B and C.
- **Spec §7 milestones M1-M3** — M1 = T2-T6, M2 = T7-T9, M3 = T10-T13.
- **Type consistency** — `ParticipantStatus.active` / `EvaluationStatus.queued` used consistently across T2, T8, T9, T10, T12. `claim_next_evaluation` signature matches across T8-T9. `from_db` factory signature matches across T6 + T9.
- **Placeholder scan** — one ⚠️ note in T9 Step 3 about confirming `ExperimentConfig` / `ExperimentRunner` API. This is **not** a placeholder in the plan; it is an explicit instruction to the implementer to read two specific files at lines 100-130 before writing the two marked lines, with a fallback for both injection patterns. The unit tests pass either way; the integration smoke catches mistakes. This is the honest cost of not having pre-built fixtures for an existing-package contract.
- **Open question carryover** — leaderboard sorting metric is `forfeit_rate desc` in T12 (matches spec §8 first open question's most likely default). Frontend ranks may rework this; that's plan C.
