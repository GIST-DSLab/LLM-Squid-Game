# Human-Play 난이도 선택 + 게임별 DB 난이도 태그 — 설계 스펙

> 작성일: 2026-07-05 · 대상 브랜치: `worktree-signal-game-difficulty-arena`
> 선행 스펙: `docs/superpowers/specs/2026-07-04-signal-game-difficulty-arena-design.md` (LLM 아레나 난이도 — 이미 구현 완료)

## 배경

LLM 아레나(`JOIN` 탭)는 이미 난이도 선택(Easy/Normal/Hard = 엔진 `easy`/`hard`/`expert`)을 지원한다. 그러나:

1. **워크트리 발산** — 이 난이도 작업이 담긴 워크트리 브랜치는 분기점 `7dcfa7a` 이후 갈라졌고, 그동안 `main`은 29커밋 앞서 나갔다(web-arena 관련 작업). 워크트리는 더 이상 `main`을 조상으로 두지 않는다.
2. **human-play UI 미배선** — 백엔드(`NewGameRequest.difficulty` → `HumanGameSession` → 시그널 게임 규칙)는 난이도를 완전히 지원하지만, 사람 플레이 UI(`web/app.js`의 `playScreen`)에는 선택기가 없고 `/api/new_game` POST 바디에 `difficulty`를 보내지 않는다. 결과적으로 **사람이 UI로 시작하는 모든 게임은 백엔드 기본값 `easy`로 고정**된다.
3. **DB 난이도 태그 부재** — `sessions` 테이블에 `difficulty` 컬럼이 없어, 게임이 어떤 난이도로 플레이됐는지 저장되지 않는다. `SeasonResult`는 `difficulty` 필드를 갖지만 영속화되지 않는다.
4. **API 검증 갭** — `/api/new_game`은 difficulty 값을 검증하지 않아 잘못된 값이 `Difficulty("banana")`에서 `HTTP 500`으로 크래시한다(아레나 `/api/arena/run`은 깔끔한 400을 반환).

## 목표

1. **root(main) 불변**으로, 워크트리의 difficulty 변경 내역을 유지하면서 최신 main의 업데이트를 가져온다.
2. human-play UI에서 **캠페인 단위**로 난이도를 선택할 수 있게 한다(6게임 캠페인 전체 동일 난이도).
3. 모든 게임 세션(human + LLM)이 DB에 자신의 난이도로 태깅되도록 한다.
4. `/api/new_game`의 difficulty 검증 갭(500 → 400)을 수정한다.

## Non-Goals

- `main` 브랜치 자체의 수정(리베이스는 워크트리 브랜치만 이동, main은 불변).
- MEDIUM 난이도 노출 — 아레나와 동일하게 제외(human-play도 `num_few_shot`이 고정이라 medium이 easy와 사실상 동일 동작). 향후 `num_few_shot`을 난이도 인지형으로 바꾸는 것은 별도 작업.
- 게임마다 다른 난이도 선택(캠페인 중간 난이도 변경) — 난이도는 캠페인 단위로 고정.
- 아레나 난이도 UI/로직 재설계 — 이미 구현 완료, 그대로 유지.

## 결정 사항 (사용자 승인)

| 결정 | 선택 |
|---|---|
| Git 통합 방식 | **Rebase** (`git rebase main`, main 불변, 5커밋 replay) |
| human-play 난이도 단계 | **3단계** (Easy/Normal/Hard = `easy`/`hard`/`expert`, medium 제외 — 아레나와 일관) |
| 기존 DB 행 백필 | **`'easy'`** (`ALTER TABLE ... NOT NULL DEFAULT 'easy'`; 지금까지 UI가 easy 고정이었으므로 실제로 정확) |
| 난이도 적용 범위 | **캠페인 단위** (6게임 공통, 각 게임 행에 동일 난이도 태그) |

---

## Phase 0 — 워크트리를 최신 main 위로 Rebase (main 불변)

**목적:** root의 업데이트를 가져오면서 워크트리의 difficulty 5커밋을 유지한다.

### 절차
- 워크트리 디렉토리(`.claude/worktrees/signal-game-difficulty-arena`)에서 `git rebase main` 실행.
- 분기점 `7dcfa7a` 이후의 5커밋(`da82d51`, `09f1229`, `c758360`, `977ae3d`, `3a99287`)이 `main` tip(`769a075`) 위로 재배치된다. **main 브랜치 ref는 이동하지 않는다.**

### 충돌 예상 및 해결 원칙
분기점 이후 main과 워크트리가 **함께 수정한 파일 = 충돌 위험 4개**:

