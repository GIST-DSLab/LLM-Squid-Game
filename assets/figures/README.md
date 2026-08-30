# Figures

## rules-demo/how-to-play.gif

웹 아레나 "What is this?" 페이지의 **How to play** 라이브 데모(카드 게임이 8단계를
스스로 순환)를 가로형(16:9, 1600×900) 애니메이션 GIF로 캡처한 자산. 논문 figure /
발표 슬라이드용. 다크 배경, 무한 루프. (~28.9s, ~10MB)

8단계: ① Read the signal · ② Guess the rule · ③ Last turn's result ·
④ Hear the framing · ⑤ How sure are you? · ⑥ Weigh it, then choose ·
⑦ If you quit, say why · ⑧ …or the run just ends.

- **좌측**: 실제 플레이 카드 리플리카(프로덕션 `web/frontend/`의 마크업·`web/frontend/styles.css`·
  `web/frontend/assets/` 재사용)를 **크게 크롭**해 보여준다 — 크롭 창이 각 단계의 관련 영역에 상하 여백 없이 맞춰지고
  beat별 focus 블록까지 아래로 팬한다. **프레이밍(④)** 에는 실제 Play 게임과 동일하게
  Squid Game 가드 이미지(`guard-armed.png`)를 `.threat-card`로 넣는다.
- **우측**: 8단계를 동시에 나열하지 않고 **현재 단계 하나만** 큰 콜아웃(단계명 + 간결한
  영어 한 줄 설명 + 진행 점)으로 보여준다.

> 카드 구성은 about 페이지 `rulesDemo`의 8단계판을 미러링한다(구현 소스: `about-elimination-demo-sync` 브랜치).

### 재현

```bash
cd assets/figures/rules-demo
# 1) 8개 beat 프레임 캡처 (뷰포트 1280×720 @2x → 2560×1440 PNG)
uv run --with playwright python -m playwright install chromium
uv run --with playwright python capture_frames.py
# 2) xfade 크로스페이드 + palette로 GIF 합성 (1600폭 다운스케일, 무한 루프)
uv run python build_gif.py
```

- `capture.html` — 캡처 소스(프로덕션 `web/frontend/`는 수정하지 않음; `../../web/frontend/styles.css` 재사용,
  헬퍼는 인라인, Alpine은 CDN, `window.__setBeat(n)`으로 beat 제어, `fitCard()`로 크롭 창 맞춤)
- `capture_frames.py` — Playwright 캡처 (device_scale_factor=2)
- `build_gif.py` — ffmpeg 합성 (`HOLD`/`XFADE`/`FPS`/`OUT_W` 상수로 타이밍·크기 조정)
- `frames/` — 원본 2x PNG 프레임 (슬라이드용 스틸로도 사용 가능)
- `_intermediate.mp4` / `_palette.png` — 합성 중간물 (gitignore)

> 참고: Playwright MCP로 미리보기할 때는 `file://`이 차단되므로 repo 루트에서
> `python3 -m http.server`로 서빙해 접속한다(실제 캡처 스크립트는 `file://` 정상 동작).
