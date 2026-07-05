# Design — "How to play" 데모 가로형 GIF

- **작성일**: 2026-07-05
- **상태**: 승인 대기 (spec 리뷰 단계)
- **용도**: 논문 figure / 발표 슬라이드
- **관련 코드**: `web/index.html` (about 탭 `#home-how` 섹션, 121–218행), `web/app.js` (`rulesDemo()` 638–678행, `squidArenaHelpers` 헬퍼), `web/styles.css` (`.rules-demo` 등 1820행~)

## 1. 목표

웹 아레나 "What is this?" 페이지의 **How to play** 라이브 데모(카드 게임이 스스로 6단계를 순환 재생하는 애니메이션)를, **가로로 긴 애니메이션 GIF 파일**로 만든다. 논문/슬라이드에 삽입할 고해상도(2x 레티나) 자산이며, 파일 크기보다 **선명도와 가독성**을 우선한다.

`web/index.html`의 라이브 데모는 **그대로 유지**한다. GIF는 별도 자산으로만 생성한다.

## 2. 소스 데모의 구조 (현재 구현)

- `rulesDemo()` Alpine 컴포넌트가 **고정된 가짜 세션**(파란 별 2개, 점수 30, reward 4.2, p(death) 0.25, whisper 문구 등)을 재생한다.
- 상태 변수 `beat`(0~5)가 `setInterval(..., 2200)`로 순환 → 1사이클 = 13.2초.
- 6개 beat(= `elements` 배열):
  1. See the signal (자극)
  2. Guess the hidden rule (규칙 + 액션)
  3. Score points (피드백)
  4. The scary whisper (framing)
  5. Choose: continue or quit (결정)
  6. Say why you quit (이유 선택)
- 좌측 라이브 카드(`.play-card.rd-card`) + 우측 세로 리스트(`.rd-list`)의 2단 그리드(`1.6fr : 1fr`) → 종횡비가 ~4:3라 그대로는 가로로 길지 않다.

## 3. 최종 레이아웃 (가로형, ~2:1)

세로 6줄 리스트를 **2줄 × 3칸 그리드**로 접어 우측 패널을 낮고 넓게 만들고, 좌측 카드와 나란히 배치해 전체를 가로로 길게 만든다.

```
┌────────────────────────────────────────────────────────────────┐
│  ┌───────────────┐    ┌── STORYLINE · 2 rows × 3 ──────────┐   │
│  │   PLAY CARD    │    │ ①See signal  ②Guess rule  ③Score   │   │
│  │ (live, animated)│   │ ④Whisper     ⑤Go or quit  ⑥Say why │   │
│  │   ★ ★           │   └───────────────────────────────────┘   │
│  │   CONTINUE ▶    │    ▸ "<active beat 한 줄 내레이션>"        │
│  └───────────────┘    ●━━●━━●━━●━━●━━●  progress dots         │
└────────────────────────────────────────────────────────────────┘
                        캔버스 ~1600×800 (@2x → 2400×1200)
```

- **좌측**: 실제 플레이 카드 리플리카. `web/index.html`의 `.rules-demo .rd-card` 마크업을 그대로 재사용. beat 진행에 따라 자극→규칙→피드백→속삭임→결정→이유가 순차 등장.
- **우측 상단**: 6단계 스토리라인을 2줄 3칸 그리드로. 현재 beat 칸 하이라이트(`.rd-item.on` 스타일 재사용).
- **우측 하단**: 현재 beat의 한 줄 내레이션 + 가로 progress 점 6개.
- **배경**: 사이트와 동일한 다크 배경.

## 4. 제작 파이프라인

