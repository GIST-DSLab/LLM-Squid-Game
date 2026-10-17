# 2026-10-17 웹 백엔드를 Cloudflare로 (Python Workers + Durable Objects + D1 + R2)

연구자 결정: 정적 페이지는 GitHub Pages(이미 있음; 게임 로그·모델 비교·리더보드는 다른 작업이 정적으로 옮김), 동적인
것은 모두 Cloudflare. Render·Supabase는 쓰지 않는다. 동적 백엔드는 **Python Workers + Durable Objects (+ D1)**: squid5
엔진은 Python 그대로, 저장소의 한 벌을 공유한다(JS 포팅 없음). 방의 게임 루프는 오래 도는 백그라운드 스레드에 기대지
않게 다시 짠다.

구현: `web/cloudflare/` (README에 명령). 엔진(`squid5/`)과 `web/server/`는 한 줄도 고치지 않았다.

## 1. 결론 한 줄씩

- 방 하나 = Durable Object 하나(`RoomDO`, 이름 = 방 코드). 방의 진실은 그 DO의 SQLite(설정·사람·**받은 답 전부**).
- 게임 루프는 **재생(replay)** 으로 돈다: 답이 하나 들어올 때마다 기록된 답들로 `Session.run()`을 처음부터 다시 돌리고,
  아직 없는 답에서 멈춘다. 엔진이 seed와 답만으로 결정적이라 가능하다. 스레드도, 엔진 수정도 필요 없다.
- 모델 호출은 DO **알람**이 `fetch`로 하고(httpx 없음), 한 방 안에서는 **한 번에 하나**(Ollama 무료 플랜 = 키당 동시 1).
- SOLVE 스트리밍은 알람이 받는 조각을 DO 메모리의 관전 상태에 쌓고, 사람들은 지금처럼 `/state`를 1초마다 당겨 본다
  (WebSocket 없음 → 프런트엔드 변경 없음).
- D1 = 방 목록·이벤트 사본·설문(`probes`). R2 = 끝난 방의 run dir 내보내기.
- 기본 모델 `gemma4:31b`, think 끔. 키는 `OLLAMA_API_KEY3`만 기본, `OLLAMA_API_KEY1`은 대시보드 스위치가 `on`일 때만.

## 2. 엔드포인트 → Worker / DO

요청·응답 모양은 FastAPI와 같다. 오류는 FastAPI처럼 `{"detail": "..."}`(arena.js가 `data.detail`을 읽음).

| 지금 (web/server/app.py) | Cloudflare | 비고 |
|---|---|---|
| `GET /api/health` | Worker | `rooms` = D1의 lobby·running 방 수, `backend: "cloudflare"` |
| `GET /api/models` | Worker | `gemma4:31b` 먼저·기본, `models` 목록(gpt-oss:20b 유지), `think_levels`에 `off` 추가, `available` = KEY3 비밀값 유무 |
| `POST /api/rooms` | Worker → `RoomDO.api("create")` | 설정 검사·키 검사(400 한국어)는 Worker, 코드 충돌은 D1로 확인 |
| `GET /api/rooms` | Worker (D1 `rooms`) | 최근 50개 |
| `POST /api/rooms/{code}/join` | DO | 409: 시작됨·자리 다 참 |
| `POST .../start?token=` | DO | 호스트만(403), 모델 좌석이면 키 재검사 → 첫 재생 |
| `GET .../state?token=` | DO | 먼저 `tick()`(시간 초과·잔액 초과·관전 대기 끝) → `Room.state()` 그대로. `monitor`는 `null` |
| `POST .../submit?token=` | DO | `HumanSeat.submit` 그대로 → 답 기록 → 배치가 차면 재생 |
| `POST .../watched?token=` | DO | `watch_ack` → 모두 보면 재생 |
| `POST .../forfeit?token=` | DO | 열린 화면에 포기 답, 이후 화면도 즉시 포기 답 |
| `GET .../events` | DO | 끝나기 전엔 `public_events` (서버와 같음) |
| `POST .../export` | DO → R2 `RUNS/web5/runs/<code>/` | `{dir: "r2://RUNS/...", rounds, finished}`. 정적 게임 로그 뷰어가 쓰려면 R2 → Pages 복사 단계가 따로 필요(§10) |
| `GET /api/signal/meta`, `POST /view`, `/solve` | Worker | `web/server/signal.py` 그대로(상태 없음) |
| `POST /api/probe`, `GET /api/probe/summary` | Worker (D1 `probes`) | 검사·응답 같음 |
| `GET /api/leaderboard` | 410 | Pages 정적 페이지로 이동(다른 작업) |
| `/monitor/*` | 없음 | Pages 정적 뷰어로 이동(다른 작업) |

