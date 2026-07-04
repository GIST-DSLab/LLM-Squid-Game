# Web Arena Backup + Configurable Arena max_tokens — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** (A) Add a script that mirrors the live Supabase Web Arena DB to a local SQLite file for backup/analysis, and (B) make the BYOE Arena's per-call `max_tokens` a caller-supplied value (API + frontend) instead of the hardcoded 2048, so reasoning models get enough headroom.

**Architecture:** Both features ride the existing driver-agnostic `interface.persistence.Repository` abstraction. (A) reads via `get_repository(source_dsn)` (Postgres/Supabase) and writes via `get_repository(dest_path)` (SQLite) — the exact inverse of `scripts/seed_web_arena.py`, reusing the same idempotent skip-existing pattern. (B) threads a `max_tokens` value from `ArenaRunRequest` → `arena_run` endpoint → `run_arena_session` → `_arena_config_dict` → `provider_config.max_tokens`, which `runner.py:370` already forwards to the agent (`VanillaAgent._max_tokens`).

**Tech Stack:** Python 3.12, `uv`, pytest, FastAPI/pydantic (API), vanilla JS (`web/app.js`, `web/index.html`), `interface.persistence` (SQLite + Postgres repositories).

## Global Constraints

- Python ≥ 3.12 (`pyproject.toml: requires-python = ">=3.12"`).
- Run all Python via `uv run --no-sync`; on this macOS + iCloud checkout, prefix test/seed commands with `chflags nohidden .venv/lib/python3.12/site-packages/*.pth` (iCloud hides `*.pth`, breaking `squid_game` import).
- Persistence access goes **only** through `interface.persistence` (`get_repository`, `Repository`, `SessionRecord`, `TurnRecord`, `ModelStatsRecord`) — never a concrete DB driver in new code except where a test explicitly constructs `SQLiteRepository(":memory:")`.
- Secrets (Supabase DSN) never committed — read from `$WEB_ARENA_DSN` / `.env` / CLI arg only.
- No new third-party dependencies.
- Repository interface (verbatim signatures the new code consumes):
  - `create_session(session: SessionRecord) -> str` (preserves `session.created_at` when non-None)
  - `get_session(session_id: str) -> SessionRecord | None`
  - `list_sessions(*, source: str | None = None, task: str | None = None, framing: str | None = None, order_by_score: bool = False) -> list[SessionRecord]`
  - `add_turns(turns: list[TurnRecord]) -> None`
  - `list_turns(session_id: str) -> list[TurnRecord]`
  - `upsert_model_stats(stats: ModelStatsRecord) -> None`
  - `list_model_stats() -> list[ModelStatsRecord]`
  - `close() -> None`; also a context manager (`__enter__`/`__exit__`).

---

## File Structure

**Part A — Backup script**
- Create: `scripts/backup_web_arena.py` — CLI + `mirror_repository()` core.
- Create: `tests/unit/test_backup_web_arena.py` — offline unit test (SQLite→SQLite in-memory).

**Part B — Configurable max_tokens**
- Modify: `interface/api.py` — add `max_tokens` field to `ArenaRunRequest`; forward it in `arena_run`.
- Modify: `interface/arena.py` — add `max_tokens` param to `run_arena_session` and `_arena_config_dict`.
- Modify: `web/app.js` — add `maxTokens` to the arena form data + POST body.
- Modify: `web/index.html` — add a `max_tokens` number input to the arena form.
- Modify: `tests/integration/test_arena.py` — assert the value reaches the endpoint body.
- Modify: `tests/unit/test_api_web_arena.py` — assert the request field default + validation bounds.

Parts A and B are independent; either can be implemented and shipped alone.

---

## Part A — Backup / mirror script

### Task A1: `mirror_repository()` core + CLI

**Files:**
- Create: `scripts/backup_web_arena.py`
- Test: `tests/unit/test_backup_web_arena.py`

**Interfaces:**
- Consumes: `interface.persistence.get_repository`, `Repository` (see Global Constraints for method signatures).
- Produces:
  - `mirror_repository(source: Repository, dest: Repository) -> tuple[int, int, int]` — returns `(sessions_copied, turns_copied, model_stats_copied)`. Idempotent: skips a session whose id already exists in `dest`.
  - `main(argv: list[str] | None = None) -> None` — CLI entry.

- [ ] **Step 1: Write the failing test**

```python
# tests/unit/test_backup_web_arena.py
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/unit/test_backup_web_arena.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'scripts.backup_web_arena'`.

- [ ] **Step 3: Write minimal implementation**

