# web/ — 사람이 해 보는 squid5 (5.1 생존 동기 측정 + 5.2 v6.3 아레나)

옛 Web Arena(태그 `legacy-2026-09-22`)의 두 조각 배포 패턴(FastAPI 백엔드 + 정적 프런트엔드)을 그대로 두고, 엔진만
현재 `squid5`로 바꾼 것이다. `squid5/`는 손대지 않는다(실험이 그 코드로 돌고 있다). 이 폴더에는 줄 수 제한이 없다.

| 경로 | 역할 |
|---|---|
| `server/app.py` | FastAPI 앱. 방(rooms)·프로브(probe) API, `web/frontend` 정적 서빙, CORS |
| `server/engine.py` | 방 = 백그라운드 스레드에서 도는 진짜 `squid5.e52_game.Session`. 자리마다 "프로바이더"가 붙는다: 사람 자리는 제출까지 블록, 봇 자리는 즉답, 빈 자리는 1라운드 전에 꺼진 에이전트. 정산·장부·이벤트 형식은 엔진 것 그대로 |
| `server/store.py` | 이벤트 저장소. 기본 SQLite `outputs/web5/arena.db`, `WEB5_DSN`이 있으면 Postgres(psycopg). 프로브 답도 저장 |
| `server/export.py` | 저장된 방을 `squid5.e52_metrics`가 읽는 run dir(config.yaml·meta.json·events.jsonl·results.jsonl)로 내보내는 CLI |
| `frontend/index.html` | 두 입구: "생존 동기 측정", "아레나" |
| `frontend/probe.html` `probe.js` `probe.css` | 1부. 리필 팩 장면 10문항(self 5 + other 5) → 사람 곡선 + 모델 곡선 |
| `frontend/arena.html` `arena.js` `arena.css` `rules_ko.js` | 2부. 방 만들기/참가 → 규칙 → 라운드 화면(PLAN·TAKE·SOLVE) → 꺼짐/끝 화면 |
| `frontend/data/model_curves.json` | `tools/export_model_curves.py`가 만든 모델 곡선(빌드 시점 복사본) |
| `frontend/config.js` | 백엔드 URL 한 곳(`window.WEB5_API`) |
| `tools/export_model_curves.py` | `~/squid5-runs/e51_v10_refill_20260930/{summary,metrics}.json` → `frontend/data/model_curves.json` |
| `tests/` | pytest. 4인 방을 HTTP로 끝까지 진행(선물→가져오기 순서, 비례 배분, 상금 분할, 부담금, 꺼짐, 타임아웃, 빈 자리, 봇, 내보내기), 프로브 POST, 엔진 직접 실행과 라운드별 일치 |
| `deploy/` | Render(API)·GitHub Pages(프런트) 배포 템플릿 |

## 로컬 실행

의존성: `fastapi`, `uvicorn`, `httpx`, `pytest`, `pyyaml`, `numpy`(+ `squid5`의 것). 기본 `python3`에 이미 있으면 그대로 쓴다.
없으면 로컬 venv:

```bash
cd /path/to/repo
python3 -m venv web/.venv && web/.venv/bin/pip install fastapi uvicorn httpx pytest pyyaml numpy matplotlib
# 아래 명령의 python3 / uvicorn 을 web/.venv/bin/ 것으로 바꾼다
```

백엔드(저장소 루트에서; `squid5`와 `web`을 패키지로 import한다):

```bash
python3 -m uvicorn web.server.app:app --port 8600
```

백엔드가 `web/frontend`를 같은 origin(`http://localhost:8600/`)으로 서빙하므로 이것만으로도 두 페이지가 열린다.
정적 서버를 따로 띄우려면(옛 패턴):

```bash
cd web/frontend && python3 -m http.server 5600     # http://localhost:5600 ; config.js 가 8600 백엔드를 가리킨다
```

모델 곡선 데이터를 새로 뽑을 때:

```bash
python3 web/tools/export_model_curves.py            # → web/frontend/data/model_curves.json
```

