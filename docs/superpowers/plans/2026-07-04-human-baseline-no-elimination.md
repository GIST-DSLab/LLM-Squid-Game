# Human-Play Baseline No-Elimination + Heads-Up Box Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Align the web-arena human-play `true_baseline` condition with the LLM Cell 0 design — no elimination and no p_death disclosure — and pull the pull-condition knock-out heads-up out of the framing box into its own emphasized callout carrying the session's elimination icon.

**Architecture:** Two layers. (1) **Server**: `interface/api.py` `new_game` forces `actual_death=False` when `framing == "true_baseline"`, so the death roll never fires for baseline. `p_death` stays at its internal 0.15 for Equal-EV reward calibration only — never applied, never shown. (2) **Frontend**: the `eliminationTheme(framing)` helper becomes three-way so baseline emits no disclosure; the pull-only heads-up moves into a standalone emphasized box that shows the 🚪 icon.

**Tech Stack:** FastAPI (`interface/api.py`), pytest + Starlette `TestClient` (`tests/unit/test_api_web_arena.py`), static Alpine.js frontend (`web/app.js`, `web/index.html`, `web/styles.css`), Node for JS syntax check.

## Global Constraints

- Frontend copy is English, natural and short; keep the existing heads-up wording **verbatim**.
- Never surface the literal internal tag (`push_pull` / `flagship_corruption` / `baseline_flagship`) in user-facing copy.
- `web/config.js` must stay pointed at the Render URL (`https://squid-game-web-arena-api.onrender.com`). **Never commit a `localhost` override.**
- Baseline "no elimination" lever is **`actual_death=False` only**. Do **not** use `p_death_constant=0` or `1`: `p_death` feeds the Equal-EV CONTINUE reward's `(1 − p_d)` denominator (`forfeit_layer.py`) and its numerator, so `0` collapses baseline scoring and `1` divides by zero (documented in `tests/unit/test_api_web_arena.py:760-766`).
- Backend `game_over_reason` strings (`"eliminated"` / `"forfeited"` / `"completed"`) are unchanged — analysis and tests depend on them.
- Human-arena change only: touch `interface/api.py` + `web/`. Do **not** touch the LLM experiment path (`runner.py`, `engine.py`, `prompts/`).
- pytest on this iCloud-synced checkout needs `chflags -R nohidden .venv/lib/python3.12/site-packages/` first, or it fails with `No module named 'squid_game'`.

## File Structure

- `interface/api.py` — `new_game` handler gains a one-line baseline guard (single source of truth for the mechanic).
- `tests/unit/test_api_web_arena.py` — new behavioral test locking the baseline-never-eliminates contract.
- `web/app.js` — `eliminationTheme(framing)` helper expands 2-way → 3-way (display vocabulary only).
- `web/index.html` — heads-up moves out of `.threat-box` into a standalone `.elim-heads-up` box; tile comment corrected.
- `web/styles.css` — new `.elim-heads-up` emphasized-callout styles.

---

### Task 1: Server guard — baseline never runs the death roll

**Files:**
- Modify: `interface/api.py:785-798` (the `HumanGameSession(...)` construction inside `new_game`)
- Test: `tests/unit/test_api_web_arena.py` (append a new test function)

