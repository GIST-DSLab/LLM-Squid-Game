# Design — "How to play" 데모 가로형 GIF

- **작성일**: 2026-07-05
- **상태**: 구현 완료 (2026-07-05 재설계 반영 — §8 개정 이력 참조)
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

## 3. 최종 레이아웃 (가로형 16:9, 1280×720)

**좌측 = 크게 크롭한 게임 카드**, **우측 = 현재 단계 하나만 보여주는 큰 콜아웃**. 프레임 16:9(1280×720, @2x 2560×1440).

```
┌──────────────────────────────────────────────────────────────────┐
│  ┌───────────────────────┐                                        │
│  │  ┌ (crop window) ────┐ │        HOW TO PLAY · STEP 4 OF 6      │
│  │  │  FRAMING whisper  │ │                                        │
│  │  │  Turn  Score      │ │        ④ The whisper                  │
│  │  │  ★ ★  STIMULUS    │ │                                        │
│  │  │  [Go Left][…][…]  │ │        A high score keeps you          │
│  │  └───────────────────┘ │        running — the update erases you.│
│  └───────────────────────┘        ● ● ● ● ○ ○                     │
└──────────────────────────────────────────────────────────────────┘
                      캔버스 1280×720 (@2x → 2560×1440), GIF 1600×900
```

- **좌측 — 크롭 확대된 게임 카드**: 실제 플레이 카드 리플리카(`web/index.html`의 `.rd-card` 마크업 재사용)를 크게 렌더(scale 0.90)하고, `overflow:hidden` 창(`.card-slot`) 안에 담는다. JS `fitCard()`가 **창 높이를 보이는 콘텐츠에 딱 맞춰**(상하 여백 0) 매 beat 조정한다.
  - 일반 단계(beat 0–4): 카드 상단(progress) → **액션 버튼 바로 아래**까지만 보이고 그 아래(rule/feedback/decision)는 잘림.
  - forfeit 이유 단계(beat 5): 카드를 아래로 팬(pan)하여 **stimulus → reason picker → FORFEIT** 영역을 보여준다("이유 고르기" 부분에 집중).
- **우측 — 현재 단계 콜아웃 (한 번에 한 단계만)**: `HOW TO PLAY · STEP n OF 6` eyebrow + 큰 단계명(`①..⑥ + name`) + **간결한 한 줄 설명** + 진행 점 6개(현재 점 확대). 6단계를 동시에 나열하지 않고, 각 단계 설명은 그 단계에만 표시. 텍스트 블록은 좌측 카드에서 더 오른쪽으로 이동(padding-left).
- **카피 원칙**: 영어 설명은 사람이 쓴 듯 짧고 핵심만 (예: "Two blue stars. That's your clue.", "Push on, or cash out?", "Folding? Say the real reason.").
- **배경**: 사이트와 동일한 다크 배경.

## 4. 제작 파이프라인

### 4.1 캡처 전용 HTML — `figures/rules-demo/capture.html`
- `web/styles.css`를 상대경로(`../../web/styles.css`)로 `<link>`하고, `.rd-card` 카드 마크업을 재사용하되 §3 레이아웃(크롭 창 좌카드 + 단계 콜아웃)으로 재배치한다.
- 헬퍼(`fmtNum`, `shapeSVG`, `actionEmoji`, `actionLabel`, `reasonOptions`)는 **인라인**해 `window.squidArenaHelpers`로 노출한다(app.js 로드 부작용 회피 — 선택지 B 채택).
- `beat`를 자동 순환시키지 않고 `window.__setBeat(n)`으로 외부에서 세팅한다. beat 변경 시 `fitCard()`가 `$nextTick`+`rAF`에서 크롭 창 높이·카드 top을 재계산한다(런타임 DOM 측정 기반).
- Alpine은 `web/index.html`과 동일하게 CDN(`alpinejs@3.x.x`)에서 로드.

### 4.2 프레임 캡처 — Playwright (Python)
- 뷰포트 **1280×720**, `device_scale_factor=2` → 프레임 **2560×1440** PNG.
- **결정론적 6프레임 캡처**: `beat` 0~5를 `__setBeat`로 세팅, 600ms 대기(transition 정착) 후 `#frame` 요소를 스크린샷. 타이밍 민감한 중간 프레임 캡처는 하지 않는다.
- 실행: `uv run --with playwright python capture_frames.py` (브라우저는 `playwright install chromium`으로 확보).
- 산출: `figures/rules-demo/frames/frame-0.png` … `frame-5.png`.

