# Human-Play 난이도 + 게임별 DB 난이도 태그 구현 계획

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 워크트리를 최신 main 위로 rebase(main 불변)한 뒤, `sessions` 테이블에 게임별 난이도 태그를 추가하고 human-play UI에 캠페인 단위 난이도 선택기를 배선한다.

**Architecture:** 3-phase. Phase 0은 순수 git 통합(rebase). Phase 1은 저장 계층(SQLite+Postgres 병행)에 `difficulty` 컬럼을 멱등 마이그레이션으로 추가하고 두 write-site(human=`api.py`, LLM=`seeding.py`)에서 `SeasonResult.difficulty`로 채운다. Phase 2는 프론트엔드 `playScreen`에 난이도 상태·전송·체크포인트를 배선하고 `/api/new_game`의 검증 갭(500→400)을 고친다.

**Tech Stack:** Python 3.12, FastAPI + Pydantic, sqlite3 / psycopg, Alpine.js + vanilla JS, pytest, git rebase.

**Spec:** `docs/superpowers/specs/2026-07-05-human-play-difficulty-and-db-tag-design.md`

## Global Constraints

- 작업 디렉토리는 워크트리 `.claude/worktrees/signal-game-difficulty-arena` (브랜치 `worktree-signal-game-difficulty-arena`). **`main` 브랜치 ref는 절대 이동/수정하지 않는다.**
- 난이도 값 어휘: 엔진은 `easy`/`hard`/`expert`, UI 라벨은 Easy/Normal/Hard. MEDIUM은 노출하지 않는다(아레나와 동일).
- 모든 신규 필드 기본값은 `"easy"` (하위호환).
- DB 마이그레이션은 **멱등**(있으면 skip). SQLite는 `PRAGMA table_info` 가드 + `ALTER TABLE ADD COLUMN`, Postgres는 `ADD COLUMN IF NOT EXISTS`. 기존 행은 `NOT NULL DEFAULT 'easy'`로 백필.
- SQLite/Postgres **병행 반영**(스키마·INSERT·SELECT·row-map 모두 양쪽). 누락 시 리더보드 NULL 표기 회귀.
- 테스트 전 iCloud `.pth` 숨김 이슈 발생 시 `chflags nohidden` 선처리 후 pytest(프로젝트 메모리 참조).
- Phase 1·2 코드는 **반드시 Phase 0(rebase) 완료 후** 재배치된 tip 위에 쌓는다.

---

### Task 0: 워크트리를 최신 main 위로 Rebase (main 불변)

**Files:**
- Git 작업만. 코드 편집은 충돌 해결 시에만.

**Interfaces:**
- Produces: 워크트리 브랜치 tip = 최신 main(`769a075`) + difficulty 커밋들(재배치) + 스펙/플랜 docs 커밋. 이후 모든 Task가 이 tip 위에서 동작.

- [ ] **Step 1: 워크트리가 클린 상태인지 확인**

Run:
```bash
cd ".claude/worktrees/signal-game-difficulty-arena"
git status --porcelain
git log --oneline -1        # 현재 tip 확인 (docs 스펙/플랜 커밋이 최상단)
```
Expected: 커밋 안 된 변경 없음(있으면 stash 또는 commit). 미추적 `.playwright-mcp/`, `outputs/web_arena/`는 무시 가능.

- [ ] **Step 2: main 위로 rebase 시작**

Run:
```bash
git rebase main
```
Expected: `interface/arena.py`, `tests/integration/test_arena.py`는 자동 적용. `interface/api.py`, `web/app.js`, `web/index.html`, `tests/unit/test_api_web_arena.py`에서 충돌 발생 가능.

- [ ] **Step 3: `interface/api.py` 충돌 해결 — arena import 블록**

충돌 지점은 `from interface.arena import (...)` 블록. **union**으로 해결(main의 세 심볼 + `VALID_DIFFICULTIES`):

```python
from interface.arena import (
    VALID_DIFFICULTIES,
    VALID_FORFEITS,
    VALID_FRAMINGS,
    run_arena_session,
)
```

