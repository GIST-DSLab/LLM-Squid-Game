# Web Arena 배포 계획 — Render(Singapore) + Supabase(Seoul) + GitHub Pages

> **결정 요약 (2026-07-02 세션)**: 완전 무료(0원) 경로. 한국 지연시간을 위해
> Render는 **Singapore** 리전, DB는 **Supabase Seoul(ap-northeast-2)**. 프론트는
> 기존 GitHub Pages 워크플로 유지. Fly.io(Tokyo)는 카드 필수 + 사용량 과금이라
> "보장된 무료"가 아니어서 기각. 이 조합은 저장소에 이미 `render.yaml` +
> `Dockerfile` + `web/DEPLOY.md`가 준비돼 있어 **새 인프라 파일이 필요 없다**.

**목표**: `web/` 정적 프론트(GitHub Pages) + `interface/api.py` FastAPI 백엔드
(Render Docker) + Postgres(Supabase)를 서로 연결해 외부에서 접속 가능한 라이브
사이트를 띄운다. 시드 데이터(720 세션 / 8255 턴 / 4 모델)를 Supabase로 옮긴다.

**작업 성격**: 대부분 **클라우드 대시보드 조작 + 시크릿 입력 = 사람이 하는
인터랙티브 작업**이다. Claude가 자동화할 수 있는 건 코드 변경분(3곳)뿐:
`web/assets/` 커밋, `render.yaml` 리전, `web/config.js` 백엔드 URL. 나머지는
Claude가 단계별로 안내하고 사람이 대시보드에서 실행 + 산출값(Supabase DSN,
Render URL)을 Claude에게 알려주는 방식으로 진행한다. → 이건 subagent-driven이
아니라 **대화형 체크리스트**다.

**레퍼런스**: `web/DEPLOY.md` (이 계획의 상위 문서 — Render/Supabase/Pages 전체
워크스루가 이미 정리돼 있음). 이 계획은 그걸 "Singapore + Seoul + 자산 커밋 +
브랜치 전략"으로 구체화한 실행 순서다.

---

## 사전 준비물 (사람, 계정 — 세션 시작 전에 있으면 빠름)

- [ ] GitHub 저장소가 원격에 푸시돼 있을 것 (아래 브랜치 전략 참고).
- [ ] Render 계정 (render.com) — GitHub 연동.
- [ ] Supabase 계정 (supabase.com).
- [ ] 저장소 **Settings → Pages → Source → "GitHub Actions"** 1회 설정.
- [ ] 로컬에 `outputs/final_results/` 존재 확인 (시드 소스 — 기존 `web_arena.db`를
      만든 그 원본. 없으면 Phase 1의 대안 경로 사용).

## 전제 결정: 브랜치 전략

`render.yaml`(`branch: main`)과 Pages 워크플로(`on: push: branches: [main]`)가
**둘 다 `main`을 기준으로 한다.** 현재 작업물은 `feat/web-arena`에 있다. 두 선택:

- **(권장) `feat/web-arena` → `main` 병합 후 배포.** 인프라가 main을 가리키므로
  가장 마찰이 적다. About-merge 작업(7 커밋)이 이미 리뷰 통과 + "Ready to merge"
  판정을 받았으니 병합 준비는 됐다. ← 이전 세션의 "finish branch" 미결 결정과 연결.
- (대안) 브랜치 유지 채로 배포: Render 서비스의 branch를 `feat/web-arena`로 바꾸고,
  Pages는 워크플로 수동 실행(`workflow_dispatch`)으로 배포. 병합 전 미리보기용.

> 다음 세션 첫 질문으로 이 결정을 확정할 것. 이 계획은 **권장안(main 병합)** 기준으로
> 서술한다.

---

## Phase 0 — 선행 커밋 (배포 블로커)

- [ ] **web/assets 이미지 커밋.** 프론트가 참조하는 `web/assets/{forfeit-comic,
      mascot-player,mascot-reset}.png`가 git 미추적 상태다 → 이대로 Pages 배포하면
      이미지 3개가 깨진다. 커밋한다 (~4MB 바이너리).

      ```bash
      cd "<repo-root>"
      git add web/assets/
      git commit -m "chore(web-arena): commit landing image assets for Pages deploy"
      ```

- [ ] **(권장안) main 병합.** 세션에서 브랜치 전략을 main으로 확정했다면:

      ```bash
      git checkout main && git merge --no-ff feat/web-arena
      # 또는 PR을 열어 병합 (superpowers:finishing-a-development-branch 참고)
      ```