| 파일 | 충돌 위험 | difficulty 변경 성격 | 해결 원칙 |
|---|:-:|---|---|
| `interface/api.py` | ⚠ | import 추가, `ArenaRunRequest.difficulty` 필드, 400 검증, forward | main 베이스 유지 + 추가분 재적용 |
| `web/app.js` | ⚠ | `DIFFICULTY_OPTIONS`, `squidArenaHelpers` export, `arenaScreen` 상태, `launch()` 페이로드 | main 베이스 유지 + 추가분 재적용 |
| `web/index.html` | ⚠ | 아레나 Conditions 카드 셀렉터 마크업 | main 베이스 유지 + 추가분 재적용 |
| `tests/unit/test_api_web_arena.py` | ⚠ | difficulty 수용/거부 테스트 2개 | main 베이스 유지 + 추가분 재적용 |

**클린(자동 적용) 2개:** `interface/arena.py`, `tests/integration/test_arena.py`.

모든 difficulty 변경은 **추가(additive)** 성격(새 import 한 줄, 새 필드, 새 옵션 배열, 새 마크업 블록)이므로, 충돌은 import 블록·인접 삽입 지점에 국한된다. 해결 시 main의 변경을 삭제하지 않고 difficulty 추가분만 다시 얹는다.

### 검증 게이트 (Phase 0 완료 조건)
- `uv sync --extra dev` 후 `uv run pytest tests/integration/test_arena.py tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py` → **신규 실패 0** (기존 pre-existing 실패는 프로젝트 메모리 기준 허용).
- difficulty 6개 테스트 그린 확인.
- `node --check web/app.js` → exit 0.
- iCloud `.pth` 숨김 이슈 발생 시 `chflags nohidden` 선처리(프로젝트 메모리 참조).

> Phase 1·2의 신규 작업은 **반드시 Phase 0 완료 후** 이 재배치된 브랜치 tip 위에 쌓는다(구 베이스에서 작업 후 리베이스하면 충돌 재발).

---

## Phase 1 — 게임별 DB 난이도 태그

**목적:** 모든 세션(human + LLM)이 자신의 난이도로 DB에 태깅된다.

### 데이터 모델 변경
- `interface/persistence/models.py` — `SessionRecord` 데이터클래스에 `difficulty: str` 필드 추가(기존 `framing`/`forfeit` 옆). 기본값 `"easy"`로 기존 생성자 호출 하위호환.

### 스키마 마이그레이션 (SQLite + Postgres 병행)
- `interface/persistence/sqlite_repository.py` / `postgres_repository.py` 양쪽 `sessions` 테이블:
  - 신규 DB: `CREATE TABLE`에 `difficulty TEXT NOT NULL DEFAULT 'easy'` 포함.
  - 기존 DB: **멱등 추가 마이그레이션** — 컬럼 부재 시에만 `ALTER TABLE sessions ADD COLUMN difficulty TEXT NOT NULL DEFAULT 'easy'`. 기존 `model_stats` 확장 컬럼(예: `n_forfeits_verbal`, 미디에이션 컬럼)에서 이미 쓰는 "있으면 skip, 없으면 ADD COLUMN" 패턴을 그대로 재사용.
  - 기존 행은 DEFAULT로 `'easy'` 백필(실제로 정확).
- INSERT 컬럼 목록·바인딩, SELECT 컬럼 목록에 `difficulty` 반영(양쪽 repo). `get_session`/`list_sessions`가 반환하는 `SessionRecord`에도 값 채움.

### 저장 지점 배선 (두 곳, `SeasonResult.difficulty`로 채움)
- `interface/api.py:~712` — human 세션 `SessionRecord(...)` 생성부에 `difficulty=result.difficulty.value` 추가.
- `interface/seeding.py:~128` — LLM 세션 `SessionRecord(...)` 생성부에 인제스트 중인 season의 `difficulty.value` 추가.

### 테스트
- repo 단위 테스트(sqlite + postgres 파리티):
  - difficulty 저장/조회 라운드트립(`create_session(difficulty="hard")` → `get_session().difficulty == "hard"`).
  - 마이그레이션 멱등성(difficulty 컬럼 없는 구 스키마 DB를 열면 자동 추가되고 기존 행 = `'easy'`; 재실행해도 에러 없음).

---

## Phase 2 — human-play UI 난이도 선택기 + API 검증

**목적:** 사람이 캠페인 시작 시 난이도를 고르고, 그 난이도가 6게임 전체·DB·재개까지 일관되게 흐른다.

### 프론트엔드 상태/전송 (`web/app.js`)
- `playScreen()` 데이터에 `difficulty: "easy"` 상태 추가.
- `startGame()`의 `/api/new_game` POST 바디에 `difficulty: this.difficulty` 추가.
- 아레나가 이미 export하는 `squidArenaHelpers.difficultyOptions`(3단계, medium 제외) **재사용** — human 전용 옵션 배열을 새로 만들지 않는다.