```python
# scripts/backup_web_arena.py
"""Mirror the live Web Arena DB (Supabase/Postgres) to a local SQLite file.

Inverse of scripts/seed_web_arena.py: reads sessions/turns/model_stats from a
source Repository and writes them to a destination Repository, both obtained
via interface.persistence.get_repository (so it works Postgres->SQLite,
SQLite->SQLite, etc). Idempotent: sessions already present in the destination
(by id) are skipped; model_stats are upserted. Only durable rows are copied —
this is a backup/analysis snapshot, not a live sync.

Usage::

    # Supabase -> dated local SQLite (default dest)
    uv run --no-sync python scripts/backup_web_arena.py \
        --source-dsn "$WEB_ARENA_DSN"

    # explicit destination
    uv run --no-sync python scripts/backup_web_arena.py \
        --source-dsn "postgresql://..." --dest outputs/web_arena/backup.db
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from interface.persistence import Repository, get_repository  # noqa: E402

logger = logging.getLogger("backup_web_arena")


def mirror_repository(source: Repository, dest: Repository) -> tuple[int, int, int]:
    """Copy all sessions+turns+model_stats from ``source`` into ``dest``.

    Returns ``(sessions_copied, turns_copied, model_stats_copied)``. Skips a
    session (and its turns) whose id already exists in ``dest`` so re-runs are
    safe; ``model_stats`` are upserted every run.
    """
    n_sessions = n_turns = n_stats = 0
    for session in source.list_sessions():
        if dest.get_session(session.id) is not None:
            continue
        dest.create_session(session)  # created_at preserved (non-None)
        turns = source.list_turns(session.id)
        if turns:
            dest.add_turns(turns)
            n_turns += len(turns)
        n_sessions += 1
    for stats in source.list_model_stats():
        dest.upsert_model_stats(stats)
        n_stats += 1
    return n_sessions, n_turns, n_stats


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--source-dsn", default=None,
        help="Source DB DSN (default: $WEB_ARENA_DSN, else local SQLite fallback).",
    )
    parser.add_argument(
        "--dest", default=None,
        help="Destination SQLite path (default: outputs/web_arena/backup_<UTC-date>.db).",
    )
    args = parser.parse_args(argv)

    dest_path = args.dest
    if dest_path is None:
        stamp = datetime.utcnow().strftime("%Y%m%d_%H%M")
        dest_dir = REPO_ROOT / "outputs" / "web_arena"
        dest_dir.mkdir(parents=True, exist_ok=True)
        dest_path = str(dest_dir / f"backup_{stamp}.db")

    source = get_repository(args.source_dsn)
    dest = get_repository(dest_path)
    try:
        n_sessions, n_turns, n_stats = mirror_repository(source, dest)
    finally:
        source.close()
        dest.close()

    logger.info(
        "mirrored %d sessions, %d turns, %d model_stats -> %s",
        n_sessions, n_turns, n_stats, dest_path,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
    main()
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/unit/test_backup_web_arena.py -v`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add scripts/backup_web_arena.py tests/unit/test_backup_web_arena.py
git commit -m "feat(web-arena): add backup script mirroring live DB to local SQLite"
```

### Task A2: Live smoke against Supabase (manual, no test)

**Files:** none (operational verification).

- [ ] **Step 1: Run the backup against the live Supabase DSN**

Run (substitute the real DSN — from `.env` `OLLAMA`-style, do NOT paste inline in committed files):
```bash
cd "<repo-root>"
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null
uv run --no-sync python scripts/backup_web_arena.py \
  --source-dsn "postgresql://postgres.ptiifyeixluosuyuhqcu:<pw>@aws-1-ap-northeast-2.pooler.supabase.com:5432/postgres"
