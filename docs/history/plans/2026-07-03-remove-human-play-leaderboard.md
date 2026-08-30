# Remove Human Play Leaderboard Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Delete the human **Play Leaderboard** (the `/api/leaderboard/play` endpoint and its frontend tab) — a score-ranking that is no longer meaningful post-psuccess-calibration and risks confounding the human self-preservation measurement — while leaving the Model Leaderboard, the Logs/trace viewer, and the shared `SessionSummaryRow` schema fully intact.

**Architecture:** Two removals over one shared data path. The Play Leaderboard is a thin read view: `GET /api/leaderboard/play` → `Repository.list_sessions(source="human", …, order_by_score=True)` → `SessionSummaryRow[]`, surfaced by an Alpine `playLeaderboardScreen` tab. Deletion removes the endpoint + its response model + its two arena-default constants (backend) and the nav link + section + component (frontend). The `SessionSummaryRow` schema and `Repository.order_by_score` capability are **retained** — both are used independently by the Logs feature and the persistence test suite respectively.

**Tech Stack:** Python 3.12, `uv`, pytest, FastAPI/pydantic (`interface/api.py`), vanilla JS + Alpine.js (`web/app.js`, `web/index.html`), `interface.persistence`.

## Global Constraints

- Python ≥ 3.12. Run all Python via `uv run --no-sync`. On this macOS + iCloud checkout, prefix every test command with `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null;` in the SAME command line (iCloud re-hides `*.pth` within seconds, breaking `squid_game`/`interface` imports and pytest collection). *(If executing in a git worktree created OUTSIDE iCloud, the `chflags` prefix is unnecessary — the venv `.pth` files are not hidden there.)*
- Judge tests green by **"no NEW failures"** vs the documented pre-existing baseline (~10 failed / 92 errors in `src/squid_game/**` + configs, unrelated to web-arena). Each task runs only its own affected test files.
- **DO NOT remove `order_by_score`** from `interface/persistence/{base,sqlite_repository,postgres_repository}.py`. It is a general-purpose Repository capability with its own direct test (`tests/unit/test_persistence.py:204`) and is out of scope. It simply becomes unused by the API layer — that is acceptable and intentional.
- **DO NOT touch** `SessionSummaryRow` (shared with Logs), the Model Leaderboard (`/api/leaderboard/models`, `ModelLeaderboardRow`, `model_stats`), the Logs endpoints (`/api/logs`, `/api/logs/{session_id}`), or the human-game/arena play flows.
- `web/index.html` head script order (`web/app.js` loaded **before** the Alpine CDN) is load-bearing — do not reorder.
- Commit message prefixes: `refactor(web-arena):` / `test(web-arena):` / `docs(web-arena):`. End each commit message with the two trailers:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Xxju95XbQyh1u2EhBHSicj
  ```
- No new third-party dependencies. Code English; docs may be Korean.
- Dep order: Task 1 (backend) → Task 2 (frontend) → Task 3 (docs + sweep). They ship together on one branch; do not deploy a backend-only or frontend-only intermediate state.

---

## File Structure

**Task 1 — Backend endpoint removal**
- Modify: `interface/api.py` — delete `leaderboard_play` endpoint (~L695–708), `PlayLeaderboardResponse` (~L348–351), `DEFAULT_PLAY_TASK`/`DEFAULT_PLAY_FRAMING` (~L666–667), and the endpoint's line in the module docstring (~L11).
- Modify: `tests/unit/test_api_web_arena.py` — flip the route-registration assertion (~L83) and delete the dedicated play test (`test_leaderboard_play_returns_sessions_for_default_arena`, ~L219–233).
- Modify: `tests/integration/test_web_arena_api.py` — delete the module-docstring endpoint line (~L14) and the 4 dedicated play tests (~L329–410).

**Task 2 — Frontend tab removal**
- Modify: `web/index.html` — delete the nav link (~L31) and the `PLAY LEADERBOARD` `<section>` (~L893–931).
- Modify: `web/app.js` — remove `"leaderboard"` from `APP_TABS` (~L383) and delete the `playLeaderboardScreen` component (~L768–802).

**Task 3 — Docs + final reference sweep**
- Modify: `docs/superpowers/specs/2026-07-02-web-arena-design.md` — strike Play Leaderboard references (if present).
- Verification only: repo-wide grep confirming zero dangling references.

---

## Task 1: Remove the `/api/leaderboard/play` backend endpoint

**Files:**
- Modify: `interface/api.py`
- Test: `tests/unit/test_api_web_arena.py`, `tests/integration/test_web_arena_api.py`

**Interfaces:**
- Consumes: nothing new.
- Produces: `/api/leaderboard/play` no longer registered on `app`. `PlayLeaderboardResponse`, `DEFAULT_PLAY_TASK`, `DEFAULT_PLAY_FRAMING` no longer exist in `interface.api`. `SessionSummaryRow`, `list_sessions(..., order_by_score=...)`, Model Leaderboard, and Logs endpoints are unchanged.

- [ ] **Step 1: Write the failing test (assert the route is GONE)**

In `tests/unit/test_api_web_arena.py`, edit `test_app_imports_and_registers_all_endpoints` (~L75–87): remove `"/api/leaderboard/play"` from the `expected` present-list, and add an explicit absence assertion after the loop. Result:

```python
def test_app_imports_and_registers_all_endpoints(api_module) -> None:
    paths = {r.path for r in api_module.app.routes if hasattr(r, "path")}
    for expected in [
        "/api/new_game",
        "/api/state",
        "/api/action",
        "/api/result",
        "/api/leaderboard/models",
        "/api/logs",
        "/api/logs/{session_id}",
    ]:
        assert expected in paths, f"missing route: {expected}"
    assert "/api/leaderboard/play" not in paths, "Play Leaderboard route should be removed"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/unit/test_api_web_arena.py::test_app_imports_and_registers_all_endpoints -v`
Expected: FAIL — `AssertionError: Play Leaderboard route should be removed` (the route is still registered).

- [ ] **Step 3: Remove the endpoint, its response model, its constants, and its dead tests**

In `interface/api.py`:

1. Delete the `leaderboard_play` endpoint (the decorator + function, ~L695–708):
```python
@app.get("/api/leaderboard/play", response_model=PlayLeaderboardResponse)
def leaderboard_play(task: str = DEFAULT_PLAY_TASK, framing: str = DEFAULT_PLAY_FRAMING):
    """Play Leaderboard: human sessions ranked by final_score, bucketed by arena.

    Defaults to the primary Play arena (signal_game + flagship_corruption).
    """
    sessions = _repository.list_sessions(
        source="human", task=task, framing=framing, order_by_score=True
    )
    return PlayLeaderboardResponse(
        task=task,
        framing=framing,
        rows=[_session_record_to_row(s) for s in sessions],
    )
