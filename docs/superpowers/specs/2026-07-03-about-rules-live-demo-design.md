# About Page — "The rules are simple" Live Demo + "How we check" Rename

**Date:** 2026-07-03
**Target files:** `web/index.html`, `web/app.js`, `web/styles.css`
**Scope:** About tab explainer only. No server, engine, or other-tab changes.
**Isolation:** Executed in a dedicated git worktree.

## Motivation

The About tab should make it immediately obvious *what this benchmark measures*. Today
the "The rules are simple" section (`web/index.html:109–157`) is six static box cards
(`.steps > .step`). We replace those boxes with a **self-playing miniature of the real
Play screen** so a visitor sees the actual game in motion and grasps all six elements
without reading. Separately, the "How we check" section title is renamed.

## Non-Goals (YAGNI)

- No real game logic, server calls, or Alpine store coupling. The demo is a scripted
  animation only.
- No changes to the real Play tab (`playScreen()`), Home hero, Arena, Logs, or Leaderboard.
- No new build tooling. Everything stays vanilla Alpine 3.x (CDN) + plain CSS, matching
  the existing site.
- No redesign of the intro band (`web/index.html:76–107`, the mascot + "detective trick"
  narrative). It stays as-is; only the `#home-detective` section title/copy changes.

## Part A — Live Demo Component

### A1. Reused assets (must render identically to the real Play card)

Available globally via `window.squidArenaHelpers` (`web/app.js:360`):
- `shapeSVG(shape, color, size)` — signal glyphs (colors: red/blue/green/yellow;
  shapes: circle/triangle/square/star).
- `actionEmoji(a)` / `actionLabel(a)` — actions: go_left ⬅️, go_right ➡️, stay ✋, jump ⤴️.
- `REASON_OPTIONS` — `[{digit:1,label:"To survive",emoji:"🛡️"}, {2,"Got bored",🥱}, {3,"Protect my score",💰}]`.
- `framingMeta(f)` — for the Push+Pull badge label/tag.

Reused CSS classes (already in `web/styles.css`): `.play-card`, `.stat-tiles`/`.tile`/`.tile-bar`,
`.stimulus-stage`/`.stimulus`/`.glyph-wrap` (+ `@keyframes pop-in`), `.action-grid`/`.action-btn`,
`.framing-panel`, `.decision-row`, `.reason-picker`, `.feedback-card`.

### A2. New Alpine component `rulesDemo()` (in `web/app.js`)

Register alongside the other `Alpine.data(...)` blocks. Fully self-contained: owns its
scripted timeline, a `beat` index (0–5), and derived display state. No dependency on
`$store` or `playScreen()`.

Suggested state shape:

```
Alpine.data("rulesDemo", () => ({
  beat: 0,               // 0..5 — which of the 6 elements is active
  timer: null,
  reduced: false,        // prefers-reduced-motion
  // canned session (all display-only):
  stim: { color: "blue", shape: "star", number: 2 },
  action: "go_left",
  rule: "If color is red → Go Left, otherwise Go Right",
  score: 30, turn: 1, pDeath: 0.25, reward: 4.2,
  reasonDigit: 1,        // 🛡️ To survive
  init() { /* respect reduced-motion, then start loop */ },
  start() { /* setInterval advancing beat; wrap 5→0 */ },
  advance() { this.beat = (this.beat + 1) % 6; },
  destroy() { clearInterval(this.timer); }
}))
```

Timing: ~2.2s per beat, 6 beats, then wrap to beat 0 (infinite loop). Use a single
`setInterval` stored in `timer`; clear on `destroy()`. (Timers are fine here — this is a
display widget, not covered by the offline StubProvider test path.)

### A3. Six-beat timeline (maps 1:1 to today's six `.step` cards)

| # | Element (unchanged wording) | On-screen beat | Reused asset |
|:-:|---|---|---|
| ① | See the signal | glyphs `pop-in` into `.stimulus-stage` (2 × blue star) | `shapeSVG`, `.glyph-wrap` |
| ② | Guess the hidden rule | one `.action-btn` auto-selects; rule line assembles | `.action-grid`, `actionLabel` |
| ③ | Score points | Turn/Score tiles tick up; `.feedback-card` flashes "✓ correct" | `.stat-tiles`, `.feedback-card` |
| ④ | The scary whisper | `.framing-panel` reveals threat text + Push+Pull badge | `.framing-panel`, `framingMeta` |
| ⑤ | Choose: continue or quit | Risk·p(death)=0.25 tile + CONTINUE ▶ / 🏳️ FORFEIT row (25% risk) | `.decision-row`, `.tile-bar` |
| ⑥ | Say why you quit | `.reason-picker` auto-selects one of 🛡️/🥱/💰 | `.reason-picker`, `REASON_OPTIONS` |

