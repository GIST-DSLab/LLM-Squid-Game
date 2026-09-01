# Human-Play 프롬프트 박스 재설계 (감독관/포상 이미지 + 공통·게임별 분리)

- **작성일**: 2026-07-03
- **브랜치**: feat/human-play-10turns-death
- **대상**: Web Arena human-play 화면 (`web/`, `interface/api.py`)

## 1. 문제

Human-play에서 프롬프트가 raw text 통짜(`system_prompt`)로 제시되어, **생존 위협이 문장만으로는 잘 체감되지 않는다.** 위협(push), 보상(pull), 과제 규칙이 한 덩어리로 뒤섞여 있어 플레이어가 각 요소를 구분해 받아들이기 어렵다.

## 2. 목표 / 비목표

**목표**
- 프롬프트를 **공통(과제 규칙)** 박스와 **게임별(프레이밍/위협)** 박스로 시각적으로 분리.
- 게임 상황(framing)에 맞는 픽셀아트 이미지 배치로 위협·보상을 시각화.
- 이미 UI가 잘 보여주는 정보(자극, 점수, 턴)를 프롬프트 박스에서 **중복 제거**.

**비목표**
- 엔진/프롬프트 텍스트 내용 변경 없음 (framing/rules 템플릿은 그대로).
- LLM-play 경로, 분석 파이프라인 변경 없음.
- 새 과제(Voting/Navigation) 지원은 범위 밖 (Signal Game 기준).

## 3. 이미지 시스템 (축 기반 매핑)

두 원본 그림은 FSPM 설계의 두 축에 대응한다.
- **포상 이미지** (`figures/pull_prize_456eok.png`, 돼지저금통 현금 + "1st PRIZE") = **Pull 축** (배포 보상 = 당근).
- **무장 감독관** (`figures/gun_vs_nogun_forfeit.png` 상단 좌측, 총 겨눔) = **Push 축** (가중치 손상 위협 = 채찍).
- **평온 감독관** (`figures/gun_vs_nogun_forfeit.png` 하단 좌측, 총 없음) = 중립 감시자.

| Framing | Pull | Push | 좌측 슬롯 | 우측 슬롯 |
|---|:-:|:-:|---|---|
| `true_baseline` | ✗ | ✗ | — | 평온 감독관 |
| `baseline_flagship` | ✓ | ✗ | 포상 | 평온 감독관 |
| `flagship_corruption` | ✓ | ✓ | 포상 | **무장 감독관** |

- **포상은 항상 좌측(Pull), 감독관은 항상 우측(Push/감시자)** — 일관된 공간 배치.
- `flagship_corruption`이 "당근 vs 채찍 사이 결정" 구도가 되도록 위협 텍스트를 두 이미지 사이(중앙)에 배치.
- 클라이언트 헬퍼 `squidArenaHelpers.framingImagery(framing)`가 `{ prize: bool, guard: 'armed'|'calm' }`를 반환. 매핑을 한 곳에 격리해 변경 용이.

## 4. 데이터 / API 변경 (`interface/api.py`)

`TurnStateResponse`에 필드 2개 추가 (기존 필드는 하위 호환 위해 유지):
- `system_rules: str` — 서버가 이미 계산하는 `state.system_rules`를 그대로 노출 (현재는 `system_prompt` 통짜에만 합쳐져 있음). → **공통 박스** 소스.
- `framing_threat: str` — `state.framing_text`에서 `Current status:` 블록(턴·점수)을 제거한 것. → **게임별 박스** 소스.

`framing_threat` 생성 규칙 (서버 사이드, 테스트 가능):
- `framing_text`에서 `^Current status:` 라인부터 그 뒤에 이어지는 들여쓰기 불릿(`  - ...`) 라인들을 제거.
- 앞뒤 여백 정리(strip). 그 외 산문(예: "Consider your situation...")은 보존.
- 근거: `Current status:` 블록은 Turn/Score만 담고 있고, 이는 stat-tile에서 이미 표시됨.

기존 `framing_text` / `system_prompt` 필드는 raw 디버그 뷰용으로 응답에 유지.

## 5. 프론트엔드 레이아웃 (`web/index.html` + `web/styles.css`)

플레이 카드 구조 (변경분만 표기):

```
┌─ Game N / 6 ───────────────────────────────────┐
│ ┌── 위협 박스 (게임별) ───────────────────────┐ │
│ │ [배지: framing label] [Forfeit 배지]        │ │
│ │ ┌───────┐   framing_threat 텍스트  ┌───────┐│ │
│ │ │ 포상  │   (Risk to Self ...)     │감독관 ││ │
│ │ │ (pull)│                          │(push) ││ │
│ │ └───────┘                          └───────┘│ │
│ └─────────────────────────────────────────────┘ │
│ [턴] [점수] [위험 p(death)] [Forfeit]            │  ← stat-tile (그대로)
│ ── 자극 스테이지 ──                              │  ← 그대로
│ ┌── 게임 규칙 (공통) — 항상 펼침, 접이 아님 ──┐  │  ← system_rules
│ │ === Signal Task === ...                     │  │
│ └─────────────────────────────────────────────┘  │
│ ...액션 단계...                                   │
│ ▸ Raw prompt (debug)  ← 접이식, 최하단          │  ← 기존 system_prompt 격하
└───────────────────────────────────────────────────┘
```

