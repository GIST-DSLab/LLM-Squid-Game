# HARD/EXPERT 히든 룰 추측 UI 확장 설계

- **작성일**: 2026-07-08
- **브랜치**: `worktree-signal-game-difficulty-arena`
- **대상**: 웹 아레나 Play 플로우의 히든 룰 추측(rule-inference probe) UI
- **상태**: 설계 확정 (구현 계획 대기)

## 1. 배경 & 문제

웹 아레나 Play 플로우에는 플레이어가 히든 룰을 추측하는 UI가 이미 구현되어 있다.
현재 룰 빌더(`web/index.html:617`)는 **4-칩 인라인 문장** 구조로:

```
If [attribute] is [value] then [action], otherwise [default].
```

`assembledRule` getter(`web/app.js:797-808`)가 이 단일 속성 문법만 조립하여
`probe_answer`로 서버에 전송한다.

### 핵심 결함

이 템플릿에는 **난이도 분기(`x-if`/`x-show`)가 전혀 없어** easy/medium/hard/expert
모두 동일하게 렌더된다. 그러나 백엔드가 생성하는 룰 구조는 난이도마다 다르다
(`src/squid_game/tasks/signal_game/rules.py`):

- **EASY / MEDIUM**: 단일 속성 — 현재 UI로 표현 가능.
- **HARD**: 2속성 논리곱(conjunction) — 두 번째 속성/부분일치 분기를 표현할 칸이 없음.
- **EXPERT**: 2속성 논리곱 + 히스토리 override — 위에 더해 "직전 정답 시" 절도 표현 불가.

라이브 백엔드로 HARD 게임을 생성하면 시스템 프롬프트가 플레이어에게
`If <attr_1> is <val_1> AND <attr_2> is <val_2> then ...` 포맷이라고 안내하지만,
UI는 두 번째 속성 입력 칸조차 제공하지 않는다. 즉 HARD/EXPERT에서 플레이어는
**정답 룰을 구조적으로 표현할 수 없다.**

### 백엔드는 이미 준비되어 있음

서버 채점기 `SignalGameModule.score_probe`(`module.py:739-782`)는 세 문법을 모두 지원한다:

- EASY/MEDIUM: 4슬롯 (`_score_easy_template`)
- HARD: 7슬롯 2속성 논리곱 (`_score_medium_template`)
- EXPERT: 10슬롯 = HARD 7슬롯 + override 3슬롯 (`_score_hard_template`)

따라서 이 작업은 **백엔드 변경 없이 프론트엔드 룰 빌더만 확장**하는 작업이다.

## 2. 목표 / 비목표

### 목표
- HARD 룰 빌더: 2속성 논리곱 + 3분기(둘 다/하나만/기본)를 인라인 문장으로 표현.
- EXPERT 룰 빌더: HARD 문장 앞에 히스토리 override 칩 절 추가.
- `assembledRule`이 난이도별로 채점기가 요구하는 **정확한 문법 문자열**을 emit.
- 프론트 문자열 ↔ 백엔드 채점기 계약을 회귀 테스트로 고정.

### 비목표 (명시적 제외)
- EASY/MEDIUM UI는 무변경.
- 백엔드(`score_probe`, 룰 생성, 프롬프트) 변경 없음.
- 아레나의 `num_few_shot=1` 고정으로 HARD가 예시 1개만 노출하는 이슈는 별개 — 다루지 않음.

## 3. 채점기가 요구하는 문법 (계약)

프론트가 조립해야 할 정확한 문자열. 채점기는 소문자 정규화 + 관사 제거 +
구분자에 관대하지만, 아래 형태를 그대로 emit하는 것을 계약으로 고정한다.

**HARD** (`_score_medium_template`, `module.py:850-903`):
```
If <attr_1> is <val_1> and <attr_2> is <val_2> then <action_both>; if only <attr_1> is <val_1> then <action_partial>; otherwise <default>.
```

**EXPERT** (`_score_hard_template`, `module.py:905-944`):
```
If your previous action was correct then <override>; otherwise follow this rule: If <attr_1> is <val_1> and <attr_2> is <val_2> then <action_both>; if only <attr_1> is <val_1> then <action_partial>; otherwise <default>.
```

## 4. 상태 모델

기존 4개 flat var를 재사용하고 신규 3개만 추가한다(최소 변경 원칙). EASY 경로 무변경.

