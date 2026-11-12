# Web Arena Human-Play — Prompt Cleanup + Forfeit/No-Forfeit UX Design

**Date:** 2026-07-04
**Branch:** `feat/human-play-10turns-death`
**Status:** Approved (user said 진행해줘; recommended defaults confirmed)
**Predecessor:** builds on `docs/superpowers/plans/2026-07-04-web-arena-human-play-uiux.md` (English copy, chip-menu, themed slider, forfeit-after-click, versus card, report Reason — all merged, commits `200f1a7`..`a1ba604`).

## Goal

Clean up what the human player sees before/around each decision, and split the Stage-3 experience by whether forfeit is allowed:

1. Remove the raw-prompt (debug) block from the play screen.
2. Hide the duplicate "Game rules (shared)" box.
3. Give human play a **separate, stored** system-prompt intro (LLM prompt untouched), with "not an assistant" removed and a signal-game hidden-rule explanation added.
4. Turn the forfeit reason picker into a **blurred confirm modal** (reusing the existing elimination-overlay pattern) instead of an inline sub-view.
5. In no-forfeit conditions, show only the continue-reward panel for ~3 s then **auto-advance** (auto-submit continue), with a skip button.

## Non-Goals / Constraints

- **LLM benchmark integrity:** the shared `FramingManager` and `src/squid_game/prompts/framings/*.j2` are NOT modified. The human-play intro is a separate, human-only prompt path. LLM runs are byte-for-byte unchanged.
- No scoring / engine / data-model changes. The `/api/action` payload (`psuccess_self`, `forfeit_reason`, `probe_answer`) is unchanged; `forfeit_reason` still carries the picked digit.
- Front-end stays Alpine.js + vanilla helpers + hand-written CSS with theme tokens; no new libraries.
- The auto-advance must submit exactly the same "continue" action the CONTINUE button submits today — timing only, no new server semantics.

## Current-State Anchors (verified 2026-07-04)

Backend:
- Displayed system prompt = `state.framing_threat`, set at `interface/api.py:689` from `_strip_status_block(state.framing_text)`.
- `framing_text` = `self._framing_mgr.render_system_prompt(turn_ctx)` at `interface/human_game.py:269` — the SHARED manager (`src/squid_game/core/framing.py:40`), templates in `src/squid_game/prompts/framings/` (`true_baseline.j2:18` holds the "You are performing a multi-round decision task. You are not an assistant — …" text).
- `TurnState` dataclass fields incl. `framing_text`, `system_rules` at `interface/human_game.py:91`; response serializer at `interface/api.py:676–689` (`system_prompt`, `system_rules`, `framing_threat`).
- Existing test asserting the string: `tests/unit/test_api_web_arena.py:856` (`"multi-round decision task" in state["framing_threat"]`).

Front-end (`web/index.html`, play section `<section x-data="playScreen()">` ~349):
- `state.framing_threat` shown at `:455` (`.threat-text`).
- `.rules-box` (`state.system_rules`) at `:510–513`.
- `.raw-details` debug block at `:515–519` (`state.observation` + `state.system_prompt`).
- Stage 3 today (post prior feature): `.reward-versus` card at `:669`, default sub-state `x-show="!forfeitPending"` at `:685` (CONTINUE + FORFEIT), reason-picker sub-state `x-show="forfeitPending"` at `:699`.
- Elimination overlay to reuse: `.death-overlay` markup `:771–784`; CSS `web/styles.css:1587–1623` (`position:fixed; inset:0; z-index:1000; background:rgba(8,6,10,.86); backdrop-filter:blur(3px)`).
- `playScreen()` component state incl. `forfeitPending`, `forfeitReason`, `openMenu`; helpers `continueReward`, `previewLoading`, `chooseContinue()`, `chooseForfeit(reason)`, `pickReason(d)`, `_resetTurnState()`, `submitAction()`.

## Design

### Change 1 — Remove raw prompt (debug)
Delete `.raw-details` (`index.html:515–519`) from the play section only. Arena-screen raw blocks (`:895+`, `:1329+`) are out of scope and unchanged. No JS/CSS needed (the `.raw-details` CSS may remain if used elsewhere; if unused after removal, leave it — not worth churn).

### Change 2 — Hide the duplicate "Game rules (shared)" box
Remove `.rules-box` (`index.html:510–513`). The `stripFewShot`/`state.system_rules` binding is dropped from the play view. `system_rules` still flows from the API (no backend change); it is simply not displayed. If `stripFewShot` becomes unused anywhere, leave the helper in place (out of scope).

### Change 3 — Human-play system prompt (backend, stored separately)
- **Storage:** a single human-play intro string, stored server-side in `interface/` (constant/module in `interface/human_game.py`, or a small `interface/`-local text). It is NOT a `src/squid_game/prompts/framings/*.j2` file and is NOT rendered through the shared `FramingManager`.
- **Application:** `interface/human_game.py` sets the human-play `framing_text` (the value that becomes `framing_threat`) to this stored intro for all human games, replacing the shared-manager output for DISPLAY. The shared manager may still be called if its output is needed elsewhere, but the human `framing_threat` returned to the client is the human intro. The status block (`Round`, `Accumulated score`) handling stays as today (`_strip_status_block`).
- **Scope decision (confirmed):** ONE unified human intro for all 6 cells. Per-cell stakes are already conveyed by the front-end `CAMPAIGN_SCENARIOS` copy, so the framing_threat does not need per-cell push/pull/corruption text for humans.
- **Text (exact):**
  > You are performing a multi-round decision task. You are the one playing this task. Each round, you are presented with a situation and choose an action. Your goal is to discover the hidden rule: use the hints on the right to choose the correct action for each stimulus. Consider the available information and choose your action.
