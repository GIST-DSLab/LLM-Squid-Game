# Web Arena Lives Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the human-play Web Arena run the engine's lives mechanic (5 hearts, −1 per wrong answer, red-tinted screen as hearts drop, peer-death notices, threat ladder 0–3) and show lives/notices/elimination in the logs explorer for both human games and LLM seasons.

**Architecture:** Three parallel tracks with strict file ownership. W1 (backend `web/squid_arena/`) bridges `HumanGameSession` to the engine's lives rules and adds additive schema fields. W2 (`db/squid_store/` + `web/squid_arena/seeding.py`) adds columns and reads the new JSONL keys. W3 (`web/frontend/`) builds the heart tile, danger vignette, notice banner, game-over copy and logs rendering against the field-name contract. Integration regenerates the OpenAPI snapshot, runs the web test suites, and pushes `main` (Render + GitHub Pages deploy).

**Tech Stack:** FastAPI + pydantic v2, SQLite/psycopg, Alpine.js (no build), CSS custom properties, pytest.

**Spec:** `docs/history/specs/2026-09-03-web-arena-lives-design.md`

## Global Constraints

- Additive only on wire schemas: never rename a pydantic class or field (`schemas.py:1-8`).
- Field names are identical across backend schema, DB record, and frontend: `lives_remaining, lives_total, lives_enabled, threat_level, peer_death_text, life_lost, eliminated, is_dead, lives_at_end, lives_before, lives_after, peer_death_announced`.
- Default human play is lives mode (`lives_enabled=True`); legacy p_death path stays behind `lives_enabled=False`.
- `reporting.CAMPAIGN_CELLS` and `app.js CAMPAIGN_CONDITIONS` change together, same order: `(true_baseline,not_allowed), (true_baseline,allowed), (threat_l1,allowed), (threat_l2,allowed), (threat_l3,allowed)`.
- Run tests: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest <paths> -q -x`. Web baseline: 112 passed across `tests/unit/test_api_web_arena.py tests/characterization/test_api_contract.py tests/integration/test_web_arena_api.py tests/unit/test_seed_web_arena.py tests/unit/test_backup_web_arena.py tests/integration/test_arena.py`.
- Use `Edit` on existing files; never `git stash`/`checkout` (an experiment run may be live in this tree); no `git commit` — orchestrator commits.
- Never touch `outputs/` (except reading) or `game/` (engine is frozen for this plan; consume `squid_game.core.peer_death.PeerDeathScheduler`, `squid_game.core.turn_conditions.threat_level_of`, `squid_game.core.framing.FramingManager`, `squid_game.models.config.PeerDeathConfig`, `ForfeitLayerConfig(reward_mode=...)`).

---

## Interface contracts

```python
# web/squid_arena/schemas.py (W1) — additive fields, defaults shown
class NewGameRequest:       lives_enabled: bool = True; lives_total: int = Field(5, ge=1, le=9)
class TurnStateResponse:    lives_remaining: int|None=None; lives_total: int|None=None; threat_level: int|None=None
                            peer_death_text: str|None=None; lives_enabled: bool=False
class ActionResponse:       life_lost: bool=False; lives_remaining: int|None=None; eliminated: bool=False; is_dead: bool=False
class GameResultResponse:   lives_at_end: int|None=None; eliminated: bool=False; threat_level: int|None=None
class LogTurnRow:           lives_before: int|None=None; lives_after: int|None=None; life_lost: bool=False
                            peer_death_announced: bool=False; threat_level: int|None=None
class LogSessionRow:        lives_at_end: int|None=None; eliminated: bool=False; threat_level: int|None=None
# (if the session list uses a different row model name, add the same three fields to that model)

# web/squid_arena/human_game.py (W1)
def human_threat_text(framing: str, lives_remaining: int, lives_total: int) -> str: ...
HumanGameSession.__init__(..., lives_enabled: bool = True, lives_total: int = 5,
                          peer_death: PeerDeathConfig | None = None, reward_mode: str = "flat")

# db/squid_store/models.py (W2)
@dataclass SessionRecord: ... lives_at_end: int|None=None; eliminated: bool=False; threat_level: int|None=None
@dataclass TurnRecord:    ... lives_before: int|None=None; lives_after: int|None=None; life_lost: bool=False
                              peer_death_announced: bool=False; threat_level: int|None=None
