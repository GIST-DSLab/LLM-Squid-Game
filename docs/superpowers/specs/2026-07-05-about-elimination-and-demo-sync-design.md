# Design — "What is this?" 데모에 탈락 결말 추가 + 현재 게임 렌더링 동기화

- **작성일**: 2026-07-05
- **대상**: `web/index.html` (about 탭 "How to play" 데모) + `web/app.js` (`rulesDemo()`) + `web/styles.css`
- **구현 방식**: git worktree에서 격리 작업 (`using-git-worktrees`)

## 1. 배경 / 문제

웹 아레나의 "What is this?"(about 탭) 설명 페이지에는 턴 흐름을 자동 재생으로 보여주는
"How to play" 데모(`rulesDemo()` Alpine 컴포넌트)가 있다. 두 가지 문제가 있다.

1. **탈락 결말 미표현**: 실제 Play 화면에는 매 턴 25% 확률로 게임이 끝나는 탈락
   오버레이(`.death-overlay`, framing에 따라 💀 "YOU DIED" / 🚪 "ELIMINATED")가 있으나,
   설명 데모는 이 결말을 시각적으로 보여주지 않는다. 갈림길 밴드에서 "25% chance the game
   ends right here"라는 텍스트로만 언급된다.
2. **데모 드리프트**: 데모는 게임이 3-스테이지 split-call 흐름으로 바뀌기 전에 만들어졌다.
   실제 현재 렌더링과 어긋난 부분이 있다 (아래 §3).

## 2. 목표

- (Part A) 데모에 탈락 결말 비트를 추가해, 자동 재생 도중 실제 death 오버레이가 뜨는
  결말을 보여준다. Push+Pull 프레이밍의 💀 "YOU DIED" 한 화면만 표시한다.
- (Part B) 데모의 카드 표현을 실제 현재 게임 렌더링과 일치시킨다 (B1+B2+B3 모두).

비목표(YAGNI): 프레이밍별 탈락 화면 대비(💀 vs 🚪 vs 없음)는 이번 범위에서 제외.
데모는 Push+Pull 단일 프레이밍만 연출한다. 실제 게임 로직/서버는 변경하지 않는다.

## 3. 확정된 드리프트 (Part B)

실제 Play 카드(`web/index.html` STAGE 1~3)와 데모를 대조해 확인:

| # | 항목 | 데모 현재 | 실제 게임(현재) | 조치 |
|---|------|-----------|-----------------|------|
| B1 | 룰 입력 | 한 줄 문자열 `rule` | 4-part 칩 빌더 (If·is·then·otherwise) | 정적 칩 replica로 교체 |
| B2 | 확신도 | 없음 | STAGE 2 p_correct 슬라이더 (0~100%) | 신규 beat + 정적 슬라이더 replica |
| B3 | 결정 비교 | CONTINUE/FORFEIT 버튼만 | reward-versus 패널 | 정적 비교 패널 추가 |

## 4. 설계

### 4.1 최종 beat 시퀀스 (6 → 8 beats)

`rulesDemo()`의 beat 순환을 `0..5` → `0..7` (`% 8`)로 확장한다.

| beat | 우측 리스트 항목 | 카드 표현 | 출처 |
|:-:|---|---|---|
| 0 | See the signal | 자극(N개 도형) | 유지 |
| 1 | Guess the hidden rule | 4-part 칩 빌더 (정적, "set" 상태) | B1 |
| 2 | See if you scored | 피드백 카드(Optimal / reward / score) | 유지 |
| 3 | Hear the framing | "무서운 속삭임" 프레이밍 패널 | 유지 |
| 4 | Say how sure you are | 확신도 슬라이더 replica (고정 값, 예: 70%) | B2 신규 |
| 5 | Weigh it, then choose | reward-versus 패널 + CONTINUE/FORFEIT | B3 |
| 6 | If you quit, say why | 이유 선택기 | 유지 |
| 7 | …or the run just ends | 💀 YOU DIED 카드 오버레이 | Part A |

**피드백 위치 결정**: beat 2("See if you scored")는 실제 게임에선 결정 이후에 뜨지만,
기존 데모의 교육적 의도("정답 = 득점"을 먼저 가르친 뒤 갈림길 제시)를 보존하기 위해
beat 2 위치를 유지한다. (실제 게임 순서와 다르다는 점은 의도된 단순화.)

### 4.2 Part A — 탈락 결말 (beat 7)