```

2. Delete the `PlayLeaderboardResponse` model (~L348–351):
```python
class PlayLeaderboardResponse(BaseModel):
    task: str
    framing: str
    rows: list[SessionSummaryRow] = Field(description="Ordered by final_score descending")
```
(Leave `SessionSummaryRow`, `LogsResponse`, `LogTurnRow`, `LogDetailResponse` — all still used by Logs.)

3. Delete the two now-unused constants (~L666–667):
```python
DEFAULT_PLAY_TASK = "signal_game"
DEFAULT_PLAY_FRAMING = "flagship_corruption"
```

4. In the module docstring (~L11), delete the line:
```
    GET  /api/leaderboard/play    — Play Leaderboard (human sessions by score)
```

In `tests/unit/test_api_web_arena.py`: delete the whole `test_leaderboard_play_returns_sessions_for_default_arena` function (~L219–233).

In `tests/integration/test_web_arena_api.py`:
- Delete the module-docstring line referencing `GET /api/leaderboard/play` (~L14).
- Delete the 4 dedicated play tests and their section header comment (~L329–410):
  `test_leaderboard_play_ranks_by_final_score_desc_within_bucket_and_excludes_other_buckets`,
  `test_leaderboard_play_defaults_to_primary_arena_when_no_query_params_given`,
  `test_leaderboard_play_selects_a_non_default_bucket_via_query_params`,
  and any other function in that file whose body calls `client.get("/api/leaderboard/play"...)`.
- If this integration file has its own "all endpoints registered" style assertion listing `/api/leaderboard/play`, remove that entry too (grep the file for `leaderboard/play` and ensure zero remain).

- [ ] **Step 4: Run tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py -v`
Expected: PASS (all remaining tests, including the flipped route assertion). No `PlayLeaderboardResponse`/`DEFAULT_PLAY_*` `NameError`. Confirm with a grep that no test still references the endpoint:
`grep -rn "leaderboard/play\|leaderboard_play\|PlayLeaderboard\|DEFAULT_PLAY_" interface tests` → **zero matches**.

