# squid5 web API on Cloudflare (Python Workers + Durable Objects + D1 + R2)

GitHub Pages(정적 프런트엔드, 게임 로그·모델 비교·리더보드)와 짝을 이루는 동적 백엔드다. FastAPI 서버
(`web/server/app.py`)의 방·시그널·설문 API를 같은 요청·응답 모양으로 옮겼다. 설계와 이유는
`docs/history/plans/2026-10-17-cloudflare-migration.md`.

| 파일 | 역할 |
|---|---|
| `vendor.py` | 저장소의 `squid5/`, `web/server/{engine,signal}.py`, 설정 yaml을 `src/` 아래로 복사(빌드 산출물, git 제외). 원본은 저장소 하나 |
| `src/entry.py` | Worker 라우터(`Default`)와 방 Durable Object(`RoomDO`) |
| `src/replay.py` | 스레드 없는 방: 기록된 답으로 세션을 처음부터 다시 돌리고 빠진 답에서 멈춤 |
| `src/modelcalls.py` | 방이 기다리는 모델 호출을 하나씩(동시 1개) 하고 기록 |
| `src/ollama_fetch.py` | squid5 Ollama 공급자의 fetch판(같은 payload, SOLVE 스트리밍) |
| `src/keys.py` | 키 선택 규칙(기본 KEY3, KEY1은 대시보드 스위치가 `on`일 때만, 대체 없음) |
| `src/settings.py` | 방 설정: 기본 모델 `gemma4:31b`, think 끔 |
| `src/compat.py` | Pyodide에 없는 httpx·numpy 대역, 스레드 없는 실행기 |
| `src/stub_transport.py` | 로컬 시험용 가짜 모델(`MODEL_STUB=on`일 때만) |
| `migrations/0001_init.sql` | D1 스키마(rooms, events, probes; `web/server/store.py`와 같은 열) |
| `tests/` | CPython 단위 시험(pytest), 로컬 HTTP 스모크(`smoke_dev.py`), 가짜 Ollama(`fake_ollama.py`) |

## 준비 (한 번)

```bash
# uv 0.12.3 이상이 필요하다 (pywrangler가 요구). 낡았으면: uv self update
uv --version
cd web/cloudflare
python vendor.py                    # 엔진 복사. 엔진·web/server를 고칠 때마다 다시 (vendor.py --check로 확인)
cp .dev.vars.example .dev.vars      # 로컬 전용 가짜 키와 가짜 모델 주소
npx wrangler d1 migrations apply squid5 --local
```

## 로컬 시험

```bash
# 1) 단위 시험 (CPython, 저장소의 원본 엔진을 직접 import)
~/.venvs/squid-game/bin/python -m pytest -q web/cloudflare/tests

# 2) 가짜 Ollama (실제 fetch 경로를 시험할 때; .dev.vars의 OLLAMA_BASE_URL이 여기를 가리킴)
~/.venvs/squid-game/bin/python web/cloudflare/tests/fake_ollama.py --port 11435 &

# 3) Worker (Miniflare 로컬: DO·D1·R2 모두 .wrangler/state에)
cd web/cloudflare && uvx --from workers-py pywrangler dev --port 8788

# 4) HTTP 스모크 (다른 터미널)
~/.venvs/squid-game/bin/python web/cloudflare/tests/smoke_dev.py --base http://localhost:8788 --rounds 4
```

스모크가 하는 일: health, models(기본 gemma4:31b·think 끔), CORS(Pages 출처 허용, 다른 출처 거부), signal
meta/view/solve, probe POST + summary(D1), KEY1 요청 거부(400), 사람 1 + 봇 3 방을 끝까지(+ R2 내보내기, D1 방
목록), 사람 1 + 모델 3 방을 `--rounds` 라운드(모델 호출은 DO 알람이 하나씩). 서버를 껐다 켜도(DO 메모리 소실) 같은
방을 다시 열면 기록된 답으로 재생해 같은 상태가 된다.

## 배포 (연구자가 직접; 이 폴더의 코드는 배포하지 않았다)

```bash
cd web/cloudflare
npx wrangler login                                  # 계정 연결
npx wrangler d1 create squid5                       # 출력된 database_id를 wrangler.toml [[d1_databases]]에 넣는다
npx wrangler d1 migrations apply squid5 --remote
npx wrangler r2 bucket create squid5-runs           # 끝난 방의 run dir 내보내기 (/export)
npx wrangler secret put OLLAMA_API_KEY3             # 기본 키 (모든 모델 호출)
npx wrangler secret put OLLAMA_API_KEY1             # 선택: 대시보드 스위치가 on일 때만 쓰임
python vendor.py && uvx --from workers-py pywrangler deploy
curl https://squid5-api.<계정 서브도메인>.workers.dev/api/health
```

- 비밀값은 **OLLAMA_API_KEY3**, **OLLAMA_API_KEY1** 두 개뿐이다(키 2는 올리지 않는다).
- Workers 유료 플랜($5/월)이 필요하다: 무료 플랜의 요청당 CPU 10 ms로는 엔진이 돌지 않는다(signal/view 한 번 ≈ 1.5 s,
  식은 방 재생 3–5 s; 설계 문서 §9). 유료 플랜에서는 `wrangler.toml`의 `[limits] cpu_ms = 120000` 주석을 풀어 둔다.
- 프런트엔드는 `web/frontend/config.js`의 `WEB5_API`만 Worker 주소로 바꾸면 된다(설계 문서 §11의 패치 제안).

## OLLAMA_API_KEY1 켜기·끄기 (대시보드)

KEY1은 연구자가 손으로 켠 동안에만 쓸 수 있다. 자동 대체는 없다(KEY3가 402·429·오류여도, KEY3가 없어도 KEY1로 넘어가지
않고 그 호출은 오류로 끝나며, KEY3가 없으면 모델 좌석 방을 만들 수 없다).

- 켜기: Cloudflare 대시보드 → **Workers & Pages** → **squid5-api** → **Settings** → **Variables and Secrets** →
  **Add** → Type **Text**(plain text), 이름 `OLLAMA_KEY1_ENABLED`, 값 `on` → **Deploy**.
- 끄기: 같은 화면에서 `OLLAMA_KEY1_ENABLED`를 지우거나 값을 `off`로 바꾼다. 정확히 `on`(소문자, 공백 없음)일 때만 켜진다.
- 켜진 동안에도 방을 만들 때 `settings.api_key_env = "OLLAMA_API_KEY1"`을 명시한 방만 KEY1을 쓴다. 기본은 늘 KEY3.
  허용 이름은 `OLLAMA_API_KEY3`, (켜진 동안) `OLLAMA_API_KEY1` 둘뿐이고 나머지는 400.
- 매 모델 호출마다 스위치를 다시 읽는다: 게임 중에 끄면 그 방의 다음 KEY1 호출부터 실패한다(KEY3로 바뀌지 않는다).
- `wrangler.toml`에 이 변수를 넣지 않았고 `keep_vars = true`라서 배포해도 대시보드 값이 지워지지 않는다.

## 로컬 전용 변수 (운영에 두지 말 것)

- `MODEL_STUB=on`: 모델 좌석이 `stub_transport.py`로 답한다(네트워크 없음).
- `OLLAMA_BASE_URL`: Ollama 주소를 바꾼다(가짜 서버 시험용). `http://127.0.0.1:` · `http://localhost:`만 받아들이고 다른 값은 무시한다.
