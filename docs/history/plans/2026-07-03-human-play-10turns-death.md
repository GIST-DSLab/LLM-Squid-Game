# Human Play: 10 Turns + Real Death + Elimination UI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the web arena's human-play mode run 10 turns per session with a real per-turn 0.15 death check that zeroes the score, and show a dramatic elimination overlay when the player dies.

**Architecture:** Two surfaces. (1) Backend: flip two defaults on the human-only `/api/new_game` request model — no new game logic, the death path already exists in `HumanGameSession`/`SurvivalPressure`. (2) Frontend: sync the duplicated `TOTAL_TURNS` constant and add an Alpine-driven elimination overlay that intercepts the `game_over_reason === "eliminated"` case before the normal finish flow.

**Tech Stack:** Python 3.12, FastAPI + Pydantic, pytest (+ FastAPI `TestClient`), Alpine.js + vanilla JS/CSS (no JS test framework in this repo).

## Global Constraints

- Changes apply to **human play only** (`/api/new_game` → `state`/`action`). Do **not** touch the LLM arena path (`/api/arena/run`, `ArenaRunRequest`).
- Per-turn death probability stays **constant 0.15** (`p_death_constant` default unchanged). No logistic schedule.
- On death the engine zeroes the score and ends the session — reuse existing behavior, add no new death logic server-side.
- Frontend `TOTAL_TURNS` (in `web/app.js`) MUST equal the server `total_turns` (10).
- Death is detected on the frontend via `ActionResponse.game_over_reason === "eliminated"` — do **not** add an `is_dead` field to the API contract.
- Tests are offline/deterministic. Use `p_death_constant: 1.0` to force a guaranteed death (`apply_death_check` returns `rng.random() < p_death`, always true at 1.0) rather than seed-hunting.
- Pre-existing test failures in the web-arena suite are known baseline noise; judge green by "no *new* failures".

---

### Task 1: Backend defaults — 10 turns + real death

