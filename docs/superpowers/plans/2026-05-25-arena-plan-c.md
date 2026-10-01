# Arena Plan C — Backend Debt Cleanup + Participant Kit Follow-ups + Unregister CLI

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Land the three remaining maintenance items that fall out of Plan A (backend foundation) and Plan B (participant kit): (a) cleanup of known Plan A debt flagged by the Plan B final review, (b) follow-up fixes for the eight Important/Minor issues left open after Plan B's whole-branch review, and (c) the long-deferred `arena-cli unregister` command so participants can deactivate their identities cleanly.

**Architecture:** Three phases, executed in order so each phase's tests build on the prior phase. Phase 1 hardens the backend (datetime deprecation, indexed key lookup, DELETE coverage). Phase 2 tightens the CLI (exit-code convention, file-perm race, CI portability, output polish). Phase 3 adds one new public REST endpoint (`POST /api/participants/me/deactivate` — see Note 1 below) and the matching CLI command. No new packages, no UX redesign.

**Tech Stack:** Same as Plan A/B — Python 3.12, FastAPI, SQLAlchemy 2.0, Alembic, Click 8, httpx, respx, pytest.

**Prerequisite:** Plan B branch `feature/arena-participant-kit` merged to master, OR this plan is implemented on a branch off `feature/arena-participant-kit` HEAD (`f7fb2dc`).

**Out of scope — deferred to dedicated future plans:**
- **Plan D — `arena-cli` separate PyPI package.** Extracting `src/arena/participant_kit/arena_cli/` into its own `pyproject.toml` + Hatch build + publish workflow. Distinct lifecycle (semver, release notes) and CI surface (PyPI credential, wheel build) make it a dedicated plan, not a phase here.
- **Plan E — React frontend (spec §3.2 `src/arena/frontend/`).** Needs UX brainstorming before any task decomposition — out of scope for a pure follow-up plan.

**Note 1 — DELETE vs POST for deactivate:** Plan A already exposes `DELETE /api/participants/me` (`src/arena/backend/api/participants.py:52`). Plan C does NOT add a new endpoint — it only adds **server-side tests** for the existing one (Phase 1, T3) plus the matching CLI surface (Phase 3). The "POST /me/deactivate" wording was an early draft mistake; the canonical surface is the existing `DELETE`.

---

## File Structure

### Modified (Phase 1 — backend debt)

- `src/arena/backend/api/evaluations.py` — replace `datetime.utcnow()` (line 52)
- `src/arena/backend/api/participants.py` — replace `datetime.utcnow()` (line 33)
- `src/arena/backend/worker/queue.py` — replace `datetime.utcnow()` (line 28)
- `src/arena/backend/worker/runner.py` — replace `datetime.utcnow()` (lines 75, 80)
- `src/arena/backend/db/models.py` — add `api_key_prefix` column to `Participant`
- `src/arena/backend/db/migrations/versions/0002_api_key_prefix.py` — new alembic migration
- `src/arena/backend/api/participants.py` — store prefix at registration
- `src/arena/backend/api/deps.py` — lookup by prefix in `require_api_key`
- `src/arena/backend/security.py` — add `key_prefix(plaintext)` helper
- `tests/unit/arena/test_api_participants.py` — DELETE /me coverage (3 new cases)
- `tests/unit/arena/test_security.py` — `key_prefix` tests
- `tests/unit/arena/test_api_participants.py` — adjust registration tests for prefix

### Modified (Phase 2 — Plan B CLI follow-ups)

- `src/arena/participant_kit/arena_cli/commands/register.py` — exit code 3→2
- `src/arena/participant_kit/arena_cli/cli.py` — exit-code docstring + custom Group for help order
- `src/arena/participant_kit/arena_cli/config.py` — TOCTOU-safe save + force dir 0o700
- `src/arena/participant_kit/arena_cli/commands/status.py` — None-field normalization
- `src/arena/participant_kit/README.md` — Windows perm disclaimer
- `tests/integration/test_arena_cli_e2e.py` — uv-on-PATH skip guard
- `tests/unit/arena_cli/test_*.py` — remove dead `import respx` (7 files)
- `tests/unit/arena_cli/test_register.py` — model-meta error UX assertion
- `tests/unit/arena_cli/test_config.py` — TOCTOU + force-perm assertions
- `tests/unit/arena_cli/test_status.py` — None display assertion

### Created (Phase 3 — unregister command)

- `src/arena/participant_kit/arena_cli/commands/unregister.py`
- `tests/unit/arena_cli/test_unregister.py`

### Modified (Phase 3 — wiring)

- `src/arena/participant_kit/arena_cli/client.py` — add `unregister()` method
- `src/arena/participant_kit/arena_cli/cli.py` — register `unregister_cmd`
- `src/arena/participant_kit/README.md` — commands table + 5-minute path mention
- `tests/unit/arena_cli/test_client.py` — `unregister()` HTTP test
- `tests/unit/arena_cli/test_cli_entry.py` — help-lists-unregister assertion

---

## Phase 1 — Plan A Backend Debt

### Task 1: Replace `datetime.utcnow()` with timezone-aware `datetime.now(UTC)`

**Why:** Python 3.13 removed `datetime.utcnow()`. Plan B's integration tests already emit 4 `DeprecationWarning`s from these sites. Five call sites total (Plan A backend code).

**Files:**
- Modify: `src/arena/backend/api/evaluations.py:52`
- Modify: `src/arena/backend/api/participants.py:33`
- Modify: `src/arena/backend/worker/queue.py:28`
- Modify: `src/arena/backend/worker/runner.py:75, 80`
- Modify: `tests/unit/arena/test_models.py` (add timezone assertion if not present)

- [ ] **Step 1: Write a failing test that pins behavior**

Add to `tests/unit/arena/test_api_participants.py` (append, do NOT replace existing):

```python
def test_register_stores_timezone_aware_timestamp(client, db):
    """Plan C T1: registered_at must be timezone-aware (UTC), not naive."""
    r = client.post("/api/participants", json={
        "display_name": "tz_test", "owner_email": "tz@x.c",
        "base_url": "http://p/v1", "model_name": "m", "model_meta": {},
    })
    assert r.status_code == 201
    from arena.backend.db.models import Participant
    p = db.query(Participant).filter_by(display_name="tz_test").one()
    assert p.registered_at.tzinfo is not None
    # And the value should be within 5 seconds of "now in UTC":
    from datetime import datetime, timezone, timedelta
    delta = abs((datetime.now(timezone.utc) - p.registered_at).total_seconds())
    assert delta < 5.0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/arena/test_api_participants.py::test_register_stores_timezone_aware_timestamp -v`