`ArenaRunRequest.difficulty` 필드, `arena_run`의 400 검증 등 나머지 difficulty 추가분은 main 코드를 베이스로 두고 그대로 재적용(삭제 금지). main이 추가한 주변 코드도 유지.

- [ ] **Step 4: `web/app.js` / `web/index.html` / `tests/unit/test_api_web_arena.py` 충돌 해결**

모든 difficulty 변경은 **추가(additive)**다. 각 충돌 hunk에서 **main 쪽 코드를 유지하고 difficulty 추가분(DIFFICULTY_OPTIONS, `squidArenaHelpers.difficultyOptions`, `arenaScreen().difficulty`, `launch()`의 `difficulty`, index.html 아레나 셀렉터 마크업, test 2개)만 다시 얹는다**. main 코드를 지우지 않는다.

각 파일 해결 후:
```bash
git add interface/api.py web/app.js web/index.html tests/unit/test_api_web_arena.py
git rebase --continue
```
반복하여 rebase 완료.

- [ ] **Step 5: 의존성 동기화 + 검증 게이트**

Run:
```bash
find .venv -name "*.pth" -exec chflags nohidden {} \; 2>/dev/null; chflags -R nohidden .venv/lib 2>/dev/null
uv sync --extra dev
uv run pytest tests/integration/test_arena.py tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py -q
node --check web/app.js
```
Expected: difficulty 6개 테스트 포함 그린(신규 실패 0; 기존 pre-existing 실패는 허용 — "no NEW failures" 기준). `node --check` exit 0.

- [ ] **Step 6: rebase 결과 확인 (커밋 불필요 — rebase가 tip을 이동시킴)**

Run:
```bash
git log --oneline -8
git merge-base --is-ancestor main HEAD && echo "main is now an ancestor ✓"
```
Expected: 최신 main 커밋들이 difficulty 커밋 아래에 있고, `main is now an ancestor ✓` 출력. main 브랜치 tip은 불변.

---

### Task 1: `SessionRecord.difficulty` + SQLite 컬럼/마이그레이션/저장 (양쪽 backend 중 SQLite)

**Files:**
- Modify: `interface/persistence/models.py` (`SessionRecord` dataclass)
- Modify: `interface/persistence/sqlite_repository.py` (`_SCHEMA`, `init_schema`, `create_session`, `_row_to_session`)
- Test: `tests/unit/test_persistence.py`

**Interfaces:**
- Produces: `SessionRecord.difficulty: str = "easy"` — 새 필드, 기본값 있음(기존 생성자 하위호환).
- Produces: `sessions` 테이블에 `difficulty TEXT NOT NULL DEFAULT 'easy'` 컬럼; `create_session`이 값 저장, `get_session`/`list_sessions`가 값 복원.

- [ ] **Step 1: 실패 테스트 작성 — round-trip + 마이그레이션**

`tests/unit/test_persistence.py`에 추가(기존 `repo` fixture와 `_session` 헬퍼 재사용):

```python
def test_session_round_trips_difficulty(repo: Repository) -> None:
    sid = repo.create_session(_session(difficulty="hard"))
    fetched = repo.get_session(sid)
    assert fetched is not None
    assert fetched.difficulty == "hard"


def test_session_difficulty_defaults_to_easy(repo: Repository) -> None:
    sid = repo.create_session(_session())  # helper omits difficulty
    assert repo.get_session(sid).difficulty == "easy"


def test_sessions_difficulty_migration_adds_column_to_old_db(tmp_path) -> None:
    import sqlite3
    from interface.persistence.sqlite_repository import SQLiteRepository

    db = str(tmp_path / "old.db")
    # Simulate a pre-migration DB: sessions without the difficulty column.
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE sessions (id TEXT PRIMARY KEY, nickname TEXT NOT NULL, "
        "task TEXT NOT NULL, framing TEXT NOT NULL, forfeit TEXT NOT NULL, "
        "seed INTEGER NOT NULL, final_score REAL NOT NULL, forfeited INTEGER NOT NULL, "
        "source TEXT NOT NULL, created_at TEXT NOT NULL, campaign_id TEXT)"
    )
    conn.execute(
        "INSERT INTO sessions (id, nickname, task, framing, forfeit, seed, "
        "final_score, forfeited, source, created_at, campaign_id) VALUES "
        "('old1','bob','signal_game','flagship_corruption','allowed',1,5.0,0,'human','2026-01-01T00:00:00+00:00',NULL)"
    )
    conn.commit()
    conn.close()

    repo = SQLiteRepository(db)  # __init__ -> init_schema() -> migration
    try:
        cols = {r["name"] for r in repo._conn.execute("PRAGMA table_info(sessions)")}
        assert "difficulty" in cols
        # Existing row backfilled to 'easy'.
        assert repo.get_session("old1").difficulty == "easy"
    finally:
        repo.close()
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/unit/test_persistence.py -k difficulty -v`
Expected: FAIL — `SessionRecord`에 `difficulty` 인자 없음 / `difficulty` 컬럼 없음.