## 3. 스레드 없는 게임 루프: 재생

### 왜 재생인가

`squid5.e52_game.Session.run()`은 `provider.complete()`를 부르고 답을 기다리는 동기 루프 하나다. FastAPI 서버는 이를
스레드에서 돌렸고 사람의 제출이 스레드를 깨웠다. Pyodide에는 스레드가 없고, DO 요청 사이에 파이썬 호출 스택을 붙잡아
둘 방법도 없다(JSPI·greenlet 의존은 피했다). 엔진을 단계 기계로 다시 쓰는 것은 엔진 수정이 크고 실험 엔진과 갈라진다.

엔진은 seed와 답만 같으면 같은 길을 간다(모든 난수가 `random.Random(f"{seed}:...")`, 퍼즐은 `lru_cache`). 그래서 방은
**받은 답만** 저장하고, 답이 하나 늘 때마다 세션을 처음부터 다시 만든다.

### 동작 (`src/replay.py`)

1. `ReplayRoom(E.Room)` — 서버의 `Room`을 상속. `replay()`가 `Room.start`와 똑같이 `Session`을 만들고 좌석을 붙인다.
2. 좌석
   - `ReplayHuman(E.HumanSeat)`: 그 에이전트의 i번째 호출에 기록된 답이 있으면 돌려주고, 없으면 화면을 연다(`pending`,
     view는 서버의 `VIEWS` 그대로) → need 등록 → `Suspend`.
   - `ReplayModel(E.ModelSeat)`: 기록이 있으면 돌려주고 서버와 같은 `model_call` 이벤트를 다시 낸다. 없으면 need 등록 →
     `Suspend`(DO가 호출).
   - 봇(`E.BotSeat`)은 재생마다 새로 만들어 다시 계산(같은 seed라 같은 답).
3. `Suspend`는 `BaseException`이라 엔진의 `except Exception`이 삼키지 않는다. `Session._calls`의 `ThreadPoolExecutor`는
   `compat.InlineExecutor`로 바꿔 끼운다(모듈 속성 하나): 배치의 모든 작업을 차례로 실행하고 예외를 보관하므로, 배치에서
   빠진 답이 **모두** need로 등록된 뒤에 멈춘다.
4. 멈춘 뒤 남은 `Session` 객체가 바로 그 호출 시점의 상태(잔액·대화·결과·solver)라서 서버의 `Room.state()`, 화면 view,
   `talk_state`, `spectate_view`가 바뀌지 않고 돈다 → 응답 모양이 같다.
5. 재생은 같은 이벤트를 같은 순서로 다시 내므로 새 이벤트는 꼬리뿐이다(`doc.saved_events`). 기록된 답에는 그 답이 받은
   프롬프트의 해시(`h`)가 있어, 엔진이 바뀌어 다른 질문이 나오면 엉뚱한 답을 넣지 않고 방을 `error`로 멈춘다.
6. 사람 화면의 시계: 화면이 처음 열린 시각을 `doc.screens`에 저장해 재생이 시계를 되돌리지 않는다. 시간 초과·잔액 초과는
   `tick()`이 서버와 같은 규칙(초 × rate, `talk_timeout_s` / `timeout_s`)으로 닫는다.
7. LLM solver 관전(`Room.watched`): 답이 오면 `doc.holds`에 대기 끝 시각(서버와 같은 `min(watch_hold_s, 8 + 단어/15)`)을
   적고, 사람이 모두 `watched`를 보내거나 그 시각이 지나면 풀린다(need `watch`). 풀린 기록이 있어 재생은 다시 기다리지 않는다.

### 비용 (측정)

| 무엇 | CPython 3.12 | Pyodide (wrangler dev, 로컬 Mac) |
|---|---|---|
| 8라운드 한 판 전체 재생, 퍼즐 캐시 있음 | 13 ms | (warm 상태 요청 5–12 ms) |
| 같은 판, 퍼즐 처음 생성(cold) | 2.7 s | 라운드당 약 1 s 안팎 |
| 방 시작(1라운드 퍼즐 생성 포함, 새 isolate) | — | 5.1 s |
| DO 메모리를 잃은 뒤 진행 중 방(2라운드) 다시 열기 | — | 3.4 s |
| 끝난 5라운드 방 다시 열기 | — | 4.2 s |
| `POST /api/signal/view` 첫 호출 | — | 1.6 s |