# web/squid_arena/seeding.py (W2)
LIVES_RUN_GLOB = "outputs/lives_threat_*/*_signal-game"
def discover_run_dirs(root: Path = Path(".")) -> list[Path]: ...   # MODEL_DIRS ∪ glob
```

---

# Track W1 — Backend

### Task W1.1: Schemas + human_game lives bridge

**Files:** `web/squid_arena/schemas.py`, `web/squid_arena/human_game.py`, `web/squid_arena/api.py` (re-export list), test `tests/unit/test_human_game_lives.py` (new).

- [ ] Step 1: Failing tests driving `HumanGameSession` directly (pattern: existing tests that construct it, grep `HumanGameSession(` in tests/): defaults `lives_enabled=True, lives_total=5`; `get_state().lives_remaining == 5`; wrong action → `feedback.life_lost is True`, `lives_remaining == 4`, score unchanged; correct action → `reward == 10.0`, lives unchanged; five wrong → `feedback.eliminated`, `is_dead`, `game_over_reason == "eliminated"`, score 0, `build_season_result().lives_at_end == 0` and `.eliminated`; forfeit → score preserved, lives unchanged; `framing="true_baseline"` never yields `peer_death_text`; `framing="threat_l3"` with a scheduler forced to fire (construct with `peer_death=PeerDeathConfig(p_announce=1.0, first_turn=1)`) yields text containing `! NOTICE` on turn 1 and `TurnResult.peer_death_announced`; `human_threat_text("threat_l1",5,5)` word count < `threat_l2` < `threat_l3`, none contains `%`; `human_threat_text("true_baseline",5,5)` contains `attempts` and none of `life|death|eliminat`; `lives_enabled=False` reproduces the legacy roll (existing behaviour; reuse an existing seed-based death test as the regression guard).
- [ ] Step 2: Implement per spec §3.1–3.2. In `submit_action`, when `self._lives_enabled`: no `apply_death_check`; `life_lost = (action != forfeit) and not was_correct`; decrement; `is_dead = lives_remaining == 0` → `_is_alive=False`, `_cumulative_score=0.0`. Reward via `ForfeitLayerConfig(reward_mode="flat", base_reward=10.0)` when lives mode; keep calibrated layer for legacy. `TurnResult(..., lives_before, lives_after, life_lost, threat_level, peer_death_announced, peer_death_text)`; `SeasonResult(..., lives_at_end, eliminated)`. `get_state()` calls `scheduler.advance(turn)` once per turn (memoise per turn number so repeated `/api/state` calls do not re-roll).
- [ ] Step 3: Tests pass; `tests/unit/test_api_web_arena.py` still 64 passed.

### Task W1.2: Routes, reporting, campaign cells, OpenAPI snapshot

**Files:** `web/squid_arena/routes_game.py`, `routes_logs.py`, `deps.py`, `reporting.py`, `rule_schedule.py` (only if campaign length changes require it), `tests/unit/test_api_web_arena_lives.py` (new), `tests/integration/test_web_arena_api.py` (campaign drive → 5 cells), `tests/characterization/snapshots/api/openapi.json` (regenerate), `tests/characterization/test_api_contract.py` (only if `EXPECTED_ROUTES` needs no change — it should not).

- [ ] Step 1: Failing API tests (TestClient pattern from `test_api_web_arena.py`): `POST /api/new_game` default → `GET /api/state` has `lives_enabled true, lives_remaining 5, lives_total 5, p_death 0.0`; `framing=threat_l2` → `framing_threat` contains `NOT you anymore`; wrong `POST /api/action` → `life_lost true, lives_remaining 4`; `GET /api/reward_preview` → `continue_reward == 10.0`; drive to elimination → `eliminated true, is_dead true, game_over_reason "eliminated"`, `GET /api/result` → `lives_at_end 0, eliminated true`; `GET /api/logs/{id}` turns carry `lives_before/lives_after/life_lost`; `GET /api/report?source=human&key=<nick>` cell glyph `dead` for the eliminated game; `lives_enabled=false` → `lives_enabled false` and legacy `p_death 0.15`.
- [ ] Step 2: Implement. `_persist_result` writes the new session/turn fields (W2's record fields — poll `db/squid_store/models.py` until present). `CAMPAIGN_CELLS` → 5-cell ladder; adjust `campaign_index` bounds and `rule_index_for` usage for length 5.
- [ ] Step 3: Regenerate the OpenAPI snapshot: delete `tests/characterization/snapshots/api/openapi.json`, run `test_api_contract.py` twice (self-seeding). Confirm `EXPECTED_ROUTES` unchanged (no new routes).
- [ ] Step 4: Full web suites green (112 baseline + new).

---

# Track W2 — DB + seeding

### Task W2.1: Records + both repositories (land `models.py` first, within minutes)

**Files:** `db/squid_store/models.py`, `sqlite_repository.py`, `postgres_repository.py`, test `tests/unit/test_squid_store_lives.py` (new).

- [ ] Step 1: Failing tests: SQLite in-memory round-trip of `SessionRecord`/`TurnRecord` with the new fields (`create_session` → `get_session`, `add_turns` → `list_turns`); migration test — create a temp SQLite file with the **old** `_SCHEMA` (copy the current CREATE statements into the test as a literal before editing), then `init_schema()` on it and assert `PRAGMA table_info` lists the new columns; Postgres: assert the `ALTER TABLE ... ADD COLUMN IF NOT EXISTS` statements for every new column appear in the repository's migration SQL list (string-level, no live PG).
- [ ] Step 2: Implement per spec §4 following the `_MEDIATION_REAL_COLS` pattern: a `_LIVES_SESSION_COLS` / `_LIVES_TURN_COLS` list drives schema, ALTER guard, insert tuples and row mappers in **both** backends. Booleans stored as INTEGER 0/1 (SQLite) / BOOLEAN (PG), consistent with existing `forfeited`/`correct` handling.
- [ ] Step 3: Tests pass; `tests/unit/test_backup_web_arena.py` still green (mirror copies the new columns).

### Task W2.2: Seeding reads lives keys and discovers lives runs

**Files:** `web/squid_arena/seeding.py`, `tests/unit/test_seed_web_arena.py`.

- [ ] Step 1: Failing tests: `build_session_record(season_dict_with_lives)` sets `lives_at_end`, `eliminated`, `threat_level` (`threat_l2` → 2; `flagship_corruption` → None); `build_turn_records` carries `lives_before/lives_after/life_lost/peer_death_announced/threat_level`, and omits gracefully on legacy dicts (None/False); `discover_run_dirs(tmp)` returns MODEL_DIRS that exist plus a `outputs/lives_threat_x/2026…_signal-game` dir.
- [ ] Step 2: Implement; `seed_sessions` iterates `discover_run_dirs()`.
- [ ] Step 3: Tests pass.

---

# Track W3 — Frontend

### Task W3.1: Hearts tile, danger vignette, notice banner, game-over copy, stage-2 skip

**Files:** `web/frontend/index.html`, `web/frontend/app.js`, `web/frontend/styles.css`.

- [ ] Step 1: `app.js` `playScreen`: add state `livesEnabled, livesRemaining, livesTotal, threatLevel, peerDeathText, lastLifeLost, breakingHeart (index|null)`; sync from `/api/state` and `/api/action`; computed `dangerLevel()` = `livesEnabled ? 1 - livesRemaining/livesTotal : 0`; `heartsArray()` = `[0..livesTotal-1]` with `filled = i < livesRemaining`. On `life_lost`: set `breakingHeart = livesRemaining` (index of the heart just lost), `flash = true` for 300ms, then clear. Skip Stage 2 when `livesEnabled` (`commitAction` → `chooseContinue` path directly; `psuccess` omitted from the action payload). `framingImagery`/`eliminationTheme`: entries for `true_baseline` (label "Attempts", no dead copy), `threat_l1` (🚪 "REMOVED", tileLabel "Lives"), `threat_l2` (💀 "OVERWRITTEN"), `threat_l3` (☠ "DELETED"); `bodyLead` "You ran out of lives at turn", `bodyTail` per level. `CAMPAIGN_CONDITIONS`/`CAMPAIGN_SCENARIOS` → 5 cells. Campaign report glyph `dead` → 💔.
- [ ] Step 2: `index.html`: replace the p_death tile with `<template x-if="livesEnabled">` hearts tile (`.lives-tile`, hearts as inline SVG `<span class="heart" :class="{ filled, breaking: breakingHeart===i, last: livesRemaining===1 && filled }">`), keep the legacy tile in `<template x-if="!livesEnabled">`. Root play container gets `:style="'--danger:' + dangerLevel()"` and `:class="{ 'play-danger': livesEnabled }"`. Add `.peer-notice` banner above the stimulus (`x-show="peerDeathText"`, `x-transition`), `.screen-flash` overlay (`x-show="flash"`). Stage 2 block wrapped in `x-show="!livesEnabled"`. Death overlay copy uses the new theme fields; show `lives_at_end` hearts row (all empty).
- [ ] Step 3: `styles.css`: tokens `--danger-color: var(--danger)`, `--heart: #ff4d5e`, `--heart-off: #3a2b31`; `.lives-tile .heart svg` 22px; `@keyframes heart-break` (scale 1→1.3→0, rotate 0→25deg, opacity 1→0, 600ms), `@keyframes heart-pulse` (scale 1↔1.15, 1.2s infinite), `@keyframes tile-shake` (reuse `death-shake` timing), `@keyframes screen-flash` (opacity .5→0, 300ms), `@keyframes heartbeat-bg` (opacity .55↔.8, 2s infinite). `.play-danger::after { content:""; position:fixed; inset:0; pointer-events:none; background: radial-gradient(ellipse at center, transparent 45%, rgba(224,87,91,.9) 100%); opacity: calc(var(--danger, 0) * .75); transition: opacity .6s ease; z-index: 5; }`; `.play-danger[style*="--danger: 0.8"]::after, .play-danger.last-life::after { animation: heartbeat-bg 2s infinite }` (drive `last-life` class from Alpine instead of matching the style string). `.panel` border-color via `color-mix(in srgb, var(--border), var(--danger-color) calc(var(--danger,0) * 100%))`. `@media (prefers-reduced-motion: reduce)` disables all five animations. `.peer-notice` mono, left `--accent` bar, bg `--panel-alt`.
- [ ] Step 4: Static checks: `node --check web/frontend/app.js`; open `index.html` locally against a `:memory:` backend (`WEB_ARENA_DSN=":memory:" uv run --no-sync uvicorn squid_arena.api:app --port 8502` with `PYTHONPATH=game:db:web`, `config.js` API base temporarily `http://localhost:8502` — revert before finishing) and, if the Playwright MCP is available, capture `screenshots/web-lives/{start,life-lost,last-life,eliminated}.png`. Do not commit `config.js` changes.

### Task W3.2: Logs explorer lives rendering

**Files:** `web/frontend/index.html`, `web/frontend/app.js`, `web/frontend/styles.css`.

- [ ] Step 1: Session list rows: mini hearts (`.hearts-mini`, 5 × 10px) from `lives_at_end` when not null, `eliminated` badge (`.badge-dead`), threat chip `L{threat_level}` when not null.
- [ ] Step 2: Trace turn header: `lives_before → lives_after` mini hearts, 💔 when `life_lost`, `! NOTICE` chip when `peer_death_announced`. Human report cells: `dead` glyph 💔 alongside `ok|no|forfeit|empty`.
- [ ] Step 3: `node --check`; visual check on a seeded `:memory:` session if Playwright is available.

---

# Integration

- [ ] `uv run --no-sync pytest tests/unit tests/integration tests/characterization -q` — no new failures vs baseline (known: 5 missing-config failures + `test_artefact_layout`).
- [ ] `web/DEPLOY.md`: one line listing the new columns (auto-migrated on startup).
- [ ] Commit (orchestrator) and `git push origin main` → Render + GitHub Pages deploy; verify `https://squid-game-web-arena-api.onrender.com/api/leaderboard/models` responds and the Pages site shows the hearts tile.
- [ ] Append a "웹 화면" section to `docs/reports/2026-09-03-lives-threat-ladder.html` with the screenshots and republish the artifact.