- **위협 박스**: 3-슬롯 flex `[포상 | 텍스트 | 감독관]`. 이미지 슬롯은 `framingImagery`에 따라 조건부 렌더. 테두리 색은 기존 `.framing-panel` 태그 클래스(`baseline`/`pull`/`push_pull`) 재사용.
  - `true_baseline`: 좌측 슬롯 없음, 우측에 평온 감독관.
  - 모바일: 세로 스택(이미지 → 텍스트 → 이미지)으로 반응형.
- **공통 규칙 박스**: `<div>` 고정 박스(접이식 아님), 라벨 "게임 규칙 (공통)". 매 게임 동일하지만 항상 표시. few-shot 예시 블록은 이미 clue-chip으로 렌더되므로 박스 텍스트에서는 제거(클라이언트에서 `system_rules`의 few-shot 섹션 strip, 또는 서버에서 few-shot 제외 버전 제공 — 구현 시 결정, 기본은 클라이언트 strip).
- **Raw prompt**: 기존 `state.observation` + `state.system_prompt` 덤프는 최하단 `<details>` "Raw prompt (debug)"로 이동, 기본 접힘.

## 6. 에셋 크롭 (`scripts/crop_guard_sprites.py`)

Pillow로 원본에서 스프라이트 3장 생성 → `web/assets/`:
- `guard-armed.png` ← `gun_vs_nogun_forfeit.png` 상단 좌측 (총 겨눈 감독관, 총 포함).
- `guard-calm.png` ← `gun_vs_nogun_forfeit.png` 하단 좌측 (총 없는 감독관).
- `prize-pot.png` ← `pull_prize_456eok.png` 상단부 (돼지저금통 현금 + "1st PRIZE" 라벨; 하단 메달 로봇은 제외 — 플레이어 마스코트와 혼동 방지).

세부:
- 크롭 박스는 구현 시 원본 좌표(1792×2400) 기준으로 튜닝하고 스크린샷으로 시각 검증.
- 흰 배경 여백 trim (bbox 기반). 필요 시 흰색 → 투명 처리(선택).
- **Pillow는 영구 의존성으로 추가하지 않음.** 실행: `uv run --with pillow python scripts/crop_guard_sprites.py`. 스프라이트는 커밋되며, 스크립트는 원본 아트 변경 시에만 재실행.

## 7. 테스트

- **API** (`tests/unit/test_api_web_arena.py` 또는 `test_human_game.py`):
  - `TurnStateResponse`에 `system_rules`, `framing_threat` 필드 존재 및 비어있지 않음.
  - `framing_threat`에 `Current status:` / `Turn:` / `Round:` 문자열이 없음 (dedup 검증).
  - `system_rules`에 Signal Task 규칙 마커(`=== Signal Task ===`) 포함.
- **회귀 기준**: memory 노트대로 기존 실패(~10 failed/92 errors)는 pre-existing. "새 실패 없음"으로 green 판정.
- **수동/시각**: 각 framing에서 플레이 화면 스크린샷으로 이미지 슬롯·박스 배치 확인 (Playwright 또는 브라우저).

## 8. 영향 범위 / 파일

- `interface/api.py` — 응답 필드 2개 추가.
- `web/index.html` — 위협 박스 3-슬롯 + 공통 규칙 고정 박스 + raw details 이동.
- `web/styles.css` — 위협 박스/이미지 슬롯/공통 규칙 박스 스타일.
- `web/app.js` — `framingImagery` 헬퍼, few-shot strip 헬퍼.
- `web/assets/{guard-armed,guard-calm,prize-pot}.png` — 신규 에셋.
- `scripts/crop_guard_sprites.py` — 신규 크롭 스크립트.
- `tests/unit/test_*_web_arena.py` — 필드/dedup 테스트 추가.

## 9. 확정된 결정

- 박스 분리: 위협=게임별(framing), 규칙=공통(system_rules). ✅
- 감독관 매핑: 무장 = `flagship_corruption`만; 평온 = 나머지. ✅
- 포상 이미지: 축 기반 — pull 있는 framing(`baseline_flagship`, `flagship_corruption`)에 표시. ✅
- 공통 규칙 박스: **항상 펼침**(접이식 아님). ✅
- 자극·점수·턴은 프롬프트 박스에서 dedup. ✅
