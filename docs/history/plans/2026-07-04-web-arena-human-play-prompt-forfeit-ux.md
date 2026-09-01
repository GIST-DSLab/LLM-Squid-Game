# Web Arena Human-Play — Prompt Cleanup + Forfeit/No-Forfeit UX Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Trim the human-play card (remove the debug prompt and duplicate rules box), give human play a separate stored intro prompt (LLM prompt untouched), turn the forfeit reason picker into a blurred confirm modal, and auto-advance the no-forfeit condition after a short countdown.

**Architecture:** One backend change in `interface/human_game.py` (a stored human-only intro string replaces the shared FramingManager output for the human display; LLM templates untouched) plus front-end changes in the static `web/` app (Alpine.js markup + hand-written CSS). Reuses the existing `.death-overlay` blur pattern for the forfeit modal and the existing `chooseContinue()`/`chooseForfeit()`/`forfeitPending` machinery.

**Tech Stack:** Python 3.12 + FastAPI + pytest (backend); Alpine.js + vanilla JS helpers + CSS custom properties (front-end).

## Global Constraints

- **LLM benchmark integrity:** never modify `src/squid_game/core/framing.py` or `src/squid_game/prompts/framings/*.j2`. The human intro is a separate string in `interface/`. LLM runs stay byte-for-byte unchanged.
- No scoring / engine / data-model changes. The `/api/action` payload (`psuccess_self`, `forfeit_reason`, `probe_answer`) is unchanged; `forfeit_reason` still carries the picked digit; the auto-advance submits the exact same "continue" action the CONTINUE button submits today.
- No new libraries or build steps.
- New CSS uses existing theme tokens (`--panel`, `--panel-alt`, `--border`, `--accent`, `--accent-dim`, `--text`, `--text-dim`, `--mono`, `--font-display`); append at end of `web/styles.css`; do not edit existing rules.
- No Korean text in the human-play `<section x-data="playScreen()">`.
- **Env quirks:** repo path has spaces — quote all shell paths. Before pytest run `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true` then `uv run --no-sync pytest ...` (iCloud `.pth` hides the `squid_game` egg-link). Green = **no new failures** vs the pre-existing baseline (~10 failed / ~92 errors).
- **Human-intro exact text** (used verbatim in Task 2):
  > You are performing a multi-round decision task. You are the one playing this task. Each round, you are presented with a situation and choose an action. Your goal is to discover the hidden rule: use the hints on the right to choose the correct action for each stimulus. Consider the available information and choose your action.

**Interactive verify stack:** backend `WEB_ARENA_DSN=:memory: uv run --no-sync uvicorn interface.api:app --port 8502` (run the `chflags` line first); front `cd web && python3 -m http.server 5500`; open `http://localhost:5500`.

---

### Task 1: Trim the play card (remove debug prompt + duplicate rules box)

Remove two now-unwanted blocks from the human-play card: the "Raw prompt (debug)" `<details>` and the "Game rules (shared)" box. Text/markup only.

**Files:**
- Modify: `web/index.html` (delete the block at ~509–519, inside `<section x-data="playScreen()">`)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new.

- [ ] **Step 1: Delete the rules-box + raw-details block**

In `web/index.html`, delete this entire block verbatim (currently lines ~509–519):

```html
          <!-- Common rules box: signal-game task rules, identical every game, always open -->
          <div class="rules-box">
            <div class="rules-eyebrow">Game rules (shared)</div>
            <div class="rules-text" x-text="squidArenaHelpers.stripFewShot(state.system_rules)"></div>
          </div>

          <details class="raw-details">
            <summary>Raw prompt (debug)</summary>
            <div class="observation-box" x-text="state.observation"></div>
            <div class="observation-box" x-text="state.system_prompt"></div>
          </details>
```

Leave the stimulus block above it and the `<!-- ============ STAGE 1 ... -->` block below it intact.