**Files:**
- Modify: `interface/api.py` (class `NewGameRequest`, ~lines 220–224)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: existing `POST /api/new_game` (body = `NewGameRequest`), `GET /api/state`, `POST /api/action?session_id=…`. Existing `NewGameRequest` fields: `total_turns: int`, `actual_death: bool`, `p_death_constant: float | None`.
- Produces: new `NewGameRequest` defaults `total_turns=10`, `actual_death=True` (consumed implicitly by the frontend, which sends neither field). `ActionResponse.game_over_reason` value `"eliminated"` on death (already produced by `HumanGameSession`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_api_web_arena.py` (uses the existing `client` fixture):

```python
def test_new_game_defaults_to_ten_turns(client: TestClient) -> None:
    """Human play defaults to a 10-turn season (was 15)."""
    resp = client.post("/api/new_game", json={})
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    assert state["total_turns"] == 10


def test_new_game_defaults_enable_real_death(client: TestClient) -> None:
    """actual_death defaults to True: a forced p_death=1.0 eliminates the
    player on the first action and zeroes the score. If the default were
    False, no death check would run and the game would not end here."""
    resp = client.post(
        "/api/new_game",
        # No actual_death / total_turns => server defaults. p_death_constant
        # forced to 1.0 makes the death roll deterministic.
        json={"p_death_constant": 1.0, "num_few_shot": 0, "curriculum_turns": 0},
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    state = client.get("/api/state", params={"session_id": session_id}).json()
    assert not state["game_over"]
    action = state["available_actions"][0]
    act = client.post(
        f"/api/action?session_id={session_id}",
        json={"action": action, "probe_answer": "", "reasoning": ""},
    ).json()

    assert act["game_over"] is True
    assert act["game_over_reason"] == "eliminated"
    assert act["new_score"] == 0.0

    result = client.get("/api/result", params={"session_id": session_id}).json()
    assert result["survived"] is False
    assert result["final_score"] == 0.0
```

Note on `state["total_turns"]`: confirm the field name in `TurnStateResponse`. `get_turn_state()` returns `total_turns`; the API maps it into the state response. If the JSON key differs, read `interface/api.py` around the `/api/state` handler and use the actual key — do not guess.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/unit/test_api_web_arena.py::test_new_game_defaults_to_ten_turns tests/unit/test_api_web_arena.py::test_new_game_defaults_enable_real_death -v`
Expected: FAIL — `total_turns` is 15, and `actual_death` defaults False so no `"eliminated"` game over.

- [ ] **Step 3: Change the defaults**

In `interface/api.py`, class `NewGameRequest`:

```python
    total_turns: int = 10        # was 15
    actual_death: bool = True     # was False
```

Leave `p_death_constant: float | None = 0.15` unchanged.

- [ ] **Step 4: Run the new tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_web_arena.py::test_new_game_defaults_to_ten_turns tests/unit/test_api_web_arena.py::test_new_game_defaults_enable_real_death -v`
Expected: PASS (both).

- [ ] **Step 5: Run the web-arena suites to confirm no new failures**

Run: `uv run pytest tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py -q`
Expected: No failures beyond the known baseline. Existing tests that need death off pass their own `"actual_death": False` explicitly (verified in the current suite), so flipping the default does not regress them.

- [ ] **Step 6: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): human play defaults to 10 turns with real p_death"
```

---

### Task 2: Frontend — turn-count sync + elimination overlay

**Files:**
- Modify: `web/app.js` (constant `TOTAL_TURNS` ~line 191; `playScreen()` data ~line 420–445; `submitAction` game-over branch ~line 655; `_resetTurnState` ~line 709)
- Modify: `web/index.html` (play `<section x-data="playScreen()">`, add overlay near the play-layout close ~line 568)
- Modify: `web/styles.css` (append overlay styles; reuse `pop-in` keyframe near line 431)

**Interfaces:**
- Consumes (from Task 1 / existing API): `ActionResponse` JSON with `game_over`, `game_over_reason` (`"eliminated"` on death), `new_score`. Turn state JSON with `cumulative_score`.
- Produces: Alpine state `eliminated: bool`, `eliminatedTurn: number|null`, `eliminatedLostScore: number`; method `dismissDeath()`. Overlay element `.death-overlay` gated by `x-show="eliminated"`.

- [ ] **Step 1: Sync the turn-count constant**

In `web/app.js`:

```js
const TOTAL_TURNS = 10;  // was 15 — must match server NewGameRequest.total_turns
```

- [ ] **Step 2: Add elimination state to `playScreen()` data**

In `web/app.js`, in the object returned by `playScreen()` (alongside `gameOver: false,` and the other reset fields), add:

```js
      eliminated: false,
      eliminatedTurn: null,
      eliminatedLostScore: 0,
```

- [ ] **Step 3: Intercept the eliminated case in `submitAction`**

In `web/app.js` `submitAction`, replace the existing game-over branch:

```js
          if (resp.game_over) {
            await this.finishGame();
          } else {
            await this.refreshState();
          }
```

with:

```js
          if (resp.game_over) {
            if (resp.game_over_reason === "eliminated") {
              // Score entering this turn (pre-wipe) drives the "you lost N" line.
              this.eliminatedLostScore =
                (this.state && this.state.cumulative_score) || 0;
              this.eliminatedTurn = turnNo;
              this.eliminated = true; // overlay; dismissDeath() runs the finish flow
            } else {
              await this.finishGame();
            }
          } else {
            await this.refreshState();
          }
```

(`turnNo` is the turn number already computed at the top of `submitAction` for the `history.push`. Confirm its local variable name there and reuse it; if it is named differently, use that name.)

- [ ] **Step 4: Add the `dismissDeath()` method**

In `web/app.js`, add a method on `playScreen()` (near `finishGame`):

```js
      async dismissDeath() {
        this.eliminated = false;
        await this.finishGame();
      },
```

- [ ] **Step 5: Reset elimination state in `_resetTurnState`**

In `web/app.js` `_resetTurnState()`, add (next to `this.gameOver = false;`):

```js
        this.eliminated = false;
        this.eliminatedTurn = null;
        this.eliminatedLostScore = 0;
```

- [ ] **Step 6: Add the overlay markup**

In `web/index.html`, inside the play `<section>` (after the `</div><!-- /play-layout -->` at ~line 568, before the section's loading card), add:

```html
      <!-- Elimination overlay: dramatic death moment before the between/report flow -->
      <div class="death-overlay" x-show="eliminated" x-cloak x-transition.opacity>
        <div class="death-panel">
          <div class="death-skull">💀</div>
          <h2 class="death-title">ELIMINATED</h2>
          <p class="death-sub">
            You were erased at turn <strong x-text="eliminatedTurn"></strong>.
            Your score
            (<strong x-text="squidArenaHelpers.fmtNum(eliminatedLostScore, 1)"></strong>)
            is gone.
          </p>
          <button class="submit-btn" @click="dismissDeath()">Continue →</button>
        </div>
      </div>
```

- [ ] **Step 7: Add the overlay styles**

Append to `web/styles.css`:

```css
/* Elimination overlay */
.death-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  background: rgba(8, 6, 10, 0.86);
  backdrop-filter: blur(3px);
}
.death-panel {
  text-align: center;
  padding: 40px 32px;
  max-width: 420px;
  color: #f5f5f7;
}
.death-skull {
  font-size: 88px;
  line-height: 1;
  animation:
    pop-in 0.32s cubic-bezier(0.34, 1.56, 0.64, 1) both,
    death-shake 0.5s ease-in-out 0.32s 2;
  filter: drop-shadow(0 4px 10px rgba(0, 0, 0, 0.6));
}
.death-title {
  font-family: var(--font-display);
  letter-spacing: 0.12em;
  color: #ff4d5e;
  margin: 14px 0 8px;
}
.death-sub { color: #d8d2da; margin-bottom: 22px; }
@keyframes death-shake {
  0%, 100% { transform: translateX(0) rotate(0); }
  25% { transform: translateX(-6px) rotate(-4deg); }
  75% { transform: translateX(6px) rotate(4deg); }
}
```

(Overlay backdrop is dark in both themes, so light text is correct regardless of `prefers-color-scheme`. `var(--font-display)` is already used elsewhere in this stylesheet — confirm the token name matches the codebase and adjust if different.)

- [ ] **Step 8: Verify in the running app**

Start the app and drive a human game with death forced on, to see the overlay deterministically:
- Temporarily append `&pdeath=1` handling is NOT wired — instead verify via the API-backed UI by playing normally (0.15 death is ~80% likely within 10 turns), OR use the browser devtools/Playwright to POST `/api/new_game` with `{"p_death_constant": 1.0}` and then drive one action.

Using Playwright MCP (preferred, deterministic): navigate to the app, then in the page context force a session via `fetch('/api/new_game', {method:'POST', headers:{'Content-Type':'application/json'}, body:'{"p_death_constant":1.0}'})`, wire its `session_id` into the Alpine component, submit one action, and confirm:
- The `.death-overlay` appears with 💀, "ELIMINATED", the turn number, and the pre-wipe score.
- Clicking "Continue →" hides the overlay and advances to the between-conditions / report view.
- The report table shows turns-survived out of **10** and score **0** for that condition.

Expected: overlay renders and dismisses cleanly; report denominators read `/ 10`.

- [ ] **Step 9: Commit**

```bash
git add web/app.js web/index.html web/styles.css
git commit -m "feat(web-arena): elimination overlay + sync human play to 10 turns"
```

---

## Self-Review

**Spec coverage:**
- 15→10 turns → Task 1 Step 3 (backend default) + Task 2 Step 1 (frontend `TOTAL_TURNS`). ✓
- Activate real p_death 0.15 → Task 1 Step 3 (`actual_death=True`; `p_death_constant` left at 0.15). ✓
- Death zeroes score + ends session → existing engine; asserted in Task 1 Step 1 (`new_score == 0.0`, `survived is False`). ✓
- Dramatic death UI → Task 2 Steps 2–7. ✓
- Human-play-only / no LLM arena change → Global Constraints; only `NewGameRequest` + `web/*` touched. ✓
- No `is_dead` API field → Global Constraints; frontend keys off `game_over_reason`. ✓
- Tests offline/deterministic → `p_death_constant: 1.0` forces death (Task 1 Step 1). ✓

**Placeholder scan:** No TBD/TODO. Two "confirm the exact name" notes (`state["total_turns"]` key, `turnNo` local var, `var(--font-display)` token) are verification guards, not deferred work — each names the file/location to check and the fallback action.

**Type consistency:** `eliminated`/`eliminatedTurn`/`eliminatedLostScore` and `dismissDeath()` are defined in Task 2 Step 2/4 and consumed in Step 6 with matching names. `game_over_reason === "eliminated"` matches the server string produced by `HumanGameSession` (`get_turn_state`/`submit_action`). `new_score` / `game_over` match `ActionResponse` fields.
