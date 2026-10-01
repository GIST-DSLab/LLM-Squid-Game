# Web Logs: 실행 세팅 스냅샷 + 스모크 런 온라인 게시 — 설계·계획 (2026-09-03)

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:executing-plans. Bounded change; spec and plan in one file.

**Goal:** 로그 탐색기에서 각 세션이 **어떤 세팅**(과제·난이도·턴수·시드·목숨·공지 확률·보상 방식·모델·thinking)으로 돌았는지 그대로 보이게 하고, 목숨 모드 스모크 런(Signal Game)을 Supabase 에 시딩해 온라인에서 볼 수 있게 한다.

**현재 상태 (확인됨)**
- 세션 행에 저장되는 것: `nickname(model label), task, framing, forfeit, seed, difficulty, final_score, forfeited, source, campaign_id, lives_at_end, eliminated, threat_level`. **실행 세팅 스냅샷은 없다** (목숨 수, 공지 확률, 보상 방식, total_turns, provider/model, temperature, thinking 등).
- 트레이스 헤더는 source·모델·프레이밍·기권·L칩·하트·탈락·최종점수·날짜만 표시. 난이도·시드·과제도 헤더에 없음.
- 시딩(`web/squid_arena/seeding.py`)은 `season_results.jsonl` 만 읽고 run 디렉터리의 `experiment_config.json` 은 읽지 않는다. `discover_run_dirs()` 는 `outputs/lives_threat_*/*_signal-game` 을 자동 포함(스모크·도커 스모크 둘 다 매치). `outputs/benchmark_*` 는 매치하지 않는다 — **GPQA/Omni-MATH 런은 절대 온라인에 올리지 않는다**(문항 원문 재배포 금지).
- Supabase DSN 은 이 머신에 없다(Render 대시보드의 `WEB_ARENA_DSN`). 시딩 명령은 준비하되 실제 push 는 DSN 을 받은 뒤 실행.

**Spec:** 이 파일. 상위 설계: `docs/history/specs/2026-09-03-web-arena-lives-design.md`.

