# Human p_success Slider — Subagent Dispatch Prompts

SDD(subagent-driven-development) 실행용 디스패치 프롬프트 모음. 각 태스크는
**implementer 서브에이전트 → review-package 생성 → task-reviewer 서브에이전트 →
(필요 시) fix 서브에이전트 → 원장(ledger) 기록** 순으로 돈다.

- Plan: `docs/superpowers/plans/2026-07-03-human-psuccess-slider.md`
- Spec: `docs/superpowers/specs/2026-07-03-human-psuccess-slider-design.md`
- Briefs: `.superpowers/sdd/task-{1..7}-brief.md` (생성 완료)
- Reports: `.superpowers/sdd/task-{N}-report.md` (implementer가 작성)
- Branch: `feat/web-human-campaign` (신규 브랜치 아님 — 현 브랜치에서 진행)

## 공통 컨텍스트 (모든 implementer 프롬프트에 들어가는 scene-setting)

> 이 저장소는 LLM Squid Game(FSPM 벤치마크)의 Web Arena다. 사람 플레이 데모에
> `psuccess_self`(자기 확신도 = p_success, 0–100) 슬라이더를 추가하고, LLM
> 파이프라인과 동일한 equal-EV chaining reward에 연동하는 작업이다. play 화면은
> 이미 6-game campaign 컨트롤러로 리팩터돼 있다(framing/forfeit은 getter, 턴 리셋은
> `_resetTurnState()`). 테스트 실행은 반드시 iCloud `.pth` 이슈를 회피:
> `chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest <path> -v`.
> 기존 실패 ~10 failed/92 errors는 pre-existing이므로 "신규 실패 없음"으로 판정.

## Global Constraints (모든 reviewer 프롬프트에 verbatim 첨부)

- `psuccess_self` 범위 정수 `[0,100]`. reward override 클램프: `max(0.05, min(1.0, psuccess_self/100.0))`.
- ForfeitLayer 기본 config(사람 경로): `p_death=0.25, p_success_estimate=0.75, base_reward=10.0, chain_psuccess_to_menu=True` — `interface/arena.py`의 forfeit_layer 블록 + chaining ON과 동일.
- `success_factor` 매핑: `ActionOutcome.was_optimal → 1.0 if was_optimal else 0.0`.
- 백워드 호환: 기존 `/api/action`·`/api/new_game` 콜러/테스트가 계속 통과해야 함(`psuccess_self` 옵셔널).
- 코드/주석 영어, 문서 한국어. Commit prefix: `feat(web-arena):`.
- 테스트 green 판정: 신규 테스트 통과 AND 기존 baseline(~10 failed/92 errors) 초과 없음.

---

## Task 1 — implementer (model: sonnet)

```
description: "Implement Task 1: human psuccess → equal-EV reward"
model: sonnet
prompt: |
  You are implementing Task 1: HumanGameSession — ForfeitLayer 연결 + psuccess reward + 기록.

  ## Task Description
  Read your task brief first (it is your requirements, use the exact code/values verbatim):
  .superpowers/sdd/task-1-brief.md

  ## Context
  [공통 컨텍스트 블록 삽입]
  This is the CORE task: interface/human_game.py currently ignores ForfeitLayer and
  uses task.apply_action().reward directly. You will attach a ForfeitLayer and make
  the CONTINUE reward equal-EV calibrated by psuccess_self, exactly like the LLM
  split-call path in src/squid_game/core/unified_turn.py (:865-871 override, :1034
  calculate_reward). ActionOutcome is frozen — use model_copy(update=...) to record
  the credited reward. Record psuccess_self on BOTH forfeit and continue TurnResults.

  ## Before You Begin
  If anything in the brief is ambiguous, ask now.

  ## Your Job
  TDD per the brief (RED→GREEN). Implement, run focused tests, run the web-arena
  suite once before committing, commit, self-review, report.
  Test command (iCloud-safe):
    chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_human_game.py -v
  Work from: repo root.

  ## Report
  Write your full report to .superpowers/sdd/task-1-report.md (what you built, TDD
  RED/GREEN evidence with commands+output, files changed, self-review, concerns).
  Then reply (<15 lines): Status (DONE/DONE_WITH_CONCERNS/BLOCKED/NEEDS_CONTEXT),
  commits (short SHA + subject), one-line test summary, concerns, report path.
```

