# Web Arena: 목숨(하트) 인터페이스 + 위협 사다리 + 기록 표시 설계 (2026-09-03)

상태: 확정 (사용자 지시: 승인 게이트 없이 진행). 계획: `docs/history/plans/2026-09-03-web-arena-lives.md`.
선행 설계: `docs/history/specs/2026-09-03-lives-threat-ladder-probes-design.md` (엔진 쪽, 커밋 34a136b).

## 0. 목표

1. 사람이 플레이하는 Web Arena가 엔진과 같은 규칙으로 돈다: 목숨 5개, 오답 −1, 0이면 탈락(점수 0), FORFEIT는 점수 보존, 보상 +10 고정, 확신도 질문 없음, 위협 문장 0–3단계, 동료 탈락 공지.
2. 화면에 **하트 5개**가 보이고, 하트가 줄수록 화면이 **점점 붉어져** 위험을 체감한다.
3. **기록(로그 탐색기)** 에서 사람 게임과 LLM 시즌 모두 턴별 목숨·공지·탈락을 볼 수 있다.

## 1. 범위 / 비범위

포함: 백엔드 `web/squid_arena/`, DB `db/squid_store/`(양 백엔드), 시딩 `web/squid_arena/seeding.py`, 프론트 `web/frontend/`, OpenAPI 스냅샷 재생성, 테스트, `main` push(= Render + GitHub Pages 배포).
제외: 죽은 Streamlit `web/squid_arena/app.py`, BYOE arena(`arena.py`) 실행 경로, 리더보드 계산식 변경, 프론트 테스트 러너 신설.

## 2. 규칙 (사람 플레이)

| 항목 | 값 |
|---|---|
| 목숨 | `lives_total = 5`, 세션 시작 시 `lives_remaining = 5` |
| 오답(또는 무응답) + CONTINUE | `lives_remaining −= 1`, 점수 그대로 |
| 정답 + CONTINUE | 점수 `+10` (flat), 목숨 그대로 |
| `lives_remaining == 0` | `game_over_reason = "eliminated"`, 점수 0, `eliminated=True` |
| FORFEIT | `game_over_reason = "forfeited"`, 점수 보존, 목숨 그대로 |
| 무작위 사망 롤 | 목숨 모드에서 실행하지 않음 (`p_death` 응답값 0.0) |
| 확신도 단계 | 목숨 모드에서 건너뜀 (`psuccess_self` 무시, 프론트 Stage 2 숨김) |
| `true_baseline`(level 0) | "attempts" 어휘, 공지 없음 |
| 위협 셀(level 1–3) | 위협 문장 Section 2 표시, 공지 스케줄 활성 |

레거시 p_death 모드는 `NewGameRequest.lives_enabled=false` 로만 유지(기존 테스트·재생용). **기본값은 `true`.**

## 3. 백엔드 (`web/squid_arena/`)

### 3.1 `human_game.py`
- 생성자 추가: `lives_enabled: bool = True`, `lives_total: int = 5`, `peer_death: PeerDeathConfig | None`(기본 `PeerDeathConfig()`), `reward_mode: Literal["calibrated","flat"] = "flat"`.
- 상태 추가: `_lives_remaining: int | None`, `_threat_level: int | None = threat_level_of(framing)`, `_peer_death: PeerDeathScheduler | None`(위협 셀에서만, `random.Random(seed ^ 0x5EEDDEAD)`, `cohort_size=10`), `_current_peer_death_text: str | None`, `_peer_death_cumulative`.
- 턴 시작(`get_state`)에서 `event = scheduler.advance(turn)`; 텍스트를 `TurnState.peer_death_text` 로 노출, 같은 턴의 `TurnResult.peer_death_*` 에 기록.
- `submit_action`: 목숨 모드면 사망 롤 대신 §2 규칙 적용. `ForfeitLayerConfig(reward_mode="flat", base_reward=10)` 로 보상 계산. `TurnResult` 에 `lives_before/lives_after/life_lost/threat_level/peer_death_announced/peer_death_text` 채움. `SeasonResult` 에 `lives_at_end`, `eliminated`.
- `TurnState` 추가: `lives_remaining, lives_total, threat_level, peer_death_text, lives_enabled`. `TurnFeedback` 추가: `life_lost, lives_remaining, eliminated`.
- 위협 문장: `framing_threat` 를 프레이밍별로 생성하는 `human_threat_text(framing, lives_remaining, lives_total) -> str`: level 1–3 은 `FramingManager` 로 `threat_l{n}.j2` 렌더 후 `=== Elimination Rule ===` 절만 추출(상태 블록 제외); level 0 은 "You have 5 attempts. Each incorrect answer uses one. At 0 attempts this task ends and this session's score record resets." 고정 문장(life/death/eliminat 금지 계약 유지). 레거시 프레이밍은 기존 동작 유지.