Expected: FAIL — `p.registered_at.tzinfo is None` (current `datetime.utcnow()` is naive).

- [ ] **Step 3: Replace all 5 call sites**

In each of the 5 lines listed above, replace:
```python
datetime.utcnow()
```
with:
```python
datetime.now(timezone.utc)
```

For each file, ensure the import includes `timezone`:

```python
# Before:
from datetime import datetime
# After:
from datetime import datetime, timezone
```

**Sanity:** `grep -rn "datetime.utcnow" src/arena/ tests/` must return zero matches after this task.

- [ ] **Step 4: Run tests**

Run: `uv run pytest tests/unit/arena/ tests/integration/ -v`
Expected: All tests pass. Specifically the new `test_register_stores_timezone_aware_timestamp` is green, and the prior 4 `DeprecationWarning`s in integration logs are gone.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/backend/api/evaluations.py \
        src/arena/backend/api/participants.py \
        src/arena/backend/worker/queue.py \
        src/arena/backend/worker/runner.py \
        tests/unit/arena/test_api_participants.py
git commit -m "fix(arena/backend): replace datetime.utcnow() with timezone-aware now(UTC)"
```

---

### Task 2: Indexed `api_key_prefix` lookup (replace linear bcrypt scan)

**Why:** `src/arena/backend/api/deps.py:32-34` runs `bcrypt verify` against every active participant on every authed request. O(N) scaling — fine for 10 participants, painful at 100+. Solution: store first 8 chars of plaintext key (sufficient entropy with `api_key_bytes=32` default) as an indexed column; lookup narrows to ≤1 row before bcrypt verify.

**Files:**
- Modify: `src/arena/backend/security.py` — add `key_prefix()` helper
- Modify: `src/arena/backend/db/models.py` — add `api_key_prefix` column with index
- Create: `src/arena/backend/db/migrations/versions/0002_api_key_prefix.py`
- Modify: `src/arena/backend/api/participants.py` — populate prefix at registration
- Modify: `src/arena/backend/api/deps.py` — narrow query by prefix
- Modify: `tests/unit/arena/test_security.py` — `key_prefix` tests
- Modify: `tests/unit/arena/test_api_participants.py` — prefix stored at registration
- Modify: `tests/unit/arena/test_migrations.py` — migration upgrade smoke

- [ ] **Step 1: Write failing tests for `key_prefix` helper**

Add to `tests/unit/arena/test_security.py`:

```python
def test_key_prefix_returns_first_8_chars():
    from arena.backend.security import key_prefix
    assert key_prefix("abcdefghijklmnop") == "abcdefgh"


def test_key_prefix_handles_short_keys():
    """For test fixtures using short keys, prefix == full key (length-capped)."""
    from arena.backend.security import key_prefix
    assert key_prefix("abc") == "abc"


def test_key_prefix_is_deterministic():
    from arena.backend.security import key_prefix
    assert key_prefix("alpha") == key_prefix("alpha")
```

- [ ] **Step 2: Run to verify failure**

Run: `uv run pytest tests/unit/arena/test_security.py -v`
Expected: `ImportError: cannot import name 'key_prefix'`.

- [ ] **Step 3: Implement `key_prefix`**

Append to `src/arena/backend/security.py`:

```python
def key_prefix(plaintext: str, length: int = 8) -> str:
    """Return the first `length` chars of plaintext (or the whole string if shorter).

    Used as a non-secret narrowing key for bcrypt lookup — see deps.require_api_key.
    Stored alongside the full bcrypt hash; collision means at most ~1 wasted bcrypt
    verify per ~16^8 = 4B keys.
    """
    return plaintext[:length]
```

- [ ] **Step 4: Run security tests**

Run: `uv run pytest tests/unit/arena/test_security.py -v`
Expected: 3 new tests pass.

- [ ] **Step 5: Add column to model**

Edit `src/arena/backend/db/models.py` — in the `Participant` class, add this field next to `api_key_hash`:

```python
api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
```

- [ ] **Step 6: Create migration**

Create `src/arena/backend/db/migrations/versions/0002_api_key_prefix.py`:

```python
"""Add api_key_prefix column to participants.

Revision ID: 0002_api_key_prefix
Revises: 0001_initial
"""

from alembic import op
import sqlalchemy as sa

revision = "0002_api_key_prefix"
down_revision = "0001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add as nullable for existing rows.
    op.add_column(
        "participants",
        sa.Column("api_key_prefix", sa.String(length=16), nullable=True),
    )
    # 2) Backfill: for any existing participants, mark prefix as empty string
    #    (they'll fail subsequent auth attempts; an admin must rotate keys).
    op.execute("UPDATE participants SET api_key_prefix = '' WHERE api_key_prefix IS NULL")
    # 3) Tighten to NOT NULL + index.
    with op.batch_alter_table("participants") as batch:
        batch.alter_column("api_key_prefix", existing_type=sa.String(length=16),
                            nullable=False)
        batch.create_index("ix_participants_api_key_prefix", ["api_key_prefix"])


def downgrade() -> None:
    with op.batch_alter_table("participants") as batch:
        batch.drop_index("ix_participants_api_key_prefix")
    op.drop_column("participants", "api_key_prefix")
```

- [ ] **Step 7: Wire migration into the test bootstrap**

Verify `tests/unit/arena/test_migrations.py` already exercises `0001_initial`. Append a smoke for `0002_api_key_prefix`:

```python
def test_migration_0002_adds_api_key_prefix_column(tmp_path):
    """Plan C T2: 0002 upgrade adds the indexed prefix column."""
    from sqlalchemy import create_engine, inspect
    from alembic.config import Config
    from alembic import command
    db_file = tmp_path / "m.sqlite"
    cfg = Config()
    cfg.set_main_option("script_location", "src/arena/backend/db/migrations")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{db_file}")
    command.upgrade(cfg, "head")
    eng = create_engine(f"sqlite:///{db_file}")
    cols = {c["name"] for c in inspect(eng).get_columns("participants")}
    assert "api_key_prefix" in cols
    idxs = {i["name"] for i in inspect(eng).get_indexes("participants")}
    assert "ix_participants_api_key_prefix" in idxs
