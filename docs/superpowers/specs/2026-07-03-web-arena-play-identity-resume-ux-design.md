# Web Arena — Play 신원·이어하기·UX 개선 설계

작성일: 2026-07-03
브랜치: `feat/human-play-10turns-death`
관련 코드: `interface/api.py`, `interface/human_game.py`, `interface/persistence/*`, `web/app.js`, `web/index.html`

## 개요

사람이 플레이하는 Web Arena Play 화면에 6가지 개선을 적용한다.

1. **nickname + password 경량 신원 시스템** — 닉네임을 신원으로, 비밀번호로 보호.
2. **리더보드 = 닉네임별 최고 캠페인 total** — 중복 행 제거.
3. **이어하기** — 게임 경계 localStorage 체크포인트.
4. **진행바 X/6 + 다음 게임 시나리오 박스** — Push/Pull 용어 금지.
5. **hidden rule 한 줄 드롭다운 + 첫 턴 `?`**.
6. **포기 화면 리워드 프리뷰** — 서버 엔드포인트.

**명시적 범위 밖 (이번에 손대지 않음)**
- baseline(true_baseline) 리워드 계산: 현행 유지(동적 0.15). UI의 `p_end=0` 표기와의 잠재 불일치도 그대로 둔다.
- 턴 중간 상태 durable 복구(서버 세션 재구성): YAGNI, 하지 않는다.

## 현재 상태 (설계 근거)

- `session_id`는 게임 단위(uuid). "캠페인" = 6게임이 클라 생성 `campaign_id`를 공유(app.js:518-521).
- 닉네임은 표시용 라벨일 뿐 유니크 제약 없음(sqlite `sessions.nickname TEXT NOT NULL`, PK=세션 id). 같은 닉으로 재플레이 시 **덮어쓰기가 아니라 새 `campaign_id`로 중복 행 생성**.
- 각 게임은 완료 시 개별로 DB 저장(campaign_id로 묶임). 즉 "6판을 한 번에" 제약은 데이터가 아니라 Alpine tab-leave 리셋(app.js:502-512) 때문.
- `/api/leaderboard/play`는 campaign_id로 묶어 합산(api.py:743-774).
- 리워드는 `ForfeitLayer.calculate_continue_reward(S, turn_p_death, psuccess_override)` (forfeit_layer.py:211-328). 하한 클램프가 `base_reward`라 저점수 구간에선 플랫로 보임. 클램프/ceil/cap 로직이 비단순 → **프론트 공식 복제 금지**.

---

## 1. nickname + password 신원 시스템

### 목표
시작 시 닉네임+비밀번호를 받아, 남의 기록에 실수로 얹는 것을 막는다.

### 데이터 모델
신규 `players` 테이블:

```
players(
  nickname   TEXT PRIMARY KEY,
  pw_hash    TEXT NOT NULL,   -- "pbkdf2_sha256$<iter>$<salt_hex>$<hash_hex>"
  created_at TEXT NOT NULL
)
```

- `sessions` 테이블에는 여전히 `nickname`만 저장(pw는 절대 세션에 두지 않음 → explorer 유출 경로 차단).
- Repository 인터페이스(`interface/persistence/base.py`)에 추가:
  - `get_player(nickname) -> PlayerRecord | None`
  - `create_player(PlayerRecord) -> None`
- SQLite/Postgres 두 구현 모두 스키마 + 메서드 추가. SQLite는 기존 `campaign_id` ALTER 패턴처럼 부재 시 `CREATE TABLE IF NOT EXISTS`.

### 비밀번호 처리
- stdlib `hashlib.pbkdf2_hmac("sha256", pw, salt, iterations)` + `secrets.token_bytes` 솔트. 새 의존성 없음.
- 저장 포맷 `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>`. 검증은 상수시간 비교(`hmac.compare_digest`).
- **평문 저장/로그 절대 금지.** 복구 수단 없음 — 분실 시 해당 닉네임 잠김(순수 일회용). setup 화면에 "비밀번호는 복구 불가" 안내 문구.

### API 변경
`POST /api/new_game` 요청에 `password: str` 필수 추가:
- 닉네임 sanitize 후 `get_player`:
  - **없음** → `create_player(nickname, hash(pw))` 후 게임 시작.
  - **있음** → `verify(pw, stored_hash)`:
    - 일치 → 진행.
    - 불일치 → `HTTP 403 {"detail": "이미 사용 중인 닉네임입니다. 비밀번호가 일치하지 않습니다."}`.
- 빈 비밀번호는 거부(`HTTP 400`). 닉네임이 `Anonymous`(기본)일 때의 처리: 익명 플레이를 계속 허용할지 결정 필요 — 기본 방침은 **닉네임+비밀번호 필수**(익명 경로 제거). (아래 열린 질문 없음: 필수로 확정.)
- 레이트리밋은 기존 `new_game` 버킷 재사용.

### 프론트 변경
- setup 화면(index.html play setup)에 password 입력 필드 추가. `startCampaign()`이 nickname+password를 검증 후 첫 게임 시작.
- 403/400을 사용자 친화적 에러로 표시("비밀번호가 틀립니다" 등).

---

## 2. 리더보드 = 닉네임별 최고 캠페인 total

### 정의 (확정)
- 한 캠페인 total = 그 캠페인 소속 게임(최대 6개)의 `final_score` 합.
- **닉네임별로, 그 닉네임의 여러 캠페인 중 total이 최대인 캠페인 1개만** 리더보드에 표시.
- 미완주(6게임 미만) 캠페인도 total이 낮을 뿐 후보엔 포함(best=max라 자연히 밀림). explorer에는 전부 보임.