### 프론트엔드 마크업 (`web/index.html`)
- Play 셋업 카드(`x-data="playScreen()"`, `section` ~line 351; nickname/password 입력과 "Start 6-game run" 버튼 ~line 420 사이)에 난이도 셀렉터 삽입.
- 아레나와 동일한 `cond-cards`/`cond-card`/`cond-label`/`cond-blurb` 클래스 재사용(CSS 변경 불필요), `squidArenaHelpers.difficultyOptions`를 `x-for`로 렌더, `difficulty === opt.value`로 선택 표시.
- **위치 의미:** 셀렉터는 셋업 카드 안에 두어, 캠페인 시작 전(`!started`)에만 렌더된다. `startGame()` 성공으로 `started=true`가 되면 셋업 카드 전체가 `x-show`로 숨겨지므로 셀렉터도 사라진다 → 캠페인 진행 중 난이도 변경 경로가 구조적으로 차단되어 캠페인 단위 고정이 보장된다.

### 캠페인 단위 고정 + 재개 일관성 (핵심 정합성)
- 난이도는 `startGame()`이 매 게임 호출될 때 `this.difficulty`(캠페인 내 불변)를 전송 → 6게임 모두 동일 난이도, 각 게임 행이 동일 태그로 저장.
- **체크포인트 정합성:** `_saveCheckpoint()` 페이로드(`web/app.js:764`)에 `difficulty` 추가. 현재 페이로드는 `nickname/password/campaignId/campaignIndex/campaignResults`만 담아, 재개 시 난이도가 기본값 `easy`로 되돌아가는 버그가 생긴다. 스키마 버전 `v`를 올리고(`v:1`→`v:2`) `_loadCheckpoint()`에서 복원, 구버전 체크포인트는 `difficulty` 부재 시 `'easy'`로 폴백.

### API 검증 수정 (`interface/api.py`)
- `NewGameRequest`에 아레나와 동일한 `VALID_DIFFICULTIES` 검증 추가 → 잘못된 difficulty는 `HTTPException(400)`. 현재의 `Difficulty("banana")` → 500 크래시를 400으로 교정. `/api/arena/run`의 검증 스타일과 일치.

### 테스트
- `tests/unit/test_api_web_arena.py`(또는 human-game 테스트 파일)에 `/api/new_game`:
  - `difficulty="hard"` 수용 → 세션 생성 + 저장된 행의 difficulty == `"hard"`.
  - `difficulty="banana"` → `HTTP 400`(500 아님).
  - difficulty 생략 → 기본값 `"easy"`.
- `node --check web/app.js`.
- Playwright 스모크: Play 탭에서 3개 난이도 카드 렌더 + Normal 선택 시 `/api/new_game` 페이로드에 `"difficulty":"hard"` 확인, 체크포인트 저장/복원 시 난이도 유지.

---

## 단위 경계 요약

| 단위 | 책임 | 의존 | 테스트 방법 |
|---|---|---|---|
| Rebase(Phase 0) | 워크트리를 최신 main 위로 이동 | git | 테스트 스위트 그린 게이트 |
| `SessionRecord.difficulty` + 스키마 | DB에 난이도 영속화 | `SeasonResult.difficulty` | repo 라운드트립·마이그레이션 멱등성 |
| 저장 배선(api/seeding) | season의 난이도를 레코드로 전달 | 위 스키마 | 저장 후 조회 검증 |
| `playScreen` 난이도 상태/전송 | 캠페인 난이도 선택·전송·재개 | `difficultyOptions`(아레나) | node --check + Playwright |
| `NewGameRequest` 검증 | 잘못된 난이도 400 | `VALID_DIFFICULTIES` | API 유닛 테스트 |

## 리스크 / 시퀀싱

- **순서 엄수:** Phase 0(rebase) → 1 → 2. rebase를 나중에 하면 신규 작업이 구 베이스에 쌓여 충돌이 커진다.
- **Postgres 파리티:** 스키마·INSERT·SELECT 변경은 sqlite/postgres 양쪽에 동일 적용(프로젝트 메모리: 파리티 누락 시 리더보드 NULL 표기).
- **프로덕션 DB:** 141MB 시딩 DB는 멱등 `ADD COLUMN`으로 안전하게 마이그레이션(기존 행 `'easy'` 백필). 파괴적 변경 없음.
- **하위호환:** `SessionRecord.difficulty`·`NewGameRequest.difficulty`·`playScreen.difficulty` 모두 기본값 `"easy"` → 기존 호출·구 체크포인트 무해.