```
Expected log: `mirrored 720 sessions, 8255 turns, 4 model_stats -> outputs/web_arena/backup_<stamp>.db` (counts grow as live plays accumulate).

- [ ] **Step 2: Verify the local snapshot**

Run:
```bash
uv run --no-sync python -c "from interface.persistence import get_repository; r=get_repository('outputs/web_arena/backup_<stamp>.db'); print(len(r.list_sessions()), 'sessions', len(r.list_model_stats()), 'model_stats')"
```
Expected: prints the same counts as the mirror log.

- [ ] **Step 3: (docs) note the backup cadence** — add one line to `web/DEPLOY.md` "Seeding data" section pointing at `scripts/backup_web_arena.py` for pulling live plays down. Commit with `docs(web-arena): document backup script`.

---

## Part B — Configurable Arena `max_tokens`

### Task B1: Thread `max_tokens` through the arena engine

**Files:**
- Modify: `interface/arena.py` (`run_arena_session` signature ~L108-120; `_arena_config_dict` signature + `provider_config` block ~L42-90)
- Modify: `interface/api.py` (`ArenaRunRequest` ~L720-728; `arena_run` `_work` call ~L795+)
- Test: `tests/integration/test_arena.py`

**Interfaces:**
- Consumes: `run_arena_session(repository, *, endpoint_url, model_label, framing, forfeit, auth_header=None, auth_value=None, total_turns=15, timeout=60.0, progress=None)` (current signature).
- Produces:
  - `run_arena_session(..., max_tokens: int = 2048, ...)` — new keyword param, forwarded to `_arena_config_dict`.
  - `_arena_config_dict(framing, forfeit, model_label, total_turns, max_tokens)` — new positional param, written into `provider_config["max_tokens"]`.
  - `ArenaRunRequest.max_tokens: int` (default 2048, bounds 256–32768).

- [ ] **Step 1: Write the failing test**

Add to `tests/integration/test_arena.py` (the fake `_fake_post` already receives the `json=` body; capture `max_tokens` from it):

```python
def test_arena_forwards_max_tokens_to_endpoint(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")
    seen: dict = {}

    def _fake_post(url, json=None, headers=None, timeout=None):  # noqa: A002
        seen.setdefault("max_tokens", json.get("max_tokens"))
        phase = _fake_post.n % 3
        _fake_post.n += 1
        content = ("RULE: if red then go_left otherwise stay\nACTION: go_left"
                   if phase == 0 else "P_CORRECT: 60" if phase == 1 else "CHOICE: CONTINUE")
        return _FakeResponse({"choices": [{"message": {"content": content}}],
                              "usage": {"prompt_tokens": 20, "completion_tokens": 5}})
    _fake_post.n = 0
    monkeypatch.setattr("interface.remote_provider.httpx.post", _fake_post)

    repo = SQLiteRepository(":memory:")
    arena_mod.run_arena_session(
        repo, endpoint_url="https://p.example/v1/chat/completions",
        model_label="Contender-7B", framing="flagship_corruption",
        forfeit="allowed", total_turns=1, max_tokens=8192,
    )
    assert seen["max_tokens"] == 8192
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/integration/test_arena.py::test_arena_forwards_max_tokens_to_endpoint -v`
Expected: FAIL — `TypeError: run_arena_session() got an unexpected keyword argument 'max_tokens'`.

- [ ] **Step 3: Write minimal implementation**

In `interface/arena.py`, `_arena_config_dict` — add the parameter and use it:

```python
def _arena_config_dict(
    framing: str, forfeit: str, model_label: str, total_turns: int, max_tokens: int
) -> dict:
```
```python
                "provider_config": {
                    "provider": "openai",  # ignored; _create_provider is overridden
                    "model": model_label,
                    "temperature": 0.7,
                    "max_tokens": max_tokens,
                },
```

In `interface/arena.py`, `run_arena_session` — add the param (after `total_turns`) and forward it:

```python
def run_arena_session(
    repository: Repository,
    *,
    endpoint_url: str,
    model_label: str,
    framing: str,
    forfeit: str,
    auth_header: str | None = None,
    auth_value: str | None = None,
    total_turns: int = 15,
    max_tokens: int = 2048,
    timeout: float = 60.0,
    progress: ArenaProgress | None = None,
) -> ArenaProgress:
```
```python
    cfg_path.write_text(
        yaml.safe_dump(_arena_config_dict(framing, forfeit, model_label, total_turns, max_tokens)),
        encoding="utf-8",
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/integration/test_arena.py -v`
Expected: PASS (existing tests + new `test_arena_forwards_max_tokens_to_endpoint`).

- [ ] **Step 5: Commit**

```bash
git add interface/arena.py tests/integration/test_arena.py
git commit -m "feat(web-arena): thread caller-supplied max_tokens through run_arena_session"
```

### Task B2: Expose `max_tokens` on the arena API

**Files:**
- Modify: `interface/api.py` (`ArenaRunRequest`, `arena_run`)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: `run_arena_session(..., max_tokens=...)` from Task B1.
- Produces: `POST /api/arena/run` accepting an optional `max_tokens` (default 2048, 256–32768).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_api_web_arena.py` (follow the file's existing `TestClient` fixture pattern):

```python
def test_arena_request_max_tokens_default_and_bounds():
    from interface.api import ArenaRunRequest
    import pytest as _pytest
    from pydantic import ValidationError

    # default
    assert ArenaRunRequest(endpoint_url="https://x/v1").max_tokens == 2048
    # accepts an in-range override
    assert ArenaRunRequest(endpoint_url="https://x/v1", max_tokens=8192).max_tokens == 8192
    # rejects out-of-range
    with _pytest.raises(ValidationError):
        ArenaRunRequest(endpoint_url="https://x/v1", max_tokens=999999)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/unit/test_api_web_arena.py::test_arena_request_max_tokens_default_and_bounds -v`
Expected: FAIL — `AttributeError`/`ValidationError` (field does not exist yet, so `max_tokens=999999` is ignored and no error raised).

- [ ] **Step 3: Write minimal implementation**

In `interface/api.py`, add the field to `ArenaRunRequest` (below `total_turns`):

```python
    max_tokens: int = Field(2048, ge=256, le=32768, description="Per-call generation budget. Reasoning models need >=4096 so their answer lands after the thinking block.")
```

In `interface/api.py`, `arena_run` `_work()` — pass it through:

```python
            run_arena_session(
                _repository,
                endpoint_url=req.endpoint_url,
                model_label=model_label,
                framing=req.framing,
                forfeit=req.forfeit,
                total_turns=req.total_turns,
                max_tokens=req.max_tokens,
                auth_header=req.auth_header,
                auth_value=req.auth_value,
            )
```

(Keep the other existing kwargs in that call exactly as they already are; only add the `max_tokens=req.max_tokens` line.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/unit/test_api_web_arena.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): accept optional max_tokens on POST /api/arena/run"
```

### Task B3: Frontend `max_tokens` input

**Files:**
- Modify: `web/index.html` (arena form — near the `total_turns` input)
- Modify: `web/app.js` (arena form data + POST body ~L900-911)

**Interfaces:**
- Consumes: `POST /api/arena/run` `max_tokens` field from Task B2.
- Produces: user-visible number input bound to `maxTokens`, sent in the request body.

- [ ] **Step 1: Add the data field + request body entry in `web/app.js`**

In the arena component's data object, add alongside `totalTurns`:
```javascript
      maxTokens: 4096,
```
In the `/api/arena/run` POST body (currently ending with `total_turns: Number(this.totalTurns) || 15,`), add:
```javascript
                max_tokens: Number(this.maxTokens) || 4096,
```

- [ ] **Step 2: Add the input in `web/index.html`**

Next to the existing "total turns" control in the arena form, add (match the surrounding markup's classes):
```html
<label>Max tokens / call
  <input type="number" min="256" max="32768" step="256" x-model.number="maxTokens">
</label>
```
(If the arena form uses a different binding syntax than `x-model`, mirror whatever `totalTurns`'s input uses — inspect the `totalTurns` control first and copy its pattern exactly.)

- [ ] **Step 3: Manual verification (local)**

Run backend + static server locally, open the arena form, confirm the field renders and that submitting sends `max_tokens` (check the Network tab request payload). No automated test — this is static markup + a request field already covered by Task B2's API test.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(web-arena): max_tokens input on the BYOE arena form"
```

### Task B4: Deploy note

- [ ] **Step 1:** Push `main`; Render auto-redeploys the backend (Tasks B1–B2), and the Pages workflow redeploys `web/` (Task B3). If the Pages deploy times out in `deployment_queued`, re-run it from the Actions tab (known intermittent GitHub Pages behavior).

---

## Self-Review

**Spec coverage:**
- "backup script mirroring Supabase → local SQLite" → Task A1 (core+test) + A2 (live smoke). ✓
- "make max_tokens user-configurable, not hardcoded" → B1 (engine threading), B2 (API field), B3 (frontend input). ✓

**Placeholder scan:** All code steps contain complete code. The only deferred detail is B3's exact HTML binding syntax, with an explicit instruction to mirror the existing `totalTurns` control — acceptable because the surrounding framework (Alpine `x-model` vs other) must be read from the file at implementation time; the data/body changes in `app.js` are exact.

**Type consistency:**
- `mirror_repository(source, dest) -> tuple[int, int, int]` used identically in tests and `main`. ✓
- `run_arena_session(..., max_tokens: int = 2048, ...)` and `_arena_config_dict(..., max_tokens)` signatures match across B1/B2 call sites. ✓
- `ArenaRunRequest.max_tokens` default (2048) matches `run_arena_session` default; frontend default (4096) is a deliberately higher UX default and is clamped by the API's 256–32768 bounds. Note the intentional mismatch: API default 2048 (back-compat for existing callers), frontend suggests 4096 (reasoning-model friendly). ✓

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-web-arena-backup-and-configurable-maxtokens.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks, fast iteration.
2. **Inline Execution** — execute tasks in this session with checkpoints for review.

Parts A and B are independent — either can be done first, or one alone.
