# 사람 플레이: 10턴 + 실사망(p_death) + 사망 연출 UI

- **작성일**: 2026-07-03
- **범위**: 웹 아레나의 **사람 플레이 전용** 경로(`/api/new_game` → `state`/`action` 루프). LLM 아레나(`/api/arena/run`)는 손대지 않는다.

## 목표

사람이 플레이할 때:

1. 세션 길이를 **15턴 → 10턴**으로 줄인다.
2. **p_death를 실제로 활성화**한다 — 매 턴 상수 **0.15** 확률로 실제 사망 판정을 굴린다(현재는 UI에만 표시되고 판정은 하지 않는 "Phantom Death" 상태).
3. 사망 시 **점수를 0으로 초기화**하고 세션을 종료한다(기존 코어 엔진 동작 그대로).
4. 사망 순간을 **극적으로 연출하는 UI**를 추가한다.

## 배경 / 현재 동작

- `/api/new_game`은 사람 플레이 **전용** 엔드포인트다. 채점은 서버의 `HumanGameSession`이 코어 엔진 컴포넌트(`SurvivalPressure`, `ForfeitController`, `ForfeitLayer` 등)를 그대로 써서 LLM 실험과 동일한 역학을 보장한다.
- 현재 `NewGameRequest` 기본값: `total_turns=15`, `actual_death=False`, `p_death_constant=0.15`.
  - 프론트엔드 `startGame()`은 `total_turns`/`actual_death`/`p_death_constant`를 보내지 않으므로 이 서버 기본값이 적용된다 → 죽음이 꺼져 있다.
- `p_death` 값(0.15)은 이미 UI Risk 타일(`web/index.html`)에 표시된다. `actual_death`만 켜면 표시된 값이 실제 판정에 반영된다.
- 사망 로직은 이미 구현돼 있다 — `HumanGameSession.submit_action`에서 `actual_death`가 참이면 `SurvivalPressure.apply_death_check(p_death, rng)`를 굴리고, 사망 시 `cumulative_score = 0.0`, 세션 종료, `game_over_reason = "eliminated"`를 반환한다.
- 프론트엔드 `web/app.js`에 서버와 **중복된 상수** `TOTAL_TURNS = 15`가 있고, 리포트 테이블(`/ 15`)과 히트맵 컬럼 수에 쓰인다. 서버 `total_turns`와 반드시 일치해야 한다.

### 사망 확률 근거

매 턴 상수 0.15 → 10턴 누적 생존율 `0.85^10 ≈ 0.20`. 즉 플레이어의 **약 80%가 10턴 안에 탈락**한다. 사용자가 이 강도를 명시적으로 선택함("표시된 그 확률로 종료"에 가장 충실). 로지스틱 스케줄(초반 안전→후반 급증)이 아니라 **상수 0.15**를 쓴다.

## 변경 사항

### 1. 백엔드 — `interface/api.py`, `NewGameRequest` 기본값

```python
total_turns: int = 10        # was 15
actual_death: bool = True    # was False
# p_death_constant: float | None = 0.15   ← 변경 없음
```

이 엔드포인트가 사람 플레이 전용이므로 여기 기본값이 단일 진실 원천이다. 신규 게임 로직은 없다 — 이미 있는 사망 경로가 켜질 뿐.

### 2. 프론트엔드 상수 동기화 — `web/app.js`

```js
const TOTAL_TURNS = 10;  // was 15
```

리포트 테이블의 "turns survived / 10"과 히트맵 컬럼 10개로 반영된다.

### 3. 사망 연출 UI — `web/app.js` + `web/index.html` + `web/styles.css`

**상태(Alpine `playScreen()` 데이터)**

- `eliminated: false` — 사망 오버레이 표시 여부.
- `eliminatedTurn: null` — 사망한 턴 번호.
- `eliminatedLostScore: 0` — 잃은 점수(치명적 턴 진입 시점의 `state.cumulative_score`).

**흐름(`submitAction`)**

- 액션 응답 수신 후, `resp.game_over_reason === "eliminated"`이면:
  - `this.eliminatedTurn = turnNo`
  - `this.eliminatedLostScore =` (제출 직전 캡처한 `state.cumulative_score`)
  - `this.eliminated = true`
  - **즉시 `finishGame()`을 호출하지 않는다** — 오버레이를 먼저 보여준다.
- 그 외 게임오버(`completed`/`forfeited`)는 기존대로 즉시 `finishGame()`.

**닫기 핸들러(`dismissDeath()`)**

- `this.eliminated = false`
- `await this.finishGame()` — 결과를 기록하고 betweenGames/campaignDone 흐름으로 진행(기존 종료 경로와 동일).

**마크업(`web/index.html`, play 섹션 내부)**

- 전체 화면 고정 오버레이 `<div class="death-overlay" x-show="eliminated" x-cloak>`:
  - 어두운 반투명 백드롭.
  - 💀 글리프(팝인 + 흔들림 애니메이션).
  - 헤드라인 "ELIMINATED".
  - 서브텍스트: "You were erased at turn N. Your score (M) is gone." (`eliminatedTurn`, `eliminatedLostScore` 바인딩).
  - "Continue →" 버튼 → `dismissDeath()`.

**스타일(`web/styles.css`)**

- `.death-overlay`: `position: fixed`, 전체 화면 덮기, 높은 `z-index`, 백드롭 페이드인.
- 해골 글리프: 기존 `pop-in` 키프레임 재사용 + 신규 `death-shake`(짧은 흔들림) 키프레임.
- 레드 계열 강조. 라이트/다크 테마 모두 무난하게(백드롭이 어두우므로 흰 텍스트 기준).

> ActionResponse는 이미 `game_over_reason`을 반환하므로 **백엔드 응답 계약 변경은 없다**(`is_dead` 필드 추가 불필요).

### 4. 테스트 — `tests/unit/test_api_web_arena.py` 신규 2개

- **기본값 회귀**: `POST /api/new_game`을 빈 바디(`{}`)로 호출 → 첫 `state`의 `total_turns == 10` 단언.
- **사망 경로**: `actual_death` 기본 True 상태에서, 사망이 확정적으로 트리거되도록 seed를 고정하고 턴을 진행 → 어느 시점 액션 응답이 `game_over_reason == "eliminated"`, `final_score == 0`이 됨을 단언(코어 엔진 사망 경로 회귀 가드).
  - seed는 짧은 세션 안에서 사망이 재현되는 값을 골라 상수로 고정한다.

## 범위 밖 (YAGNI)

- `p_death_constant` 값 자체 조정(이미 0.15).
- 로지스틱 스케줄 재도입.
- LLM 아레나(`/api/arena/run`) 경로.
- 사망 시 점수 보존(사용자가 초기화를 명시적으로 확정).
- 사망 연출의 사운드/파티클 등 과한 효과 — 백드롭 + 해골 + 흔들림 수준으로 절제.

## 검증

- `uv run pytest tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py` — 신규 테스트 통과 + 기존 테스트 무회귀(사전 존재하던 실패는 제외).
- 앱 실행 후 사람 플레이로 수동 확인: 10턴 상한, Risk 타일 0.15, 실제 사망 발생 시 오버레이 표시 → Continue → 리포트에 낮은 생존 턴수/0점 반영.