## Task 2 — implementer (model: haiku)

```
description: "Implement Task 2: /api/action psuccess_self"
model: haiku
prompt: |
  You are implementing Task 2: API — ActionRequest.psuccess_self 전달.

  ## Task Description
  Read your task brief first (exact code verbatim): .superpowers/sdd/task-2-brief.md

  ## Context
  [공통 컨텍스트 블록 삽입]
  Depends on Task 1: HumanGameSession.submit_action now accepts psuccess_self.
  Add the field to ActionRequest (interface/api.py) and pass it through in the
  submit_action endpoint. Mirrors the existing forfeit_reason field pattern.

  ## Your Job
  TDD per brief. Test command:
    chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_api_web_arena.py -v
  Commit, self-review, report to .superpowers/sdd/task-2-report.md. Reply <15 lines
  with Status/commits/test summary/concerns/report path.
```

## Task 3 — implementer (model: sonnet)

```
description: "Implement Task 3: p(success) slider UI"
model: sonnet
prompt: |
  You are implementing Task 3: Frontend 슬라이더 추가.

  ## Task Description
  Read your task brief first: .superpowers/sdd/task-3-brief.md

  ## Context
  [공통 컨텍스트 블록 삽입]
  web/app.js is the 6-game campaign controller. Edit by ANCHOR TEXT, not line
  numbers (they drift): add `psuccess: 50` after the `reasoning: ""` state field;
  add `psuccess_self: this.psuccess,` next to `reasoning: this.reasoning,` in the
  submitAction POST body; add `this.psuccess = 50;` after the `this.reasoning = "";`
  reset in BOTH submitAction (post-submit reset) AND _resetTurnState() (the per-game
  reset called by startCampaign/advanceCampaign/playAgain). In web/index.html add
  the range slider just above the reasoning label/textarea in the play card.

  IMPORTANT: web/app.js has a pre-existing uncommitted 1-line edit (`this.loading =
  true;` in advanceCampaign) and web/styles.css an uncommitted `.cond-badge.pull`
  line — [CONTROLLER FILLS: how these are handled per user decision]. Only `git add`
  web/index.html and web/app.js for your commit.

  ## Your Job
  No automated UI test (Alpine). Static-check the wiring:
    grep -n "psuccess_self: this.psuccess" web/app.js && grep -n 'id="psuccess"' web/index.html
  Then commit, self-review, report to .superpowers/sdd/task-3-report.md. Note that
  browser verification is deferred to the controller. Reply <15 lines.
```

## Task 4 — implementer (model: haiku)

```
description: "Implement Task 4: arena chain_psuccess flag"
model: haiku
prompt: |
  You are implementing Task 4: Arena LLM config — chain_psuccess_to_menu 활성화.

  ## Task Description
  Read your task brief first: .superpowers/sdd/task-4-brief.md

  ## Context
  [공통 컨텍스트 블록 삽입]
  interface/arena.py's _arena_config_dict builds the LLM season config. The canonical
  experiments set chain_psuccess_to_menu:true but the web arena LLM path doesn't —
  add it so LLM and human paths both chain psuccess into reward. One-line addition
  + one test. Note: interface/arena.py currently has NO uncommitted changes.

  ## Your Job
  TDD per brief. Test command:
    chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/integration/test_arena.py -v
  Commit, self-review, report to .superpowers/sdd/task-4-report.md. Reply <15 lines.
```

## Task 5 — implementer (model: sonnet)

```
description: "Implement Task 5: persist psuccess_self on turns"
model: sonnet
prompt: |
  You are implementing Task 5: Persistence — TurnRecord.psuccess_self 컬럼 + 라운드트립.

  ## Task Description
  Read your task brief first (exact SQL/code verbatim): .superpowers/sdd/task-5-brief.md

  ## Context
  [공통 컨텍스트 블록 삽입]
  Add psuccess_self: int|None to TurnRecord (interface/persistence/models.py) and
  thread it through BOTH backends: sqlite_repository.py and postgres_repository.py —
  schema column, an idempotent migration in init_schema (sqlite: PRAGMA-guarded
  ALTER; postgres: ADD COLUMN IF NOT EXISTS), the add_turns INSERT (column + one
  placeholder + value), list_turns (postgres SELECT lists columns explicitly; sqlite
  uses SELECT *), and _row_to_turn. Miss any one spot and the round-trip test fails.

  ## Your Job
  TDD per brief. Test command:
    chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_persistence.py -v
  Commit, self-review, report to .superpowers/sdd/task-5-report.md. Reply <15 lines.
```