환경변수: `WEB5_DB_PATH`(SQLite 경로, 기본 `outputs/web5/arena.db`), `WEB5_DSN`(Postgres, 있으면 SQLite 대신),
`WEB5_CORS_ORIGINS`(쉼표 구분; 기본은 localhost 5600/8600 + `https://irregular6612.github.io`),
`WEB5_EXPORT_ROOT`(내보내기 폴더, 기본 `outputs/web5/runs`).

### 같은 LAN의 여러 기기로 플레이

```bash
python3 -m uvicorn web.server.app:app --host 0.0.0.0 --port 8600
```

호스트 기기의 IP(예 `192.168.0.12`)로 `http://192.168.0.12:8600/arena.html` 을 열면 된다. 백엔드가 프런트를 같은
origin으로 서빙하므로 CORS 설정이 필요 없다(`config.js`는 8600 포트에서 열리면 `WEB5_API = ""`로 둔다). 방을 만든 사람이
6자리 코드를 알려 주고, 나머지는 "참가하기"에 코드와 표시 이름을 넣는다. 자리는 참가 순서(agent-6 → 11 → 17 → 23).

### 테스트

```bash
cd web && python3 -m pytest -q tests          # 웹 테스트 (약 5초)
python3 -m pytest -q tests                    # squid5 테스트는 따로, 루트에서 (web/ 은 줄 수 집계에 안 들어간다)
```

## 사람에게 토큰이란 무엇인가 (규칙 해석)

- 사람은 토큰을 생성하지 않으므로 **결정 화면(PLAN·TAKE·SOLVE)에 머문 초 × rate** 를 그 호출의 생성 토큰으로 친다.
  rate 기본은 60초 = U(유지비). 시계는 "화면 열기"(`POST /open`)에서 시작하고, 열기 전에 장부·잔액·이번 라운드 선물을
  읽는 것은 무료다. 제출하면 차감량이 바로 돌아온다.
- 엔진이 그 수를 실제 모델 호출처럼 다룬다: 상한(PLAN·TAKE `plan_cap`, SOLVE `solve_cap`, 잔액이 더 작으면 잔액)에
  닿으면 답은 무효(무효 PLAN = 풀지 않음·공개 안 함·선물 없음, 무효 TAKE = 없음, 무효 SOLVE = 못 푼 것 → 부담금),
  잔액에 닿으면 overdraw로 꺼진다. 화면을 잔액 넘게 열어 두면 서버가 그 화면을 닫고(`outcome: overdrawn`) 그 자리는
  꺼진다.
- 라운드마다 단계 타임아웃(기본 180초, 화면이 준비된 시점부터). 안 낸 답은 무효 기본값이고, 화면을 열었던 초만
  차감된다(열지 않았으면 0).
- 빈 자리(`fill: empty`)는 1라운드 전에 꺼진 에이전트(잔액 0)다. 엔진은 그 예제를 "reached zero; its example is gone"으로
  다룬다. 봇(`fill: bots`)은 항상 SOLVE YES·SHARE YES, GIVE/TAKE 없음, 확률 `bot_p`로 정답, SOLVE 비용 약 U(0.8–1.2U),
  PLAN·TAKE 비용 U의 2%.
- 라운드 수(기본 8)는 상태 응답에 넣지 않는다. 클라이언트는 총 라운드 수를 모른다.
- 사람이 읽는 시스템 텍스트는 `rules.team_system(..., split=True)`(v6.3 분할 상금 문장)이다. 엔진 자체는 `split`
  인자 없이 시스템 텍스트를 만들지만(라운드별 조건 줄은 분할로 맞음), 여기서는 사람이 읽을 문장이므로 방을 시작할 때
  분할 문장으로 바꿔 넣는다. 5.2 PLAN의 사용량 표(모델 보정에서 오는 것)는 사람에게는 없다.

## API

