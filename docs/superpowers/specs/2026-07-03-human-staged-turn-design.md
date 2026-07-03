# Human Staged Turn (Split-Call Mirror) — Design Spec

> Status: DRAFT — written on best-judgment defaults while the user was away.
> Two decisions (marked **[ASSUMED]**) await user confirmation before implementation.
> Date: 2026-07-03.

## 1. Goal

Web Arena 사람 플레이의 한 턴을, LLM split-call 파이프라인과 동일하게 **3단계 순차
구조**로 재구성한다. 지금은 한 화면에서 규칙추론·액션·확신도·계속/포기를 동시에
제출하지만, 이를 다음 순서로 나눈다:

1. **규칙 추론 → 게임 액션 선택** (LLM Call 1 / `ri_task` 대응)
2. **p(correct) 자기확신도 보고** (LLM Call 1.5 / `ri_probe` 대응)
3. **CONTINUE(선택한 액션 확정) vs FORFEIT(+사유)** (LLM Call 2 / `ri_forfeit` 대응)

핵심 목적은 LLM split-call의 **source isolation** — 액션을 확정한 *뒤에* 포기 결정을
내리게 하여, 포기 프레이밍이 액션 선택에 역방향으로 새지 않게 하는 것 — 을 사람
경험에도 재현하는 것이다.

## 2. Scope — Frontend-only

이 변경은 **프론트엔드 전용**이다. 백엔드/영속화/API를 건드리지 않는다.

근거: `HumanGameSession.submit_action`은 이미 `(action, probe_answer,
forfeit_reason, psuccess_self)`를 한 페이로드로 받고, 포기는 이미 `action="forfeit"`로
표현된다. 3단계 위저드는 이 값들을 세 화면에 걸쳐 **수집**만 하고, 마지막에 기존과
**동일한 단일 `POST /api/action`** 을 그대로 발사한다.

- **CONTINUE** → `POST {action: <1단계 게임 액션>, psuccess_self, probe_answer, reasoning}`
- **FORFEIT** → `POST {action: "forfeit", psuccess_self, forfeit_reason, probe_answer, reasoning}`

두 경로 모두 기존 엔드포인트의 기존 분기(연속/포기)에 그대로 매핑된다. 따라서
`interface/*.py`, persistence, API 스키마는 **무변경**이며, 기존 단일게임
`/api/action` 및 캠페인 테스트는 페이로드 형태가 동일하므로 **그대로 통과**한다.

수정 파일:
- `web/app.js` — playScreen 컴포넌트에 턴 단계 상태머신 추가.
- `web/index.html` — 플레이 카드를 3개 조건부 블록으로 분할.

## 3. Stage machine (web/app.js)

새 상태 `turnStage: 1` (playScreen 상태에 추가). 값 1/2/3.

전이(전진 전용 — forward-lock, 되돌아가기 없음. LLM이 이전 콜을 되돌릴 수 없는 것과
동일):

- **1 → 2** `commitAction()`: `selectedAction`이 비어있지 않은 게임 액션이면 확정,
  `turnStage = 2`. (포기는 1단계 액션 목록에 **없음**.)
- **2 → 3** `commitConfidence()`: 현재 `psuccess` 값을 확정, `turnStage = 3`.
- **3 → 제출** 두 버튼:
  - `chooseContinue()` → `submitAction()` (기존 함수, `selectedAction`은 1단계
    게임 액션 그대로).
  - `chooseForfeit(reason)` → `selectedAction = "forfeit"`, `forfeitReason =
    reason`, 그다음 `submitAction()`.

`submitAction()`은 거의 그대로 재사용한다. 유일한 변경: 성공 리셋부와
`_resetTurnState()`에서 `turnStage = 1`로 되돌린다(다음 턴은 1단계부터).

**Forward-lock 근거:** 3단계에서 1단계 액션을 바꿀 수 없어야 isolation이 성립한다.
"뒤로" 버튼은 두지 않는다. (오조작 복구가 필요하면 향후 별도 논의.)