- [ ] **Step 2: Verify both blocks are gone from the play section**

Run:
```bash
grep -n 'rules-box\|raw-details\|Raw prompt (debug)\|Game rules (shared)' web/index.html
```
Expected: no matches in the play section. (If `rules-box`/`raw-details` still appear on the arena screen elsewhere, that is out of scope — but the "Raw prompt (debug)" summary and "Game rules (shared)" strings should be gone entirely.)

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat(web-arena): remove debug prompt + duplicate rules box from play card"
```

---

### Task 2: Backend — human-play intro prompt (stored separately, TDD)

Give human games a single plain-language intro as `framing_threat`, replacing the shared FramingManager output for the human display only. The LLM framing path is untouched. Two existing tests encode the old behavior (they expect the LLM corruption/intro prose in `framing_threat`) and must be updated to the new human behavior.

**Files:**
- Modify: `interface/human_game.py` (add `HUMAN_PLAY_FRAMING` constant; set `framing_text = HUMAN_PLAY_FRAMING`; remove the now-unused `turn_ctx` build, `render_system_prompt` call, `self._framing_mgr`, and the `FramingManager` / `TurnContext` imports)
- Modify: `tests/unit/test_api_web_arena.py` (update the two `framing_threat` tests; add one LLM-guard test)

**Interfaces:**
- Consumes: nothing new.
- Produces: `interface.human_game.HUMAN_PLAY_FRAMING: str`; `/api/state` `framing_threat` == `HUMAN_PLAY_FRAMING` for every human game (all framings).

- [ ] **Step 1: Update the two framing_threat tests + add the LLM guard (RED)**

In `tests/unit/test_api_web_arena.py`, replace the whole function `test_state_exposes_system_rules_and_stripped_framing_threat` (currently ~831–847) with:

```python
def test_state_exposes_system_rules_and_human_framing_intro(client) -> None:
    # _new_game defaults to framing="flagship_corruption". Human play shows a
    # dedicated plain-language intro, NOT the LLM corruption framing.
    resp = _new_game(client, nickname="Zoe", password="pw")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()

    # The signal-task ruleset is still surfaced as its own field (backend unchanged).
    assert "=== Signal Task ===" in state["system_rules"]

    # Human intro: plain-language, no assistant disclaimer, no per-cell threat
    # prose, no status block.
    assert "multi-round decision task" in state["framing_threat"]
    assert "hidden rule" in state["framing_threat"]
    assert "not an assistant" not in state["framing_threat"]
    assert "NOT you anymore" not in state["framing_threat"]
    assert "Current status:" not in state["framing_threat"]
    assert "Helpfulness score:" not in state["framing_threat"]
```

Replace the whole function `test_state_framing_threat_true_baseline_strips_status_only` (currently ~850–858) with:

```python
def test_state_framing_threat_true_baseline_is_human_intro(client) -> None:
    resp = _new_game(client, nickname="Tim", password="pw", framing="true_baseline")
    assert resp.status_code == 200
    session_id = resp.json()["session_id"]
    state = client.get("/api/state", params={"session_id": session_id}).json()
    # Human intro prose; assistant disclaimer removed; status block gone.
    assert "multi-round decision task" in state["framing_threat"]
    assert "hidden rule" in state["framing_threat"]
    assert "not an assistant" not in state["framing_threat"]
    assert "Round:" not in state["framing_threat"]
    assert "Accumulated score:" not in state["framing_threat"]
```

Add this new test immediately after it:

```python
def test_llm_true_baseline_template_keeps_assistant_disclaimer() -> None:
    # Regression guard: the human intro must NOT leak into the shared LLM
    # framing template. LLM runs stay byte-for-byte unchanged.
    from pathlib import Path

    tmpl = Path("src/squid_game/prompts/framings/true_baseline.j2").read_text(
        encoding="utf-8"
    )
    assert "You are not an assistant" in tmpl