```

- [ ] **Step 8: Populate prefix at registration**

Edit `src/arena/backend/api/participants.py`. In the existing `register()` handler, locate the `Participant(...)` constructor call. Add `api_key_prefix=key_prefix(plaintext_key)` and ensure `key_prefix` is imported:

```python
from arena.backend.security import generate_api_key, hash_api_key, key_prefix
# ...
plaintext_key = generate_api_key()
p = Participant(
    display_name=body.display_name,
    # ... existing fields ...
    api_key_hash=hash_api_key(plaintext_key),
    api_key_prefix=key_prefix(plaintext_key),
    registered_at=datetime.now(timezone.utc),  # already done in T1
    status=ParticipantStatus.active,
)
```

- [ ] **Step 9: Narrow `require_api_key` query**

Edit `src/arena/backend/api/deps.py`. Replace lines 26-34 (the `require_api_key` body) with:

```python
def require_api_key(
    db: Annotated[Session, Depends(get_db)],
    authorization: Annotated[str | None, Header()] = None,
) -> Participant:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    from arena.backend.security import key_prefix, verify_api_key
    prefix = key_prefix(token)
    # Narrow by indexed prefix; collision is rare (16^8 ≈ 4B keyspace per prefix).
    candidates = db.query(Participant).filter(
        Participant.status == ParticipantStatus.active,
        Participant.api_key_prefix == prefix,
    )
    for p in candidates:
        if verify_api_key(token, p.api_key_hash):
            return p
    raise HTTPException(status.HTTP_401_UNAUTHORIZED, "invalid api key")
```

- [ ] **Step 10: Add a registration test asserting the prefix is stored**

Add to `tests/unit/arena/test_api_participants.py`:

```python
def test_register_stores_api_key_prefix(client, db):
    """Plan C T2: api_key_prefix column is populated at registration."""
    r = client.post("/api/participants", json={
        "display_name": "px", "owner_email": "px@x.c",
        "base_url": "http://p/v1", "model_name": "m", "model_meta": {},
    })
    assert r.status_code == 201
    returned_key = r.json()["api_key"]
    from arena.backend.db.models import Participant
    p = db.query(Participant).filter_by(display_name="px").one()
    assert p.api_key_prefix == returned_key[:8]
    assert len(p.api_key_prefix) == 8
```

- [ ] **Step 11: Run the full backend suite + integration**

Run: `uv run pytest tests/unit/arena/ tests/integration/ -v`
Expected: All previously green tests stay green; 4 new tests (3 key_prefix + 1 register-stores-prefix + 1 migration) are green.

- [ ] **Step 12: Commit**

```bash
git status -s
git add src/arena/backend/security.py \
        src/arena/backend/db/models.py \
        src/arena/backend/db/migrations/versions/0002_api_key_prefix.py \
        src/arena/backend/api/participants.py \
        src/arena/backend/api/deps.py \
        tests/unit/arena/test_security.py \
        tests/unit/arena/test_api_participants.py \
        tests/unit/arena/test_migrations.py