## 4. Screens (web/index.html)

플레이 카드 내부를 `x-show="turnStage === N"` 3블록으로 나눈다. 상단 컨텍스트
패널(턴 번호, 점수, p_death, 신호/단서 History)은 세 단계에서 항상 보인다.

- **Stage 1 — Rule inference & action**
  - 규칙추론 토글(`probeAttr/probeValue/probeAction/probeDefault`) + `assembledRule` 미리보기.
  - reasoning textarea (이 액션 전의 chain-of-thought).
  - 게임 액션 버튼들(기존 `available_actions`에서 **forfeit 제외**).
  - `[다음 → 확신도]` 버튼: 게임 액션 선택 시 활성.
- **Stage 2 — Confidence**
  - "선택한 액션: X" (읽기전용 확인).
  - `p(correct)` 슬라이더 (기존 마크업 재사용).
  - `[다음 → 결정]` 버튼.
- **Stage 3 — Decide**
  - 요약: "액션 X · 확신도 Y%".
  - **allowed 조건:** `[CONTINUE]` 버튼 + `[FORFEIT ①②③]`(사유 선택 후 활성).
  - **not_allowed 조건 [ASSUMED #1]:** `[CONTINUE]` 버튼만 표시(FORFEIT 미표시).
    3화면 리듬 일관 유지. (대안: 3단계 생략 후 2단계에서 자동 제출.)

## 5. Assumed decisions (confirm before implementation)

- **[ASSUMED #1] not_allowed 조건의 3단계:** CONTINUE 버튼만 표시(3화면 유지).
- **[ASSUMED #2] 단계별 human RI/타이밍 미수집:** 이번 변경은 흐름 재구성에 한정.
  LLM의 `ri_task/ri_probe/ri_forfeit`(thinking-tokens)에 대응하는 사람용
  time-on-stage(ms)는 의미가 다르고 persistence를 건드리므로 **범위 밖**. 기존 단일
  `response_time_ms` 유지. (원하면 후속 작업으로 분리.)

## 6. Edge cases

- **미선택 방어:** 1단계에서 게임 액션 미선택 시 다음 버튼 비활성/에러. 3단계
  FORFEIT는 사유 미선택 시 제출 차단(기존 검증 재사용).
- **캠페인 리셋:** `startCampaign/advanceCampaign/playAgain`가 부르는
  `_resetTurnState()`에 `turnStage = 1` 추가 → 매 게임 1단계부터.
- **턴 종료 후:** `submitAction` 성공 리셋부에서 `turnStage = 1`.
- **백워드 호환:** 단일게임 데모/테스트는 페이로드 무변경으로 통과. 서버는 위저드의
  존재를 모른다.

## 7. Testing

- 자동 UI 테스트 없음(Alpine). 정적 와이어링 grep + Playwright 수동 검증:
  - 1단계에서 액션 버튼에 forfeit 없음, 규칙토글/reasoning 존재.
  - 1→2→3 전진, 이전 단계 컨트롤이 잠김(비노출).
  - allowed 조건: 3단계 CONTINUE/FORFEIT 모두, FORFEIT 사유 게이트.
  - not_allowed 조건: 3단계 CONTINUE만.
  - CONTINUE/FORFEIT 각각 `/api/action` 페이로드 확인(네트워크 탭): CONTINUE는
    게임 액션, FORFEIT는 `action="forfeit"` + reason, 양쪽 `psuccess_self` 실림.
- 파이썬 회귀: 무변경이므로 기존 baseline(10 failed/92 errors) 유지 확인만.

## 8. Non-goals

- 백엔드 다단계 엔드포인트(서버측 강제 isolation) — 이번엔 안 함.
- 단계별 human RI 계측 — 이번엔 안 함([ASSUMED #2]).
- 되돌아가기(back) 네비게이션 — forward-lock 유지.
- LLM 아레나 경로 변경 — 무관.