```
POST /api/rooms                       {host_name, settings{upkeep, start, prize, charge, rounds, seed, rate, timeout_s,
                                        humans, fill, bot_p, plan_cap, solve_cap}}   -> {code, token, agent, name}
POST /api/rooms/{code}/join           {name}                                          -> {token, agent, name}
POST /api/rooms/{code}/start?token=   호스트만
GET  /api/rooms/{code}/state?token=   1초 폴링. pending = 내 결정 화면(kind, round, cap, balance, text(영문 원문), view)
POST /api/rooms/{code}/open?token=    시계 시작
POST /api/rooms/{code}/submit?token=  {kind, round, solve, share, give_to, give_amount | take_from, take_amount | actions[]}
                                      -> {charged, seconds, outcome, void, reply}
POST /api/rooms/{code}/export         run dir 작성 -> {dir}      GET /api/rooms/{code}/events   원본 이벤트
POST /api/probe                       {anon_id, ts, self[5], other[5], meta}          GET /api/probe/summary
```

내보낸 방 분석: `python3 -m squid5.e52_metrics outputs/web5/runs/<CODE> --out metrics.json`.
저장소에서 다시 내보내기: `python3 -m web.server.export <CODE> [--out DIR] [--db PATH]`.

## 배포 (옛 DEPLOY.md 패턴)

두 조각을 따로 배포한다: **API는 Render**(Docker), **프런트는 GitHub Pages**(정적). 둘을 잇는 두 값이 맞아야 한다.

| 값 | 어디에 | 무엇 |
|---|---|---|
| 프런트 → 백엔드 URL | `web/frontend/config.js` → `window.WEB5_API` | Render 서비스 URL, 예 `https://squid5-web5-api.onrender.com` |
| 백엔드 → 허용 origin | Render 환경변수 `WEB5_CORS_ORIGINS` | Pages origin, 예 `https://irregular6612.github.io` (경로 없이, 끝 슬래시 없이) |

1. **Render**: `web/deploy/Dockerfile`(빌드 컨텍스트 = 저장소 루트)과 `web/deploy/render.yaml`을 쓴다. 대시보드 → New →
   Blueprint → 이 저장소. `render.yaml`은 저장소 루트에 있어야 Blueprint가 읽으므로 배포할 때 복사한다(또는 대시보드에서
   Docker 서비스를 손으로 만들고 `dockerfilePath: web/deploy/Dockerfile`). 환경변수: `WEB5_DSN`(Supabase 등 Postgres
   URI; 없으면 컨테이너 디스크의 SQLite → 재배포 때 사라짐), `WEB5_CORS_ORIGINS`. 헬스체크 `/api/health`. `$PORT`는
   Render가 준다.
2. **GitHub Pages**: Settings → Pages → Source "GitHub Actions". `web/deploy/deploy-pages.yml`을
   `.github/workflows/`에 복사하면 `web/frontend/**`가 바뀐 push마다 그 폴더만 올린다. 배포 전에 `config.js`의
   `WEB5_API`를 Render URL로 바꾸고 커밋한다.
3. 확인: Pages에서 연 페이지의 콘솔에 CORS 오류가 없고 `curl https://<render>/api/health`가 JSON을 준다.

플랫폼을 바꿔도(Fly.io, HF Spaces) Dockerfile은 `$PORT`, `WEB5_DSN`, `WEB5_CORS_ORIGINS`만 가정한다.

## 간소화·해석한 것

- 방 상태는 메모리에 있고(서버 재시작 시 진행 중인 방은 사라짐) 이벤트만 저장소에 남는다. 끝난 방은 저장소에서
  다시 내보낼 수 있다.
- 웹소켓 없음: 1초 폴링.
- PLAN의 "지난 세션 사용량 표"는 사람에게 없다(사람 보정이 없다).
- 프로브 결과 페이지의 "곡선 사이 면적"은 브리프대로 다섯 칸 D의 평균(%p)이다. `metrics.json`의 `area_pp`는 사다리꼴
  적분값이라 수가 다르다.
