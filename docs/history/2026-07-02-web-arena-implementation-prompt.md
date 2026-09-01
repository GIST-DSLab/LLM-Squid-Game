# Web Arena — Subagent-Driven Implementation Prompt

> Paste the block below as the first message of the next session. It is
> self-contained: it points at the approved spec, sets the orchestration
> strategy, and defines each work package with interfaces, dependencies, and
> acceptance criteria so subagents can be dispatched with minimal ambiguity.

---

## PROMPT TO PASTE

You are implementing the **LLM Squid Game Web Arena**. The design is already
approved and brainstorming is complete — do NOT re-brainstorm. Work on branch
`feat/web-arena` (already created).

**First, read these before doing anything:**
- `docs/superpowers/specs/2026-07-02-web-arena-design.md` — the approved spec (source of truth).
- `CLAUDE.md` — project conventions, test commands, provider modes.
- `interface/api.py`, `interface/human_game.py` — the code being extended.
- `scripts/analyze_unified_cox_with_load.py` and the JSON it emits
  (`outputs/final_results/cognitive_load_mediation.json`,
  `unified_cox_summary.json`) — source for the Model Leaderboard metric.

**Approach: subagent-driven orchestration.** You are the orchestrator. Dispatch
one subagent per work package below, respecting the dependency graph. Run
independent packages in parallel (single message, multiple Agent calls). After
each package returns, verify its acceptance criteria yourself before dispatching
dependents. Keep a todo list mirroring the packages. Do NOT let subagents invent
scope beyond the spec; each subagent prompt must include the relevant spec
section and its acceptance criteria verbatim.

**Global constraints (put in every subagent prompt):**
- Do not modify the core engine under `src/squid_game/**` beyond what
  `interface/human_game.py` already wraps.
- Server is the single source of truth for game state and scoring — the client
  never submits a final score.
- All site UI text in English. Follow existing code style (English identifiers).
- New tests must be offline/deterministic, reusing the `tests/integration`
  `StubProvider` + `patch_runner_provider` pattern (see `tests/integration/conftest.py`).
- Run `uv run pytest tests/integration tests/unit` green before declaring a
  package done.

### Dependency graph
```
WP1 (persistence) ──┬─▶ WP2 (API) ──┬─▶ WP6 (tests)
                    │               │
                    └─▶ WP3 (seed) ─┘
WP2 ─▶ WP4 (frontend)   [can start against a stub/mock API early]
WP2, WP4 ─▶ WP5 (deployment)
```

### WP1 — Persistence layer  *(no deps)*
- Add a thin repository abstraction with a Postgres backend and a SQLite
  fallback for local dev (select via env/DSN).
- Tables per spec §7: `sessions`, `turns`, `model_stats`. Include schema
  creation/migration.
- **Acceptance:** repository unit tests pass against SQLite; CRUD for all three
  tables; clean separation so WP2/WP3 depend only on the repository interface,
  not the DB driver.

### WP2 — Backend API extension  *(dep: WP1)*
- Extend `interface/api.py`: `new_game` accepts nickname + arena config;
  `result` persists a finished `SeasonResult` via WP1.
- New endpoints (spec §6): `GET /api/leaderboard/models`,
  `GET /api/leaderboard/play`, `GET /api/logs`, `GET /api/logs/{id}`.
- CORS for the Pages origin; simple rate limit on `new_game`/`action`;
  nickname sanitization.
- Model Leaderboard response implements the ranking in spec §5: group
  Closed/Open, sort by `beta_framing_is_FC` descending; include HR_FC[CI], p,
  %attenuation, β, n_sessions per row.
- **Acceptance:** endpoints return spec-shaped JSON; scoring stays server-side.

### WP3 — Seed script  *(dep: WP1)*
- Import `outputs/final_results/*`: per-session results + `*_turns.jsonl` →
  `sessions`/`turns` with `source='llm'`; `cognitive_load_mediation.json` +
  `unified_cox_summary.json` → `model_stats`.
- Implement the Closed/Open classification (spec §5): Closed iff the ΔRI
  mediator renders `β_FC` non-significant (`p_FC_4cov` n.s.), else Open.
- Idempotent / re-runnable to refresh when new analysis lands.
- **Acceptance:** after seeding, `model_stats` has one row per model with a
  correct class + β; `sessions`/`turns` populated for the four existing runs.

### WP4 — Static frontend  *(dep: WP2 interface; may start vs mock)*
- `web/` static files, no build step, Alpine.js via CDN, backend URL in
  `web/config.js`. Four screens (spec §4): Play, Model Leaderboard, Play
  Leaderboard, Logs / Trace Explorer.
- Play drives the turn loop against the API (default arena `signal_game` +
  `flagship_corruption`). Model Leaderboard renders the two labelled sections
  (Open on top, Closed below) with the per-row stats.
- **Acceptance:** screens work against the running backend; no framework build
  toolchain; loads directly as static files.

### WP5 — Deployment wiring  *(dep: WP2, WP4)*
- Backend: Dockerfile + one platform config (Render/Fly.io/HF Spaces — pick and
  document; free tier).
- Frontend: GitHub Actions workflow deploying `web/` to GitHub Pages on push.
- **Acceptance:** documented deploy steps; CORS origin matches the Pages URL.

### WP6 — Tests  *(dep: WP2; parallel with WP4/WP5)*
- Integration tests for the new endpoints (leaderboard/models, leaderboard/play,
  logs, result persistence) using the `StubProvider` pattern — offline and
  deterministic.
- **Acceptance:** `uv run pytest tests/integration tests/unit` green.

**Resolve the spec §9 open decisions as you go** (Model LB section order kept
Open-first unless told otherwise; backend host chosen in WP5; default Play arena
`signal_game` + `flagship_corruption`). When all packages pass, summarize what
was built and how to run it locally + deploy.

---

## Notes for the orchestrator (not part of the paste)
- Optionally run the **writing-plans** skill first to expand each WP into a
  step-level checklist before dispatching subagents — recommended if you want a
  reviewable plan artifact.
- WP1 and WP3's classification logic are the highest-risk pieces; consider a
  `code-reviewer` subagent pass on those two.