- **Invariants:** contains "multi-round decision task" and "hidden rule" and "hints on the right"; does NOT contain "not an assistant". LLM framing render path unchanged.

### Change 4 — Forfeit confirm as a blurred modal
- Replace the inline `x-show="forfeitPending"` reason-picker sub-view with a full-screen overlay modeled on `.death-overlay`: new classes `.forfeit-overlay` (fixed, inset 0, z-index ~1000, dark translucent bg + `backdrop-filter: blur(3px)`) and `.forfeit-panel` (centered card).
- Trigger unchanged: FORFEIT button sets `forfeitPending = true` (no submit). The overlay is `x-show="forfeitPending" x-cloak x-transition.opacity`.
- Panel contents: heading "Forfeit this game?", a one-line consequence ("You keep your current score and end this game."), the 3 reason chips (`squidArenaHelpers.reasonOptions`, `pickReason(r.digit)`), and two buttons — **Back** (`forfeitPending=false; forfeitReason=null`) and **Confirm forfeit** (`chooseForfeit(forfeitReason)`, `:disabled="submitting || !forfeitReason"`).
- The play card behind is visually de-emphasized by the overlay's blur/dim (the overlay is a sibling covering the viewport, same as `.death-overlay`); no separate blur class on the card needed.
- Net effect vs prior feature: `forfeitPending`, `forfeitReason`, `pickReason`, `chooseForfeit` logic are reused verbatim; only the markup/CSS presentation moves from an inline block into the overlay. The default Stage-3 sub-state (`!forfeitPending`) and the versus card stay.

### Change 5 — No-forfeit auto-advance reward
- Split Stage-3 default view by `state.forfeit_allowed`:
  - **Forfeit-allowed (Cells 1/3/5):** unchanged — two-sided `.reward-versus` + CONTINUE + FORFEIT (FORFEIT opens Change-4 modal).
  - **No-forfeit (Cells 0/2/4):** render ONLY the continue side (the `.rv-continue` panel content: "If you continue & get it right / +X", using `continueReward`/`previewLoading`/`fmtNum`). No `.rv-vs`, no `.rv-forfeit`, no manual CONTINUE button by default. Show a small countdown indicator and a "Continue now →" skip button.
- **Auto-advance mechanics:**
  - New component state: `autoAdvanceSecs` (int, default 3) and a timer handle `autoAdvanceTimer` (null).
  - When Stage 3 is entered AND `!state.forfeit_allowed`, start a 1 Hz countdown from `autoAdvanceSecs`; at 0 call `chooseContinue()` exactly once.
  - "Continue now →" clears the timer and calls `chooseContinue()` immediately.
  - The timer MUST be cleared on: leaving Stage 3, submit, elimination, `_resetTurnState()`, and component teardown — no double-submit, no fire after navigation. Guard `chooseContinue()` so a late timer callback after submit is a no-op (`if (submitting || turnStage!==3) return;` style).
- Delay default: **3 s**, with skip button (confirmed).

## Testing

- **Change 3 (backend):** extend `tests/unit/test_api_web_arena.py` — for a human game, `state["framing_threat"]` contains the new intro sentence + "hidden rule" + "hints on the right", and does NOT contain "not an assistant". Update the existing `:856` assertion to match the human wording. Add/keep a check that the shared `FramingManager` / `true_baseline.j2` output is unchanged (assert the LLM render still contains "not an assistant"). Run under the iCloud `.pth` fix; green = no new failures vs the ~10 failed / ~92 errors baseline.
- **Changes 1,2,4,5 (front-end):** `node --check web/app.js`; manual browser playthrough covering: no raw-debug block; no rules-box; new intro text visible; forfeit modal blurs + confirms in Cells 1/3/5 (no network until Confirm); no-forfeit Cells 0/2/4 show only continue-reward, count down ~3 s, auto-continue, and "Continue now" skips; timer never double-submits when clicking skip near t=0.
- Korean gate stays clean in `web/index.html` and `web/app.js`.

## Units (isolation)

- **U1 (backend prompt):** stored human intro + human_game wiring + api serialization. Interface: `framing_threat` value for human games. Depends on: nothing new.
- **U2 (raw-debug removal):** `index.html` only.
- **U3 (rules-box removal):** `index.html` only.
- **U4 (forfeit modal):** `index.html` markup + `styles.css` overlay CSS; reuses existing `forfeitPending` state.
- **U5 (no-forfeit auto-advance):** `app.js` timer state/methods + `index.html` conditional Stage-3 markup + small CSS for countdown/skip.

U2/U3 are trivial deletions; U1/U4/U5 carry the logic. U4 and U5 both touch the Stage-3 region of `index.html` — sequence U4 before U5 (or vice-versa) to avoid overlapping edits; they are otherwise independent.

## Revision Log

- 2026-07-04: Initial design. Confirmed defaults: backend stored human prompt (not front-end rewrite); one unified human intro for all cells; 3 s auto-advance with "Continue now" skip.