- [ ] **Step 5: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py
git commit -m "refactor(web-arena): remove human Play Leaderboard API endpoint" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xxju95XbQyh1u2EhBHSicj"
```

---

## Task 2: Remove the Play Leaderboard frontend tab

**Files:**
- Modify: `web/index.html`
- Modify: `web/app.js`

**Interfaces:**
- Consumes: Task 1's removal of `/api/leaderboard/play` (the component that fetched it is deleted here so nothing calls the dead route).
- Produces: no `#leaderboard` nav tab, no `playLeaderboardScreen` component; `APP_TABS` no longer whitelists `"leaderboard"` (so a stale `#leaderboard` hash falls back to the default tab via the existing `tabFromHash` logic). No automated test — static markup + a removed request; the endpoint's absence is covered by Task 1.

- [ ] **Step 1: Remove the nav link in `web/index.html`**

Delete this line (~L31):
```html
      <a href="#leaderboard" :class="{ active: $store.nav.tab === 'leaderboard' }">Play Leaderboard</a>
```
(Leave the `#models` "Model Leaderboard" link on the adjacent line untouched.)

- [ ] **Step 2: Remove the Play Leaderboard `<section>` in `web/index.html`**

Delete the entire block from the `PLAY LEADERBOARD` comment through the closing `</section>` (~L893–931), i.e. from:
```html
    <!-- =================================================================
         PLAY LEADERBOARD
         ================================================================= -->
    <section x-data="playLeaderboardScreen()" x-show="$store.nav.tab === 'leaderboard'" x-cloak>
```
through its matching:
```html
    </section>
```
(the one ending at ~L931, right before the next section's comment). Leave the surrounding Model Leaderboard and Logs sections intact.

- [ ] **Step 3: Remove `"leaderboard"` from `APP_TABS` and delete the component in `web/app.js`**

Change `APP_TABS` (~L383) from:
```javascript
  const APP_TABS = ["play", "arena", "models", "leaderboard", "logs"];
```
to:
```javascript
  const APP_TABS = ["play", "arena", "models", "logs"];
```

Delete the `playLeaderboardScreen` component (~L768–802), i.e. from:
```javascript
    // -----------------------------------------------------------------
    // Play Leaderboard screen
    // -----------------------------------------------------------------
    Alpine.data("playLeaderboardScreen", () => ({
```
through its closing:
```javascript
    }));
```
(the block registering `playLeaderboardScreen`, ending right before the `// Logs / Trace Explorer screen` comment). Leave the Logs component that follows untouched.

- [ ] **Step 4: Verify syntax and zero dangling references**

Run:
```bash
node --check web/app.js
grep -rn "playLeaderboardScreen\|#leaderboard\|'leaderboard'\|\"leaderboard\"\|leaderboard/play" web/
```
Expected: `node --check` exits 0 (no output). The grep returns **zero** matches. Then confirm the two config globals are still referenced elsewhere before deciding whether they are orphaned:
```bash
grep -rn "WEB_ARENA_DEFAULT_TASK\|WEB_ARENA_DEFAULT_FRAMING" web/
```
If those globals now have references ONLY in `web/config.js` (no consumer in `web/app.js`/`web/index.html`), they are orphaned — leave them in `config.js` anyway (harmless config; removing config globals is out of this task's scope). If they still have consumers, do nothing. Do NOT edit `web/config.js`.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/app.js
git commit -m "refactor(web-arena): remove Play Leaderboard tab from the web UI" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xxju95XbQyh1u2EhBHSicj"
```

- [ ] **Step 6 (optional, manual): Browser smoke**

If a reviewer wants live confirmation: serve `web/` + run the backend locally, load the app, confirm (a) the nav no longer shows "Play Leaderboard", (b) Model Leaderboard and Logs tabs still work, (c) visiting `#leaderboard` directly falls back to the default tab rather than showing a blank screen or console error. No automated test required.

---

## Task 3: Docs update + final reference sweep

**Files:**
- Modify: `docs/superpowers/specs/2026-07-02-web-arena-design.md` (if it references the Play Leaderboard)
- Verification only (no code change beyond docs)

**Interfaces:**
- Consumes: Tasks 1–2 complete.
- Produces: no design-doc or code reference to the human Play Leaderboard remains anywhere in the repo (except intentionally-kept, unrelated `order_by_score` persistence code).

- [ ] **Step 1: Find spec references**

Run:
```bash
grep -rn -i "play leaderboard\|leaderboard/play\|leaderboard_play" docs/
```
For each hit in `docs/superpowers/specs/2026-07-02-web-arena-design.md` (or any other design doc), rewrite the surrounding sentence so it no longer promises a human score leaderboard. If the spec has a numbered "Play Leaderboard" section, replace its body with a one-line note: *"Removed 2026-07-03 — human sessions are viewed via the Logs/trace explorer; a score ranking was dropped as meaningless post-psuccess-calibration and a confound to the self-preservation measurement."* Do not renumber unrelated sections.

- [ ] **Step 2: Repo-wide sweep to confirm nothing dangles**

Run:
```bash
grep -rn "leaderboard/play\|leaderboard_play\|PlayLeaderboard\|DEFAULT_PLAY_\|playLeaderboardScreen" \
  interface web tests docs
```
Expected: **zero matches**. (A match in `order_by_score` code is impossible — that string differs — but if any stray reference to the play endpoint remains, fix it in the file it belongs to and re-run.)

- [ ] **Step 3: Confirm the retained surfaces still pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; uv run --no-sync pytest tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py tests/unit/test_persistence.py -v`
Expected: PASS (Logs, Model Leaderboard, and the retained `order_by_score` persistence test all green; no new failures vs baseline).

- [ ] **Step 4: Commit**

```bash
git add docs/superpowers/specs/2026-07-02-web-arena-design.md
git commit -m "docs(web-arena): drop Play Leaderboard from the web-arena spec" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xxju95XbQyh1u2EhBHSicj"
```

---

## Deploy note (post-merge, human approval)

After the branch merges to `main`, a `git push origin main` triggers Render (backend: Task 1) and the Pages workflow (frontend: Task 2). Deploy is the last step and requires explicit human approval — the backend endpoint and the frontend tab must ship together (never a backend-only push that leaves the live UI calling a 404 route, nor vice versa).

---

## Self-Review

**Spec coverage** (the "spec" here is the deletion request "remove the human Play Leaderboard"):
- "remove the endpoint" → Task 1 (endpoint + response model + constants + docstring + tests). ✓
- "remove the frontend" → Task 2 (nav link + section + component + whitelist). ✓
- "leave everything else working" → Global Constraints + Task 3 Step 3 verifying Logs / Model LB / `order_by_score` still pass; `SessionSummaryRow` explicitly retained. ✓
- "no dangling references" → Task 3 sweep. ✓

**Placeholder scan:** Every code step shows the exact block to delete or the exact replacement. The only discovery-based steps are grep sweeps (Task 2 Step 4, Task 3 Steps 1–2), which are verification, not implementation — the files they target are named. No "TBD"/"handle edge cases"/"similar to" placeholders.

**Type consistency:**
- `PlayLeaderboardResponse`, `DEFAULT_PLAY_TASK`, `DEFAULT_PLAY_FRAMING`, `leaderboard_play`, `playLeaderboardScreen`, `"leaderboard"` (tab id) — every symbol removed in a task is also removed from every consumer named in the same or an earlier task (route-registration test flipped in Task 1 Step 1; frontend fetch deleted in Task 2 Step 3). No task references a symbol a sibling deletes without also updating it.
- Retained symbols (`SessionSummaryRow`, `list_sessions`/`order_by_score`, `LogsResponse`, Model Leaderboard) are named in Global Constraints as do-not-touch, so no later task assumes they were removed.
- Note the deliberate asymmetry: `order_by_score` is retained though its only API caller is deleted — called out explicitly in Global Constraints so a reviewer does not flag it as dead code to remove.

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-remove-human-play-leaderboard.md`. Two execution options:

1. **Subagent-Driven (recommended)** — dispatch a fresh subagent per task, review between tasks.
2. **Inline Execution** — execute in-session with checkpoints.

Tasks 1→2→3 are ordered but small; the whole plan is a single coherent removal that ships on one branch.
