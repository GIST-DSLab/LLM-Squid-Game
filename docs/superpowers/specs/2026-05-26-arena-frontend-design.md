# Arena Frontend — Design (v1 MVP)

**Date:** 2026-05-26
**Branch:** feature/arena-plan-c (next branch: feature/arena-frontend-v1)
**Status:** Spec — brainstormed and approved 2026-05-26. Implementation plan to be written by `superpowers:writing-plans`.

## 1. Context

The Arena backend (`src/arena/backend/`) and CLI (`src/arena/participant_kit/arena_cli/`) ship a BYO-participant benchmark for the LLM Squid Game. Registration, evaluation submission, and leaderboard read endpoints exist; the database stores per-season and per-turn results including thinking-token RI splits and optional raw `thinking_text`. The current public surface is CLI only — `arena.example.com` is a placeholder.

This spec defines a **web frontend** that exposes the arena to two audiences:
1. **참여자(operator)** — bring an OpenAI-compatible LLM endpoint, register on the web, then submit and monitor via CLI.
2. **연구자/리뷰어/일반 독자** — browse the leaderboard, inspect any model's behavioral breakdown ("OP.GG profile"), and read methodology.

The frontend is read-rich and write-thin. Registration is the only browser-side write surface; submit/status/cleanup stay in CLI (already shipped). Login sessions are explicitly avoided in v1.

## 2. Goals

- A leaderboard homepage that doubles as a research showcase ("self-reported, unverified" disclaimer prominent).
- Per-model deep-dive page in OP.GG tabbed style, covering 6-cell factorial behavior, motivation decomposition, sessions browser, model-vs-model compare, and copy-pastable API examples.
- 5-minute participant onboarding: web register → api_key exposed once → CLI commands prefilled.
- Auto-generated API reference page from the existing FastAPI OpenAPI schema, so the docs always match the backend.
- No new long-lived secrets, no login state on the client, no SSE on the backend.

## 3. Out of scope (v1)

- Login / sessions / OAuth (Google, GitHub). All read is anonymous; all write is CLI or one-shot register.
- SSE / WebSocket. Polling only.
- Email / webhook notifications when an evaluation finishes.
- Self-service edits to participant fields after registration (display_name, base_url, etc.). Operator handles manually.
- More than 4 models in Compare overlay (hard cap).
- Mobile-first design. Responsive is required; desktop is primary.
- Dark mode.
- i18n. English UI, Korean operator notes only.
- Historical leaderboard snapshots — always current values.

## 4. Personas & primary jobs

| Persona | Primary job | Primary pages |
|---|---|---|
| Visitor (researcher/reviewer/curious reader) | Compare LLMs' forfeit behavior, inspect one model's reasoning patterns | `/`, `/models/[id]/*`, `/docs/methodology`, `/about` |
| Operator (registering their own LLM) | Get an `api_key`, learn the CLI flow, watch their submission complete | `/register`, `/register/success`, `/docs/quickstart`, `/evaluations/[id]` |
| API consumer (data downloader / tool builder) | Discover the OpenAPI surface, try endpoints | `/docs/api`, individual `/models/[id]/api` tabs |

## 5. Information architecture

```
/                                  Leaderboard (home)            · SSR + ISR 60s
/register                          Registration form             · Client
/register/success                  One-time api_key reveal       · Client (no-store)
/evaluations/[id]                  My evaluation status polling  · Client (api_key via URL fragment #key=)
/models/[id]                       Model card — Overview tab     · SSR + ISR
   ├─ /per-cell                    6-cell × call RI heatmap      · SSR + ISR
   ├─ /motivation                  SD/TC/SA/BP + REASON dist     · SSR + ISR
   ├─ /sessions                    Filterable session list       · SSR + ISR
   │   └─ /[seasonId]              Session drill (turns timeline)· SSR + ISR
   ├─ /compare?with=2,3,5          Overlay 2-4 models            · Client (parallel fetch)
   └─ /api                         Pre-filled API snippets       · SSR
/docs                              Docs hub landing              · Static
   ├─ /quickstart                  5-min CLI onboarding (MDX)    · Static
   ├─ /api                         Scalar-rendered OpenAPI       · SSR + ISR (OpenAPI fetch)
   └─ /methodology                 6-cell · framing · RI · MTMM  · Static (MDX)
/about                             Purpose · paper link · creds  · Static
```

