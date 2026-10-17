# squid5 thin API on Cloudflare (Python Worker, FREE plan)

게임 엔진은 방문자의 브라우저에서 돈다(`web/pyodide/`, Pyodide를 Web Worker에서). 이 Worker는 엔진을 import하지 않고
네 가지만 한다: 모델 자리의 Ollama 호출 대리(키는 여기에만), 브라우저가 올린 게임 기록 저장, 5.1 설문, health · models.
설계와 이유: `docs/history/plans/2026-10-18-browser-engine.md` (그 전 단계: `2026-10-17-cloudflare-migration.md`).

| 파일 | 역할 |
|---|---|
| `src/entry.py` | 라우터(`Default`)와 경로 로직(`Api`): 게임 토큰(HMAC), 한도, Ollama 대리, 기록 저장, 내보내기, 설문 |
| `src/keys.py` | 키 선택 규칙(기본 KEY3, KEY1은 대시보드 스위치가 `on`일 때만, 대체 없음) |
| `migrations/0001_init.sql` | rooms · events · probes (rooms · events는 보관 중인 서버 방 코드의 표, 지금은 안 씀) |
| `migrations/0002_browser_games.sql` | games · llm_calls · quota |
| `tests/test_entry.py`, `test_keys.py` | CPython 단위 시험(sqlite D1, dict R2, 가짜 Ollama) |
| `tests/fake_ollama.py` | 로컬 가짜 Ollama(실제 fetch 경로 시험) |
| `tests/bench_cpu.mjs` | 요청마다 Python CPU 시간을 Pyodide(Node)로 잼 |
| `legacy/` | 서버에서 엔진을 재생하던 Durable Object 판(유료 플랜 필요해 접음). 배포하지 않음 |

## 경로

| 경로 | 무엇 | 인증 |
|---|---|---|
| `GET /api/health`, `GET /api/models` | 상태, 모델 목록 · KEY3 유무 · 한도 | 없음 |
| `POST /api/games` | 브라우저 게임 등록 → `{game, token, expires_at}` | 없음(IP당 시간당 게임 수 한도) |
| `POST /llm/api/chat` | Ollama `/api/chat`과 같은 모양. 허용 모델만, 게임의 모델만, num_predict는 131,072로 자름 | `Bearer <게임 토큰>` |
| `POST /api/games/{id}/record` | gzip 게임 기록(본문은 읽지 않고 R2에 그대로) + 요약 헤더 `X-Squid5-Summary` → D1 | `Bearer <게임 토큰>` |
| `GET /api/games`, `/api/games/{id}/record`, `/api/games/{id}/calls` | 오프라인 검증기용 내보내기 | `Bearer <ARENA_EXPORT_TOKEN>` |
| `POST /api/probe`, `GET /api/probe/summary` | 설문 | 없음 |
| `/api/rooms*`, `/api/signal*` | 410(엔진은 브라우저로 옮김) | — |

한도(`[vars]`의 `LIMIT_*`, 기본값은 `entry.py` `LIMITS`): 게임당 모델 호출 600, IP당 시간당 호출 1,200, IP당 시간당 게임
12, 토큰 수명 6시간, 기록 4 MB · 게임당 80번. 거절은 HTTP 429와 한국어 `detail`, `code`(`limit_game` · `limit_ip` ·
`limit_ip_games`). Ollama의 402는 402(“KEY3 무료 사용량 끝, 다른 키로 넘어가지 않음”), 429는 429(브라우저가 같은 키로
다시 시도).

## 로컬 시험

```bash
~/.venvs/squid-game/bin/python -m pytest -q web/cloudflare/tests          # 단위 시험
npm ci --prefix web/pyodide && node web/cloudflare/tests/bench_cpu.mjs     # 요청당 Python CPU

cd web/cloudflare
cp .dev.vars.example .dev.vars
npx wrangler d1 migrations apply squid5 --local
~/.venvs/squid-game/bin/python tests/fake_ollama.py --port 11435 &
uvx --from workers-py pywrangler dev --port 8788    # uv 0.12.3 이상이 PATH에 있어야 함 (uv self update)
```