같은 isolate 안에서는 `_public_order`가 캐시돼 재생이 싸다. 비싼 것은 라운드마다 퍼즐을 처음 만드는 일과 DO가 메모리에서
내려간 뒤의 첫 요청(전체 재생)이다. 줄이는 방법(아직 안 함): (a) `_public_order` 결과를 DO SQLite에 pickle로 저장,
(b) 흔한 모양의 `_space(shape)`를 모듈 최상위에서 미리 계산해 Python Workers 메모리 스냅샷에 넣기.

## 4. 모델 호출

- 어디서: DO의 `alarm()`. 요청 처리 중에는 모델을 부르지 않는다(알람은 벽시계 15분까지; 요청과 무관하게 돈다).
  재생 뒤 모델 need가 있으면 `setAlarm(now)`, 사람 화면만 열려 있으면 가장 이른 마감 시각으로 알람을 건다.
- 어떻게: `src/ollama_fetch.py` — squid5 `Ollama` 공급자와 같은 payload(`model`, `messages`, `options.temperature`,
  `options.num_predict = cap`, `think`는 값이 있을 때만), 같은 `Reply`(`eval_count` = 생각 포함 생성 토큰). 실패 시 같은 키로
  `retries`번 재시도(대기 min(30, 2^n) s). 그래도 실패하면 서버처럼 빈 답·0토큰 + `model_call.error`.
- **한 번에 하나**: `modelcalls.run_all`이 need를 하나씩 순서대로 부른다. 여는 턴처럼 모델 3자리가 한 배치면 세 번 차례로
  부르고, 그동안 그 자리들은 `thinking`으로 보인다. 이유: Ollama 무료 플랜은 동시 1요청(넘치면 줄 서다 거부). 가짜 Ollama로
  잰 동시 요청 최대값 = 1. **남는 위험**: 방이 여러 개면 방끼리는 동시에 같은 키를 쓴다. 키당 직렬화가 필요하면 키 하나당
  DO 하나(`KeyGate`)를 두고 모든 방이 거기서 차례를 받게 하면 된다(미구현).
- 기본 모델: `gemma4:31b`, think 끔(필드를 보내지 않음). 연구자 확인(10-17, KEY3 무료): TALK 한 번 1.3–1.7 s·약 200토큰,
  think 켜면 8–10 s·약 2,500토큰. `gpt-oss:20b`는 목록에 남김. `RoomSettings`는 think를 low/medium/high만 받으므로
  `settings.make`가 "off"를 자리표시자로 검사한 뒤 `None`으로 바꾼다(저장은 `think: null`).

### 키 규칙 (`src/keys.py`, 테스트 `tests/test_keys.py`)

- 비밀값: `OLLAMA_API_KEY3`(기본, 모든 호출), `OLLAMA_API_KEY1`. 그 밖의 키는 올리지 않는다.
- KEY1은 plain 변수 `OLLAMA_KEY1_ENABLED`가 정확히 `"on"`일 때만. 이 변수는 `wrangler.toml`에 없고 `keep_vars = true`라
  배포가 켜는 일도 지우는 일도 없다. 클라이언트는 `api_key_env`로 `OLLAMA_API_KEY3` 또는 (켜진 동안) `OLLAMA_API_KEY1`만
  고를 수 있고 나머지는 400(한국어).
- 자동 대체 없음: KEY3가 402·429·오류여도 KEY1로 넘어가지 않는다. KEY3가 없으면 모델 좌석 방을 만들거나 시작할 수 없다.
  매 호출마다 스위치를 다시 읽는다.

## 5. SOLVE 스트리밍

서버는 httpx 스트리밍 조각을 `Room.watch`에 쌓고 사람들은 `/state`의 `spectate`를 당겨 봤다. 같은 방식을 유지한다:
알람이 `fetch` 응답 본문을 reader로 읽어 NDJSON 줄마다 `room.stream_delta()` → DO 메모리의 `watch`에 생각·답을 덧붙인다.
DO는 알람이 `await` 하는 동안에도 `/state` 요청을 처리하므로(입력 게이트는 저장소 작업에만 걸림) 사람들은 조각이 오는 대로
본다. 가짜 Ollama로 확인(스트리밍 SOLVE 3번, 관전 화면에 `status: streaming`과 생각 조각이 보임 — 단위 시험).
WebSocket(Hibernation)으로 바꾸면 폴링 요청 수가 줄지만 arena.js를 고쳐야 해서 이번 범위에서 뺐다.