- [ ] **Step 3: `SessionRecord`에 `difficulty` 필드 추가**

`interface/persistence/models.py` — `SessionRecord`의 `campaign_id` 필드 아래에 추가:

```python
    campaign_id: str | None = None
    # Signal Game difficulty this session was played at (easy | hard | expert).
    # Defaults to "easy" for legacy rows written before this column existed.
    difficulty: str = "easy"
```

- [ ] **Step 4: SQLite `_SCHEMA`에 컬럼 추가**

`interface/persistence/sqlite_repository.py` — `CREATE TABLE ... sessions`의 `campaign_id TEXT` 줄 뒤에 추가:

```python
    campaign_id TEXT,
    difficulty TEXT NOT NULL DEFAULT 'easy'
```

- [ ] **Step 5: SQLite `init_schema` 마이그레이션 가드 추가**

`init_schema`의 기존 `if "campaign_id" not in session_cols:` 블록 바로 뒤에 추가:

```python
            if "difficulty" not in session_cols:
                self._conn.execute(
                    "ALTER TABLE sessions ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'easy'"
                )
```

- [ ] **Step 6: SQLite `create_session` INSERT에 컬럼/값 추가**

INSERT 컬럼 목록·placeholder·params에 difficulty 추가:

```python
                INSERT INTO sessions
                    (id, nickname, task, framing, forfeit, seed,
                     final_score, forfeited, source, created_at, campaign_id, difficulty)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
```

params 튜플에서 `session.campaign_id,` 뒤에 추가:

```python
                    session.campaign_id,
                    session.difficulty,
```

- [ ] **Step 7: SQLite `_row_to_session`에 매핑 추가**

`_row_to_session`의 `campaign_id=...` 줄 뒤에 추가(migration 컬럼과 동일한 `in row.keys()` 가드):

```python
        campaign_id=row["campaign_id"] if "campaign_id" in row.keys() else None,
        difficulty=row["difficulty"] if "difficulty" in row.keys() else "easy",
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_persistence.py -k difficulty -v`
Expected: PASS — 3개 테스트 그린.

- [ ] **Step 9: 커밋**