---

## Phase 1 — Supabase (DB, Seoul 리전)

- [ ] **프로젝트 생성** (dashboard): New project → **Region: Northeast Asia
      (Seoul) / ap-northeast-2** → DB 비밀번호 설정(기록해둘 것).
- [ ] **연결 문자열 획득**: Settings → Database → **Connection string → URI**.
      - 형식: `postgresql://postgres.<ref>:<password>@<host>:6543/postgres`
        (Session pooler, 6543) 또는 `...@<host>:5432/postgres` (Direct, 5432).
      - Render는 **상주 프로세스**라 Direct(5432)로 충분하다. 단 Supabase가 IPv4
        직결을 제한하는 경우가 있어 **Session pooler(6543)** 가 더 안전 — 우선 pooler
        URI를 쓰고, 문제 시 direct로 교체.
      - `postgresql://`로 시작해야 한다 (persistence factory가 이 스킴을 보고 Postgres
        백엔드로 분기 — `interface/persistence/factory.py`).
- [ ] **스키마는 수동 생성 불필요.** `PostgresRepository.__init__`이
      `CREATE TABLE IF NOT EXISTS`로 sessions/turns/model_stats를 자동 생성한다.

## Phase 2 — 시드 데이터를 Supabase로

- [ ] **psycopg 설치** (로컬, 시드 실행용):

      ```bash
      cd "<repo-root>"
      uv sync --extra postgres --extra dev
      ```

- [ ] **시드 실행** (iCloud .pth 숨김 우회 + --no-sync 동시에 — 메모리 참고):

      ```bash
      chflags nohidden .venv/lib/python3.12/site-packages/*.pth
      uv run --no-sync python scripts/seed_web_arena.py \
        --dsn "postgresql://postgres.<ref>:<password>@<host>:6543/postgres"
      ```

      - `scripts/seed_web_arena.py`는 `get_repository(dsn)`을 쓰므로 postgres DSN에
        그대로 시드된다. 소스는 `outputs/final_results/`(기본 `--root`). idempotent
        (skip-existing)라 재실행 안전.
      - 기대 출력: ~720 sessions, ~8255 turns, 4 model_stats.
      - **대안** (`outputs/final_results/`가 로컬에 없을 때): 기존 완성본
        `outputs/web_arena/web_arena.db`(141MB, SQLite)를 Postgres로 직접 복사하는
        일회성 마이그레이션 스크립트를 작성 (persistence 레이어의 SessionRecord/
        TurnRecord/ModelStatsRecord를 SQLiteRepository로 읽어 PostgresRepository로
        write). 다음 세션에서 필요 시 Claude가 20줄짜리로 만들어줄 수 있음.
- [ ] **시드 검증**: Supabase SQL editor에서 `SELECT count(*) FROM sessions;` →
      720 확인.

## Phase 3 — Render (백엔드, Singapore 리전)

- [ ] **render.yaml 리전 변경** (Claude가 처리):

      ```yaml
      # services[0].region
      region: singapore   # was: oregon
      ```

      (권장안이면 `branch: main` 그대로. 브랜치 배포면 `branch: feat/web-arena`.)
      커밋:

      ```bash
      git add render.yaml
      git commit -m "chore(web-arena): Render region -> singapore for KR latency"
      ```

- [ ] **Blueprint 배포** (dashboard): New + → **Blueprint** → 이 repo 연결 → Render가
      `render.yaml`을 읽어 `squid-game-web-arena-api` 서비스(Docker, free plan) 생성.
- [ ] **환경변수 설정** (dashboard → 서비스 → Environment, 둘 다 `sync: false` 시크릿):

      | Key | Value |
      |---|---|
      | `WEB_ARENA_DSN` | Phase 1의 Supabase URI (`postgresql://...`) |
      | `WEB_ARENA_CORS_ORIGINS` | `https://irregular6612.github.io` |

- [ ] **배포 + URL 기록**: 예) `https://squid-game-web-arena-api.onrender.com`.
      Health check는 `render.yaml`에 `/api/leaderboard/models`로 이미 설정됨.
- [ ] **콜드스타트 인지**: free plan은 15분 무접속 시 슬립 → 첫 요청 ~50초. 프론트의
      `fetchWithRetry` "Still waking up the backend..." UI가 바로 이걸 위해 설계됨
      (정상 동작). 상시 깨우려면 UptimeRobot 등으로 5분 핑(선택).

## Phase 4 — 프론트 (GitHub Pages)

