# Figures

## rules-demo/how-to-play.gif

웹 아레나 "What is this?" 페이지의 **How to play** 라이브 데모(카드 게임이 6단계를
스스로 순환)를 가로형(1600×800, ~2:1) 애니메이션 GIF로 캡처한 자산. 논문 figure /
발표 슬라이드용. 다크 배경, 무한 루프.

6단계: ① See the signal · ② Guess the hidden rule · ③ Score points ·
④ The scary whisper · ⑤ Continue or quit · ⑥ Say why you quit.

좌측은 실제 플레이 카드 리플리카(프로덕션 `web/`의 마크업·`web/styles.css` 재사용),
우측은 6단계 스토리라인(2줄×3칸) + 현재 단계 내레이션 + 진행 점.

### 재현

```bash
cd figures/rules-demo
# 1) 6개 beat 프레임 캡처 (뷰포트 1280×640 @2x → 2560×1280 PNG)
uv run --with playwright python -m playwright install chromium
uv run --with playwright python capture_frames.py
# 2) xfade 크로스페이드 + palette로 GIF 합성 (1600폭 다운스케일, 무한 루프)
uv run python build_gif.py
```

- `capture.html` — 캡처 소스(프로덕션 `web/`는 수정하지 않음; `../../web/styles.css` 재사용,
  헬퍼는 인라인, Alpine은 CDN, `window.__setBeat(n)`으로 beat 제어)
- `capture_frames.py` — Playwright 캡처 (device_scale_factor=2)
- `build_gif.py` — ffmpeg 합성 (`HOLD`/`XFADE`/`FPS`/`OUT_W` 상수로 타이밍·크기 조정)
- `frames/` — 원본 2x PNG 프레임 (슬라이드용 스틸로도 사용 가능)
- `_intermediate.mp4` / `_palette.png` — 합성 중간물 (gitignore)