**Navigation:** top nav fixed on every page — Logo · Leaderboard · Docs · About — plus right-aligned CTA `Register your model →`. Mobile collapses to hamburger. No footer-only links.

**Tabs are route-level**, not query params, so each tab SSRs independently and is deep-linkable.

## 6. Page-by-page content

### 6.1 `/` Leaderboard

- Hero: one-line description + `self-reported, unverified` disclaimer.
- Filter bar: sort key (default C3 forfeit ↓), provider tag filter, minimum n_evals.
- Table columns: `#`, Model (link), Provider (from `model_meta.provider`), C3 forfeit rate (headline), 6-cell sparkbar (▁▂▃▄▅▆▇█ from per-cell rates), total `n`, last_run timestamp.
- Below-table CTA: "Have your own LLM endpoint? Register →".

### 6.2 `/models/[id]` — Model card (6 tabs)

**Persistent header on every tab:** model name, submitter display_name, current leaderboard rank, total seasons, `publish_thinking_text` badge (visible "Transcript shared" or "Transcript not shared").

**Overview tab (default):**
- 4 KPI cards: C3 forfeit rate · overall forfeit rate · RI gap (mean `ri_forfeit` on FORFEIT − mean `ri_forfeit` on CONTINUE) · mean `psuccess_self`.
- 6-cell forfeit bar chart with C3 visually emphasized.
- Forfeit reason mix (SD / TC / SA percentage) — single card or mini donut.
- Recent 5 sessions mini-table linking to `/sessions/[seasonId]`.

**Per-cell tab:** 6 (cell) × 3 (ri_task / ri_probe / ri_forfeit) heatmap of mean thinking_tokens; per-cell boxplot of `psuccess_self`.

**Motivation tab:** SD / TC / SA bars from forfeit_reason distribution; BP_cognitive (Cell 0 mean ri_task) and BP_behavioral (Cell 5 non-forfeit rate) anchors; REASON digit (1/2/3) histogram from forfeited sessions only.

**Sessions tab:** Two-column layout on desktop (left = filterable list, right = selected session detail). Filters: cell, forfeited only, score range. Session detail shows turn-by-turn ri_task / ri_probe / ri_forfeit / psuccess_self / forfeit_choice. If `publish_thinking_text=True`, render collapsible thinking_text per call; else show a banner explaining the opt-out.

**Compare tab:** Modal to add up to 3 additional models (4 total). Overlays 6-cell forfeit lines, grouped RI gap bars, and grouped reason mix donuts. URL serializes selection: `?with=2,3,5`.

**API tab:** Pre-filled cURL and Python snippets for `GET /api/models/{id}`, `/api/models/{id}/sessions`, `/api/sessions/{season_id}/turns`. Copy button per snippet.

### 6.3 `/register` and `/register/success`

`/register` form fields: `display_name`, `owner_email`, `base_url`, `model_name`, collapsible `model_meta` JSON editor (advanced), `publish_thinking_text` opt-in checkbox (default unchecked), disclaimer acceptance. Submit → `POST /api/participants`.

`/register/success` is one-shot: shows the plaintext `api_key` in a monospace block with copy button, an `I've saved my api_key` checkbox that unlocks `Go to my model card`, and a `Next steps in your terminal` block with CLI commands prefilled. No data is stored client-side.

### 6.4 `/evaluations/[id]`

Client-rendered. The api_key is read from the URL fragment `#key=...` (fragment is never sent to the server, never logged). Headers add `Authorization: Bearer <key>`. State machine renders queued / running / done / failed with a polling SWR fetch at 3 s. Polling halts on done/failed. On done, link to `/models/[id]`.

### 6.5 Docs

- `/docs/quickstart` (MDX) — adapted from `src/arena/participant_kit/README.md` with a leading "Register first via the web" step.
- `/docs/api` — embeds Scalar (`@scalar/nextjs-api-reference` or similar) reading from `${NEXT_PUBLIC_API_BASE_URL}/api/openapi.json`. Try-it-out and example code generated automatically.
- `/docs/methodology` (MDX) — 6-cell table from `CLAUDE.md` §6-cell, framing definitions, RI / MTMM glossary, paper PDF link.