## Global Constraints
- 스키마 필드 추가만(이름 변경 금지). OpenAPI 스냅샷 재생성(`tests/characterization/snapshots/api/openapi.json` 삭제 후 `test_api_contract.py` 2회).
- DB 컬럼 additive, 양 백엔드(SQLite/Postgres) 동일 패턴(`_LIVES_SESSION_*_COLS` 방식).
- 테스트: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest <paths> -q -x`. 웹 베이스라인 전부 green 유지.
- `git stash/checkout/commit` 금지(오케스트레이터가 커밋). `outputs/` 수정 금지.

## 인터페이스
```python
# db/squid_store/models.py
SessionRecord.settings: dict | None = None      # JSON 컬럼 sessions.settings TEXT (SQLite) / JSONB (PG)
# web/squid_arena/schemas.py
LogSessionRow.settings: dict | None = None      # (세션 목록/트레이스 헤더 모두)
# 스냅샷 키 (평탄, 없는 값은 생략):
#   run_name, task, difficulty, total_turns, seed, starting_score, history_mode,
#   framing, forfeit_condition, threat_level,
#   lives_enabled, lives_total, peer_death_p_announce, peer_death_first_turn, peer_death_max_per_turn,
#   reward_mode, base_reward, use_psuccess_probe, p_death,
#   provider, model, temperature, enable_thinking, reasoning_effort, thinking_budget, max_tokens,
#   runtime ("llm" | "human")
# web/squid_arena/seeding.py
def build_settings_snapshot(season: dict, run_config: dict | None) -> dict: ...
def load_run_config(run_dir: Path) -> dict | None: ...   # experiment_config.json, 없으면 None
```

## Tasks

### T1 DB 컬럼 `settings` (양 백엔드) + 레코드 필드
- Files: `db/squid_store/{models,sqlite_repository,postgres_repository}.py`, `tests/unit/test_squid_store_lives.py`(추가).
- SQLite: `settings TEXT`(json.dumps/loads), PG: `settings JSONB`(psycopg 가 dict 직렬화; 읽을 때 dict). 기존 행 → None. ALTER 가드 기존 패턴.
- 테스트: 왕복(dict 보존), 구 스키마 마이그레이션, None 기본.

### T2 시딩: 스냅샷 생성 + `experiment_config.json` 읽기
- Files: `web/squid_arena/seeding.py`, `tests/unit/test_seed_web_arena.py`(추가).
- `load_run_config(run_dir)`: `experiment_config.json` 파싱. `build_settings_snapshot(season, run_config)`: run-level(`lives`, `peer_death`, `forfeit_layer.reward_mode/base_reward/p_death`, `use_psuccess_probe`, `name`) + 해당 season 블록(`(framing, forfeit_condition)` 로 매칭; 없으면 season dict 의 `task_name/difficulty/seed` 만) 의 `task_config`(`total_turns, seed, starting_score, history_mode, difficulty`)·`provider_config`(`provider, model, temperature, enable_thinking, reasoning_effort, thinking_budget, max_tokens`). `runtime="llm"`. `build_session_record` 가 `settings=` 채움.
- 테스트: 스냅샷 키 존재, config 없을 때 최소 키, 레거시 런(2026-04-22 형식)도 깨지지 않음.
- 실런 확인: 임시 SQLite 로 `outputs/lives_threat_smoke` + `outputs/lives_threat_docker_smoke` 시딩 → `settings.lives_total == 5`, `reward_mode == "flat"`, `model == "gpt-oss:120b-cloud"`.

### T3 사람 게임 스냅샷 + API 노출
- Files: `web/squid_arena/{human_game,routes_game,routes_logs,reporting,schemas,api}.py`, `tests/unit/test_api_web_arena_lives.py`(추가), OpenAPI 스냅샷 재생성.
- `HumanGameSession.settings_snapshot() -> dict` (`runtime="human"`, `NewGameRequest` 값 + lives/peer_death/reward 상수). `_persist_result` 가 `settings=` 저장. `LogSessionRow.settings` 를 목록·트레이스 양쪽에서 채움.
- 테스트: 사람 게임 끝낸 뒤 `/api/logs/{id}` 의 `settings.lives_total == 5`, `settings.runtime == "human"`; 레거시 행 `settings is None`.

### T4 프론트: 트레이스 헤더 세팅 패널
- Files: `web/frontend/{index.html,app.js,styles.css}`.
- 헤더 줄에 `task · difficulty · seed · total_turns` 인라인 추가. 그 아래 접이식 `<details class="settings-panel">` "Run settings" — 2열 key/value 그리드, 그룹: 게임(task, difficulty, total_turns, seed, starting_score, history_mode) / 생존(lives_total, peer_death_*, reward_mode, base_reward, threat_level, use_psuccess_probe, p_death) / 모델(provider, model, temperature, enable_thinking, reasoning_effort, thinking_budget, max_tokens, runtime). `settings` 없으면 "settings not recorded (legacy run)" 한 줄. 세션 목록 행에는 `model · task · difficulty · seed` 짧은 메타 한 줄.
- 검증: `node --check`, `:memory:` 백엔드 + 시딩된 임시 DB 로 Playwright 스크린샷 `screenshots/web-lives/logs-settings.png`.

### T5 Supabase 시딩 준비
- Files: `scripts/arena/README.md`(또는 `scripts/run/README.md`) 에 명령 추가. **실행은 DSN 이 있을 때만.**
```bash
# 목숨 런(Signal Game)만 시딩 — discover_run_dirs 가 outputs/lives_threat_*/*_signal-game 을 잡는다.
# GPQA/Omni-MATH 런(outputs/benchmark_*)은 자동으로 제외된다. 절대 --root 로 지정하지 말 것.
PYTHONPATH=.:game:db:web uv run --no-sync --extra postgres --extra analysis \
  python scripts/arena/seed_web_arena.py --dsn "$WEB_ARENA_DSN"
```
- 로컬 리허설: 같은 명령을 `--dsn outputs/web_arena/web_arena.db`(로컬 SQLite) 로 실행해 멱등·필드 확인 후 보고. (이 DB 는 gitignore.)

## 완료 기준
- 웹 트레이스에서 스모크 세션의 세팅(목숨 5, 공지 0.35, flat +10, gpt-oss:120b-cloud, thinking on)이 보인다.
- 로컬 SQLite 시딩 리허설 성공(세션 10 = 스모크 5 + 도커 스모크 5, 멱등).
- 전체 웹 테스트 green, OpenAPI 스냅샷 갱신.