```bash
git add interface/persistence/models.py interface/persistence/sqlite_repository.py tests/unit/test_persistence.py
git commit -m "feat(persistence): sessions.difficulty column + SQLite round-trip/migration

Add SessionRecord.difficulty (default easy). SQLite schema, idempotent
ADD COLUMN migration (backfill 'easy'), INSERT and row-map wired.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Postgres 병행 반영 (스키마/마이그레이션/INSERT/SELECT/row-map)

**Files:**
- Modify: `interface/persistence/postgres_repository.py` (`_SCHEMA`, `init_schema`, `create_session`, `get_session`, `list_sessions`, `_row_to_session`)
- Test: `tests/unit/test_persistence.py`

**Interfaces:**
- Consumes: `SessionRecord.difficulty` (Task 1).
- Produces: Postgres `sessions.difficulty` 컬럼 + INSERT/SELECT/row-map 병행. SELECT 컬럼 순서와 `_row_to_session` 언패킹 순서는 **difficulty를 끝에 append**하여 일치.

- [ ] **Step 1: 실패 테스트 작성 — SQL 문자열 파리티(오프라인 검증)**

`tests/unit/test_persistence.py`에 추가:

```python
def test_postgres_schema_and_sql_include_difficulty() -> None:
    import interface.persistence.postgres_repository as pg

    # Schema declares the column with the easy default.
    assert "difficulty TEXT NOT NULL DEFAULT 'easy'" in pg._SCHEMA
    # Idempotent migration present in init_schema source.
    src = inspect.getsource(pg.PostgresRepository.init_schema)
    assert "ADD COLUMN IF NOT EXISTS difficulty" in src
    # INSERT and both SELECT column lists carry difficulty.
    ins = inspect.getsource(pg.PostgresRepository.create_session)
    assert "difficulty" in ins
    get_src = inspect.getsource(pg.PostgresRepository.get_session)
    list_src = inspect.getsource(pg.PostgresRepository.list_sessions)
    assert "difficulty" in get_src and "difficulty" in list_src
    # Row-mapper unpacks difficulty.
    assert "difficulty" in inspect.getsource(pg._row_to_session)
```

파일 상단 import에 `import inspect` 없으면 추가.

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/unit/test_persistence.py::test_postgres_schema_and_sql_include_difficulty -v`
Expected: FAIL — postgres 소스에 difficulty 부재.

- [ ] **Step 3: Postgres `_SCHEMA` 컬럼 추가**

`interface/persistence/postgres_repository.py` — `CREATE TABLE ... sessions`의 `campaign_id TEXT` 줄 뒤:

```python
    campaign_id TEXT,
    difficulty TEXT NOT NULL DEFAULT 'easy'
```

- [ ] **Step 4: Postgres `init_schema` 마이그레이션 추가**

기존 `ALTER TABLE sessions ADD COLUMN IF NOT EXISTS campaign_id TEXT` cur.execute 뒤에 추가:

```python
            cur.execute(
                "ALTER TABLE sessions ADD COLUMN IF NOT EXISTS difficulty "
                "TEXT NOT NULL DEFAULT 'easy'"
            )
```

- [ ] **Step 5: Postgres `create_session` INSERT 추가**

컬럼 목록·placeholder·params:

```python
                INSERT INTO sessions
                    (id, nickname, task, framing, forfeit, seed,
                     final_score, forfeited, source, created_at, campaign_id, difficulty)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s,
                        COALESCE(%s::timestamptz, now()), %s, %s)
```

params 튜플의 `session.campaign_id,` 뒤에:

```python
                    session.campaign_id,
                    session.difficulty,
```

- [ ] **Step 6: Postgres 두 SELECT에 difficulty 추가 (끝에 append)**

`get_session`과 `list_sessions`의 SELECT 컬럼 문자열을 각각 수정 — `campaign_id ` 뒤에 `, difficulty` (row-map 언패킹 순서와 일치하도록 **맨 끝**):

`get_session`:
```python
                "SELECT id, nickname, task, framing, forfeit, seed, "
                "final_score, forfeited, source, created_at, campaign_id, difficulty "
                "FROM sessions WHERE id = %s",
```

`list_sessions`:
```python
            "SELECT id, nickname, task, framing, forfeit, seed, "
            "final_score, forfeited, source, created_at, campaign_id, difficulty "
            f"FROM sessions {where} ORDER BY {order}"
```

- [ ] **Step 7: Postgres `_row_to_session` 언패킹/생성 추가**

튜플 언패킹 끝에 `difficulty` 추가하고 SessionRecord에 전달:

```python
def _row_to_session(row: tuple) -> SessionRecord:
    (
        id_, nickname, task, framing, forfeit, seed,
        final_score, forfeited, source, created_at, campaign_id, difficulty,
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
        difficulty=difficulty,
    )
```