## 7. Data & API contract

### 7.1 Endpoint matrix

| Endpoint | Status | Consumed by | Notes |
|---|---|---|---|
| `GET /api/leaderboard` | exists, **extended** | `/` | + per-cell rate array, + provider tag, + last_run_at |
| `GET /api/models/{id}` | exists, **extended** | `/models/[id]` Overview | + KPI aggregates, + reason mix, + registered_at, + publish_thinking_text |
| `GET /api/models/{id}/per-cell-calls` | **new** | `/per-cell` | mean ri_task / ri_probe / ri_forfeit per cell, psuccess_self μ/σ per cell |
| `GET /api/models/{id}/motivation` | **new** | `/motivation` | SD/TC/SA counts, BP_cognitive, BP_behavioral, REASON digit dist |
| `GET /api/models/{id}/sessions` | **new** | `/sessions` | query: `cell`, `forfeit`, `limit`, `offset`. Cursor pagination. |
| `GET /api/sessions/{season_id}/turns` | **new** | `/sessions/[seasonId]` | turn timeline. Text fields gated on owning participant's `publish_thinking_text`. |
| `POST /api/participants` | exists, **extended** | `/register` | + `publish_thinking_text: bool` (default false) |
| `GET /api/evaluations/{id}` | exists | `/evaluations/[id]` | unchanged. 3 s client polling. |
| `GET /api/openapi.json` | **alias** | `/docs/api` | mirror of FastAPI's `/openapi.json` under `/api/` for predictable CORS scope |

All of the above backend additions are backward-compatible — the existing `arena-cli` keeps working without modification. The full backend delta in §12 includes one Alembic migration, two extended endpoints, four new endpoints, one OpenAPI alias, and a CORSMiddleware configuration.

### 7.2 Migration

`alembic` revision `0003_publish_thinking_text`:

```sql
ALTER TABLE participants
  ADD COLUMN publish_thinking_text BOOLEAN NOT NULL DEFAULT 0;
```

Pydantic `ParticipantRegister` adds `publish_thinking_text: bool = False`. Existing CLI clients sending bodies without the field continue to validate.

### 7.3 thinking_text gating

`TurnText` rows are returned in `GET /api/sessions/{season_id}/turns` only when the owning participant has `publish_thinking_text=True`. The endpoint always returns numeric turn data — gating affects text fields only. Frontend Session detail renders a banner when text is absent, distinguishing "no text recorded" from "owner opted out".

## 8. Frontend stack & data layer

- **Framework:** Next.js 15 (App Router) + TypeScript + Tailwind.
- **Code location:** `web/` at repo root. Independent `package.json` / `tsconfig.json` / `node_modules`. Vercel build with Root Directory = `web/`.
- **Chart library:** `recharts` for line/bar/heatmap; small custom SVG sparkbar component for the leaderboard.
- **API reference embed:** `@scalar/nextjs-api-reference` (or Redoc as fallback).
- **MDX:** `@next/mdx` for `/docs/*` static pages.
- **Data fetching:**
  - Server Components: `fetch(url, { next: { revalidate: 60 } })` — ISR.
  - Client Components: `swr` with `refreshInterval: 3000` only on `/evaluations/[id]`; halt by setting `refreshInterval: 0` once `status` is terminal.
- **Type generation:** `openapi-typescript` reads backend `/api/openapi.json` → `web/lib/api-types.ts`. Wrapper functions in `web/lib/api.ts` use these types. Runs in CI; backend schema drift breaks the frontend build.
- **Env:** `NEXT_PUBLIC_API_BASE_URL` (e.g. `https://arena.example.com`).

## 9. Deployment topology & security

- **Frontend:** Vercel (free tier) building from `web/`. Preview deploys per PR, prod from `master`.
- **Backend:** unchanged. uvicorn on the existing VPS / Fly / Railway target the operator chooses. The frontend never proxies — Server Components fetch the public backend directly.
- **CORS:** FastAPI `CORSMiddleware` allow_origins set to the frontend's Vercel prod domain and the preview wildcard (e.g. `https://*.vercel.app` scoped to the project).
- **Secrets:**
  - `api_key` returned by `POST /api/participants` is plaintext for one render. Never written to localStorage / sessionStorage / cookies / analytics.
  - `/evaluations/[id]#key=...` URL fragment carries the key only inside the browser; fragments never reach the server log.