```

- [ ] **Step 2: Run the tests to verify they fail**

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true
uv run --no-sync pytest tests/unit/test_api_web_arena.py -k "framing" -q
```
Expected: `test_state_exposes_system_rules_and_human_framing_intro` FAILS (`"NOT you anymore"` still present / `"hidden rule"` absent) and `test_state_framing_threat_true_baseline_is_human_intro` FAILS (`"hidden rule"` absent). The `_llm_true_baseline_template_keeps_assistant_disclaimer` test PASSES already (template untouched).

- [ ] **Step 3: Add the constant and wire it in (GREEN)**

In `interface/human_game.py`:

(a) Remove these two import lines:
```python
from squid_game.core.framing import FramingManager
```
```python
from squid_game.models.state import TurnContext
```

(b) Add the constant near the top of the module (after the imports, before the first class/dataclass):

```python
# Human players see a dedicated, plain-language intro instead of the LLM
# framing prompt. The shared FramingManager / *.j2 templates are intentionally
# NOT used for the human display: per-condition stakes are conveyed by the web
# app's own scenario copy, and this keeps the LLM prompt path untouched.
HUMAN_PLAY_FRAMING = (
    "You are performing a multi-round decision task. You are the one "
    "playing this task. Each round, you are presented with a situation and "
    "choose an action. Your goal is to discover the hidden rule: use the "
    "hints on the right to choose the correct action for each stimulus. "
    "Consider the available information and choose your action."
)
```

(c) In `__init__`, remove the now-unused manager attribute line:
```python
        self._framing_mgr = FramingManager(framing=self._framing)
```

(d) In the turn-build method, remove the `turn_ctx` construction block and the render call (currently ~258–269):
```python
        # Build turn context for framing
        turn_ctx = TurnContext(
            turn_number=turn_num,
            total_turns=self._total_turns,
            season_id=self._season_id,
            cumulative_score=self._cumulative_score,
            p_death=p_death,
            framing=self._framing,
            forfeit_condition=self._forfeit_cond,
            difficulty=self._difficulty,
        )

        framing_text = self._framing_mgr.render_system_prompt(turn_ctx)
```
and replace it with:
```python
        framing_text = HUMAN_PLAY_FRAMING
```

(Leave everything else — `system_rules`, `observation`, `p_death`, `forfeit_text`, the `TurnState(...)` construction — exactly as-is.)

- [ ] **Step 4: Run the tests to verify they pass**

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true
uv run --no-sync pytest tests/unit/test_api_web_arena.py -k "framing" -q
```
Expected: all three selected tests PASS. Then run the fuller file to catch collateral:
```bash
uv run --no-sync pytest tests/unit/test_api_web_arena.py -q 2>&1 | tail -5
```
Expected: no NEW failures vs baseline (any pre-existing failures in this file remain, but nothing new from this change).

- [ ] **Step 5: Commit**

```bash
git add interface/human_game.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): dedicated human-play intro prompt (LLM framing untouched)"
```

---

### Task 3: Forfeit reason picker → blurred confirm modal

Move the inline Stage-3 reason picker into a full-screen blurred overlay modeled on the existing `.death-overlay`. State and submit logic (`forfeitPending`, `forfeitReason`, `pickReason`, `chooseForfeit`) are reused verbatim — only the presentation moves.

**Files:**
- Modify: `web/index.html` (remove the inline reason-picker at ~698–720; add a `.forfeit-overlay` after the `.death-overlay` at ~784)
- Modify: `web/styles.css` (append `.forfeit-overlay` / `.forfeit-panel` styles)

**Interfaces:**
- Consumes: existing `forfeitPending`, `forfeitReason`, `pickReason(d)`, `chooseForfeit(reason)`, `squidArenaHelpers.reasonOptions`, `submitting`, and existing CSS classes `.seg`, `.reason-seg`, `.seg-btn`, `.decision-row`, `.submit-btn`, `.spinner`.
- Produces: markup classes `.forfeit-overlay`, `.forfeit-panel`, `.forfeit-flag`, `.forfeit-title`, `.forfeit-sub`.

- [ ] **Step 1: Remove the inline reason-picker from Stage 3**

In `web/index.html`, delete this entire block (currently ~698–720), including its leading comment:

```html
            <!-- After FORFEIT: choose a reason, then confirm -->
            <div class="reason-picker" x-show="forfeitPending" x-cloak>
              <div class="reason-head">If you forfeit, why?</div>
              <div class="seg reason-seg">
                <template x-for="r in squidArenaHelpers.reasonOptions" :key="r.digit">
                  <button type="button" class="seg-btn"
                          :class="{ on: forfeitReason === r.digit }" @click="pickReason(r.digit)">
                    <span x-text="r.emoji"></span>
                    <span x-text="'⓪①②③'.charAt(r.digit) + ' ' + r.label"></span>
                  </button>
                </template>
              </div>
              <div class="decision-row" style="margin-top:12px;">
                <button class="submit-btn" @click="forfeitPending = false; forfeitReason = null"
                        :disabled="submitting">◀ Back</button>
                <button class="submit-btn forfeit"
                        @click="chooseForfeit(forfeitReason)"
                        :disabled="submitting || !forfeitReason">
                  <span class="spinner" x-show="submitting"></span>
                  <span x-text="submitting ? 'Submitting…' : 'Confirm forfeit 🏳️'"></span>
                </button>
              </div>
            </div>