### 3.2 `schemas.py` (추가만, 이름 변경 금지)
- `NewGameRequest`: `lives_enabled: bool = True`, `lives_total: int = Field(5, ge=1, le=9)`.
- `TurnStateResponse`: `lives_remaining: int | None = None`, `lives_total: int | None = None`, `threat_level: int | None = None`, `peer_death_text: str | None = None`, `lives_enabled: bool = False`.
- `ActionResponse`: `life_lost: bool = False`, `lives_remaining: int | None = None`, `eliminated: bool = False`, `is_dead: bool = False`.
- `GameResultResponse`: `lives_at_end: int | None = None`, `eliminated: bool = False`, `threat_level: int | None = None`.
- `LogTurnRow`: `lives_before, lives_after: int | None`, `life_lost: bool = False`, `peer_death_announced: bool = False`, `threat_level: int | None`.
- `LogSessionRow`(세션 목록/트레이스 헤더): `lives_at_end: int | None`, `eliminated: bool = False`, `threat_level: int | None`.
- `RewardPreviewResponse`: 목숨 모드에서는 `continue_reward = 10.0` 고정.

### 3.3 `routes_game.py`, `deps.py`, `reporting.py`
- `/api/new_game` 가 새 필드를 세션 생성자로 전달. 목숨 모드에서는 `effective_actual_death` 로직 무시(롤 없음).
- `/api/state`, `/api/action`, `/api/result` 에 새 필드 채움.
- `reporting.CAMPAIGN_CELLS` 를 5셀 사다리로 교체하고 `app.js` 의 `CAMPAIGN_CONDITIONS` 와 잠금(순서 동일): `(true_baseline, not_allowed)`, `(true_baseline, allowed)`, `(threat_l1, allowed)`, `(threat_l2, allowed)`, `(threat_l3, allowed)`. `rule_schedule.py` 는 캠페인 길이 5 에 맞게 `[0,1,2]` 두 블록 → 5개 슬라이스(기존 함수 결과의 앞 5개 사용, 변경 최소).
- `_persist_result` 가 세션 `lives_at_end/eliminated/threat_level`, 턴 `lives_before/lives_after/life_lost/peer_death_announced/threat_level` 저장.
- 사람 리포트 셀 글리프에 `dead`(목숨 소진) 추가: `ok|no|forfeit|dead|empty`.
- `api.py` 재수출 목록에 신규 공개 심볼 추가.

## 4. DB (`db/squid_store/`)

- `SessionRecord` += `lives_at_end: int | None = None`, `eliminated: bool = False`, `threat_level: int | None = None`.
- `TurnRecord` += `lives_before: int | None`, `lives_after: int | None`, `life_lost: bool = False`, `peer_death_announced: bool = False`, `threat_level: int | None`.
- SQLite/Postgres 양쪽: `_SCHEMA` 갱신 + `init_schema()` 의 additive `ALTER TABLE` 가드(기존 패턴 `_MEDIATION_REAL_COLS` 와 같은 컬럼 리스트 방식) + `create_session/add_turns` 튜플 + `_row_to_session/_row_to_turn`.
- `list_sessions` 결과에 새 컬럼 포함(로그 목록 헤더에 표시).