git commit -m "perf(arena/auth): narrow require_api_key by indexed api_key_prefix"
```

---

### Task 3: Server-side test coverage for `DELETE /api/participants/me`

**Why:** Plan B's final review noted the existing `DELETE /me` endpoint (Plan A `src/arena/backend/api/participants.py:52`) is shipped but test-light. Three behaviors need explicit tests: happy path, idempotency on already-deactivated, missing/invalid bearer.

**Files:**
- Modify: `tests/unit/arena/test_api_participants.py`

- [ ] **Step 1: Write the 3 failing tests**

Append to `tests/unit/arena/test_api_participants.py`:

```python
def test_delete_me_returns_204_and_deactivates(client, db):
    """Plan C T3: happy path — deactivate sets status to inactive, returns 204."""
    r = client.post("/api/participants", json={
        "display_name": "to_delete", "owner_email": "d@x.c",
        "base_url": "http://p/v1", "model_name": "m", "model_meta": {},
    })
    key = r.json()["api_key"]

    r = client.delete("/api/participants/me",
                      headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 204

    from arena.backend.db.models import Participant, ParticipantStatus
    p = db.query(Participant).filter_by(display_name="to_delete").one()
    assert p.status == ParticipantStatus.inactive


def test_delete_me_is_idempotent_for_already_inactive(client, db):
    """Plan C T3: second DELETE after deactivation returns 401 (key no longer authes).

    NOTE: This is the current contract — once inactive, the bearer rejects.
    If we ever want true idempotency, we need to allow inactive participants
    to call DELETE again, which means weakening require_api_key. Out of scope.
    """
    r = client.post("/api/participants", json={
        "display_name": "idem", "owner_email": "i@x.c",
        "base_url": "http://p/v1", "model_name": "m", "model_meta": {},
    })
    key = r.json()["api_key"]
    client.delete("/api/participants/me", headers={"Authorization": f"Bearer {key}"})
    # Second attempt:
    r = client.delete("/api/participants/me", headers={"Authorization": f"Bearer {key}"})
    assert r.status_code == 401
    assert "invalid api key" in r.json()["detail"].lower()


def test_delete_me_rejects_missing_bearer(client):
    """Plan C T3: no Authorization header → 401."""
    r = client.delete("/api/participants/me")
    assert r.status_code == 401
    assert "bearer" in r.json()["detail"].lower()
```

- [ ] **Step 2: Run to verify**

Run: `uv run pytest tests/unit/arena/test_api_participants.py -v -k delete_me`
Expected: 3 new tests; they should all pass against the existing endpoint, OR reveal a bug for fixing. If any fail, investigate — do not modify the test to make it pass without understanding the underlying behavior.

- [ ] **Step 3: Commit**

```bash
git status -s
git add tests/unit/arena/test_api_participants.py
git commit -m "test(arena/api): cover DELETE /me happy path + idempotency + missing-auth"
```

---

## Phase 2 — Plan B CLI Follow-ups

### Task 4: Normalize `register` exit code (3 → 2) + document convention

**Why:** Plan B established that `1=identity/creds`, `2=usage/server`, `3=ping-specific`. `register` currently uses `code=3` for `ArenaServerError`, which inconsistent. CI scripts that branch on exit code are confused.

**Files:**
- Modify: `src/arena/participant_kit/arena_cli/commands/register.py:53`
- Modify: `src/arena/participant_kit/arena_cli/cli.py` (docstring update)
- Modify: `tests/unit/arena_cli/test_register.py` (exit code assertion update)

- [ ] **Step 1: Update the failing test first**

In `tests/unit/arena_cli/test_register.py`, `test_register_surfaces_422_validation_error`, change:

```python
assert result.exit_code != 0
```

to:

```python
assert result.exit_code == 2, result.output
```

- [ ] **Step 2: Run — confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_register.py::test_register_surfaces_422_validation_error -v`
Expected: FAIL — `exit_code == 3` currently.

- [ ] **Step 3: Change register.py exit code**

Edit `src/arena/participant_kit/arena_cli/commands/register.py` — change the only `raise click.exceptions.Exit(code=3)` to `code=2`.

- [ ] **Step 4: Add docstring to cli.py**

Edit `src/arena/participant_kit/arena_cli/cli.py`. Replace the module docstring with:

```python
"""arena-cli entrypoint: top-level Click group.

Exit code convention (uniform across commands):
    0 = success
    1 = local-side error (missing/duplicate credentials, bad CLI args)
    2 = server-side error (HTTP non-2xx from arena backend)
    3 = ping-specific validation failure (endpoint not OpenAI-compatible)
"""
```

- [ ] **Step 5: Run to verify GREEN**

Run: `uv run pytest tests/unit/arena_cli/ -v`
Expected: all green.

- [ ] **Step 6: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/register.py \
        src/arena/participant_kit/arena_cli/cli.py \
        tests/unit/arena_cli/test_register.py
git commit -m "fix(arena-cli): normalize register exit code to 2 + document convention"
```

---

### Task 5: TOCTOU-safe `save_credentials` (open with 0o600 from creation)

**Why:** `path.write_text(...)` creates the file with the process umask (typically 0o644) before `path.chmod(0o600)`. A race-window observer on a shared host can read the file. Switch to `os.open(..., O_CREAT, 0o600)` to atomically set the mode.

**Files:**
- Modify: `src/arena/participant_kit/arena_cli/config.py`
- Modify: `tests/unit/arena_cli/test_config.py`

- [ ] **Step 1: Add a TOCTOU-pinning test**

Append to `tests/unit/arena_cli/test_config.py`:

```python
def test_save_creates_file_with_0600_from_start(cred_dir, monkeypatch):
    """Plan C T5: file is born 0o600 — no window where it's world-readable."""
    import os
    observed = {}
    real_open = os.open

    def spy_open(path, flags, mode=0o777, *, dir_fd=None):
        # Capture the mode passed at creation.
        if "credentials.json" in str(path) and flags & os.O_CREAT:
            observed["mode"] = mode
        return real_open(path, flags, mode, dir_fd=dir_fd)

    monkeypatch.setattr(os, "open", spy_open)
    save_credentials(Credentials(participant_id=1, api_key="k", server="http://x"))
    assert observed.get("mode") == 0o600, f"file born with mode {oct(observed.get('mode', 0))}"
```

- [ ] **Step 2: Confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_config.py::test_save_creates_file_with_0600_from_start -v`
Expected: FAIL — current code does not use `os.open`.

- [ ] **Step 3: Rewrite `save_credentials`**

Edit `src/arena/participant_kit/arena_cli/config.py`. Replace the existing `save_credentials` body with:

```python
def save_credentials(creds: Credentials) -> None:
    d = _config_dir()
    d.mkdir(parents=True, exist_ok=True, mode=0o700)
    d.chmod(0o700)  # enforce even if dir pre-existed with looser perms
    path = _config_file()
    payload = creds.model_dump_json().encode("utf-8")
    # Born-0600 to avoid a TOCTOU window between create and chmod.
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    fd = os.open(path, flags, 0o600)
    try:
        os.write(fd, payload)
    finally:
        os.close(fd)
```

Note: T5 also fixes I3 (parent dir perm not enforced on existing dir) — the `d.chmod(0o700)` line.

- [ ] **Step 4: Re-run full config suite**

Run: `uv run pytest tests/unit/arena_cli/test_config.py -v`
Expected: 6 passed (5 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/config.py \
        tests/unit/arena_cli/test_config.py
git commit -m "fix(arena-cli): born-0600 credentials.json + enforce 0700 on parent dir"
```

---

### Task 6: CI portability — skip integration smoke if `uv` not on PATH

**Why:** `tests/integration/test_arena_cli_e2e.py` shells out to `uv run arena-cli`. CI environments without `uv` installed will fail this test loudly. Skip cleanly with a discoverable reason.

**Files:**
- Modify: `tests/integration/test_arena_cli_e2e.py`

- [ ] **Step 1: Add skip guard at top of test file**

Edit `tests/integration/test_arena_cli_e2e.py`. After the imports, add:

```python
import shutil
import pytest

if shutil.which("uv") is None:
    pytest.skip(
        "`uv` not on PATH — arena-cli integration smoke requires uv. "
        "Install via https://docs.astral.sh/uv/getting-started/installation/",
        allow_module_level=True,
    )
```

(Place this BEFORE the fixtures/test definitions so it executes at collection time.)

- [ ] **Step 2: Verify it still passes locally**

Run: `uv run pytest tests/integration/test_arena_cli_e2e.py -v`
Expected: 1 passed (since `uv` IS on PATH in our env).

- [ ] **Step 3: Verify the skip path**

Run with PATH stripped of uv:
```bash
env -i PATH="/usr/bin:/bin" uv run pytest tests/integration/test_arena_cli_e2e.py -v
```
Expected: 1 skipped (reason includes "uv not on PATH").

- [ ] **Step 4: Commit**

```bash
git status -s
git add tests/integration/test_arena_cli_e2e.py
git commit -m "test(arena-cli): skip e2e smoke gracefully when uv missing from PATH"
```

---

### Task 7: Remove dead `import respx` from 7 test files

**Why:** The `respx_mock` fixture is auto-discovered via the respx pytest plugin entry-point; the bare `import respx` is unused. Lint tools (ruff F401) will flag them.

**Files (all `tests/unit/arena_cli/`):**
- Modify: `test_cli_entry.py`
- Modify: `test_client.py`
- Modify: `test_leaderboard.py`
- Modify: `test_ping.py`
- Modify: `test_register.py`
- Modify: `test_status.py`
- Modify: `test_submit.py`

- [ ] **Step 1: Remove the bare imports**

In each of the 7 files above, delete the line:
```python
import respx
```

Leave all other imports (e.g., `httpx`, `pytest`, `click.testing`) untouched.

- [ ] **Step 2: Run the full unit suite**

Run: `uv run pytest tests/unit/arena_cli/ -v`
Expected: all green (count unchanged).

- [ ] **Step 3: Commit**

```bash
git status -s
git add tests/unit/arena_cli/test_cli_entry.py \
        tests/unit/arena_cli/test_client.py \
        tests/unit/arena_cli/test_leaderboard.py \
        tests/unit/arena_cli/test_ping.py \
        tests/unit/arena_cli/test_register.py \
        tests/unit/arena_cli/test_status.py \
        tests/unit/arena_cli/test_submit.py
git commit -m "chore(arena-cli/tests): remove dead 'import respx' (respx_mock is plugin-loaded)"
```

---

### Task 8: Order subcommands by workflow in `--help`

**Why:** Click's default is alphabetical (`leaderboard, ping, register, status, submit`). New users reading `arena-cli --help` should see the workflow order: `register → ping → submit → status → leaderboard → unregister` (the last added in Phase 3 but reserve the spot here).

**Files:**
- Modify: `src/arena/participant_kit/arena_cli/cli.py`
- Modify: `tests/unit/arena_cli/test_cli_entry.py`

- [ ] **Step 1: Write a failing test for the order**

Add to `tests/unit/arena_cli/test_cli_entry.py`:

```python
def test_help_lists_commands_in_workflow_order():
    """Plan C T8: --help shows register first, leaderboard last (workflow order)."""
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    # Find each command's position in the output:
    positions = {c: result.output.find(c) for c in
                 ("register", "ping", "submit", "status", "leaderboard")}
    # All present:
    assert all(p > 0 for p in positions.values()), positions
    # Workflow order:
    assert positions["register"] < positions["ping"] < positions["submit"] \
           < positions["status"] < positions["leaderboard"]
```

- [ ] **Step 2: Confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_cli_entry.py::test_help_lists_commands_in_workflow_order -v`
Expected: FAIL — alphabetical default puts leaderboard first.

- [ ] **Step 3: Implement custom Group**

Edit `src/arena/participant_kit/arena_cli/cli.py`. Replace the `@click.group()` decorator and following block with:

```python
WORKFLOW_ORDER = ["register", "ping", "submit", "status", "leaderboard"]


class _WorkflowOrderGroup(click.Group):
    """Click Group that lists subcommands in workflow order instead of alphabetical."""

    def list_commands(self, ctx: click.Context) -> list[str]:
        all_cmds = super().list_commands(ctx)
        ordered = [c for c in WORKFLOW_ORDER if c in all_cmds]
        # Append any commands not in WORKFLOW_ORDER (e.g., unregister added later).
        return ordered + [c for c in all_cmds if c not in ordered]


@click.group(cls=_WorkflowOrderGroup)
@click.version_option(__version__, prog_name="arena-cli")
def main() -> None:
    """arena-cli — manage your BYO endpoint registration with LLM Squid Game Arena."""
```

Keep the existing `main.add_command(...)` lines unchanged.

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/arena_cli/test_cli_entry.py -v`
Expected: all green (6 tests now, with the new ordering one).

Also visually verify: `uv run arena-cli --help` — commands should now appear in workflow order.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/cli.py \
        tests/unit/arena_cli/test_cli_entry.py
git commit -m "feat(arena-cli): list subcommands in workflow order in --help"
```

---

### Task 9: Status command — render None fields as em-dash

**Why:** When an evaluation is queued (not started), `started_at=None` and `finished_at=None` print as the literal string `"None"`, which contradicts the README example. Render `None` as `—` (em-dash) consistent with the leaderboard.

**Files:**
- Modify: `src/arena/participant_kit/arena_cli/commands/status.py`
- Modify: `tests/unit/arena_cli/test_status.py`

- [ ] **Step 1: Write a failing assertion**

Add to `tests/unit/arena_cli/test_status.py`:

```python
def test_status_renders_none_fields_as_em_dash(cred_dir, respx_mock):
    """Plan C T9: queued eval (no started_at/finished_at) shows — not 'None'."""
    _seed()
    respx_mock.get("http://srv/api/evaluations/5").mock(
        return_value=httpx.Response(200, json={
            "id": 5, "status": "queued", "participant_id": 1,
            "config_label": "smoke", "queued_at": "2026-05-24T00:00:00",
            "started_at": None, "finished_at": None, "error_message": None,
        })
    )
    result = CliRunner().invoke(status_cmd, ["5"])
    assert result.exit_code == 0
    assert "started_at=—" in result.output
    assert "finished_at=—" in result.output
    assert "None" not in result.output
```

- [ ] **Step 2: Confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_status.py::test_status_renders_none_fields_as_em_dash -v`
Expected: FAIL — output currently contains `started_at=None`.

- [ ] **Step 3: Implement the normalization**

Edit `src/arena/participant_kit/arena_cli/commands/status.py`. In the `else` (eval_id given) branch, change the two `click.echo` calls to:

```python
def _none_as_dash(v):
    return "—" if v is None else v

ev = client.get_evaluation(eval_id)
click.echo(f"id={ev['id']} status={ev['status']} "
           f"config_label={ev['config_label']}")
click.echo(f"queued_at={_none_as_dash(ev['queued_at'])} "
           f"started_at={_none_as_dash(ev['started_at'])} "
           f"finished_at={_none_as_dash(ev['finished_at'])}")
if ev.get("error_message"):
    click.echo(f"error_message: {ev['error_message']}")
```

(Define `_none_as_dash` inside the function — single use, no need to hoist.)

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/arena_cli/test_status.py -v`
Expected: 5 passed (4 existing + 1 new).

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/status.py \
        tests/unit/arena_cli/test_status.py
git commit -m "fix(arena-cli): render null timestamps as em-dash in status output"
```

---

### Task 10: `register --model-meta` JSON parse error UX

**Why:** When the user passes malformed JSON to `--model-meta`, the current error message dumps the raw `json.JSONDecodeError` repr ("Expecting value: line 1 column 1 (char 0)") with no example of valid input. Append an example.

**Files:**
- Modify: `src/arena/participant_kit/arena_cli/commands/register.py`
- Modify: `tests/unit/arena_cli/test_register.py`

- [ ] **Step 1: Add a failing UX test**

Append to `tests/unit/arena_cli/test_register.py`:

```python
def test_register_model_meta_error_includes_example(cred_dir):
    """Plan C T10: bad --model-meta error message shows a valid example."""
    result = CliRunner().invoke(register_cmd, [
        "--server", "http://srv", "--display-name", "x",
        "--owner-email", "x@x.c", "--base-url", "http://p/v1",
        "--model-name", "m",
        "--model-meta", "not-json{",
    ])
    assert result.exit_code == 2
    # Helpful example must appear:
    assert '{"params":"8B"}' in result.output or '{"params": "8B"}' in result.output
```

- [ ] **Step 2: Confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_register.py::test_register_model_meta_error_includes_example -v`
Expected: FAIL — current error has no example.

- [ ] **Step 3: Append example to the error message**

Edit `src/arena/participant_kit/arena_cli/commands/register.py`. Change the JSON parse error block from:

```python
except ValueError as exc:
    click.echo(f"--model-meta must be valid JSON: {exc}", err=True)
    raise click.exceptions.Exit(code=2)
```

to:

```python
except ValueError as exc:
    click.echo(
        f"--model-meta must be valid JSON: {exc}\n"
        f'Example: --model-meta \'{{"params":"8B"}}\'',
        err=True,
    )
    raise click.exceptions.Exit(code=2)
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/arena_cli/test_register.py -v`
Expected: all green (4 tests now).

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/register.py \
        tests/unit/arena_cli/test_register.py
git commit -m "fix(arena-cli): include valid JSON example in --model-meta error"
```

---

### Task 11: README — Windows perm disclaimer

**Why:** README's "Privacy and security" section promises mode `0600`, but Windows NTFS does not honor Unix file modes. Add a one-line disclaimer.

**Files:**
- Modify: `src/arena/participant_kit/README.md`

- [ ] **Step 1: Append disclaimer**

Edit `src/arena/participant_kit/README.md`. In the "Privacy and security" section, after the existing "Your `~/.arena/credentials.json` is created with mode `0600`..." bullet, add:

```markdown
- **Windows users:** filesystem ACLs differ — `credentials.json` is created with
  default Windows permissions (the file mode bits are not enforced on NTFS).
  Use Windows BitLocker or per-user profile isolation for equivalent protection.
```

- [ ] **Step 2: Sanity check**

Run: `grep -c '^```' src/arena/participant_kit/README.md` → must remain even (code fences paired).

- [ ] **Step 3: Commit**

```bash
git status -s
git add src/arena/participant_kit/README.md
git commit -m "docs(arena-cli): document Windows perm caveat for credentials.json"
```

---

## Phase 3 — `arena-cli unregister` Command

### Task 12: Add `ArenaClient.unregister()` HTTP method

**Why:** `ArenaClient` is the single seam for arena REST calls. Add a method that calls `DELETE /api/participants/me` with Bearer auth and returns `None` (204 has no body).

**Files:**
- Modify: `src/arena/participant_kit/arena_cli/client.py`
- Modify: `tests/unit/arena_cli/test_client.py`

- [ ] **Step 1: Failing test**

Add to `tests/unit/arena_cli/test_client.py`:

```python
def test_unregister_sends_delete_with_bearer(respx_mock):
    """Plan C T12: unregister() calls DELETE /api/participants/me with Bearer auth."""
    route = respx_mock.delete("http://srv/api/participants/me").mock(
        return_value=httpx.Response(204)
    )
    c = ArenaClient(server="http://srv", api_key="k")
    out = c.unregister()
    assert route.called
    assert route.calls.last.request.headers["authorization"] == "Bearer k"
    assert out is None


def test_unregister_401_raises_arena_error(respx_mock):
    """Plan C T12: stale token → ArenaServerError."""
    respx_mock.delete("http://srv/api/participants/me").mock(
        return_value=httpx.Response(401, json={"detail": "invalid api key"})
    )
    c = ArenaClient(server="http://srv", api_key="stale")
    with pytest.raises(ArenaServerError):
        c.unregister()
```

- [ ] **Step 2: Confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_client.py -v -k unregister`
Expected: FAIL — `AttributeError: 'ArenaClient' object has no attribute 'unregister'`.

- [ ] **Step 3: Add method**

Edit `src/arena/participant_kit/arena_cli/client.py`. Add this method to `ArenaClient`, between `get_evaluation` and `leaderboard`:

```python
def unregister(self) -> None:
    """DELETE /api/participants/me — deactivate the calling participant.

    Returns None on 204. Raises ArenaServerError on any non-2xx.
    """
    r = self._client.delete(
        "/api/participants/me", headers=self._headers()
    )
    self._raise_for(r)
    return None
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/arena_cli/test_client.py -v`
Expected: 7 passed (5 existing + 2 new).

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/client.py \
        tests/unit/arena_cli/test_client.py
git commit -m "feat(arena-cli/client): add unregister() — DELETE /api/participants/me"
```

---

### Task 13: `arena-cli unregister` CLI command

**Why:** Wire the new HTTP method to a Click command. Confirm before destructive action; on success, clear local credentials so re-registration can proceed.

**Files:**
- Create: `src/arena/participant_kit/arena_cli/commands/unregister.py`
- Create: `tests/unit/arena_cli/test_unregister.py`

- [ ] **Step 1: Failing tests**

Create `tests/unit/arena_cli/test_unregister.py`:

```python
"""unregister command: DELETE /api/participants/me + clear local credentials."""

from click.testing import CliRunner

import httpx
import pytest

from arena.participant_kit.arena_cli.commands.unregister import unregister_cmd
from arena.participant_kit.arena_cli.config import (
    Credentials,
    CredentialsNotFound,
    load_credentials,
    save_credentials,
)


def _seed():
    save_credentials(Credentials(participant_id=1, api_key="K", server="http://srv"))


def test_unregister_with_yes_deactivates_and_clears_creds(cred_dir, respx_mock):
    _seed()
    respx_mock.delete("http://srv/api/participants/me").mock(
        return_value=httpx.Response(204)
    )
    result = CliRunner().invoke(unregister_cmd, ["--yes"])
    assert result.exit_code == 0, result.output
    assert "deactivated" in result.output.lower()
    with pytest.raises(CredentialsNotFound):
        load_credentials()


def test_unregister_without_yes_prompts_and_aborts_on_no(cred_dir, respx_mock):
    _seed()
    # The route must NOT be called when the user says no.
    route = respx_mock.delete("http://srv/api/participants/me").mock(
        return_value=httpx.Response(204)
    )
    result = CliRunner().invoke(unregister_cmd, [], input="n\n")
    assert result.exit_code != 0
    assert not route.called
    # Local creds must still exist.
    assert load_credentials().participant_id == 1


def test_unregister_requires_credentials(cred_dir):
    result = CliRunner().invoke(unregister_cmd, ["--yes"])
    assert result.exit_code == 1
    assert "register" in result.output.lower()


def test_unregister_surfaces_server_error_keeps_local_creds(cred_dir, respx_mock):
    _seed()
    respx_mock.delete("http://srv/api/participants/me").mock(
        return_value=httpx.Response(500, json={"detail": "db down"})
    )
    result = CliRunner().invoke(unregister_cmd, ["--yes"])
    assert result.exit_code == 2
    assert "db down" in result.output
    # If server failed, local creds remain — user can retry.
    assert load_credentials().participant_id == 1
```

- [ ] **Step 2: Confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_unregister.py -v`
Expected: `ModuleNotFoundError`.

- [ ] **Step 3: Implement**

Create `src/arena/participant_kit/arena_cli/commands/unregister.py`:

```python
"""arena-cli unregister — DELETE /api/participants/me + clear local credentials.

Destructive: once unregistered, the api_key is permanently invalid (re-registration
gets a new id). Confirms with the user unless --yes is passed.

Exit codes:
    0 = success
    1 = missing local credentials (nothing to unregister)
    2 = server-side error (HTTP non-2xx)
"""

import click

from arena.participant_kit.arena_cli.client import ArenaClient, ArenaServerError
from arena.participant_kit.arena_cli.config import (
    CredentialsNotFound,
    clear_credentials,
    load_credentials,
)


@click.command("unregister")
@click.option("--yes", is_flag=True,
              help="Skip the confirmation prompt (use with care in scripts).")
def unregister_cmd(yes: bool) -> None:
    """Deactivate the current participant on the arena server and forget local credentials."""
    try:
        creds = load_credentials()
    except CredentialsNotFound as exc:
        click.echo(str(exc) + " Nothing to unregister.", err=True)
        raise click.exceptions.Exit(code=1)

    if not yes:
        confirmed = click.confirm(
            f"Deactivate participant_id={creds.participant_id} on {creds.server}? "
            "This is permanent — your api_key will be rejected from this point on.",
            default=False,
        )
        if not confirmed:
            click.echo("Aborted.", err=True)
            raise click.exceptions.Exit(code=1)

    client = ArenaClient(server=creds.server, api_key=creds.api_key)
    try:
        client.unregister()
    except ArenaServerError as exc:
        # Server-side failure: keep local creds so the user can retry.
        click.echo(str(exc), err=True)
        raise click.exceptions.Exit(code=2)
    finally:
        client.close()

    # Only clear local creds AFTER the server confirms deactivation.
    clear_credentials()
    click.echo(f"Deactivated participant_id={creds.participant_id} "
               "and cleared local credentials.")
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/arena_cli/test_unregister.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/commands/unregister.py \
        tests/unit/arena_cli/test_unregister.py
git commit -m "feat(arena-cli): unregister command — deactivate participant + clear creds"
```

---

### Task 14: Wire `unregister` into the CLI group + verify in `--help`

**Files:**
- Modify: `src/arena/participant_kit/arena_cli/cli.py`
- Modify: `tests/unit/arena_cli/test_cli_entry.py`

- [ ] **Step 1: Failing assertion**

In `tests/unit/arena_cli/test_cli_entry.py`, update `test_help_lists_all_commands` to include `unregister`:

```python
def test_help_lists_all_commands():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    for c in ("register", "ping", "submit", "status", "leaderboard", "unregister"):
        assert c in result.output
```

Also extend the workflow-order assertion from Task 8 so `unregister` appears last:

```python
def test_help_lists_commands_in_workflow_order():
    result = CliRunner().invoke(main, ["--help"])
    assert result.exit_code == 0
    positions = {c: result.output.find(c) for c in
                 ("register", "ping", "submit", "status", "leaderboard", "unregister")}
    assert all(p > 0 for p in positions.values()), positions
    assert positions["register"] < positions["ping"] < positions["submit"] \
           < positions["status"] < positions["leaderboard"] < positions["unregister"]
```

And update `WORKFLOW_ORDER` in `cli.py` (next step).

- [ ] **Step 2: Confirm RED**

Run: `uv run pytest tests/unit/arena_cli/test_cli_entry.py -v`
Expected: 2 failures (help-lists-all and workflow-order both reference `unregister` not yet added).

- [ ] **Step 3: Wire the command**

Edit `src/arena/participant_kit/arena_cli/cli.py`:

```python
# Update WORKFLOW_ORDER:
WORKFLOW_ORDER = ["register", "ping", "submit", "status", "leaderboard", "unregister"]

# Add the import alongside the others:
from arena.participant_kit.arena_cli.commands.unregister import unregister_cmd

# Add the command line alongside the others:
main.add_command(unregister_cmd)
```

- [ ] **Step 4: Run**

Run: `uv run pytest tests/unit/arena_cli/test_cli_entry.py -v`
Expected: all green.

Also visually: `uv run arena-cli --help` shows 6 commands in workflow order.

- [ ] **Step 5: Commit**

```bash
git status -s
git add src/arena/participant_kit/arena_cli/cli.py \
        tests/unit/arena_cli/test_cli_entry.py
git commit -m "feat(arena-cli): wire unregister into the Click group"
```

---

### Task 15: README — document `unregister`

**Files:**
- Modify: `src/arena/participant_kit/README.md`

- [ ] **Step 1: Update commands table**

Edit `src/arena/participant_kit/README.md`. Append a row to the existing commands table:

```markdown
| `unregister [--yes]` | Deactivate the participant on the server and clear local credentials. Asks for confirmation; pass `--yes` for non-interactive scripts. |
```

- [ ] **Step 2: Add to the 5-minute path appendix**

After the existing "6) See yourself on the leaderboard" block, append:

```markdown
# 7) (Optional) When you're done — deactivate.
uv run arena-cli unregister
# → Deactivate participant_id=42 on https://arena.example.com? [y/N]: y
# → Deactivated participant_id=42 and cleared local credentials.
```

- [ ] **Step 3: Sanity check**

Run: `grep -c '^```' src/arena/participant_kit/README.md` → must remain even.

- [ ] **Step 4: Commit**

```bash
git status -s
git add src/arena/participant_kit/README.md
git commit -m "docs(arena-cli): document unregister command"
```

---

## Final Verification

After all 15 tasks:

- [ ] Run full backend + cli + integration suite:

```bash
uv run pytest tests/unit/arena/ tests/unit/arena_cli/ tests/integration/test_arena_cli_e2e.py -v
```

Expected counts (approximate):
- `tests/unit/arena/` — Plan A baseline + 3 (DELETE /me) + 4 (key_prefix incl. migration) + 1 (timezone) = baseline + 8
- `tests/unit/arena_cli/` — Plan B 37 + 1 (TOCTOU) + 1 (order) + 1 (status em-dash) + 1 (model-meta UX) + 2 (client unregister) + 4 (unregister cmd) = 47
- `tests/integration/test_arena_cli_e2e.py` — 1 (unchanged, skipped if no uv)

- [ ] Confirm no `datetime.utcnow` matches remain:

```bash
grep -rn "datetime.utcnow" src/arena/ tests/
```
Expected: empty.

- [ ] Confirm no dead `import respx`:

```bash
grep -rln "^import respx$" tests/
```
Expected: empty.

- [ ] Visual help check:

```bash
uv run arena-cli --help
```
Expected output begins with:
```
Commands:
  register      ...
  ping          ...
  submit        ...
  status        ...
  leaderboard   ...
  unregister    ...
```

- [ ] PR title suggestion: `arena: Plan C — backend debt + Participant Kit follow-ups + unregister CLI`.

---

## Self-Review Notes

**Spec coverage:**
- Plan-A debt items flagged in Plan B's whole-branch review: ✅ T1 (datetime), ✅ T2 (key_prefix), ✅ T3 (DELETE /me coverage). `/api/models/{participant_id}` endpoint exists (`leaderboard.py:51`) but is unused by Plan B's CLI — adding an `arena-cli card` consumer is plausibly Plan C scope but feels weak relative to the rest. Deferred to a future plan with explicit user request.
- Plan-B Important issues (I1-I5) from final review: ✅ T4 (I1 exit code), ✅ T5 (I2 TOCTOU + I3 dir perm — combined since both touch `save_credentials`), ✅ T6 (I4 CI portability), ✅ T7 (I5 respx imports).
- Plan-B Minor issues addressed: ✅ T8 (M1 help order), ✅ T9 (M4 None display), ✅ T10 (M7 JSON error UX), ✅ T11 (M2 Windows doc). Skipped: M3 (timeout arg never overridden — true dead code candidate, but adding a CLI flag is feature creep), M5 (ping body 200-char echo — already user-local stderr only), M6 (HTTPS self-signed escape hatch — feature, not a fix).
- arena-cli unregister: ✅ T12-T15 cover HTTP method, CLI command, wiring, docs.

**Placeholder scan:** No "TBD"/"TODO"/"similar to Task N" in any task. All code blocks present.

**Type consistency:**
- `Credentials(participant_id, api_key, server)` — unchanged across Plan B/C.
- `ArenaClient(server, api_key)` — unchanged signature; new method `unregister()` returns `None`.
- `key_prefix(plaintext, length=8) -> str` — defined T2 Step 3, used T2 Steps 8/9.
- `_WorkflowOrderGroup` — Click `Group` subclass introduced T8, extended via `WORKFLOW_ORDER` list in T14 (append `"unregister"`).
- `_none_as_dash(v)` — local helper in T9, single-use.

**Cross-phase invariant:** Phase 1 changes the backend; Phases 2-3 do not depend on Phase 1 changes (the CLI talks to the public REST surface, which is unchanged in shape). However, Phase 1 must commit FIRST because some Plan B integration tests will incidentally exercise the new prefix path. If Phase 2/3 commits land first, Phase 1's `test_register_stores_api_key_prefix` is the only test that could fail in isolation — and only if Phase 2/3 introduced new API surface, which they don't. Safe to execute in order.

**Risk areas:**
- T2 step 7 (migration smoke) relies on `tests/unit/arena/test_migrations.py` existing from Plan A. Verified — file exists with `test_migration_0001`. The new test follows the same pattern.
- T6 step 3 (skip path verification) uses `env -i` to strip PATH. On some CI runners this may not work cleanly — if the step is flaky, simply confirm Step 2 (positive path) green and move on; the skip itself is exercised in environments without uv.
- T13 step 1 expectation: `test_unregister_without_yes_prompts_and_aborts_on_no` uses `runner.invoke(..., input="n\n")` — Click `confirm` reads from stdin. CliRunner provides isolated stdin, so this works.

**Deferred to Plan D (arena-cli PyPI extraction):**
- Move `src/arena/participant_kit/arena_cli/` to its own `pyproject.toml` with separate version, package name (`arena-cli`), and PyPI publish workflow.
- Separate semver, CHANGELOG, release tags.
- Trim dependency surface (the participant-side CLI should NOT depend on FastAPI/SQLAlchemy/alembic — Plan B's root pyproject ties them together).
- Estimated 5-7 tasks; needs a brief spec discussion first.

**Deferred to Plan E (React frontend):**
- `src/arena/frontend/` per BYO spec §3.2 — Next.js or Vite + React + TanStack Query.
- UX brainstorming required before any planning: who reads the leaderboard, what gates the "submit evaluation" UI vs CLI, do we need OAuth.
- Out of scope for any follow-up plan that ships in a single PR.
