# 보관: 서버에서 엔진을 재생하던 Durable Object 판 (Phase 2, c5fcc8c1)

배포하지 않는다. Workers 무료 플랜의 요청당 CPU 10 ms로는 엔진(퍼즐 생성, 재생)이 돌지 않아 유료 플랜이 필요했고, 연구자는
엔진을 브라우저로 옮기기로 했다(`docs/history/plans/2026-10-18-browser-engine.md`).

- `room_do.py`: 그때의 `src/entry.py`(방 = Durable Object 하나, 알람으로 모델 호출). 지금 이 파일이 import하던
  `replay.py` · `compat.py` · `modelcalls.py` · `ollama_fetch.py` · `settings.py`(→ `room_settings.py`) · `stub_transport.py`는
  `web/pyodide/`로 옮겨 브라우저와 오프라인 검증기가 쓴다(키 대신 게임 토큰을 받도록 조금 바뀜). 그래서 이 파일은 그대로는
  돌지 않는다.
- `vendor.py`: 엔진을 Worker 번들로 복사하던 스크립트. 지금 Worker는 엔진을 싣지 않는다(브라우저 번들은
  `web/pyodide/build_bundle.py`).
- `smoke_dev_room_do.py`: 그 판의 HTTP 스모크.

다시 쓰려면(여러 사람 방의 중계 등) 커밋 c5fcc8c1에서 `web/cloudflare/`를 통째로 보는 것이 빠르다.