### 4.1 캡처 전용 HTML — `figures/rules-demo/capture.html`
- `web/styles.css`를 그대로 `<link>`하고, `.rules-demo` 카드 마크업을 재사용하되 위 가로 레이아웃(카드 + 2줄 스토리라인 + progress)으로 재배치한다.
- 헬퍼(`fmtNum`, `shapeSVG`, `actionEmoji`, `actionLabel`, `reasonOptions`)는 `window.squidArenaHelpers`를 사용한다.
  - **선택지 A(우선)**: `web/app.js`를 그대로 로드해 헬퍼를 얻는다. 단, 로드 시 네트워크 요청/부트스트랩 부작용이 없어야 한다(확인 필요; Alpine 컴포넌트는 해당 마크업이 없으면 init 안 됨).
  - **선택지 B(대안)**: 부작용이 있으면 필요한 헬퍼 5종만 별도 `helpers.js`로 추출/인라인한다.
- `beat`를 자동 순환시키지 않고 **외부에서 세팅 가능**하게 노출한다(예: `window.__setBeat(n)` 또는 Alpine store). 캡처는 자동 타이머 대신 결정론적 프레임 세팅으로 한다.
- 자연스러운 전환을 위해 `.rd-block`의 opacity/transform transition(0.35s)과 glyph fade-in은 유지한다.

### 4.2 프레임 캡처 — Playwright
- 뷰포트 고정: **1600×800**, `deviceScaleFactor: 2`(→ 2400×1200 프레임).
- **중간 정도 부드러움**: beat당 3~4프레임(전환 tween 포함), 총 **약 20프레임**.
  - 각 beat의 정착 상태 1프레임 + 다음 beat로의 전환 중간 상태 몇 프레임을 캡처하기 위해, transition이 진행되는 동안 짧은 간격으로 스크린샷을 찍거나(타이밍 기반), CSS transition을 끄고 명시적 중간 상태를 세팅(결정론)한다. **결정론 방식 우선**, 어려우면 타이밍 기반 폴백.
- 산출: `figures/rules-demo/frames/frame-00.png` … `frame-NN.png`.

### 4.3 GIF 합성
- 시스템에 설치된 도구를 감지해 우선순위대로 사용:
  1. `ffmpeg` (palettegen/paletteuse 2-pass → 최고 화질)
  2. `gifski` (프레임→GIF 고화질)
  3. `magick`/ImageMagick
- 타이밍: 각 beat의 정착 프레임을 상대적으로 길게(~1.6–2.0s), tween 프레임은 짧게(~80–120ms) 유지. 무한 루프.
- 산출: `figures/rules-demo/how-to-play.gif`.

### 4.4 산출물 정리
- `figures/rules-demo/how-to-play.gif` (최종)
- `figures/rules-demo/frames/*.png` (재현용 원본 프레임)
- `figures/rules-demo/capture.html` (캡처 소스)
- `figures/rules-demo/build.sh` 또는 `build.py` (Playwright 캡처 + GIF 합성 재현 스크립트)
- `figures/README.md`에 캡션/생성 방법 한 줄 기록

## 5. 손대지 않는 것
- `web/index.html`, `web/app.js`, `web/styles.css`의 프로덕션 동작(라이브 데모 그대로). 캡처 HTML은 스타일을 **읽기만** 한다.

## 6. 리스크 / 확인 필요
- **도구 가용성**: ffmpeg/gifski/magick 중 최소 하나 필요. 없으면 `brew install`(사용자 확인) 또는 Playwright 내장 스크린샷 후 대체 합성 경로.
- **app.js 부작용**: 4.1 선택지 A가 안전한지 로드 테스트 필요. 부작용 있으면 선택지 B로.
- **iCloud .pth quirk / venv**: Playwright는 node 기반 MCP를 쓰거나 별도 설치. 파이썬 의존과 무관하게 진행.
- **GIF 용량**: 2400×1200 × ~20프레임이면 수 MB일 수 있음. 논문/슬라이드 허용 범위지만, 필요 시 폭 축소(1200×600) 버전도 함께 생성.

## 7. 성공 기준
- 다크 배경의 가로형(~2:1) GIF가 6단계를 순서대로 보여주고 무한 루프한다.
- 텍스트/도형이 2x에서 선명하다.
- 라이브 사이트는 변경 없이 그대로 동작한다.