- [ ] **Step 8: 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_persistence.py -k "difficulty or postgres" -v`
Expected: PASS — Task 1 SQLite 테스트 + Postgres 파리티 테스트 그린.

- [ ] **Step 9: 커밋**

```bash
git add interface/persistence/postgres_repository.py tests/unit/test_persistence.py
git commit -m "feat(persistence): Postgres parity for sessions.difficulty

Column, idempotent ADD COLUMN IF NOT EXISTS migration, INSERT, both
SELECT column lists, and positional row-map unpack all carry difficulty.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: 두 write-site에서 `SeasonResult.difficulty`로 채우기 (LLM seeding + human api)

**Files:**
- Modify: `interface/seeding.py` (`build_session_record`, ~line 128)
- Modify: `interface/api.py` (human 세션 `SessionRecord(...)`, ~line 712 부근 — Phase 0 후 위치 이동 가능; 스니펫으로 매칭)
- Test: `tests/unit/test_seed_web_arena.py`, `tests/unit/test_human_game.py`

**Interfaces:**
- Consumes: `SessionRecord.difficulty` (Task 1); `SeasonResult.difficulty` (엔진); season dict의 top-level `"difficulty"` 키.
- Produces: LLM/human 세션 레코드가 자신의 난이도로 채워짐.

- [ ] **Step 1: LLM 실패 테스트 작성**

`tests/unit/test_seed_web_arena.py`에 추가(기존 `_season`/`_turn` 헬퍼 재사용 — `_season`은 이미 `"difficulty": "medium"` 포함):

```python
def test_build_session_record_carries_difficulty() -> None:
    season = _season("seasD", final_score=10.0, forfeited=False, turns=[_turn(1)])
    session = build_session_record(season, "Test-Model", fallback_created_at="2026-01-01T00:00:00+00:00")
    assert session.difficulty == "medium"


def test_build_session_record_difficulty_defaults_when_absent() -> None:
    season = _season("seasE", final_score=10.0, forfeited=False, turns=[_turn(1)])
    del season["difficulty"]
    session = build_session_record(season, "Test-Model", fallback_created_at="2026-01-01T00:00:00+00:00")
    assert session.difficulty == "easy"
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/unit/test_seed_web_arena.py -k difficulty -v`
Expected: FAIL — `build_session_record`가 difficulty를 세팅하지 않음(기본 "easy"만 나와 첫 테스트 실패).

- [ ] **Step 3: `build_session_record`에 difficulty 추가**

`interface/seeding.py` — `build_session_record`의 `SessionRecord(...)` 반환에서 `source="llm",` 뒤에 추가:

```python
        source="llm",
        created_at=created_at,
        difficulty=season.get("difficulty", "easy"),
```

(주의: 기존에 `created_at=created_at,`가 `source="llm",` 뒤에 있으므로 그 뒤에 difficulty 추가.)

- [ ] **Step 4: LLM 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_seed_web_arena.py -k difficulty -v`
Expected: PASS.

- [ ] **Step 5: human write-site 수정 — `interface/api.py`**

human 세션 `SessionRecord(...)` 생성부(다음 스니펫으로 매칭; Phase 0 후 라인 이동 가능)에서 `source="human",` 뒤에 difficulty 추가:

find:
```python
                    source="human",
                    campaign_id=_campaigns.get(session_id),
                )
```
replace:
```python
                    source="human",
                    campaign_id=_campaigns.get(session_id),
                    difficulty=result.difficulty.value,
                )
```

(`result`는 `HumanGameSession.get_result()`가 반환한 `SeasonResult`로, `.difficulty`는 `Difficulty` enum → `.value`로 문자열화.)

- [ ] **Step 6: human 값 흐름 검증 테스트 — `tests/unit/test_human_game.py`**

`HumanGameSession.get_result().difficulty`가 선택 난이도를 반영하는지 확인(이 값이 Step 5에서 SessionRecord로 전달됨). 파일 스타일에 맞춰 추가:

```python
def test_get_result_reflects_selected_difficulty() -> None:
    from interface.human_game import HumanGameSession

    game = HumanGameSession(
        task_name="signal_game", difficulty="hard",
        framing="flagship_corruption", forfeit_condition="allowed",
        seed=7, total_turns=3,
    )
    assert game.get_result().difficulty.value == "hard"