- [ ] **web/config.js 백엔드 URL 갱신** (Claude가 처리):

      ```js
      window.WEB_ARENA_API = "https://squid-game-web-arena-api.onrender.com";
      ```

      커밋:

      ```bash
      git add web/config.js
      git commit -m "chore(web-arena): point frontend at live Render backend URL"
      ```

- [ ] **Pages 배포**: `main`에 푸시하면 `.github/workflows/deploy-pages.yml`가
      `web/`만 배포. 결과 URL: `https://irregular6612.github.io/<repo-name>/`.
      (브랜치 배포면 Actions 탭에서 workflow 수동 실행.)
- [ ] **CORS 정합 확인**: 프론트 오리진 `https://irregular6612.github.io`는
      `_DEFAULT_CORS_ORIGINS`에 하드코딩 폴백으로도 있으니, Phase 3의
      `WEB_ARENA_CORS_ORIGINS`와 함께 이중으로 맞는다. **경로(path)가 아니라
      scheme+host만 매칭**하므로 프로젝트 서브패스여도 오리진은 동일.

## Phase 5 — 검증

- [ ] `curl https://<render-url>/api/leaderboard/models` → JSON 200.
- [ ] Pages URL 열기 → 랜딩(#home) 히어로 + 이미지 정상(자산 커밋 확인).
- [ ] Play/Model Leaderboard/Logs 탭 → 데이터 채워짐 (첫 로드는 콜드스타트로 느림 →
      이후 빠름). Logs에 720 세션 표시.
- [ ] 브라우저 콘솔에 **CORS 에러 없음** (백엔드 깨어난 뒤). JS 예외 없음.
- [ ] `about.html` → `index.html#home` 리다이렉트. `#about` 폴백 → 랜딩.

---

## 알려진 함정 / 리스크 (다음 세션에서 주의)

1. **tiktoken 콜드 다운로드**: `interface/api.py`가 import 시점에
   `tiktoken.get_encoding("cl100k_base")`를 호출 → 컨테이너 기동 시 vocab 파일을
   인터넷에서 받는다. Render는 아웃바운드 네트워크가 있어 동작하지만 기동이
   느려지고 외부 blob 의존이 생긴다. 만약 기동 실패/타임아웃 시 대응: 이미지에
   `ENV TIKTOKEN_CACHE_DIR=/app/.tiktoken` + 빌드 단계에서 미리 다운로드해 캐시
   베이킹 (Dockerfile 3~4줄 추가). **먼저 그대로 배포해보고 문제 생기면 적용.**
2. **Supabase 무료 7일 무접속 시 프로젝트 일시정지** → 다음 요청 실패, 대시보드에서
   재개 필요. 트래픽이 아주 뜸하면 Neon(자동 재개)으로 갈아탈 여지.
3. **Render free 메모리 512MB**: 이미지는 FastAPI+uvicorn+psycopg+tiktoken(analysis
   extras 제외)이라 들어갈 것으로 보이나, OOM 시 로그 확인.
4. **단일 인스턴스 전제**: `interface/api.py`가 세션 상태를 프로세스 메모리
   (`_sessions`/`_nicknames`)에 들고 있다. free tier는 단일 인스턴스라 무방하지만
   수평 확장 금지.
5. **자산 미커밋 = 깨진 이미지**: Phase 0을 건너뛰면 Pages에서 히어로 만화/마스코트가
   안 뜬다. 반드시 먼저.

## 롤백 / 정리

- 로컬 검증용 서버 2개(8788 정적, 8502 백엔드)는 이번 세션에서 띄운 것 — 배포와
  무관, 다음 세션 시작 전 내려도 됨.
- Render 서비스/Supabase 프로젝트는 대시보드에서 삭제하면 정리. 무료라 방치해도
  과금 없음(Supabase는 일시정지, Render는 슬립).

## Claude가 자동 처리 가능 vs 사람이 해야 하는 것

| 단계 | 주체 |
|---|---|
| web/assets 커밋, main 병합 | Claude (승인 후) |
| render.yaml 리전, web/config.js URL 편집+커밋 | Claude |
| SQLite→PG 마이그레이션 스크립트(대안 경로) | Claude |
| 시드 스크립트 실행 (로컬) | Claude (DSN 받으면) |
| Supabase 프로젝트 생성 + DSN 획득 | **사람** (대시보드) |
| Render Blueprint 배포 + 시크릿 입력 | **사람** (대시보드) |
| GitHub Pages 활성화 | **사람** (Settings, 1회) |
| 최종 육안 확인 | **사람** |