## 6. Pyodide에서 엔진

- import: `squid5`(e52_game, core.*), `web/server/engine.py`, `signal.py`가 Pyodide(Python 3.14)에서 그대로 import된다.
  pyyaml은 Pyodide 패키지(pywrangler가 번들). 엔진이 import 때 읽는 데이터(`squid5/prompts/en/trim_v19.yaml`,
  `configs/squid5/e52v16_public_sol4.yaml`)는 wrangler `[[rules]] type = "Data"`로 번들에 넣었고, 같은 상대 경로에서 읽힌다.
- 대역(`src/compat.py`, 진짜 모듈이 없을 때만): `httpx`(providers.py와 engine.py가 최상위에서 import; Worker는 쓰지 않음),
  `numpy`(e52_game의 `report()`에서만 `np.mean`; 번들·스냅샷을 몇 MB 줄임), `ThreadPoolExecutor` → `InlineExecutor`.
- 파일 쓰기: 서버의 `RunWriter`(라이브 run dir)는 쓰지 않는다(`runs_root=None`). 내보내기는 R2.
- `os.environ` 대신 `env` 바인딩으로 키를 읽는다(`RoomSettings.check_models`는 부르지 않고 keys.py가 대신).

### 엔진 쪽 패치 제안 (적용 안 함; 없어도 Worker는 돈다)

1. `squid5/core/providers.py`: `import httpx`를 각 `_call` 안으로 옮기기(대역이 필요 없어짐).
2. `squid5/e52_game.py`: `import numpy as np`를 `report()` 안으로.
3. `squid5/e52_game.py`: `Session`에 `executor = ThreadPoolExecutor` 클래스 속성을 두고 `_calls`가 `self.executor`를 쓰기
   (모듈 속성 바꿔치기 대신 하위 클래스에서 지정).
4. `web/server/engine.py`: `THINK_LEVELS`에 `"off"`(→ think 필드 생략) 허용, 기본 모델 `gemma4:31b`·think off로 서버와
   Worker를 맞추기; `check_models`가 환경 읽기 함수를 받게.

## 7. 저장소

**DO SQLite(방마다)**: `meta(k, v)`의 `doc`(설정·seed·사람(이름·토큰·포기)·상태·화면 시각·관전 대기·저장한 이벤트 수),
`replies(agent, idx, body)`(답 하나 = 행 하나; 모델 생각이 길어도 행 2 MB 한도 안). 이벤트는 저장하지 않는다(재생이 다시
만든다).

**D1** (`migrations/0001_init.sql`, `web/server/store.py`와 같은 열):
- `rooms(code PK, created_at, settings, seats, status, updated_at)` — 방 목록·health. DO가 저장할 때마다 upsert.
- `events(id, code, seq, ts, kind, body)` + `UNIQUE(code, seq)` — DO가 새 이벤트를 50개씩 batch로 복사(실패하면 다음 저장 때
  같은 seq부터 다시; 중복은 `INSERT OR IGNORE`). 진실은 DO; D1은 목록·분석·내보내기용 사본.
- `probes(id, ts, anon_id, client_ts, self_vals, other_vals, meta)` — 설문, Worker가 직접.

**R2** `squid5-runs`: `/export`가 `web5/runs/<code>/{config.yaml, meta.json, events.jsonl, results.jsonl}`(서버의
`write_run_dir`과 같은 4개 파일)을 쓴다.

**비밀값**: `wrangler secret put OLLAMA_API_KEY3`, `OLLAMA_API_KEY1`. plain 변수: `CORS_ORIGINS`(wrangler.toml),
`OLLAMA_KEY1_ENABLED`(대시보드에서만).

## 8. CORS

`CORS_ORIGINS`(쉼표 목록; 기본 `https://gist-dslab.github.io`와 localhost 5600·8600). 목록에 있는 Origin에만
`access-control-allow-origin`을 그 값으로 돌려준다. OPTIONS는 204. 메서드 GET·POST, 헤더 Content-Type. 토큰은 쿼리
문자열이라 쿠키·credentials가 필요 없다.

## 9. 플랜·한도 (2026-10 문서 기준)