```

- [ ] **Step 7: human 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_human_game.py -k difficulty -v`
Expected: PASS.

- [ ] **Step 8: 커밋**

```bash
git add interface/seeding.py interface/api.py tests/unit/test_seed_web_arena.py tests/unit/test_human_game.py
git commit -m "feat(persistence): tag each session with its difficulty

LLM (seeding.build_session_record) reads season['difficulty']; human
(api.new_game finish) reads SeasonResult.difficulty.value. Both flow
into sessions.difficulty.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: `/api/new_game` 난이도 검증 (500 → 400)

**Files:**
- Modify: `interface/api.py` (`new_game` 핸들러; `VALID_DIFFICULTIES`는 Phase 0 후 import되어 있음)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: `VALID_DIFFICULTIES` (Phase 0 후 `interface.arena`에서 import됨).
- Produces: 잘못된 difficulty에 `HTTPException(400)` (현재 `Difficulty("banana")` → 500 크래시 교정).

- [ ] **Step 1: 실패 테스트 작성**

`tests/unit/test_api_web_arena.py`에 추가(기존 `client` fixture 재사용):

```python
def test_new_game_rejects_unknown_difficulty(client: TestClient) -> None:
    resp = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "framing": "flagship_corruption",
            "forfeit_condition": "allowed",
            "nickname": "diff_bad",
            "password": "pw",
            "difficulty": "banana",
        },
    )
    assert resp.status_code == 400


def test_new_game_accepts_valid_difficulty(client: TestClient) -> None:
    resp = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "framing": "flagship_corruption",
            "forfeit_condition": "allowed",
            "nickname": "diff_ok",
            "password": "pw",
            "difficulty": "hard",
        },
    )
    assert resp.status_code == 200
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k "new_game and difficulty" -v`
Expected: FAIL — `difficulty="banana"`가 500(400 아님)을 반환.

- [ ] **Step 3: `new_game` 핸들러에 검증 추가**

`interface/api.py` `new_game` 함수 — 기존 닉네임/비밀번호 검증(400) 블록들 뒤, `HumanGameSession(...)` 생성 앞에 추가:

```python
    if req.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(400, f"Unknown difficulty '{req.difficulty}'.")
```

(아레나 `arena_run`의 `if req.forfeit not in VALID_FORFEITS: raise HTTPException(400, ...)`와 동일 스타일.)

- [ ] **Step 4: 테스트 통과 확인**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k "new_game and difficulty" -v`
Expected: PASS.

- [ ] **Step 5: 커밋**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "fix(api): /api/new_game returns 400 (not 500) on unknown difficulty

Validate req.difficulty against VALID_DIFFICULTIES before constructing
HumanGameSession, matching /api/arena/run's style.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: `web/app.js` — playScreen 난이도 상태 + startGame 전송 + 체크포인트

**Files:**
- Modify: `web/app.js` (`playScreen` data, `startGame`, `_saveCheckpoint`, `_loadCheckpoint`)

**Interfaces:**
- Consumes: `squidArenaHelpers.difficultyOptions` (Phase 0 후 존재, 아레나가 export).
- Produces: `playScreen().difficulty` 상태(기본 `"easy"`), `/api/new_game` 바디에 `difficulty` 포함, 체크포인트에 difficulty 저장/복원. Task 6(index.html)이 `difficulty` 바인딩을 소비.

- [ ] **Step 1: `playScreen` data에 difficulty 상태 추가**

`Alpine.data("playScreen", () => ({` 블록 내부, `task: window.WEB_ARENA_DEFAULT_TASK,` 줄 뒤에 추가:

```javascript
      // Campaign-level Signal Game difficulty (engine easy|hard|expert;
      // labelled Easy/Normal/Hard). Chosen once on the setup screen and held
      // constant across all 6 games of the campaign.
      difficulty: "easy",
```

- [ ] **Step 2: `startGame()` POST 바디에 difficulty 추가**

`startGame()`의 `/api/new_game` `body: JSON.stringify({ ... })`에서 `campaign_id: this.campaignId,` 뒤에 추가:

```javascript
                campaign_id: this.campaignId,
                difficulty: this.difficulty,
```

- [ ] **Step 3: 체크포인트 저장/복원에 difficulty 반영**

`_saveCheckpoint()`의 `data` 객체에서 `v: 1,`을 `v: 2,`로 올리고 `campaignId: this.campaignId,` 뒤에 `difficulty: this.difficulty,` 추가:

```javascript
          const data = {
            v: 2,
            nickname: this.nickname,
            password: this.password,
            campaignId: this.campaignId,
            difficulty: this.difficulty,
```

`_loadCheckpoint()`의 버전 가드를 v1/v2 모두 허용하도록 완화(구버전 체크포인트 하위호환):

find:
```javascript
          if (!d || d.v !== 1 || d.campaignIndex >= 6) return null;
          return d;
```
replace:
```javascript
          if (!d || (d.v !== 1 && d.v !== 2) || d.campaignIndex >= 6) return null;
          return d;
```

- [ ] **Step 4: 체크포인트 복원 시 difficulty 적용**

체크포인트에서 캠페인을 재개하는 지점(`resume`/`resumeCampaign` 계열 메서드에서 `this.nickname = ck.nickname` 등 필드를 복원하는 곳)에 difficulty 복원을 추가. 복원 필드 세팅 근처에 삽입(구버전 체크포인트는 difficulty 부재 → `'easy'` 폴백):

```javascript
        this.difficulty = ck.difficulty || "easy";
```

(정확한 메서드는 `_loadCheckpoint()` 반환값 `ck`를 소비하는 곳 — `this.nickname = ck.nickname`이 있는 블록. 없으면 resume 진입점에서 nickname 복원 직후 추가.)

- [ ] **Step 5: JS 구문 검증**

Run: `node --check web/app.js`
Expected: exit 0, 출력 없음.

- [ ] **Step 6: 커밋**

```bash
git add web/app.js
git commit -m "feat(play-ui): campaign-level difficulty state, launch payload, checkpoint

playScreen.difficulty (default easy) sent in /api/new_game body and
persisted in the resume checkpoint (schema v2, easy fallback for v1).

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 6: `web/index.html` — Play 셋업 카드에 난이도 셀렉터

**Files:**
- Modify: `web/index.html` (Play `setup-card`, task 선택 `game-cards`와 `scenario-box` 사이)

**Interfaces:**
- Consumes: `squidArenaHelpers.difficultyOptions`, `playScreen().difficulty` (Task 5).
- Produces: 셋업 화면(`x-show="!started"` 카드 내부)의 난이도 셀렉터.

- [ ] **Step 1: 셀렉터 마크업 삽입**

`web/index.html`의 Play `setup-card` 내부, task 선택 `game-cards` 블록의 닫는 `</div>` 뒤이자 `<div class="scenario-box"` 앞에 삽입(아레나와 동일한 `cond-cards`/`cond-card`/`cond-label`/`cond-blurb` 재사용 — CSS 변경 불필요):

```html
        <label style="margin-top:14px; display:block;">Difficulty</label>
        <div class="cond-cards">
          <template x-for="opt in squidArenaHelpers.difficultyOptions" :key="opt.value">
            <div class="cond-card" :class="{ on: difficulty === opt.value }" @click="difficulty = opt.value">
              <span class="cond-label" x-text="opt.label"></span>
              <span class="cond-blurb" x-text="opt.blurb"></span>
            </div>
          </template>
        </div>
```

셀렉터가 `setup-card`(`x-show="!started"`) 안에 있으므로 캠페인 시작 후 자동으로 숨겨진다(난이도 캠페인 단위 고정 보장).

- [ ] **Step 2: 수동 렌더 검증 (오프라인 정적 확인)**

Run:
```bash
grep -n "squidArenaHelpers.difficultyOptions" web/index.html
```
Expected: Play 셋업 카드 내 새 셀렉터 1개 매칭(아레나 것과 합쳐 총 2개 매칭).

- [ ] **Step 3: 커밋**

```bash
git add web/index.html
git commit -m "feat(play-ui): difficulty selector on the human Play setup card