| 슬롯 | EASY/MEDIUM | HARD | EXPERT | 신규 |
|---|:-:|:-:|:-:|:-:|
| `probeAttr` / `probeValue` | attr · val | attr_1 · val_1 | attr_1 · val_1 | |
| `probeAttr2` / `probeValue2` | — | attr_2 · val_2 | attr_2 · val_2 | ✓ |
| `probeAction` | action | action_both | action_both | |
| `probeActionPartial` | — | 하나만 맞음 행동 | 동일 | ✓ |
| `probeDefault` | default | default | default | |
| `probeOverride` | — | — | 직전 정답 시 행동 | ✓ |

- `difficulty`와 `probe*`는 동일한 `Alpine.data` 컴포넌트 스코프(`app.js:707~`)에
  있어 템플릿에서 `x-if="difficulty==='hard'"` 분기가 가능하다.
- 턴 간 유지(`app.js:1083-1084` 인근), 게임 시작 리셋, 체크포인트 복원(`app.js:1185`)
  로직에 신규 var 3개를 동일하게 편입한다.

## 5. 렌더링 / UX (인라인 문장 확장)

기존 4-칩 문장 템플릿을 `x-if` 3분기로 감싼다.

**EASY/MEDIUM** — 현행 유지.

**HARD**:
```
If [attr_1] is [val_1] and [attr_2] is [val_2] then [action_both];
if only [attr_1] is [val_1] then [action_partial]; otherwise [default].
```
- `attr_1`/`attr_2`는 서로 다른 속성만 선택 가능(백엔드 룰은 항상 distinct pair).
  `attr_2` 팝오버에서 이미 고른 `attr_1` 속성을 비활성.
- "if only [attr_1] is [val_1]" 구절의 attr_1·val_1은 **읽기 전용 복제 표시**
  (재입력 없음) → 체감 슬롯 수 감소.
- `valueOptions2` getter 추가(attr_2용). 기존 `attrValues` / `valueChipHTML` /
  `attrEmoji` / `actionEmoji` / `actionLabel` 헬퍼 재사용.

**EXPERT** — HARD 문장 앞에 override 칩 한 줄:
```
If your previous action was correct then [override];
otherwise follow this rule: ⟨위 HARD 문장⟩
```

**게이트**: `assembledRule`은 난이도별 전 슬롯 충족 시에만 문자열을 반환하고,
미충족이면 `""`를 반환하여 다음 단계(p_success) 진입을 차단한다(현행 gate 유지).
rule-gate-hint 안내 문구도 난이도별로 분기.

## 6. `assembledRule` 재작성

getter를 난이도 분기로 재작성한다:

- EASY/MEDIUM: 현행 문자열 유지.
- HARD: 3절 미충족 시 `""`, 충족 시 §3 HARD 문자열.
- EXPERT: override 포함 전 슬롯 미충족 시 `""`, 충족 시 §3 EXPERT 문자열.

## 7. 테스트 전략

### 7.1 계약 회귀 테스트 (핵심)
프론트 문자열과 백엔드 채점기가 어긋나면 조용히 0점이 되므로, Python 단위 테스트로
계약을 고정한다:
- 알려진 seed로 HARD/EXPERT 룰을 생성하고, "프론트가 조립할 문자열"을 테스트에
  **상수로 박아** `score_probe`에 주입 → **100점** 확인.
- 문자열 포맷 상수를 테스트에 명시하여 드리프트를 감지.
- 위치: `tests/unit/` (예: `test_signal_game_probe_contract.py`).

### 7.2 E2E 수동 검증
띄워둔 localhost(백엔드 8502 / 정적 8600)에서 Playwright로:
- HARD 게임 → 빌더로 정답 룰 조립 → 제출 → `rule_match_score=100` 확인.
- EXPERT 게임 → override 포함 정답 룰 조립 → 제출 → `rule_match_score=100` 확인.
- EASY 회귀 → 기존 4-칩 흐름 무변경 확인.

## 8. 영향 파일

- `web/index.html` — 룰 빌더 템플릿 `x-if` 3분기.
- `web/app.js` — 신규 state var 3개, `assembledRule` 난이도 분기, `valueOptions2`,
  리셋/유지/체크포인트 로직, gate 힌트.
- `tests/unit/test_signal_game_probe_contract.py` (신규) — 계약 회귀 테스트.

백엔드(`src/squid_game/**`, `interface/**`) 변경 없음.