브라우저 쪽은 `web/frontend`를 정적 서버로 띄우면 `config.js`가 localhost에서 `http://localhost:8788`을 쓴다
(`python web/pyodide/build_bundle.py`로 `web/frontend/engine/`을 먼저 만든다).

## 배포 (연구자가 직접; 이 폴더의 코드는 배포하지 않았다)

```bash
cd web/cloudflare
npx wrangler login
npx wrangler d1 create squid5                         # 출력된 database_id를 wrangler.toml에 넣는다
npx wrangler d1 migrations apply squid5 --remote      # 0001, 0002
npx wrangler r2 bucket create squid5-runs             # 게임 기록 (arena/games/<id>/record.json.gz)
npx wrangler secret put OLLAMA_API_KEY3               # 모든 모델 호출의 키
npx wrangler secret put GAME_TOKEN_SECRET             # 게임 토큰 서명용, 임의의 긴 문자열 (예: openssl rand -hex 32)
npx wrangler secret put ARENA_EXPORT_TOKEN            # 검증기 · Pages 워크플로가 기록을 내려받는 토큰 (임의의 긴 문자열)
npx wrangler secret put OLLAMA_API_KEY1               # 선택: 대시보드 스위치가 on일 때만 쓰임
uvx --from workers-py pywrangler deploy
curl https://squid5-api.<계정 서브도메인>.workers.dev/api/health
```

그다음:

1. `web/frontend/config.js`의 `WORKER_URL`을 배포된 주소로 바꾼다(`REPLACE-ME`가 남아 있으면 봇 방만 되고 기록이 안 남음).
2. GitHub 저장소 설정: 변수 `ARENA_WORKER_URL` = Worker 주소, 비밀값 `ARENA_EXPORT_TOKEN` = 위와 같은 값. Pages
   워크플로(매일 03:40 KST, 또는 수동 실행)가 기록을 내려받아 엔진으로 다시 돌려 보고, 통과한 끝난 게임만 게임 기록
   (`monitor/`, `web_arena` 묶음)에 싣는다.
3. 이미 Phase 2(Durable Object 판)를 배포한 적이 있다면 `RoomDO` 클래스를 지우는 마이그레이션이 필요하다
   (`[[migrations]] tag = "v2"`, `deleted_classes = ["RoomDO"]`). 배포한 적이 없으면 할 일 없음.

무료 플랜으로 충분하다: 요청마다 Python CPU는 0.1 ms 안팎(설계 문서 §5), 나머지는 D1 · R2 · Ollama를 기다리는 시간이라
CPU로 치지 않는다. 무료 한도: 요청 하루 10만, D1 쓰기 하루 10만 행(모델 호출 하나 = 3행), R2 10 GB.

## OLLAMA_API_KEY1 켜기·끄기 (대시보드)

- 켜기: Cloudflare 대시보드 → Workers & Pages → squid5-api → Settings → Variables and Secrets → Add → Text,
  이름 `OLLAMA_KEY1_ENABLED`, 값 `on` → Deploy. 끄기: 지우거나 `off`. 정확히 `on`일 때만 켜진다.
- 켜진 동안에도 `api_key_env = "OLLAMA_API_KEY1"`로 등록한 게임만 KEY1을 쓴다(브라우저 설정에는 그 선택이 없어 기본은
  늘 KEY3). 매 호출마다 스위치를 다시 읽는다: 게임 중에 끄면 그 게임의 다음 호출은 403이고 KEY3로 바뀌지 않는다.
- `wrangler.toml`에 이 변수를 넣지 않았고 `keep_vars = true`라서 배포가 대시보드 값을 지우지 않는다.

## 로컬 전용 변수 (운영에 두지 말 것)

- `OLLAMA_BASE_URL`: Ollama 주소를 바꾼다(가짜 서버). `http://127.0.0.1:` · `http://localhost:`만 받아들인다.