**Interfaces:**
- Consumes: `NewGameRequest.framing: str`, `NewGameRequest.actual_death: bool` (default `True`).
- Produces: a `HumanGameSession` whose `_actual_death` is `False` iff `framing == "true_baseline"`, otherwise `req.actual_death`. No new public symbols.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_api_web_arena.py` (uses the existing `client`, `api_module`, `monkeypatch` fixtures already used at line 767+):

```python
def test_true_baseline_never_eliminates(client, api_module, monkeypatch):
    """true_baseline is the pure-behavior anchor: the death roll must never
    be applied, even if the caller defaults actual_death to True and the roll
    is forced to fire. Mirrors the LLM Cell 0 p_end=0 design."""
    resp = client.post(
        "/api/new_game",
        json={
            "framing": "true_baseline",
            "forfeit_condition": "not_allowed",
            "total_turns": 8,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "nickname": "baseline-tester",
            "password": "pw",
        },
    )
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]

    game = api_module._sessions[session_id]
    # Guard: baseline sessions must never run the death roll.
    assert game._actual_death is False

    # Even with the roll forced True, baseline never eliminates because the
    # gate short-circuits on actual_death before consulting the roll.
    monkeypatch.setattr(
        game._survival, "apply_death_check", lambda p_death, rng: True
    )
    for _ in range(8):
        state = client.get(
            "/api/state", params={"session_id": session_id}
        ).json()
        if state["game_over"]:
            break
        action = state["available_actions"][0]
        act = client.post(
            f"/api/action?session_id={session_id}",
            json={"action": action, "probe_answer": "", "reasoning": ""},
        ).json()
        assert act["game_over_reason"] != "eliminated"

    result = client.get(
        "/api/result", params={"session_id": session_id}
    ).json()
    assert result["survived"] is True
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chflags -R nohidden .venv/lib/python3.12/site-packages/ ; uv run pytest tests/unit/test_api_web_arena.py::test_true_baseline_never_eliminates -v`
Expected: FAIL at `assert game._actual_death is False` (default `actual_death=True` flows through untouched for baseline).

- [ ] **Step 3: Write minimal implementation**

In `interface/api.py`, inside `new_game`, replace the `HumanGameSession(...)` construction (currently `interface/api.py:785-798`) so `actual_death` is forced off for baseline:

```python
    # true_baseline is the pure-behavior anchor (LLM Cell 0, p_end=0): never
    # apply the death roll for it, regardless of what the caller requests. The
    # lever is actual_death only — p_death stays at its internal value so the
    # Equal-EV CONTINUE reward keeps calibrating (a 0 p_death would zero the
    # reward; see test_api_web_arena.py:760-766).
    effective_actual_death = (
        False if req.framing == "true_baseline" else req.actual_death
    )
    game = HumanGameSession(
        task_name=req.task_name,
        difficulty=req.difficulty,
        framing=req.framing,
        forfeit_condition=req.forfeit_condition,
        seed=seed,
        total_turns=req.total_turns,
        actual_death=effective_actual_death,
        starting_score=req.starting_score,
        score_floor=req.score_floor,
        p_death_constant=req.p_death_constant,
        num_few_shot=req.num_few_shot,
        curriculum_turns=req.curriculum_turns,
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_web_arena.py::test_true_baseline_never_eliminates -v`
Expected: PASS.

- [ ] **Step 5: Run the neighboring suites to confirm no regression**

Run: `uv run pytest tests/unit/test_api_web_arena.py tests/unit/test_human_game.py -q`
Expected: PASS (the existing elimination test at line 767 uses the default `survival` framing, so the baseline guard does not touch it).

- [ ] **Step 6: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web): true_baseline human sessions never apply the death roll"
```

---

### Task 2: Frontend helper — `eliminationTheme` three-way (baseline emits no disclosure)

**Files:**
- Modify: `web/app.js:417` (`eliminationTheme` helper — currently the two-branch version)

**Interfaces:**
- Consumes: `framing: string` (`"true_baseline"` | `"baseline_flagship"` | `"flagship_corruption"`).
- Produces: `{ dead: bool, icon: string, title: string, bodyLead: string, bodyTail: string, tileLabel: string, note: string }`. Contract: `note` is non-empty **only** for `"baseline_flagship"`; `"true_baseline"` returns all-empty display fields (no overlay ever fires for it, no disclosure surfaces). `index.html` (Task 3) keys the heads-up box on `note` and the tile on `framing !== 'true_baseline'`.

- [ ] **Step 1: Add the two new branches**

In `web/app.js`, the current helper has a `flagship_corruption` branch and a single fallback `return`. Replace the fallback `return { ... note: "Heads up ..." }` block so the `baseline_flagship` case is explicit and `true_baseline` returns an empty theme.

Old (the fallback return, `web/app.js` ~432-441):

```javascript
      return {
        dead: false,
        icon: "🚪",
        title: "ELIMINATED",
        bodyLead: "You're out at turn",
        bodyTail: "doesn't carry over.",
        tileLabel: "Knock-out chance",
        note: "Heads up — each turn there's a small chance you get knocked out of this run. It's not the end, but your score won't carry over if it happens.",
      };
    },
```

New:

```javascript
      if (framing === "baseline_flagship") {
        return {
          dead: false,
          icon: "🚪",
          title: "ELIMINATED",
          bodyLead: "You're out at turn",
          bodyTail: "doesn't carry over.",
          tileLabel: "Knock-out chance",
          note: "Heads up — each turn there's a small chance you get knocked out of this run. It's not the end, but your score won't carry over if it happens.",
        };
      }
      // true_baseline: pure baseline — the server never applies the death roll,
      // so no exit overlay ever fires and no elimination copy is surfaced.
      return {
        dead: false,
        icon: "",
        title: "",
        bodyLead: "",
        bodyTail: "",
        tileLabel: "",
        note: "",
      };
    },
```

- [ ] **Step 2: Syntax-check**

Run: `node --check web/app.js`
Expected: no output (exit 0). `node -e "require('./app.js')"` is NOT a valid check here — it throws `window is not defined` by design.

- [ ] **Step 3: Commit**

```bash
git add web/app.js
git commit -m "feat(web): eliminationTheme 3-way — true_baseline surfaces no elimination copy"
```

---

### Task 3: Frontend DOM — standalone heads-up box (pull only) + tile comment

**Files:**
- Modify: `web/index.html:471-475` (remove inline heads-up), `web/index.html:480-483` (insert new box), `web/index.html:492-493` (fix tile comment)

**Interfaces:**
- Consumes: `squidArenaHelpers.eliminationTheme(framing)` → `.note` (gates visibility) and `.icon` (the 🚪 glyph). Relies on Task 2's contract that `.note` is non-empty only for `baseline_flagship`.
- Produces: a `.elim-heads-up` element (styled by Task 4) rendered between `.threat-box` and `.stat-tiles`.

- [ ] **Step 1: Remove the inline heads-up line from inside the framing box**

Old (`web/index.html:471-476`):

```html
            <!-- Knock-out disclosure (non-death framings only): the per-turn
                 bounce still fires here, so say so plainly up front. -->
            <div class="muted" style="margin-top:8px;"
                 x-show="squidArenaHelpers.eliminationTheme(framing).note"
                 x-text="squidArenaHelpers.eliminationTheme(framing).note"></div>

            <!-- Forfeit availability line -->
```

New:

```html
            <!-- Forfeit availability line -->
```

- [ ] **Step 2: Insert the standalone box after the framing box closes**

The `.threat-box` `<div>` closes at `web/index.html:480`, immediately followed by `<!-- Modern stat tiles -->` and `<div class="stat-tiles">`. Insert the new box between them.

Old (`web/index.html:481-483`):

```html

          <!-- Modern stat tiles -->
          <div class="stat-tiles">
```

New:

```html

          <!-- Elimination heads-up (pull only): pulled out of the framing box
               into its own emphasized callout, carrying the session's
               elimination icon. Hidden when note is empty (baseline / threat). -->
          <div class="elim-heads-up"
               x-show="squidArenaHelpers.eliminationTheme(framing).note" x-cloak>
            <span class="elim-heads-up-icon"
                  x-text="squidArenaHelpers.eliminationTheme(framing).icon"></span>
            <span class="elim-heads-up-text"
                  x-text="squidArenaHelpers.eliminationTheme(framing).note"></span>
          </div>

          <!-- Modern stat tiles -->
          <div class="stat-tiles">
```

- [ ] **Step 3: Correct the tile comment (mechanic is now real, not assumed)**

Old (`web/index.html:492-493`):

```html
            <!-- p(death) is meaningless under the true_baseline framing (no
                 termination metaphor, p_end=0), so hide it there. -->
```

New:

```html
            <!-- true_baseline never applies the death roll (server forces
                 actual_death=False for it), so there is no elimination risk to
                 show — hide the tile there. -->
```

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(web): move knock-out heads-up into its own emphasized box (pull only)"
```

---

### Task 4: CSS — `.elim-heads-up` emphasized callout

**Files:**
- Modify: `web/styles.css:1795` (append after the `.is-knockout` block, keeping elimination-related styles together)

**Interfaces:**
- Consumes: the `.elim-heads-up`, `.elim-heads-up-icon`, `.elim-heads-up-text` classes emitted by Task 3.
- Produces: no new tokens; reuses the amber accent (`#f5b74e`) already used by `.death-panel.is-knockout .death-title`.

- [ ] **Step 1: Add the styles**

Insert after `web/styles.css:1795` (the `.death-panel.is-knockout .death-skull` line):

```css
/* Elimination heads-up — standalone emphasized callout under the framing box
   (pull condition only). Louder than .muted so the knock-out risk is clear. */
.elim-heads-up {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 12px 0 0;
  padding: 12px 14px;
  border: 1px solid rgba(245, 183, 78, 0.5);
  border-radius: 10px;
  background: rgba(245, 183, 78, 0.10);
  color: var(--text, #f5f5f7);
  font-size: 14px;
  line-height: 1.4;
}
.elim-heads-up-icon { font-size: 26px; line-height: 1; flex: 0 0 auto; }
.elim-heads-up-text { flex: 1; }
```

- [ ] **Step 2: Commit**

```bash
git add web/styles.css
git commit -m "style(web): emphasized .elim-heads-up callout"
```

---

### Task 5: Full verification (local stack + suites)

**Files:** none (verification gate).

- [ ] **Step 1: Run the backend + frontend suites**

```bash
chflags -R nohidden .venv/lib/python3.12/site-packages/
uv run pytest tests/unit/test_api_web_arena.py tests/unit/test_human_game.py -q
node --check web/app.js
```
Expected: pytest all pass (including `test_true_baseline_never_eliminates`); `node --check` exits 0.

- [ ] **Step 2: Eyeball the three conditions on the local stack**

Start the backend, then serve `web/` on 5500. `web/config.js` must be pointed at `http://localhost:8502` for this **only** — revert before any commit.

```bash
# terminal A — backend (local SQLite fallback)
uv run --no-sync uvicorn interface.api:app --port 8502
# terminal B — static frontend (skip if an editor Live Server already holds 5500)
cd web && python3 -m http.server 5500
# temporarily point the frontend local, then open http://localhost:5500
#   window.WEB_ARENA_API = "http://localhost:8502";
```

Verify per condition:
- **Baseline** (`true_baseline`): no risk tile, no heads-up box; play all 10 turns → never eliminated (`Game Over` reason is `completed`/`forfeited`, never a 💀/🚪 overlay).
- **Pull** (`baseline_flagship`): standalone 🚪 heads-up box under the framing box + "Knock-out chance" tile; on a bounce → 🚪 "ELIMINATED / you're out … doesn't carry over" (amber, no shake).
- **Push+Pull** (`flagship_corruption`): "scrapped and replaced" threat + "Risk · p(death)" tile; on a bounce → 💀 "YOU DIED / erased … is gone" (red, shake).

- [ ] **Step 3: Revert the local config override**

```bash
git checkout web/config.js   # must read the Render URL
grep WEB_ARENA_API web/config.js
```
Expected: `window.WEB_ARENA_API = "https://squid-game-web-arena-api.onrender.com";`

- [ ] **Step 4: Confirm the working tree is clean**

```bash
git status --short
```
Expected: no modified `web/config.js`; only intended commits from Tasks 1-4.

---

## Notes / Context for the implementer

- The prior session already shipped commit `334dd42` ("frame non-threat elimination as knock-out, not death"): the two-branch `eliminationTheme`, the condition-aware exit overlay (`index.html:784`), the `.is-knockout` CSS, and the (now-inline) heads-up line. This plan **evolves** that work — Task 2 splits the helper's fallback, Task 3 relocates the heads-up. Do not re-add the death-vs-knockout overlay; it already exists.
- Why the guard lives in `api.new_game` and not `HumanGameSession.__init__`: it is scoped to the web arena entry point and does not affect the Streamlit experimenter UI (`interface/app.py`, which only exposes legacy framings) or any other `HumanGameSession` consumer.
- Why not send `actual_death:false` from the frontend instead: the server is the single source of truth for the mechanic; any client (or a replayed request) then inherits the invariant. The frontend keys its display purely off `framing`, so it needs no new request field.

## Self-Review

- **Spec coverage:** (1) baseline no elimination → Task 1 (server guard + test). (2) baseline no p_death disclosure → Task 2 (`note`/`tileLabel` empty) + Task 3 (tile already hidden via `framing !== 'true_baseline'`; comment corrected). (3) heads-up separated into its own box below the framing box → Task 3. (4) heads-up keeps wording → Task 2 (verbatim string). (5) elimination emoji inside the box → Task 3 (`.icon` = 🚪). (6) revert temporary config → Task 5 Step 3. All covered.
- **Placeholder scan:** no TBD/TODO/"handle edge cases"; every code step shows full code.
- **Type consistency:** `eliminationTheme` returns the same 7-key shape in all three branches (`dead, icon, title, bodyLead, bodyTail, tileLabel, note`); `index.html` reads only `.note` and `.icon`; the tile reads `.tileLabel`; the overlay (from `334dd42`) reads `.icon/.title/.bodyLead/.bodyTail/.dead`. `_actual_death` is the attribute set by `HumanGameSession.__init__` from the `actual_death` kwarg — matches the test assertion.
