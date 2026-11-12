# Arena BYO-Participant 확장 설계

**Date:** 2026-05-24
**Author:** brainstorming session (irregular6612 + Claude)
**Status:** Draft for user review
**Scope:** `src/arena/` 신규 패키지 — LLM Squid Game을 외부 제출형 온라인 아레나로 확장

---

## 1. 배경과 결정 사항

LLM Squid Game은 현재 CLI/YAML 기반의 단일 연구자 워크플로다. KDD 2026 마감과 채널 분할 리팩터(`refactor/game-posthoc-split`, 2026-05-21~23) 완료 직후 시점에서, 본 설계는 외부 연구자가 자기 모델을 우리 인프라에서 평가받고 리더보드에 등재할 수 있는 **공개 제출형 아레나**로의 확장을 정의한다.

브레인스토밍 세션에서 다음 세 가지가 확정되었다.

| # | 결정 | 함의 |
|---|---|---|
| 1 | **Mode C — Public Submission Arena** | 외부 참가자가 모델을 등록해 자동 평가. (A 정적 쇼케이스 / B 연구자 콘솔은 제외) |
| 2 | **BYO-API 방식** (참가자가 OpenAI-호환 endpoint 노출, 우리 서버가 호출) | 모델 weights는 참가자 인프라에 머무름. 우리는 GPU 운영 비용 0. 업계 표준 (SEAL, LMSYS) 동일. |
| 3 | **Cheating 무방지** | latency trace, hidden eval cell, repeat-seed audit, weights-hash proof 등 검증 장치 일체 제외. 리더보드에 "self-reported, unverified" 디스클레이머 1줄. |

코드 범위는 **(X) 서버 측 onboarding + (Y) 참가자 키트** 모두를 포함한다.

---

## 2. 비목표 (Non-goals)

