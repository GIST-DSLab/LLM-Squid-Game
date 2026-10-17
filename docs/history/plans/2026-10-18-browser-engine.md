# 2026-10-18 아레나 엔진을 브라우저로 (Pyodide) — Cloudflare는 무료 플랜의 얇은 Worker만

이전 단계(`2026-10-17-cloudflare-migration.md`)는 방마다 Durable Object가 엔진을 서버에서 재생했다. Workers 무료 플랜의
요청당 CPU 10 ms로는 그 재생(퍼즐 생성 1–8 s)이 돌지 않아 유료 플랜이 필요했다. 연구자 결정: **엔진을 방문자의
브라우저에서 돌리고**, Cloudflare는 무료 플랜에 맞는 얇은 Worker만 둔다.

## 1. 결론 한 줄씩

- 엔진은 하나: 저장소의 `squid5/`와 `web/server/{engine,signal}.py`를 그대로 묶어(`web/pyodide/build_bundle.py`, 121 KiB
  zip, 이름에 내용 해시) 브라우저의 Web Worker에서 Pyodide 314.0.7(Python 3.14)로 import한다. JS로 다시 쓴 게임은 없다.
- 방은 Phase 2의 `replay.ReplayRoom`을 그대로 쓴다(스레드 없이, 답이 올 때마다 `Session.run`을 처음부터 다시 돌리고
  빠진 답에서 멈춤). 그 방이 이제 서버 DO가 아니라 브라우저 Web Worker의 메모리에 있다. `browser.Arena`가 옛 REST 경로와
  응답 모양(`/rooms/...`, `/signal/...`, `/models`)을 그대로 흉내 내므로 `arena.js` · `signal.js`는 `fetch` 대신
  `Squid5Engine.api`를 부를 뿐 화면 코드는 거의 그대로다.
- Worker(`web/cloudflare/src/entry.py`)는 엔진을 import하지 않는다: 모델 호출 대리(키 규칙 `keys.py` 그대로), 게임 기록
  저장(D1 행 + R2 객체, 본문은 읽지 않음), 설문(D1), health · models.
- 1판(v1)은 **사람 한 명 + 봇/모델**. 여러 사람 방은 숨김(선택지 비활성 + 한국어 안내), 설계 메모는 §8.
- 기록은 브라우저가 보고한 것뿐이므로 연구에 쓰기 전 `tools/arena/verify_games.py`가 오프라인에서 진짜 엔진으로 다시
  돌려 맞춰 본다. 통과한 끝난 게임만 run dir가 되어 Pages의 정적 게임 기록(`monitor/`, `web_arena` 묶음)에 실린다.

## 2. 구성

```
브라우저 ──────────────────────────────────────────────────────────────┐
 arena.js / signal.js ── Squid5Engine.api(method, path, body) ── engine.js (로딩 화면, localStorage 저장·복원)
                                                                   │ postMessage
 engine_worker.js (module Web Worker) ── Pyodide + pyyaml + engine/squid5-engine-<hash>.zip
   browser.Arena ── replay.ReplayRoom ── web.server.engine.Room ── squid5.e52_game.Session (실험 엔진 그대로)
   modelcalls.run_all (한 번에 하나) ── ollama_fetch (fetch) ─┐
   기록 업로드 (gzip, 라운드마다 + 끝) ──────────────────────┤
└────────────────────────────────────────────────────────────┼─────────┘
Cloudflare Worker (무료) ── POST /api/games (토큰) · POST /llm/api/chat (KEY3로 Ollama) · POST /api/games/{id}/record
   D1: games · llm_calls · quota · probes        R2: arena/games/<id>/record.json.gz
연구자 / Pages 워크플로 ── verify_games.py --fetch (ARENA_EXPORT_TOKEN) ── 엔진으로 재생 · 대조 ── run dir ── build_static.py
```

### 하나의 엔진을 나눠 쓰는 방법 (복제 없음)