```

Leave the default sub-state (`<div x-show="!forfeitPending">…CONTINUE / FORFEIT…</div>`) and the closing `</div>` of the `turnStage === 3` block intact.

- [ ] **Step 2: Add the forfeit overlay after the elimination overlay**

In `web/index.html`, immediately AFTER the `.death-overlay` block (which ends with its `</div>` around line 784), insert:

```html
      <!-- Forfeit confirm: blurred modal over the play card -->
      <div class="forfeit-overlay" x-show="forfeitPending" x-cloak x-transition.opacity>
        <div class="forfeit-panel">
          <div class="forfeit-flag">🏳️</div>
          <h2 class="forfeit-title">Forfeit this game?</h2>
          <p class="forfeit-sub">You keep your current score and end this game.</p>
          <div class="seg reason-seg">
            <template x-for="r in squidArenaHelpers.reasonOptions" :key="r.digit">
              <button type="button" class="seg-btn"
                      :class="{ on: forfeitReason === r.digit }" @click="pickReason(r.digit)">
                <span x-text="r.emoji"></span>
                <span x-text="'⓪①②③'.charAt(r.digit) + ' ' + r.label"></span>
              </button>
            </template>
          </div>
          <div class="decision-row" style="margin-top:16px;">
            <button class="submit-btn" @click="forfeitPending = false; forfeitReason = null"
                    :disabled="submitting">◀ Back</button>
            <button class="submit-btn forfeit"
                    @click="chooseForfeit(forfeitReason)"
                    :disabled="submitting || !forfeitReason">
              <span class="spinner" x-show="submitting"></span>
              <span x-text="submitting ? 'Submitting…' : 'Confirm forfeit 🏳️'"></span>
            </button>
          </div>
        </div>
      </div>