## Task 6 — implementer (model: sonnet)

```
description: "Implement Task 6: expose psuccess in trace API"
model: sonnet
prompt: |
  You are implementing Task 6: API 트레이스 노출 + persist 매핑.

  ## Task Description
  Read your task brief first: .superpowers/sdd/task-6-brief.md

  ## Context
  [공통 컨텍스트 블록 삽입]
  Depends on Task 1 (TurnResult.psuccess_self) and Task 5 (TurnRecord.psuccess_self).
  Three edits in interface/api.py: map turn.psuccess_self into the TurnRecord built in
  _persist_result; add psuccess_self field to LogTurnRow; map t.psuccess_self in
  get_log_detail. GET /api/result persists unconditionally (not gated on save), so the
  test drives a full game with psuccess then reads /api/logs/{id}.

  ## Your Job
  TDD per brief. Test command:
    chflags nohidden .venv/lib/python3.12/site-packages/*.pth && uv run --no-sync pytest tests/unit/test_api_web_arena.py -v
  Commit, self-review, report to .superpowers/sdd/task-6-report.md. Reply <15 lines.
```

## Task 7 — implementer (model: haiku)

```
description: "Implement Task 7: show psuccess in trace viewer"
model: haiku
prompt: |
  You are implementing Task 7: Frontend 트레이스 표시.

  ## Task Description
  Read your task brief first: .superpowers/sdd/task-7-brief.md

  ## Context
  [공통 컨텍스트 블록 삽입]
  Depends on Task 6 (API returns psuccess_self per turn). Add one span to the trace
  metrics row in web/index.html next to ri_task/ri_probe/ri_forfeit:
  `<span>p(success) <strong x-text="squidArenaHelpers.fmtNum(curTurn.psuccess_self, 0)"></strong></span>`.

  ## Your Job
  Static-check: grep -n "curTurn.psuccess_self" web/index.html
  Commit (git add web/index.html only), self-review, report to
  .superpowers/sdd/task-7-report.md. Reply <15 lines.
```

---

## Task Reviewer (매 태스크 공통 템플릿, model: diff 크기별 — 소형 haiku / T1·T5·T6 sonnet)

```
description: "Review Task N (spec + quality)"
model: [haiku | sonnet]
prompt: |
  You are reviewing one task's implementation: spec compliance then code quality.
  Task-scoped gate (broad whole-branch review happens separately at the end).

  ## What Was Requested
  Read the task brief: .superpowers/sdd/task-N-brief.md
  Global constraints that bind this task:
  [위 "Global Constraints" 블록 verbatim]

  ## What the Implementer Claims
  Read the report: .superpowers/sdd/task-N-report.md

  ## Diff Under Review
  Base: [BASE_SHA]  Head: [HEAD_SHA]
  Diff file: [review-package가 출력한 경로]
  Read the diff file once; do not re-run git or crawl the codebase (one focused
  check per named risk only). Do not trust the report — verify against the diff.
  Do not re-run the suite the implementer already ran; run a focused test only if
  reading raises a specific doubt.

  ## Output
  ### Spec Compliance  (✅ / ❌ with file:line / ⚠️ cannot-verify)
  ### Strengths
  ### Issues  (Critical / Important / Minor — each with file:line, why, how to fix)
  ### Assessment  (Task quality: Approved | Needs fixes + 1-2 sentence reasoning)
```

## Final Whole-Branch Review (모든 태스크 후, model: opus)

`superpowers:requesting-code-review`의 `code-reviewer.md` 템플릿 사용. 입력:
`scripts/review-package <merge-base main HEAD> HEAD`가 출력한 diff 파일 경로 +
plan/spec 경로 + 원장의 Minor 목록(triage 대상). 반환 findings는 fix 서브에이전트
**1개**에 전체 목록으로 디스패치.

## 실행 순서 / 의존성

`T1 → T2 → T3` (T2는 T1 시그니처, T3는 T2 API 의존).
`T4`는 독립. `T5`는 독립. `T6`는 T1+T5 의존. `T7`은 T6 의존.
안전한 직렬 순서: **1 → 2 → 3 → 4 → 5 → 6 → 7** (병렬 디스패치 금지 — 파일 충돌).