| 코드 | 브라우저 | 오프라인 검증기 | CPython 시험 | Worker |
|---|---|---|---|---|
| `squid5/`, `web/server/engine.py`, `signal.py` | 묶음으로 | 저장소에서 import | 저장소 | 안 씀 |
| `web/pyodide/replay.py`, `compat.py`, `room_settings.py` | 묶음으로 | import | import | 안 씀 |
| `web/pyodide/browser.py`, `modelcalls.py`, `ollama_fetch.py` | 묶음으로 | `browser`의 기록·다이제스트 함수 | import | 안 씀 |
| `web/cloudflare/src/keys.py`, `entry.py` | — | — | import | 그대로 |

새 접착 코드: `browser.py`(API 흉내, 저장 훅, 모델 호출 루프 시작, 기록 업로드, 쉬는 동안 다음 라운드 퍼즐 미리 만들기),
`build_bundle.py`, `selfcheck.py`(CPython과 Pyodide에서 같은 판을 두는 구동기), `engine.js` · `engine_worker.js`,
`verify_games.py`. Phase 2에서 옮긴 것: `compat.py`(httpx · numpy 대역; 스레드 없는 실행기는 이제 **재생 동안에만** 끼움 —
전역으로 바꾸면 같은 프로세스의 실험 시험이 깨졌다), `replay.py`, `modelcalls.py`(키 대신 게임 토큰), `ollama_fetch.py`
(Worker가 거절한 호출은 다시 시도하지 않음), `settings.py` → `room_settings.py`(키 이름만 고름; 키는 Worker에만).

## 3. 모델 호출

- 게임을 시작할 때 브라우저가 `POST /api/games`로 등록 → 게임 id + HMAC 서명 토큰(`{g, m, k, exp}`, 6시간).
  모델 자리 게임은 등록이 안 되면 시작하지 않는다(한국어 오류). 봇 게임은 Worker가 없어도 돌지만 기록은 남지 않는다.
- 모델 자리는 `<worker>/llm/api/chat`을 Ollama와 같은 모양으로 부르고 Bearer에 게임 토큰을 넣는다. Worker는 토큰 검증 →
  허용 모델(gemma4:31b 기본, gpt-oss:20b)이고 그 게임의 모델인지 → 필드 정리(think는 있을 때만, num_predict는 131,072로
  자름 — 엔진은 TALK의 한도로 잔액을 보내 수만이 넘는다) → 카운터(D1 한 batch: `games.calls`, `quota`의 IP·시간) →
  `keys.choose_key`(매 호출 스위치 다시 읽음) → Ollama. 스트림(SOLVE 관전)은 본문을 그대로 넘긴다.
- 호출 기록(`llm_calls`): 프롬프트 해시(엔진의 `replay.digest`와 같은 함수), 상태, 스트림이 아니면 eval_count와 답 해시.
- 한 번에 하나: 방마다 모델 호출 루프가 하나이고 차례로 부른다. 가짜 Ollama로 잰 동시 요청 최대 = 1.
- 오류(한국어): 게임·IP 한도(429 `limit_*`) · 토큰(401) · 모델(403) · 키 없음(403) · KEY3 402는 다시 시도하지 않고 바로
  빈 답 + 화면 경고. Ollama 429는 같은 키로 다시 시도(최대 2번). KEY1로 넘어가는 길은 없다.

## 4. 남용 한도 (무료 플랜에서 가장 싼 방법: D1)

KV는 무료 쓰기가 하루 1,000번이라 호출마다 세기에 모자라고, DO는 요청마다 한 번 더 깨워야 한다. D1은 이미 쓰고 있고
무료 쓰기가 하루 10만 행이다. 모델 호출 하나 = 3행(게임 카운터, IP·시간 카운터, 호출 기록).

| 한도 | 기본 | 변수 |
|---|---|---|
| 게임당 모델 호출 | 600 | `LIMIT_GAME_CALLS` |
| IP당 시간당 모델 호출(거절된 시도 포함) | 1,200 | `LIMIT_IP_CALLS_HOUR` |
| IP당 시간당 게임 등록 | 12 | `LIMIT_IP_GAMES_HOUR` |
| 게임 토큰 수명 | 6시간 | `LIMIT_TOKEN_TTL_S` |
| 요청 크기 · 기록 크기 · 게임당 기록 올리기 | 400 KB · 4 MB · 80번 | `LIMIT_*` |