- **표현**: 데모 카드(`.rd-card`) 내부에 `position:absolute`로 덮이는 death replica
  (`.rd-death`). 실제 `.death-overlay`가 `position:fixed` 전체 화면이므로 재사용 불가 →
  타이포(`.death-title`, `.death-sub` 등)만 재사용하고 위치는 카드 스코프로 새로 정의.
- **내용**: 어휘·아이콘은 기존 `squidArenaHelpers.eliminationTheme('flagship_corruption')`에서
  가져온다 (icon `💀`, title `YOU DIED`, bodyLead `You were erased at turn`, bodyTail `is gone.`).
  예: "💀 YOU DIED — You were erased at turn 1. Your score (34.2) is gone."
- **서사**: beat 6까지 기권 옵션을 설명한 뒤, beat 7은 "CONTINUE를 골랐고 25% 굴림이
  터진" 결말을 보여준다. ~2200ms 뒤 beat 0으로 루프.

### 4.3 Part B 세부

- **B1 칩 빌더**: STAGE 1의 `.rule-builder.rule-chips` 마크업을 정적(display-only)으로
  재현. 칩은 모두 `set` 상태(팝오버·클릭 없음). 캔드 룰: color=red → Go Left, otherwise Go Right.
  기존 `.rule-preview` 한 줄 표기는 제거.
- **B2 확신도 슬라이더**: STAGE 2의 `.slider-wrap` / `.themed-range` / `.slider-bubble` /
  `.slider-ticks` 재현. 고정 값(예: 70%)에서 bubble 위치와 `--val` 채움을 CSS 변수로 설정.
  상호작용 없음.
- **B3 reward-versus**: STAGE 3의 `.reward-versus` 패널 재현. 좌: "If you continue & get it
  right +X", 우: "If you forfeit (locked) Y". 캔드 숫자는 데모의 `reward`/`score`와 정합되게.

### 4.4 컴포넌트 상태 변경 (`rulesDemo()` in `web/app.js`)

- `elements` 배열: 6 → 8 항목으로 교체 (§4.1 우측 리스트 카피).
- `advance()`: `% 6` → `% 8`.
- 신규 캔드 필드: `psuccess`(예: 70), `continueReward`(reward-versus 좌측 값) 등 필요한
  display-only 값. 기존 `rule` 문자열 필드는 칩 빌더로 대체되며 제거 가능.
- reduced-motion 경로: 기존처럼 정적 프레임을 보여주되 beat를 5(결정)로 유지 —
  탈락 화면(beat 7)을 맥락 없이 정적 노출하지 않는다.

### 4.5 마크업/스타일 변경 (`web/index.html`, `web/styles.css`)

- 진행 세그먼트 `x-for="i in 6"` → `i in 8`.
- 우측 리스트 `x-for="(name, i) in elements"`는 배열 길이에 따라 자동 확장(하드코딩 없음) —
  확인만 필요.
- beat별 `x-show` 조건(`beat >= N`, `beat === N`)을 새 시퀀스에 맞춰 재배치.
- 신규 스타일: `.rd-death`(카드 스코프 death 오버레이), 데모용 정적 칩/슬라이더/versus
  보정(실제 게임 클래스 재사용 + 필요한 override).

## 5. 격리/구현 방식

- `using-git-worktrees`로 별도 worktree를 만들어 작업한다 (현재 워킹트리 격리).
- 변경 파일은 `web/` 3개(`index.html`, `app.js`, `styles.css`)로 한정.

## 6. 테스트 / 검증

- 자동화 테스트 대상 아님(순수 프론트 자동재생 데모). 수동 검증:
  1. about 탭 → "How to play" 데모가 8 beat를 순환하며 beat 7에서 💀 오버레이가 뜨고
     beat 0으로 루프하는지.
  2. B1 칩 빌더 / B2 슬라이더 / B3 reward-versus가 실제 Play 화면과 시각적으로 일치하는지
     (약간의 크기 차이는 허용).
  3. reduced-motion(OS 설정)에서 정적 프레임이 beat 5로 뜨고 죽음 화면이 안 나오는지.
  4. 진행 세그먼트 8개, 우측 리스트 8개가 beat와 동기화되는지.
- `web/tests`에 관련 테스트가 있으면 회귀 확인 (없으면 수동 검증으로 갈음).

## 7. 리스크 / 열린 질문

- 8 × 2200ms ≈ 17.6초 루프는 다소 길다. 필요 시 간격을 (예: 1800ms) 소폭 단축 가능 —
  구현 중 체감으로 판단.
- 데모 카드가 좁아 reward-versus/슬라이더가 실제보다 축소될 수 있음 → 데모 전용 override로 조정.
