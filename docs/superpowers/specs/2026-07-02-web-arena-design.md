# LLM Squid Game — Web Arena Design

**Date:** 2026-07-02
**Status:** Approved (brainstorming complete; pending implementation plan)
**Author:** irregular6612 + Claude

---

## 1. Purpose

Build a public-facing website for the LLM Squid Game benchmark that lets anyone:

1. **Play the game** in the browser (anonymous, nickname only).
2. **View a Model Leaderboard** ranking LLMs by a research-grounded metric
   (mediation-chain closure → Cox β for framing effect on forfeit timing).
3. **View a Play Leaderboard** ranking human sessions by raw final score.
4. **Browse logs** (trace explorer) for both LLM experiment runs and human sessions.

All site UI text is in **English**. The site is intended to be lightweight and
mostly static (GitHub Pages) with a small hosted backend for the parts that
require writable, trustworthy shared state.

## 2. Non-Goals (YAGNI)

- No user accounts / authentication / login (anonymous nickname only).
- No real-time multiplayer / head-to-head matches (asynchronous only).
- No re-implementation of the game logic in JavaScript — the server is the
  single source of truth for game state and scoring.
- No changes to the core benchmark engine (`src/squid_game/**`) beyond what the
  existing `interface/human_game.py` already wraps.

## 3. Architecture (Hybrid)

```
┌─────────────────────────────┐        HTTPS / CORS        ┌──────────────────────────────┐
│  GitHub Pages (static)       │  ───────────────────────▶ │  FastAPI backend (hosted)      │
│  web/ : HTML + CSS + vanilla │                            │  interface/api.py (extended)   │
│  JS  (+ CDN Alpine.js)       │  ◀─────────────────────── │  + interface/human_game.py     │
│  Screens: Play · Model LB ·  │        JSON                │  + persistence layer           │
│  Play LB · Logs              │                            │  + Postgres (Supabase free)    │
└─────────────────────────────┘                            └──────────────────────────────┘
```

- **Frontend** — pure static files, no build toolchain. Reactivity via CDN
  Alpine.js. Deployed to GitHub Pages via GitHub Actions on push. Backend base
  URL injected as a config value (e.g. `web/config.js`).
- **Backend** — extends the existing `interface/api.py`. The game and all
  scoring run server-side using `interface/human_game.py`, so the client only
  submits per-turn actions and can never forge a final score. Deployed to a
  free container platform (Render / Fly.io / Hugging Face Spaces) via a single
  Dockerfile + platform config. Free-tier cold start (~30 s) is acceptable.
- **Storage** — Supabase free Postgres for durability. A thin repository
  abstraction lets local development fall back to SQLite.

### Rationale
A human playing the benchmark needs **no LLM at inference time** — a session is
deterministic rule-logic (`SurvivalPressure`, `ForfeitController`,
`FramingManager`, task scoring). This is why the game can be served by a small
backend and the frontend can stay static. The only feature that fundamentally
needs a writable shared store is the leaderboard, so we isolate that in the
backend + Postgres and keep everything else static/read-only.

## 4. Screens (English UI)

1. **Play** — enter a nickname → play the fixed arena configuration
   (default `signal_game` + `flagship_corruption`, the primary FSPM cell)
   turn-by-turn. Each turn shows the observation, collects the action (+ probe +
   reasoning), and the end-of-game view shows the final score and the player's
   rank on the Play Leaderboard.
2. **Model Leaderboard** (scientific) — see §5.
3. **Play Leaderboard** (casual) — human sessions ranked by final score `S`,
   bucketed by arena configuration (task + framing). Anonymous nicknames.
4. **Logs / Trace Explorer** — list past sessions (LLM experiment runs +
   human sessions); expand any session to a turn-by-turn view of observation,
   action, per-call RI (`ri_task` / `ri_probe` / `ri_forfeit`), forfeit choice,
   and score.

## 5. Model Leaderboard Ranking Logic ⭐