IP는 저장하지 않고 `sha256(GAME_TOKEN_SECRET | ip)[:16]`만 둔다.

## 5. 무료 플랜에 맞는지 (측정)

요청마다 Python이 하는 일(JSON, HMAC, 해시, SQL 인자)을 Pyodide(Node, M 시리즈 Mac)에서 300번씩 잼
(`web/cloudflare/tests/bench_cpu.mjs`; D1 · R2 · Ollama는 즉시 끝나는 가짜 — 기다리는 시간은 Workers에서 CPU가 아님):

| 경로 | 평균 | p95 |
|---|---|---|
| `GET /api/models` | 0.02 ms | 0.03 ms |
| `POST /api/games` | 0.09 ms | 0.12 ms |
| `POST /llm/api/chat` (8 KB 요청) | 0.10 ms | 0.12 ms |
| `POST /llm/api/chat` (28 KB 요청) | 0.12 ms | 0.14 ms |
| `POST /api/games/{id}/record` (30 KB, 본문은 읽지 않음) | 0.04 ms | 0.05 ms |
| `POST /api/probe` | 0.04 ms | 0.04 ms |

잰 것은 Python 부분뿐이다(런타임의 JS ↔ Python 요청 변환은 빠짐). 10 ms 한도의 1–2 %라 변환 비용이 몇 배여도 남는다.
`wrangler dev`(Miniflare)의 벽시계: 로컬 D1 · R2를 쓰는 요청 4–30 ms, 모델 호출은 가짜 Ollama 0.3 s 대기 포함 324 ms.
Python Worker의 cold start(배포 때 찍는 메모리 스냅샷, 공식 수치 약 1 s)는 요청 CPU가 아니라 시작 한도(1 s)에 든다 —
엔진을 빼서 스냅샷이 작다. 실제 CPU는 배포 뒤 대시보드(Workers → Metrics → CPU time)로 확인할 것.

## 6. 브라우저 쪽 시간 (로컬 Playwright, Chromium 156, M 시리즈 Mac)

| 무엇 | 시간 |
|---|---|
| 첫 로드(빈 캐시): Pyodide 9.6 MB wasm + 2.5 MB stdlib + pyyaml + 묶음 121 KiB + import | 2.2 s |
| 다시 로드(캐시) | 1.8 s |
| 느린 망(지연 150 ms, 약 16 Mbps) + 빈 캐시 | 6.0 s |
| 시그널 페이지 첫 문제(seed 4000 R1, 퍼즐 처음 생성) | 8 s 안팎 (CPython 4.2 s) |
| 같은 seed의 다른 라운드 | 0.1–0.6 s |
| 아레나: 방을 만들고 규칙을 읽는 동안(쉬는 동안) 퍼즐을 미리 만든 뒤 시작 → 첫 화면 | 0.3 s |
| 아레나: 규칙을 바로 닫고 시작(미리 만들기 전) → 첫 화면 | 4.9 s |
| 봇 8라운드 한 판 전체의 엔진 계산(사람 시간 뺌), Node Pyodide | 9.8 s (CPython 4.2 s) |

엔진 계산은 Web Worker에서 하므로 화면은 멈추지 않는다(0.7 s 넘으면 오른쪽 아래 "엔진 계산 중…"). 쉬는 동안 다음 라운드
퍼즐을 만드는 일(`Arena.warm_step`)은 **사람 화면이 열려 있을 때는 하지 않는다**(그 사이 사람의 시계가 돌아 차감되므로).
CDP CPU 4배 늦추기는 Web Worker 스레드에 걸리지 않아(재 보니 같은 시간) 휴대폰 CPU는 따로 재지 못했다. 중간급
휴대폰의 wasm이 3–5배 느리다고 보면 시그널 첫 문제 25–40 s, 아레나 첫 라운드는 규칙을 읽는 동안 대부분 끝난다.
390 px 화면에서 가로 넘침 0.