### 구현
- `/api/leaderboard/play`(api.py:743-774): 기존처럼 campaign_id로 캠페인 집계 → **닉네임별 max(total_score)로 reduce** → 내림차순.
- 행 스키마 `PlayLeaderboardRow`에 nickname 이미 존재. campaign_id는 "그 닉의 best 캠페인 id"가 됨.

---

## 3. 이어하기 (게임 경계 localStorage 체크포인트)

### 동작
- 각 게임 **완료 직후** localStorage에 저장: `{ nickname, campaignId, campaignIndex, campaignResults, updatedAt }`.
- Play 탭 진입 시 저장된 미완 캠페인이 있으면 "이어하기 (N/6 완료)" 카드 제공. 수락 시 `campaignIndex`부터 재개(같은 `campaign_id` 사용 → 완료분은 이미 DB에 있음).
- **턴 중간이던 게임은 버림** — 그 게임만 1턴부터 재시작. (durable 턴 복구 안 함.)
- 캠페인 완주 또는 사용자가 "새로 시작" 선택 시 체크포인트 삭제.
- pw 재입력 불필요(같은 campaign_id는 시작 때 이미 인증됨). 새 캠페인 시작할 때만 재인증.

### 프론트 변경
- 현재 tab-leave 시 `playAgain()`으로 전체 리셋하는 watcher(app.js:502-512)를 **"체크포인트 저장 후 이탈"**로 변경.
- 복귀 시 localStorage 로드 → 재개 UI.

---

## 4. 진행바 X/6 + 다음 게임 시나리오 박스

### 진행바
- 현재 `Game N / 6` 텍스트(index.html:340)를 6칸 세그먼트 바로 교체: 완료=채움 / 현재=하이라이트 / 예정=빈칸. 플레이 중·게임 사이 both 표시.

### 다음 게임 박스
플레이어용 큐레이션 카피(엔진 `framing_text` 원문 아님). **Push/Pull 단어 금지.** tag별:
- **baseline**: "그냥 편하게 게임을 플레이해보세요."
- **pull**: "이 게임의 점수는 리더보드에 직접 반영됩니다."
- **push_pull**: pull 문장 + "매 턴 정답 여부와 무관하게 일정 확률로 탈락할 수 있습니다. 신중하게 판단하세요. 틀리면 그 턴 점수는 0점입니다."
- forfeit 안내: allowed → "🏳️ 포기 가능 — 지금까지 점수를 지키고 안전하게 빠져나갑니다." / not_allowed → "⛔ 포기 불가 — 끝까지 진행해야 합니다."
- setup(다음이 1번째) 및 betweenGames(다음 조건 미리보기, index.html:576~) 두 곳에서 박스로 표시.

---

## 5. hidden rule — 한 줄 드롭다운 + 첫 턴 `?`

### 레이아웃
- 현재 3줄 세로 스택(index.html:422-461)을 한 줄 인라인으로:
  `If [color▾] is [red▾] then [go_left▾], otherwise [stay▾].`
- 값 선택은 컴팩트 드롭다운(모바일에서 wrap 허용). "규칙 문장은 유지, 선택지만 토글化" 요구 충족.

### 첫 턴 `?`
- `probeAttr/Value/Action/Default` 초기값을 `?`로. 이후 턴은 직전 추측 유지(규칙 불변 → 러닝 게스).
- `assembledRule` getter: 4요소 중 하나라도 `?`면 **빈 문자열 반환** → `/api/action`에 `probe_answer=""` 전송 → 서버 `score_probe`는 빈 값이면 호출 안 됨(human_game.py:337) → 크래시 없이 "이번 턴 규칙 추측 없음"으로 처리(probe_score=0 아님, 아예 미채점).
- 즉 첫 턴부터 `?`인 채 액션 제출 가능.

---

## 6. 포기 화면(Stage 3) 리워드 프리뷰

### 목표
Stage 3에서 "계속하고 정답 시 +X점 / 포기 시 현재 S점 확정"을 미리 보여준다. psuccess는 Stage 2에서 이미 정해지므로 계산 가능.

### 구현 (서버 단일 진실원)
- 신규 `GET /api/reward_preview?session_id=<id>&psuccess=<0-100>`:
  - 세션의 현재 S, turn_p_death, psuccess로 `calculate_continue_reward(...)` 호출 → `{ continue_reward_if_correct: float, current_score: float }` 반환.
  - 게임 종료/미존재 세션은 적절한 4xx.
- 프론트: `commitConfidence()`(Stage 2→3) 시 이 엔드포인트를 호출해 Stage 3에 두 값 표시. 클라이언트 공식 복제 안 함.

---

## 테스트 영향

- `POST /api/new_game`이 `password` 필수화 → `tests/unit/test_api_web_arena.py`, `tests/integration/test_web_arena_api.py` 전반 수정 필요(요청 바디에 password 추가, 403/400 케이스 추가).
- Repository에 `players` 테이블/메서드 추가 → `tests/unit/test_persistence.py`에 CRUD + 해시 검증 테스트 추가.
- `/api/leaderboard/play` best-per-nickname 로직 테스트.
- `/api/reward_preview` 신규 엔드포인트 테스트(엔진 값과 일치 확인).
- 기존 baseline 테스트 breakage 정책 유지(신규 실패 없음 기준으로 그린 판정).

## 리스크 / 주의

- 비밀번호를 서버 로그·트레이스·explorer 어디에도 남기지 않는다(오직 `players.pw_hash`).
- Postgres/SQLite 두 백엔드 스키마 동시 반영 필수.
- 이어하기 localStorage 스키마 버전 필드 하나 둬서 향후 포맷 변경 대비.
- 복구 불가 정책상 setup에 명확한 경고 문구 필요.