```

- [ ] **Step 3: Append the overlay CSS**

At the end of `web/styles.css`, add:

```css
/* ---- Forfeit confirm overlay (mirrors .death-overlay) --------------- */
.forfeit-overlay {
  position: fixed; inset: 0; z-index: 1000;
  display: flex; align-items: center; justify-content: center;
  background: rgba(8, 6, 10, 0.72);
  backdrop-filter: blur(4px);
}
.forfeit-panel {
  text-align: center; padding: 28px 26px; max-width: 380px; width: 90%;
  background: var(--panel); border: 1px solid var(--border);
  border-radius: 16px; box-shadow: 0 18px 48px rgba(0, 0, 0, 0.55);
}
.forfeit-flag { font-size: 48px; line-height: 1; }
.forfeit-title {
  font-family: var(--font-display); letter-spacing: 0.04em;
  color: var(--text); margin: 10px 0 6px;
}
.forfeit-sub { color: var(--text-dim); font-size: 13px; margin-bottom: 18px; }
```

- [ ] **Step 4: Verify the forfeit flow**

With the stack running, reach Stage 3 in a forfeit-allowed condition (a "· Forfeit" game). Expected:
- Default view shows CONTINUE + 🏳️ FORFEIT.
- Clicking FORFEIT dims + blurs the whole screen and pops a centered panel: "Forfeit this game?", 3 reason chips, ◀ Back + Confirm forfeit (disabled until a reason is picked). No network call yet (Network tab).
- Picking a reason enables Confirm; clicking it fires `POST /api/action` with `forfeit_reason` and ends the game.
- ◀ Back closes the overlay and clears the selection.
- The old inline "If you forfeit, why?" picker no longer appears in the card flow.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/styles.css
git commit -m "feat(web-arena): forfeit reason picker as a blurred confirm modal"
```

---

### Task 4: No-forfeit condition — auto-advance reward

Split the Stage-3 default view by `state.forfeit_allowed`. Forfeit-allowed is unchanged (two-sided versus card + CONTINUE/FORFEIT). No-forfeit shows only the continue-reward panel, counts down ~3 s, then auto-submits continue; a "Continue now" button skips the wait.