## 7. 기록과 검증

- 기록(`browser.record_of`, `squid5-arena-game/1`): doc(설정 · seed · 사람 이름, **토큰은 지움**), 자리마다 호출 순서대로
  모든 답(답한 프롬프트의 해시 `h` 포함), 이벤트마다 sha1 다이제스트와 전체 다이제스트, 세션 결과, 엔진 묶음 해시. 이벤트
  본문은 보내지 않는다(봇 3자리 3라운드 판 gzip 2.5 KB).
- 올리는 때: 라운드가 끝날 때마다, 끝날 때, 끝 화면의 "기록 다시 올리기". "기록 내려받기(JSON)"로 파일도 받을 수 있다.
- 검증(`verify_games.py`): ① `ReplayRoom.load(doc, replies)`로 진짜 엔진 재생(다른 프롬프트에 단 답이면 멈춤)
  ② 재생한 이벤트 다이제스트 = 보고된 것, 세션 결과 같음 ③ 사람 답: 차감 = 초 × rate, 시간 범위, 결과 종류(1초 미만 답은
  경고) ④ 모델 답: Worker 호출 기록에 같은 프롬프트 해시가 있는지, 스트림이 아니면 토큰 수 · 답 해시까지, 모델 답 수 ≤
  성공 호출 수 ⑤ 묶음 해시가 지금 저장소와 다르면 경고. 못 막는 것: 사람이 실제로 화면을 본 시간(브라우저 시계), 스트림으로
  받은 SOLVE 답의 내용(프롬프트만 대조). 
- 같은 판의 다이제스트가 Pyodide(Node)와 CPython에서 같다(CI 시험) — 브라우저가 둔 판을 검증기가 그대로 재현한다.
- 로컬 e2e에서 올라간 10판(봇 · 모델 · 진행 중) 모두 통과, 위조(모델 토큰 수, 사람 차감, 답 바꿔치기, 결과 위조, 호출
  기록 없음)는 단위 시험에서 잡힌다.

### 게임 기록(monitor)에 보이는 길: 정적 빌드에 검증된 판을 넣기

Pages 워크플로가 `ARENA_WORKER_URL`(저장소 변수)과 `ARENA_EXPORT_TOKEN`(저장소 비밀값)이 있으면 빌드 때
`verify_games.py --fetch … --out _runs/web_arena`를 돌리고 `build_static.py --root _runs`로 묶는다(매일 03:40 KST +
수동 실행 + main 푸시). 장점: monitor 코드를 바꾸지 않고, Worker는 공개 다운로드 경로가 없으며, 검증 안 된 판은 아무에게도
안 보인다. 대가: 끝난 판이 게임 기록에 뜨기까지 다음 빌드(최대 하루)를 기다린다. Worker에서 기록을 바로 읽어 monitor가
그리는 길은 브라우저에서 `serve.py`의 payload 함수를 다시 돌려야 해서 뺐다.

## 8. 다음 버전: 여러 사람 방 (설계 메모만)

- 호스트 권한(host authority): 방을 만든 브라우저가 엔진을 돌린다(지금과 같은 `ReplayRoom`). 다른 사람의 브라우저는 화면만
  그리고 답을 보낸다.
- 중계: 방마다 DO 하나(WebSocket Hibernation)가 메시지만 나른다 — 호스트 → 사람별 상태(`Room.state(seat)`의 결과, 그 사람
  것만), 사람 → 호스트로 제출. DO는 엔진을 import하지 않으므로 요청당 CPU는 메시지 복사뿐(무료 플랜 DO: 하루 10만 요청).
- 시계: 사람의 차감은 호스트의 시계로 잰다(지금 `HumanSeat.cost`). 중계 지연만큼 불리하므로 제출 메시지에 화면을 연 뒤
  경과 시간을 실어 보내고 검증기가 범위를 본다.