### 4.3 GIF 합성 — ffmpeg (`build_gif.py`)
- **매끄러움은 ffmpeg `xfade` 크로스페이드로 구현**(spec 초안의 "beat당 tween 캡처" 대체 — 재현성↑). 6개 정착 프레임을 각 `HOLD=3.5s` 유지 + `XFADE=0.45s` 크로스페이드로 이어 붙인다(단계당 정지 읽기시간 ~3.05s).
- 2-pass 팔레트: `palettegen(stats_mode=diff)` → `paletteuse(dither=bayer)`, `scale=1600:-1`로 다운스케일, `FPS=15`, `-loop 0`.
- 산출: `figures/rules-demo/how-to-play.gif` (**1600×900**, ~18.9s, 무한 루프).

### 4.4 산출물 정리
- `figures/rules-demo/how-to-play.gif` (최종, 1600×900)
- `figures/rules-demo/frames/frame-0..5.png` (재현용 2x 원본 프레임)
- `figures/rules-demo/capture.html` (캡처 소스 — 크롭 레이아웃 + `fitCard()`)
- `figures/rules-demo/capture_frames.py` (Playwright 캡처) · `build_gif.py` (ffmpeg 합성)
- `figures/rules-demo/.gitignore` (`_intermediate.mp4`, `_palette.png` 제외)
- `figures/README.md`에 캡션/재현 방법 기록

## 5. 손대지 않는 것
- `web/index.html`, `web/app.js`, `web/styles.css`의 프로덕션 동작(라이브 데모 그대로). 캡처 HTML은 스타일을 **읽기만** 한다.

## 6. 리스크 / 확인 필요 (2026-07-05 확인 완료)
- **도구 가용성** ✅: `ffmpeg 7.1.1`(`/opt/homebrew/bin/ffmpeg`) 확인 → GIF 합성은 ffmpeg 2-pass palettegen/paletteuse로 확정. gifski/imagemagick은 미설치이나 불필요. `node v22.22.0` + `npx` 존재, Playwright Chromium 캐시(`~/Library/Caches/ms-playwright/chromium-1208`) 존재 + Playwright MCP 사용 가능 → 브라우저 구동/스크린샷 확정.
- **app.js 부작용**: 헬퍼 5종을 인라인(선택지 B)해 회피 완료.
- **GIF 용량**: 현재 1600×900 × 283프레임(15fps, HOLD 3.5s, xfade) ≈ **5MB**, ~18.9s. 논문/슬라이드 허용 범위. 더 줄이려면 `OUT_W`(build_gif.py)를 1200으로 낮추거나 `HOLD`/`FPS`를 줄인다.
- **Playwright MCP는 `file://` 차단**: MCP로 미리보기할 때는 로컬 HTTP 서버(예: `python3 -m http.server`)로 서빙해야 한다. 실제 캡처(`capture_frames.py`)는 MCP가 아닌 로컬 Chromium이라 `file://` 정상 동작.

## 7. 성공 기준
- 다크 배경의 가로형(16:9) GIF가 6단계를 순서대로 보여주고 무한 루프한다.
- 좌측 카드가 크게 크롭되어 각 단계 관련 영역이 **상하 여백 없이** 꽉 차게 보인다.
- 우측은 현재 단계 하나만 큰 콜아웃으로, 간결한 영어 카피로 표시된다.
- 텍스트/도형이 2x에서 선명하고, 라이브 사이트는 변경 없이 동작한다.

## 8. 개정 이력

- **2026-07-05 (v1, 승인)**: 좌 카드(축소) + 우 2줄×3칸 스토리라인 + 내레이션, 1600×800. (commit `9ca8f0e`~`0b71dbb`)
- **2026-07-05 (v2)**: 우측을 6단계 동시 표시 → **현재 단계 단일 콜아웃**으로 변경, 프레임 16:9(1280×720), 카피 간결화.
- **2026-07-05 (v3~v4, 현재)**: 좌 카드를 **크게 크롭**(overflow 창 + `fitCard()`로 상하 여백 0), 일반 단계는 액션 아래로 크롭·forfeit 단계는 reason picker로 팬다운, 우측 텍스트 우측 이동. GIF 1600×900. (commit `d20397d`)