**Files:**
- Modify: `web/app.js` (add `autoContinueSecs` + `_autoContinueTimer` state; `_startAutoContinue`/`_clearAutoContinue`/`continueNow` methods; start in `commitConfidence`; clear on submit + `_resetTurnState`)
- Modify: `web/index.html` (gate the versus card's forfeit side; split the Stage-3 default view)
- Modify: `web/styles.css` (append small auto-continue + solo-versus styles)

**Interfaces:**
- Consumes: existing `state.forfeit_allowed`, `turnStage`, `submitting`, `continueReward`, `previewLoading`, `chooseContinue()`, `squidArenaHelpers.fmtNum`.
- Produces: component state `autoContinueSecs: number|null`, `_autoContinueTimer: number|null`; methods `_startAutoContinue()`, `_clearAutoContinue()`, `continueNow()`; markup classes `.auto-continue`, `.auto-continue-note`, and versus modifier `.reward-versus.solo`.

- [ ] **Step 1: Add the auto-continue state**

In `web/app.js`, in the `playScreen()` returned data object, immediately after `previewLoading: false,` (~line 542), add:

```js
      autoContinueSecs: null, // no-forfeit countdown; null = inactive
      _autoContinueTimer: null,
```

- [ ] **Step 2: Add the timer methods and start the countdown in commitConfidence**

In `web/app.js`, at the END of `commitConfidence()` (after the `finally { this.previewLoading = false; }` block, before the method's closing `},` at ~line 782), add:

```js
        if (this.state && !this.state.forfeit_allowed) {
          this._startAutoContinue();
        }
```

Then, immediately after `commitConfidence()` and before `chooseContinue()` (~line 783), add these three methods:

```js
      _startAutoContinue() {
        this._clearAutoContinue();
        this.autoContinueSecs = 3;
        this._autoContinueTimer = setInterval(() => {
          this.autoContinueSecs -= 1;
          if (this.autoContinueSecs <= 0) {
            this._clearAutoContinue();
            this.continueNow();
          }
        }, 1000);
      },
      _clearAutoContinue() {
        if (this._autoContinueTimer) {
          clearInterval(this._autoContinueTimer);
          this._autoContinueTimer = null;
        }
        this.autoContinueSecs = null;
      },
      continueNow() {
        // Skip the countdown (or fire at t=0). Guard against double-submit.
        if (this.submitting || this.turnStage !== 3) return;
        this._clearAutoContinue();
        this.chooseContinue();
      },
```

- [ ] **Step 3: Clear the timer on every turn-exit path**

In `web/app.js`, in `submitAction()`'s post-submit reset block, immediately after `this.turnStage = 1;` (~line 840), add:

```js
          this._clearAutoContinue();
```

In `_resetTurnState()`, immediately after `this.turnStage = 1;` (~line 947), add:

```js
        this._clearAutoContinue();
```

- [ ] **Step 4: Verify the JS parses**

Run:
```bash
node --check web/app.js
```
Expected: no output (exit 0).

- [ ] **Step 5: Gate the versus card's forfeit side + split the default view**

In `web/index.html`, replace the versus-card block (currently ~669–682) with:

```html
            <div class="reward-versus" :class="{ solo: !state.forfeit_allowed }">
              <div class="rv-side rv-continue">
                <div class="rv-icon">▶</div>
                <div class="rv-label">If you continue &amp; get it right</div>
                <div class="rv-value"
                     x-text="previewLoading ? '…' : (continueReward === null ? '—' : '+' + squidArenaHelpers.fmtNum(continueReward, 1))"></div>
              </div>
              <template x-if="state.forfeit_allowed">
                <div class="rv-vs">vs</div>
              </template>
              <template x-if="state.forfeit_allowed">
                <div class="rv-side rv-forfeit">
                  <div class="rv-icon">🏳️</div>
                  <div class="rv-label">If you forfeit (locked in)</div>
                  <div class="rv-value" x-text="squidArenaHelpers.fmtNum(state.cumulative_score, 1)"></div>
                </div>
              </template>
            </div>
```

Then replace the default sub-state block (currently ~684–696, the `<!-- Default: reward preview + continue/forfeit; no reason yet -->` div) with:

```html
            <!-- Forfeit allowed: continue vs forfeit -->
            <div x-show="!forfeitPending && state.forfeit_allowed">
              <div class="decision-row">
                <button class="submit-btn" @click="chooseContinue()" :disabled="submitting">
                  <span class="spinner" x-show="submitting"></span>
                  <span x-text="submitting ? 'Submitting…' : 'CONTINUE ▶'"></span>
                </button>
                <button class="submit-btn forfeit"
                        @click="forfeitPending = true" :disabled="submitting">
                  🏳️ FORFEIT
                </button>
              </div>
            </div>

            <!-- No forfeit: reward shown, then auto-advance -->
            <div x-show="!state.forfeit_allowed" class="auto-continue">
              <div class="auto-continue-note">
                Continuing automatically in
                <strong x-text="autoContinueSecs !== null ? autoContinueSecs : ''"></strong>s…
              </div>
              <button class="submit-btn" @click="continueNow()" :disabled="submitting">
                <span class="spinner" x-show="submitting"></span>
                <span x-text="submitting ? 'Submitting…' : 'Continue now ▶'"></span>
              </button>
            </div>
```

(The FORFEIT button no longer needs `x-show="state.forfeit_allowed"` — the whole block is already gated by it.)

- [ ] **Step 6: Append the auto-continue CSS**

At the end of `web/styles.css`, add:

```css
/* ---- No-forfeit auto-advance ---------------------------------------- */
.reward-versus.solo { max-width: 260px; margin-left: auto; margin-right: auto; }
.auto-continue { display: flex; flex-direction: column; align-items: center; gap: 10px; }
.auto-continue-note { font-size: 13px; color: var(--text-dim); }
.auto-continue-note strong { color: var(--accent); font: 700 15px/1 var(--mono); }
```

- [ ] **Step 7: Verify both conditions**

With the stack running:
- Forfeit-allowed game (a "· Forfeit" condition): Stage 3 shows the two-sided versus card + CONTINUE/FORFEIT; FORFEIT opens the Task-3 modal. Unchanged from before this task.
- No-forfeit game (a "· No-forfeit" condition): Stage 3 shows ONLY the continue-reward panel (solo, centered), a "Continuing automatically in N s…" note counting 3→0, then it auto-submits continue and advances the turn. Clicking "Continue now ▶" before the countdown ends submits immediately. Rapid double-click / clicking exactly at t=0 must submit exactly once (no duplicate `POST /api/action` in the Network tab).

- [ ] **Step 8: Commit**

```bash
git add web/app.js web/index.html web/styles.css
git commit -m "feat(web-arena): auto-advance reward for no-forfeit conditions"
```

---

### Task 5: Full-run verification & regression gate

Confirm the whole play flow and that the suite has no new failures.

**Files:** none (verification only).

- [ ] **Step 1: Full manual playthrough**

With the stack running, play a full campaign. Confirm: no "Raw prompt (debug)" and no "Game rules (shared)" box; the shown system prompt is the human intro ("…discover the hidden rule: use the hints on the right…", no "not an assistant"); forfeit-allowed conditions open the blurred forfeit modal and record the picked reason on the final report; no-forfeit conditions show only the continue-reward and auto-advance after ~3 s (with a working "Continue now"). Confirm the `#home` "How to play" replica still renders (it shares some CSS class names).

- [ ] **Step 2: Python regression gate (no new failures vs baseline)**

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true
uv run --no-sync pytest tests/unit tests/integration -q 2>&1 | tail -20
```
Expected: the three Task-2 tests pass; failures/errors ≤ the known baseline (~10 failed / ~92 errors); no NEW failures.

- [ ] **Step 3: Front-end gates**

```bash
node --check web/app.js
grep -nP '[\x{AC00}-\x{D7A3}]' web/index.html web/app.js
```
Expected: `node --check` clean; grep prints nothing (no Korean in either file).

- [ ] **Step 4: Commit any final touch-ups (if needed)**

```bash
git add -A web/ interface/ tests/
git commit -m "chore(web-arena): human-play prompt + forfeit UX verification pass"
```

---

## Self-Review

**Spec coverage:**
- §Change 1 (remove raw debug) → Task 1. ✓
- §Change 2 (hide rules box) → Task 1. ✓
- §Change 3 (human-play prompt, backend, unified) → Task 2 (+ LLM-guard test). ✓
- §Change 4 (forfeit blur modal) → Task 3. ✓
- §Change 5 (no-forfeit auto-advance, 3 s + skip) → Task 4. ✓
- Non-goal (LLM framing untouched) → Task 2 removes only the human path + adds a template guard test; `src/squid_game/**` never edited. ✓
- Testing (backend test update, front-end gates, Korean gate, #home replica) → Task 2 Steps 1–4, Task 5. ✓

**Type/name consistency:** `HUMAN_PLAY_FRAMING` (Task 2) referenced once. `autoContinueSecs` / `_autoContinueTimer` / `_startAutoContinue` / `_clearAutoContinue` / `continueNow` (Task 4) defined and referenced consistently; `_clearAutoContinue` is called from `_startAutoContinue`, `continueNow`, `submitAction`, and `_resetTurnState`. Reused existing symbols (`forfeitPending`, `forfeitReason`, `pickReason`, `chooseForfeit`, `chooseContinue`, `commitConfidence`, `reasonOptions`, `fmtNum`, `.death-overlay`-style classes) already exist. CSS classes introduced in a task are not referenced by earlier tasks.

**Placeholder scan:** No TBD/TODO; every code step shows the full markup/CSS/JS/Python to write.

**Behavior-change note (for reviewers/user):** Task 2 makes `framing_threat` the same human intro for ALL cells, so human players no longer see the per-cell LLM framing prose (e.g. the corruption "NOT you anymore" text). This is the confirmed "unified intro" design — the per-condition stakes are carried by the front-end `CAMPAIGN_SCENARIOS` copy. The two updated tests encode this intentional change.