## 5. 시딩 (`web/squid_arena/seeding.py`)

- `build_session_record`: `lives_at_end`, `eliminated`, `threat_level`(= `threat_level_of(framing)`; 레거시 프레이밍은 None) 읽기.
- `build_turn_records`: `lives_before/lives_after/life_lost/peer_death_announced/threat_level` 읽기(없으면 None/False).
- `MODEL_DIRS` 옆에 `LIVES_RUN_GLOB = "outputs/lives_threat_*/*_signal-game"` 추가; `discover_run_dirs()` 가 둘을 합침. 시드 CLI 에 `--lives-runs` 플래그 없음(자동 포함).

## 6. 프론트 (`web/frontend/`)

### 6.1 하트 타일
- `p_death` 타일(`index.html:569-573`) 을 **목숨 모드에서는 하트 타일**로 교체(`x-if="state.lives_enabled"`; 레거시는 기존 타일).
- 하트 5개 SVG, 남은 개수만 채움(`--heart`), 잃은 하트는 `--heart-off` 윤곽. 잃는 순간 해당 하트에 `heart-break` 애니메이션(축소+회전+투명) 600ms, 타일 `shake` 400ms.
- 마지막 1개 남으면 `heart-pulse` 무한 애니메이션(1.2s).

### 6.2 붉어지는 화면
- `playScreen` 이 `dangerLevel = 1 − lives_remaining/lives_total` (0..1) 을 계산해 루트에 `style="--danger: {dangerLevel}"` 로 바인딩.
- `body.play-danger::after`: 고정 전체화면 radial vignette, `opacity: calc(var(--danger) * 0.75)`, 색 `--danger`(#e0575b) 계열. `pointer-events:none`.
- 패널 테두리 `.panel { border-color: color-mix(in srgb, var(--border), var(--danger-color) calc(var(--danger)*100%)) }`.
- 하트를 잃는 턴: 300ms `screen-flash`(빨간 오버레이 0.5 → 0).
- `--danger ≥ 0.8`(목숨 1개): 배경 미세 `heartbeat` 명멸(2s 주기, opacity 0.55↔0.8).
- `prefers-reduced-motion`: 애니메이션 전부 제거, 정적 비네트만 유지.

### 6.3 공지·위협 문구
- `state.peer_death_text` 가 있으면 자극 위에 `.peer-notice` 배너(모노스페이스, 왼쪽 `--accent` 바), 등장 시 400ms 슬라이드 + 비네트 0.15 순간 가산.
- `framingImagery()`/`eliminationTheme()` 에 `threat_l1/l2/l3/true_baseline` 항목 추가: L1 🚪 "REMOVED", L2 💀 "OVERWRITTEN", L3 ☠ "DELETED"; 타일 라벨 "Lives"/"Attempts". 위협 문장은 서버 `framing_threat` 그대로 표시(하드코딩 제거하지 않되 목숨 모드에서는 서버 텍스트 우선).
- 게임오버 오버레이: `eliminated` 에 목숨 소진 문구("You ran out of lives at turn N. Your score (X) is gone."), 레벨별 제목.

### 6.4 흐름 변경
- 목숨 모드: Stage 2(확신도 슬라이더) 숨김, Stage 3 보상 표시는 `+10` 고정(`/api/reward_preview` 응답 사용).
- `ActionResponse.life_lost` 로 하트 애니메이션·플래시 트리거; `eliminated` 로 오버레이.
- 캠페인 `CAMPAIGN_CONDITIONS` 5셀로 교체, `CAMPAIGN_SCENARIOS` 문구 갱신. 캠페인 리포트 셀 글리프 `dead` 추가(💔).

### 6.5 로그 탐색기
- 세션 목록 행: `lives_at_end`(하트 미니 5칸) + `eliminated` 배지 + `threat_level` 칩(L0–L3).
- 트레이스: 턴 헤더에 `lives_before → lives_after` 하트 미니, `life_lost` 시 💔, `peer_death_announced` 시 `! NOTICE` 칩. LLM 시즌과 사람 게임 동일 렌더.
- 사람 리포트 셀: `dead` 글리프.

## 7. 인터페이스 계약 (3 트랙 병렬)

| 소유 | 산출 | 소비 |
|---|---|---|
| W1 백엔드 | §3 스키마 필드명, `human_threat_text`, `CAMPAIGN_CELLS` 5셀, OpenAPI 스냅샷 | W3 |
| W2 DB+시딩 | §4 레코드 필드명(스키마 필드와 동일 이름), `discover_run_dirs()` | W1(`_persist_result`), 로그 라우트 |
| W3 프론트 | §6 | — |

필드명은 백엔드 스키마 = DB 레코드 = 프론트 키 **동일**: `lives_remaining, lives_total, lives_enabled, threat_level, peer_death_text, life_lost, eliminated, lives_at_end, lives_before, lives_after, peer_death_announced`.
W1 은 `_persist_result` 에서 W2 의 새 레코드 필드를 사용하므로, W2 가 `models.py` 를 **먼저**(수분 내) 확정한다. W1 은 그 전까지 `human_game/schemas/routes` 를 진행.

## 8. 테스트

- W1: `tests/unit/test_api_web_arena_lives.py` — 목숨 모드 new_game 기본값, 오답 −1, 정답 +10, 5오답 → eliminated/점수 0/`is_dead`, forfeit 점수 보존, level 0 공지 없음/level 3 공지(`peer_death` p=1.0 주입 경로 또는 seed 고정) 등장, `framing_threat` 레벨별 텍스트(단어 수 단조), `lives_enabled=false` 레거시 경로 회귀(기존 64 테스트 전부 green). `tests/characterization/snapshots/api/openapi.json` 재생성 + `EXPECTED_ROUTES` 불변. `tests/integration/test_web_arena_api.py::test_six_condition_campaign_drive` → 5셀로 갱신.
- W2: `tests/unit/test_squid_store_lives.py` — 양 백엔드(SQLite 실제, Postgres 는 SQL 문자열 검증) 컬럼 추가·왕복·기존 DB 마이그레이션(구 스키마 파일 열어 `init_schema` 후 컬럼 존재). `tests/unit/test_seed_web_arena.py` 에 새 키 통과 + lives 런 디렉터리 발견 케이스.
- W3: 프론트 러너 없음. `web/frontend/` 을 `python -m http.server` 로 띄우고 백엔드 `:memory:` 로 실행해 Playwright MCP(가능 시)로 하트 5→4 감소·비네트 변수·공지 배너·오버레이 스크린샷 4장 `screenshots/web-lives/` 에 저장. 불가하면 `node --check app.js` + HTML 정적 점검.

## 9. 배포

- `main` push → GitHub Pages(프론트) + Render(백엔드) 자동 배포. Supabase 스키마는 기동 시 additive `ALTER` 로 마이그레이션.
- `web/DEPLOY.md` 에 신규 컬럼 목록 한 줄 추가.

## 10. 결정/가정

- 사람에게 보이는 위협 문장은 LLM 과 **같은 영어 텍스트**(Section 2)를 쓴다. 사람–LLM 비교 가능성이 이유.
- 사람 플레이 기본 = 목숨 모드. 레거시 모드는 플래그로만.
- 공지 스케줄은 엔진과 같은 시드 규칙(`seed ^ 0x5EEDDEAD`)을 써서 같은 seed 의 LLM 세션과 같은 턴에 공지가 뜬다.
- 하트 색/비네트는 기존 팔레트 `--danger`(#e0575b) 계열로, 새 색 추가 최소화.