- 결과 검증·이상치 탐지·정직성 보장 메커니즘 (결정 #3에 따라 명시적으로 제외)
- 우리 서버에서 weights를 호스팅·실행하는 경로 (BYO-API만)
- 결제·과금·SLA·SSO 같은 SaaS 수준 운영 기능
- 기존 `src/squid_game/` 코드 수정 — 본 확장은 **순수 추가 only**. 어떤 기존 파일도 편집하지 않는다.

---

## 3. 아키텍처

### 3.1 4계층 구조 (`src/arena/`)

```
src/arena/
├── backend/           # FastAPI · SQLAlchemy · Alembic · MySQL (Python 3.12)
├── frontend/          # React 18 + Vite + TypeScript + Tailwind + Recharts
└── participant_kit/   # 참가자가 자기 환경에서 실행하는 CLI + 예제
```

기존 `src/squid_game/`는 의존 그래프의 하위에 머문다. `arena.backend` → `squid_game.game.runner`(import) ✅, 반대 방향은 금지 (lint 규칙으로 강제).

### 3.2 모듈 책임

#### Backend (`src/arena/backend/`)
- `app.py` — FastAPI 앱 부트스트랩, CORS, 의존성 wiring.
- `api/participants.py` — `POST /api/participants` (등록), `GET /api/participants/me`, `DELETE /api/participants/me`.
- `api/evaluations.py` — `POST /api/evaluations` (큐잉), `GET /api/evaluations/{id}` (상태), `GET /api/evaluations/{id}/logs`.
- `api/leaderboard.py` — `GET /api/leaderboard`, `GET /api/models/{participant_id}`, `GET /api/compare?a=...&b=...`.
- `db/models.py` — SQLAlchemy ORM.
- `db/migrations/` — Alembic.
- `worker/runner.py` — background task. 평가 큐를 pop하여 `squid_game.game.runner.ExperimentRunner`를 호출. MVP는 단일 프로세스 in-process worker (Python `asyncio` + `concurrent.futures`). Celery는 도입하지 않는다 (cheating 무방지 + 단순화 방침과 일치).
- `etl/ingest.py` — `outputs/<eval_id>/*.jsonl` → MySQL.
- `providers/participant_byo.py` — **신규 LLM Provider**. `squid_game.game.infra.providers.local.LocalProvider`를 상속하여 `base_url`/`api_key`/`model_name`을 DB에서 가져온다. fetch 정책: **evaluation 시작 시 1회 fetch → provider 인스턴스에 stash**. 평가 도중 참가자가 endpoint를 바꾸면 그 변경은 다음 evaluation부터 반영된다 (실행 중 evaluation은 처음의 endpoint를 끝까지 사용). 추가 LLM 호출 로직 0줄.

#### Participant kit (`src/arena/participant_kit/`)
- `arena_cli/__main__.py` — `arena-cli register / ping / status` 진입점.
- `arena_cli/ping.py` — 참가자가 자기 endpoint를 띄운 후, OpenAI-호환 응답 검증 (`POST /v1/chat/completions`, role/content/usage 필드 검사).
- `examples/vllm_compose.yml` — vLLM serving용 docker-compose.
- `examples/ollama_setup.md` — M-시리즈 Mac 등에서 ollama로 작은 모델 띄우는 가이드.
- `examples/cloudflare_tunnel.md` — NAT/방화벽 뒤에서 endpoint 노출하는 방법.
- `README.md` — 5분 onboarding 시나리오.

#### Frontend (`src/arena/frontend/`)
- React 18 + Vite + TypeScript.
- 페이지: `/` (Leaderboard) · `/model/:participant_id` (OP.GG 스타일 모델 카드) · `/compare` · `/submit` (CLI 대안 등록 폼).
- 차트: Recharts — Kaplan-Meier 생존곡선, RI trajectory, MTMM 4-component radar.
- 상태: TanStack Query (서버 상태 only, Redux 미사용).
- 스타일: Tailwind. 다크 테마 + accent color.

### 3.3 데이터 모델 (MySQL)

```sql
participants (
  id              BIGINT PK AUTO_INCREMENT,
  display_name    VARCHAR(64) NOT NULL,
  owner_email     VARCHAR(128) NOT NULL,
  base_url        VARCHAR(512) NOT NULL,        -- 참가자 OpenAI-호환 endpoint
  api_key_hash    VARCHAR(128) NOT NULL,        -- bcrypt
  model_name      VARCHAR(128) NOT NULL,
  model_meta      JSON,                          -- 파라미터수, context, thinking 지원 여부 등 자기신고
  registered_at   DATETIME NOT NULL,
  status          ENUM('active','disabled') NOT NULL DEFAULT 'active'
)

evaluations (
  id              BIGINT PK AUTO_INCREMENT,
  participant_id  BIGINT FK,
  config_label    VARCHAR(64) NOT NULL,          -- 'smoke' | 'canonical_6x30' 등
  status          ENUM('queued','running','done','failed','cancelled') NOT NULL,
  queued_at       DATETIME NOT NULL,
  started_at      DATETIME,
  finished_at     DATETIME,
  output_dir      VARCHAR(512),                  -- outputs/<eval_id>/
  error_message   TEXT
)

season_results (
  id                 BIGINT PK AUTO_INCREMENT,
  evaluation_id      BIGINT FK,
  season_id          CHAR(12) NOT NULL,
  framing            VARCHAR(32),
  forfeit_condition  VARCHAR(16),
  cell               TINYINT,                    -- 0..5
  final_score        FLOAT,
  forfeited          BOOL,
  forfeit_turn       INT,
  forfeit_reason     TINYINT,                    -- 1=SD, 2=TC, 3=SA
  total_turns        INT,
  seed               INT
)

turn_results (
  id                  BIGINT PK AUTO_INCREMENT,
  season_result_id    BIGINT FK,
  turn_number         INT,
  ri_task             INT,
  ri_probe            INT,
  ri_forfeit          INT,
  forfeit_choice      VARCHAR(16),
  psuccess_self       INT,
  decision_quality    FLOAT,
  reward_received     FLOAT,
  died                BOOL
  -- turns.jsonl의 37 필드 중 분석·시각화에 쓰이는 것만 정규화 적재.
  -- 풀 raw 데이터는 outputs/<eval_id>/<season_id>_turns.jsonl에 보존 (재분석용).
)

turn_texts (
  -- thinking_text·raw_response 같은 큰 텍스트 필드는 별도 테이블로 분리.
  -- 1:1 with turn_results, lazy join (리더보드/모델 카드에는 불필요).
  turn_result_id        BIGINT PK FK,
  thinking_text_task    MEDIUMTEXT,
  thinking_text_probe   MEDIUMTEXT,
  thinking_text_forfeit MEDIUMTEXT,
  raw_response_task     MEDIUMTEXT,
  raw_response_probe    MEDIUMTEXT,
  raw_response_forfeit  MEDIUMTEXT
)
```

리더보드 정렬용 derived view는 nightly cron으로 `leaderboard_snapshot` 테이블에 적재 (실시간 계산 회피). 정렬 메트릭 후보는 frontend 설계 단계에서 별도 확정 (`forfeit_rate`, `mean_ri`, `MTMM SD-component` 등 중 다중 선택 가능하게).

### 3.4 한 평가 세션의 시퀀스

1. 참가자: `arena-cli register --base-url … --model …` → `POST /api/participants` → `{participant_id, api_key}` 발급
2. 참가자: 자기 endpoint 띄움 (vLLM/Ollama/Modal/OpenRouter)
3. 참가자: `arena-cli ping` → 자체 검증
4. 참가자: `POST /api/evaluations` (config_label 지정) → eval_id 발급, queue enqueue
5. Worker: pop → `ExperimentRunner(provider=ParticipantBYOProvider(participant_id=X))`
6. game.runner: 6셀 × N seed × 15 turn × 3 calls, 각 call마다 X의 endpoint로 HTTP 호출
7. 완료 후 ETL: `outputs/<eval_id>/` → MySQL
8. Leaderboard 자동 갱신, 참가자가 `/model/<participant_id>`에서 결과 확인

---

## 4. 에러 처리

- **참가자 endpoint 5xx/timeout** — exponential backoff 3회 (`squid_game.game.infra.providers` 기존 `_BACKOFF_SECONDS` 패턴 재사용). 실패 시 `evaluations.status = failed`, `error_message`에 마지막 응답 코드 기록. 부분 산출물은 `outputs/<eval_id>/` 그대로 보존 (수동 디버깅용).
- **DB write 실패** — ETL은 evaluation_id 기준 idempotent. 재실행 가능.
- **Worker crash** — MVP는 in-process라 단순 재시작. 실행 중이던 evaluation은 다음 부트 시 `status=running`으로 남아있으면 운영자가 수동 `failed`로 마킹 (자동 cleanup은 Phase 2).
- **참가자 endpoint가 OpenAI-호환이 아닐 때** — `arena-cli ping`이 미리 검출. 그래도 서버에 도달하면 `ParticipantBYOProvider`가 parsing 실패 → 평가 abort.

---

## 5. 테스트 전략

- **Unit** — `ParticipantBYOProvider`가 DB lookup mock으로 `base_url`/`api_key`를 받아 `LocalProvider.complete()`를 호출하는지. `LLMProvider` 인터페이스 contract 테스트.
- **Integration** — `tests/integration/test_arena_e2e_smoke.py`. docker-compose로 mock vLLM 컨테이너 + MySQL 띄우고 register → enqueue → 6셀×1 seed smoke → leaderboard row 검증.
- **Frontend** — Vitest + React Testing Library, 페이지 단위 렌더링 + API mock.
- **CLI** — `tests/unit/test_arena_cli.py`. `ping` 명령이 OpenAI-호환 응답 / 비호환 응답을 정확히 판별.

---

## 6. 의존성 추가

### Python (backend)
- `fastapi`, `uvicorn`, `sqlalchemy`, `alembic`, `pymysql`, `cryptography`, `bcrypt` (api_key 해싱)
- `pyproject.toml`에 optional dependency group `[arena]` 신설. 기존 코어 의존성에는 영향 없음.

### Node (frontend)
- `react`, `react-dom`, `react-router-dom`, `@tanstack/react-query`, `recharts`, `tailwindcss`, `typescript`, `vite`, `vitest`.
- `src/arena/frontend/package.json` 별도 관리.

### Participant kit
- `httpx`, `click` (CLI), `pydantic` (참가자 자기 신고 메타 검증). 별도 `pyproject.toml` (`src/arena/participant_kit/`) — 참가자가 `pip install arena-cli`로 받을 수 있게.

---

## 7. 단계적 구현 순서 (writing-plans 단계로 위임)

본 spec은 **무엇을 만들지**만 정의한다. 어떤 순서로 어떤 코드를 어떤 commit 경계로 짤지는 다음 단계인 `writing-plans` 스킬에서 작성한다. 대략의 마일스톤만 표시:

1. **M1 — Provider + DB skeleton** — `ParticipantBYOProvider` + `participants`/`evaluations` 테이블 + Alembic.
2. **M2 — Worker + ETL** — 단일 in-process worker가 `ExperimentRunner`를 호출하고 결과를 MySQL에 적재.
3. **M3 — REST API** — register / enqueue / status / leaderboard.
4. **M4 — Participant kit** — `arena-cli` + 예제.
5. **M5 — Frontend skeleton** — Leaderboard + ModelCard 페이지.
6. **M6 — E2E smoke** — docker-compose로 한 사이클 검증.

---

## 8. 미해결 항목 (Open questions)

본 spec의 범위 밖이거나 writing-plans 단계에서 결정할 사항:

- **리더보드 정렬 메트릭 후보 확정** — `forfeit_rate` / `mean_ri_forfeit` / `MTMM SD-component` / cell-별 분리 등 어느 조합을 기본 정렬로 노출할지. ModelCard 화면 디자인 시점에 확정.
- **CORS 정책** — frontend가 어디서 호스팅되는지 결정된 뒤. MVP는 same-origin (frontend도 FastAPI가 정적 서빙).
- **MySQL 호스팅** — 로컬 docker / RDS / PlanetScale 중 택1. 배포 시점에 결정.
- **frontend 정렬 메트릭별 위계** — OP.GG의 "티어/승률/KDA" 위계 흉내 시 후보: "Tier (cell-3 forfeit rate band) / FSPM score / RI efficiency".