- 호스트가 나가면: 호스트의 doc + replies를 DO에 체크포인트하고 다른 사람이 이어받아 재생(재생이라 가능).
- 위험: 호스트가 다른 사람의 화면을 위조할 수 있다 → 검증기의 재생 + 사람별 제출 서명(DO가 받은 제출을 그대로 기록).

## 9. 시험

- CPython: `pytest -q tests tools/monitor web/cloudflare/tests web/pyodide/tests tools/arena` → 201 통과, 26 건너뜀
  (`web/tests` 32 통과: 옛 FastAPI 서버를 시험하지만 그 서버의 `engine.py` · `signal.py`가 브라우저가 돌리는 바로 그
  코드라 남겨 둠).
- Pyodide CI 가드: `web/pyodide/tests/test_pyodide_node.py` — Node에서 Pyodide 314.0.7로 묶음을 풀고 봇 8라운드 한 판 +
  시그널 8라운드, 이벤트 다이제스트가 CPython과 같아야 통과(약 25 s). `.github/workflows/tests.yml`의 `browser-engine` 잡
  (`SQUID5_REQUIRE_PYODIDE=1`이면 Node가 없을 때 실패).
- 로컬 e2e(Pages 빌드를 `/LLM-Squid-Game/`로 http.server + `wrangler dev` + 가짜 Ollama + Playwright): 사람 1 + 봇 3을
  UI로 끝까지, 사람 1 + 모델 3(가짜 Ollama, Worker 경유, 키 = KEY3 값, 동시 1), 기록 업로드 · 검증 · monitor 표시, 시그널
  한 문제, 설문 저장, onrender.com 요청 0, 페이지 오류 0.

## 10. 배포 순서 (연구자)

`web/cloudflare/README.md`의 "배포": d1 create(→ wrangler.toml id) · migrations apply --remote(0001, 0002) · r2 bucket
create squid5-runs · secret put `OLLAMA_API_KEY3`, `GAME_TOKEN_SECRET`, `ARENA_EXPORT_TOKEN`(+ 선택 `OLLAMA_API_KEY1`) ·
`pywrangler deploy` → `web/frontend/config.js`의 `WORKER_URL` → 저장소 변수 `ARENA_WORKER_URL`, 비밀값
`ARENA_EXPORT_TOKEN` → main에 푸시(Pages 배포).

## 11. 남은 한계 · 위험

- 휴대폰 CPU: 퍼즐 처음 생성이 수십 초일 수 있다(§6). 시그널 페이지 첫 문제가 가장 길다.
- 브라우저 요구: module Web Worker(Chrome 80+, Safari 15+, Firefox 114+), `CompressionStream`(Safari 16.4+), wasm.
  jsdelivr CDN이 막힌 망에서는 엔진이 뜨지 않는다(Pyodide를 Pages에 같이 올리면 약 12 MB 늘어남 — 필요하면).
- `importScripts`로 Pyodide 314의 `pyodide.js`를 읽으면 Chromium 156에서 "failed to load"가 나서 `pyodide.mjs`를
  module worker에서 `import()`로 읽는다.
- 브라우저가 보고하는 시계는 믿을 수 없다(사람이 화면을 본 시간). 검증기는 일관성만 본다.
- 엔진을 바꾸면 묶음 해시가 바뀐다. 진행 중인 판(localStorage에 저장된 방)은 새 엔진으로 재생하다 어긋나면 `error`로 멈춘다.
  검증기는 기록의 묶음 해시와 저장소가 다르면 경고만 하므로, 어긋나면 그 커밋을 체크아웃해 검증한다.
- 방끼리는 같은 KEY3로 동시에 호출한다(방 안에서만 한 번에 하나). 무료 키에서 동시 방이 많으면 Ollama 429 → 같은 키로
  재시도 후 빈 답.
- 게임 기록에 뜨는 데 최대 하루(Pages 빌드 주기).
- Phase 2 DO 판을 배포한 적이 있다면 `deleted_classes = ["RoomDO"]` 마이그레이션이 필요하다(배포 기록은 없음).