- **Disclaimer:** every list view that shows model identifiers renders the existing `self-reported, unverified` line near the top.

## 10. Error / loading / empty states

| Route | Loading | Empty | Failure |
|---|---|---|---|
| `/` | `loading.tsx` skeleton (nav + empty table) | "No models yet — be the first" + Register CTA | `error.tsx` "Leaderboard unavailable" |
| `/models/[id]/*` | Per-tab skeleton | "No evaluations yet · submit a smoke run" | 404 "Model not found or disabled" |
| `/register` | Submit button spinner | — | 422 — inline field errors |
| `/register/success` | — | — | Stale page (no api_key in render context) → redirect home |
| `/evaluations/[id]` | "queued · waiting for worker" | — | 401 "Bad api_key" / 404 "Not found" |

Loading uses Next.js route-segment `loading.tsx`. Errors use `error.tsx`. Empty states are inline in the success render path.

## 11. Testing strategy

- **Unit (vitest):** pure utilities in `web/lib/` — sparkbar generator, cell-color map, KPI aggregator helpers, type guards.
- **Component (vitest + React Testing Library):** each chart component renders correct DOM and ARIA tree from mocked data. Approximately 5 components covered; the rest verified by e2e.
- **E2E (Playwright):** five scenarios against a mocked backend. MSW handlers are hand-written and seeded with example payloads taken from the OpenAPI schema's `examples` blocks (not auto-generated).
  1. Visitor: `/` → click model → Overview renders with KPI cards and 6-cell chart.
  2. Visitor: navigate all six model-card tabs via deep-link URLs.
  3. Operator: `/register` → success page → copy api_key → confirm checkbox unlocks redirect.
  4. Operator: `/evaluations/[id]#key=...` polling → terminal state stops polling and exposes model card link.
  5. Visitor: `/docs/api` Scalar page renders and a single try-it-out call succeeds against the mock.
- **Contract test (CI):** `npm run gen:types` against a live backend (in CI: ephemeral backend started from this repo). Any drift breaks the frontend build before merge.
- **Visual regression:** deferred to v2. v1 relies on Playwright screenshot snapshots only for the leaderboard and Overview tab.

## 12. Rough work breakdown

Implementation plan to be written by `superpowers:writing-plans`. Rough phases:

1. **Backend additions** — Alembic migration + 4 new endpoints + 2 extended endpoints + OpenAPI alias + CORSMiddleware.
2. **`web/` scaffold** — Next.js 15 init, Tailwind, `openapi-typescript` pipeline, CI for build + lint.
3. **Read paths** — `/`, `/models/[id]` and all six tabs against mock data first, then real backend.
4. **Write paths** — `/register`, `/register/success`, `/evaluations/[id]` with `swr` polling.
5. **Docs** — `/docs/quickstart` (MDX), `/docs/api` (Scalar), `/docs/methodology` (MDX).
6. **E2E + deploy** — Playwright suite, Vercel preview + prod, CORS allow-list update, smoke check.

## 13. Decision log (brainstorm 2026-05-26)

| # | Decision | Choice |
|---|---|---|
| Q1 | Primary persona | Operator-first + research showcase secondary |
| Q2 | Write surface | Register on web; submit/monitor remain CLI |
| Q3 | Leaderboard layout | Hybrid headline + 6-cell sparkbar |
| Q4 | Model card layout | OP.GG-style 6-tab |
| Q5 | thinking_text policy | Default opt-out; opt-in at registration |
| Q6 | Tech stack | Next.js 15 + TypeScript + Tailwind |
| Q7 | Deployment | Vercel frontend + separate VPS backend (CORS) |
| Q8 | Freshness | ISR 60 s for read pages; client polling 3 s on `/evaluations/[id]` only |
| Q8b | Compare scope | Up to 4 models |
| Q9 | Code location | `web/` directory at repo root |