| 한도 | 무료 | 유료($5/월) | 이 백엔드에서 |
|---|---|---|---|
| 요청당 CPU | 10 ms | 기본 30 s, 최대 5 min(`limits.cpu_ms`) | signal/view 1.6 s, 방 시작 5 s, 식은 방 재생 3–5 s → **유료 필요** |
| 서브요청/요청 | 50 | 10,000 | 알람 하나가 모델 호출 여러 번 + D1 batch: 유료면 여유 |
| DO 알람 벽시계 | 15 min | 15 min | 알람마다 모델 호출 600 s까지, 나머지는 다음 알람 |
| DO 요청 벽시계 | 연결 동안 무제한 | 같음 | 요청 안에서 모델을 부르지 않음 |
| Worker 크기 | 64 MiB | 64 MiB | 업로드 894 KiB (gzip 245 KiB) |
| 메모리 | 128 MB | 128 MB | 방 하나 수 MB |

비용 감: 사람 4명이 1초마다 `/state` → 방 한 시간 약 14,400 요청(유료 포함량 월 1,000만). DO는 폴링 동안 깨어 있어 시간
과금(128 MB 기준 한 시간 ≈ 450 GB-s; 유료 포함 월 40만 GB-s ≈ 방 900시간). 숫자는 문서 기준 추정이며 실제 청구는 대시보드로
확인할 것. Python Workers의 cold start는 배포 때 찍는 메모리 스냅샷으로 줄어든다(엔진 import가 스냅샷에 들어감).

## 10. 단계

| 단계 | 내용 | 로컬에서 | 계정 필요 |
|---|---|---|---|
| 1 | 재생 방·키 규칙·모델 호출 단위 시험 | ✅ pytest 25개 | — |
| 2 | Worker+DO+D1+R2 로컬(Miniflare) 스모크: 봇 방 끝까지, 모델 방(가짜 Ollama, 실제 fetch 경로), 재시작 후 재생 | ✅ | — |
| 3 | 배포: d1 create·migrate, r2 create, secret 2개, `pywrangler deploy` | dry-run만 ✅ | ✅ |
| 4 | 실제 Ollama(gemma4:31b, KEY3)로 사람 1 + 모델 3 한 판, 시간·토큰·429 확인 | — | ✅ |
| 5 | 프런트엔드 `config.js` 주소 바꾸기(§11), Pages에서 방 만들기·관전·내보내기 | — | ✅ |
| 6 | (선택) 퍼즐 캐시 저장, KeyGate DO, WebSocket 관전, R2 → Pages 게임 로그 복사 | 일부 | — |

로컬에서 못 보는 것: 실제 CPU 한도 적용(로컬은 `limits`를 무시), DO 퇴출 시점(로컬은 서버 재시작으로 흉내), 실제
Ollama의 지연·429, 배포 스냅샷의 cold start.

## 11. 다른 폴더에 필요한 변경 (제안만, 적용 안 함)

- `web/frontend/config.js`: `"https://squid5-web5-api.onrender.com"` → `"https://squid5-api.<서브도메인>.workers.dev"`.
- `web/frontend/arena.html` 81·99행: think 선택에 `<option value="off" selected>off (기본)</option>`을 넣고 medium의
  `selected`를 뺀다(지금은 늘 `think: "medium"`을 보내 gemma4가 생각을 켬). 61·72·73·84·95행의 `gpt-oss:20b` 문구 →
  `gemma4:31b`(73행 span은 `/api/models`가 덮어씀).
- `web/frontend/arena.js` 273행 `think ${esc(s.think)}` → `think ${esc(s.think || "off")}`, 286행 `think ${s.think}` → `think ${s.think || "off"}`; 143행 안내문의
  `web/tools/serve_local.py` → Worker 비밀값 안내.

## 12. 위험

- 엔진 결정성에 기댄다. 진행 중인 방이 있을 때 엔진·`web/server`를 바꿔 배포하면 프롬프트 해시가 어긋나 그 방은 `error`로
  멈춘다(잘못된 답을 넣지는 않음). 배포는 진행 중인 방이 없을 때.
- 식은 방의 첫 요청이 수 초 걸린다(전체 재생). 폴링이 이어지는 동안은 DO가 깨어 있어 드물지만, 긴 휴식 뒤 첫 화면이 늦을 수
  있다.
- 방끼리는 같은 키로 동시에 호출할 수 있다(§4). 무료 키에서는 동시 방이 많으면 429 → 빈 답.
- `OLLAMA_BASE_URL`·`MODEL_STUB`은 로컬 시험용(BASE_URL은 loopback만 받음).
- Python Workers·pywrangler는 빠르게 바뀐다(이번에 uv 0.12.3 이상 요구를 만남). `pyproject.toml`의 의존은 pyyaml 하나.