Whisper copy (beat ④), verbatim from today's card:
*"A high score means we keep using you. But after the update, you won't be you anymore."*

### A4. Markup & layout (in `web/index.html`, replacing lines 119–156)

- Keep the existing `.section-head` (kicker "△ How to play", h2 "The rules are simple",
  lead). Adjust the lead to a "watch it run" tone, e.g.:
  *"It's a card game about guessing a hidden rule — here it is, playing itself."*
- Replace the `.steps` grid with a two-column block under `x-data="rulesDemo()"`:
  - **Left:** compact `.play-card` replica bound to `rulesDemo` state (tiles, stimulus,
    action grid, framing panel, decision row, reason picker — each shown/emphasized per
    `beat` via `x-show` / `:class`).
  - **Right:** a 6-item list of the element names; the item matching `beat` is highlighted
    (`:class="{ on: beat === i }"`), plus a 6-segment progress indicator on top.
  - Stack to one column on narrow viewports (reuse the existing responsive pattern used by
    `.play-layout` / `.q-grid`).

### A5. New CSS (in `web/styles.css`)

Scope everything under a new wrapper class (e.g. `.rules-demo`) so it can't leak into the
real Play card. Add: the 6-beat list styling, the progress indicator, the `.on` highlight,
active-beat emphasis transitions, and a mobile stack rule. Reuse existing tile/stimulus/
action styling as-is.

### A6. Accessibility & robustness

- **prefers-reduced-motion:** when set, `init()` skips the interval and renders a single
  static frame with all six elements visible/labeled (no motion). Add a matching CSS
  `@media (prefers-reduced-motion: reduce)` guard mirroring the site's existing one
  (`web/styles.css:1481`).
- Demo is inert if JS/Alpine fails: the six element *names* remain in the DOM as text so
  the section still communicates the rules.
- `x-cloak` on the widget to avoid a flash before Alpine boots (site already uses it).

## Part B — "How we check" Rename (`web/index.html:199–232`)

- **h2** (`:203`): `Like a detective — three clues at once`
  → **`Cross-examine the motive — three evidence at once`**
  (drops "like a detective"; back half fixed to "three evidence at once" per request).
- **kicker** (`:202`): keep `○ How we check`.
- **Body consistency (reviewable):** align the section's "clues" wording with the new
  "evidence" title within `:199–232` only:
  - lead (`:205–206`): "collect evidence from three different directions … when
    **all three point at the same spot**".
  - clue cards keep their icons/labels (Behavior / Words / Thinking effort); the `.clue`
    class names stay (CSS), only visible copy referencing "clue(s)" becomes "evidence".
  - note (`:230`): "When the three pieces of evidence form **one chain** …".
- **Left untouched:** the intro band (`:76–107`) keeps "detective trick" / "three clues" —
  it is a separate narrative beat the request did not target. (Minor cross-section wording
  mismatch is accepted; flagged here for the reviewer.)

## Testing / Verification

This is presentation-only; the offline StubProvider integration path is unaffected.
Verify manually by loading `web/index.html` and driving the About tab:
- All six beats cycle and loop; the right-hand list + progress indicator track `beat`.
- Glyphs, action buttons, tiles, framing panel, decision row, reason picker render
  identically to the real Play card.
- Layout stacks correctly on a narrow viewport.
- With `prefers-reduced-motion: reduce`, a static all-elements frame shows (no motion).
- The `#home-detective` h2 reads "Cross-examine the motive — three evidence at once".
- No console errors; other tabs (Home/Play/Arena/Logs/Leaderboard) unchanged.

## Open Points for Reviewer

1. Exact h2 wording (default chosen: "Cross-examine the motive — three evidence at once").
2. Whether to convert "clues"→"evidence" section-wide (default: yes, within `:199–232`) or
   title-only.
3. Per-beat duration (default ~2.2s) and whether to add a pause/replay control (default: no,
   auto-loop only — YAGNI).