Computed per model from the analysis pipeline outputs
(`cognitive_load_mediation.json` + `unified_cox_summary.json`).

1. **Primary grouping — Closed vs Open (mediation-chain closure):**
   Add the ΔRI (cognitive-load) mediator to the Cox model (4-cov). If the
   framing effect becomes non-significant (`p_FC_4cov` n.s., i.e. `β_FC → 0`),
   the chain is **Closed** (framing→forfeit fully mediated by decision cost).
   If the framing effect remains significant, the chain is **Open** (residual
   direct FSPM signal beyond cognitive load).
2. **Secondary sort — within each group:** `beta_framing_is_FC` in
   **descending** order — the model whose framing pulled forfeit forward the
   fastest (largest β) ranks highest.
3. **Presentation:** two labelled sections. Default order is **Open** on top,
   **Closed** below (residual FSPM is the phenomenon of interest). This
   section order is cosmetic and can be flipped without affecting the metric.
   Each row shows: model, mediation class, HR_FC [95% CI], p, %attenuation, β,
   n_sessions.

### Closure criterion (from `scripts/analyze_unified_cox_with_load.py`)
- Full mediation → `HR_FC → 1.0`, `β_FC → 0` after adding ΔRI.
- The site uses the **binary** Closed/Open distinction: Closed iff the mediator
  renders `β_FC` non-significant; Open otherwise.

## 6. Backend API

| Endpoint | Status | Role |
|---|---|---|
| `POST /api/new_game` | existing (extend) | start session with nickname + arena config |
| `GET /api/state` | existing | current turn state (system prompt + observation) |
| `POST /api/action` | existing | submit action + probe + reasoning |
| `GET /api/result` | existing (extend) | on game over, **persist result to DB** |
| `GET /api/leaderboard/models` | **new** | Closed/Open groups, β descending |
| `GET /api/leaderboard/play` | **new** | human sessions ranked by score (arena bucket) |
| `GET /api/logs` | **new** | list sessions (LLM + human) |
| `GET /api/logs/{id}` | **new** | turn-by-turn trace for one session |

CORS enabled for the GitHub Pages origin.

## 7. Data Model (Postgres; SQLite locally)

- `sessions` — `id`, `nickname`, `task`, `framing`, `forfeit`, `seed`,
  `final_score`, `forfeited` (bool), `created_at`, `source` (`human` | `llm`).
- `turns` — `session_id`, `turn_no`, `observation`, `action`,
  `ri_task`, `ri_probe`, `ri_forfeit`, `choice`, `score` (trace explorer).
- `model_stats` — `model_label`, `mediation_class` (`closed` | `open`),
  `beta_framing_is_FC`, `hr_FC_3cov`, `hr_FC_ci_low/high`, `p_FC`,
  `pct_attenuation`, `n_sessions`.

### Seed script
Import existing `outputs/final_results/*`:
- Per-session results + `*_turns.jsonl` → `sessions` / `turns` with
  `source='llm'` (feeds Logs).
- `cognitive_load_mediation.json` + `unified_cox_summary.json` → `model_stats`
  (feeds Model Leaderboard). Re-run to refresh when new analysis lands.

## 8. Integrity, Deployment, Testing

- **Integrity:** scores computed server-side; simple rate limit on
  `new_game`/`action`; nickname sanitization. No auth (anonymous by design).
- **Deployment:** frontend via GitHub Actions → Pages; backend via Dockerfile +
  Render/Fly/HF Spaces platform config.
- **Testing:** reuse the `tests/integration` `StubProvider` pattern
  (`patch_runner_provider`) to cover the new endpoints (leaderboard, logs,
  result persistence) as offline, deterministic fixture tests.

## 9. Open Decisions for Review

- Section order on the Model Leaderboard (Open-first vs Closed-first) — cosmetic.
- Exact hosting platform for the backend (Render vs Fly.io vs HF Spaces) — to be
  fixed during implementation planning.
- Default arena configuration for the Play board (currently `signal_game` +
  `flagship_corruption`).