Reuses squidArenaHelpers.difficultyOptions + cond-card classes; lives
inside the !started setup card so difficulty is locked once a campaign
begins.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 7: 전체 회귀 + 브라우저 스모크 (end-to-end 검증)

**Files:**
- Verify: 전체 테스트 스위트 + 임시 백엔드/프론트 수동 확인

- [ ] **Step 1: 관련 스위트 회귀**

Run:
```bash
uv run pytest tests/unit/test_persistence.py tests/unit/test_seed_web_arena.py \
  tests/unit/test_human_game.py tests/unit/test_api_web_arena.py \
  tests/integration/test_arena.py tests/integration/test_web_arena_api.py -q
node --check web/app.js
```
Expected: 그린(신규 실패 0). `node --check` exit 0.

- [ ] **Step 2: 임시 DB로 로컬 백엔드/프론트 기동 (프로덕션 DB 미오염)**

Run(스크래치패드 임시 DB 사용):
```bash
export WEB_ARENA_DSN="$SCRATCH/human_difficulty_test.db"; export PYTHONPATH=src
uv run --no-sync uvicorn interface.api:app --port 8502 --host 127.0.0.1 &   # 백엔드
( cd web && python3 -m http.server 8080 --bind 127.0.0.1 & )                # 프론트
```
(`$SCRATCH`는 세션 스크래치패드 경로로 치환.) config.js가 `localhost:8502`를 가리키고 CORS에 `localhost:8080`이 이미 허용됨 — **`http://localhost:8080/`로 접속(127.0.0.1 아님)**.

- [ ] **Step 3: Playwright 스모크 — 셀렉터 렌더 + 페이로드 + 캠페인 고정**

`http://localhost:8080/` Play 탭에서 확인:
1. Difficulty 카드 3개(Easy/Normal/Hard) 렌더, `easy` 기본 선택.
2. "Normal" 클릭 → 선택 이동(`on` 클래스).
3. DevTools Network에서 닉네임/비밀번호 입력 후 "Start 6-game run" → `POST /api/new_game` 바디에 `"difficulty":"hard"` 확인.
4. 게임 시작 후 셋업 카드(셀렉터 포함)가 사라지는지 확인(캠페인 중 난이도 변경 차단).

Expected: 셀렉터가 아레나와 동일하게 렌더되고, 페이로드에 엔진 값이 실림.

- [ ] **Step 4: 서버 종료**

Run:
```bash
for p in 8502 8080; do pid=$(lsof -ti tcp:$p); [ -n "$pid" ] && kill $pid; done
```

- [ ] **Step 5: (해당 시) 개발 브랜치 마무리**

구현·검증 완료 후 `superpowers:finishing-a-development-branch` 스킬로 main 병합/PR 옵션을 사용자에게 제시.

---

## Self-Review 결과 (작성자 체크)

- **스펙 커버리지:** Phase 0(rebase)=Task 0; DB 태그(스키마/마이그레이션/양쪽 backend/두 write-site)=Task 1·2·3; human UI 셀렉터=Task 5·6; 캠페인 고정=Task 5(상태)+Task 6(setup-card 위치); 체크포인트 정합성=Task 5 Step 3·4; API 400 검증=Task 4. 모든 스펙 요구 → 대응 Task 존재.
- **플레이스홀더:** 없음. Task 5 Step 4의 "resume 진입점"은 코드 앵커(`this.nickname = ck.nickname`)로 지정.
- **타입 일관성:** `SessionRecord.difficulty: str`(Task 1)를 SQLite(Task 1)·Postgres(Task 2)·write-site(Task 3)·테스트 전반에서 동일 사용. `result.difficulty.value`(enum→str), `season.get("difficulty","easy")`(str) 일관.
- **Postgres 순서 주의:** SELECT 컬럼과 `_row_to_session` 언패킹 모두 difficulty를 **끝에 append**(Task 2 Step 6·7) — 위치 불일치 없음.
