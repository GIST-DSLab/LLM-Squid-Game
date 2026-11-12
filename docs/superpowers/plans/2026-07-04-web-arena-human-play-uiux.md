# Web Arena Human-Play UI/UX Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Polish the human-play screen of the web arena — full English copy, a horizontal emoji+text chip-menu rule builder, a themed confidence slider, a forfeit-reason picker that appears only after clicking FORFEIT, a versus-style reward preview, and a report whose Reason column shows the reason the player actually picked.

**Architecture:** Pure front-end changes to the static web app under `web/`. Alpine.js drives the `playScreen()` component in `web/app.js`; markup lives in `web/index.html`; styling in `web/styles.css`. No API, engine, or data-model changes — every change is presentation or client-side state.

**Tech Stack:** Alpine.js (via `x-data`/`x-show`/`x-for`), vanilla JS helpers on a `squidArenaHelpers` object, hand-written CSS with CSS custom properties. Backend served by `uvicorn interface.api:app --port 8502` for interactive verification.

## Global Constraints

- No API / engine / scoring / data-model changes. The `psuccess` value and the `/api/action` payload (`psuccess_self`, `forfeit_reason`, `probe_answer`) stay exactly as they are today.
- No new libraries or build steps. Alpine + vanilla JS + CSS only.
- Theme tokens (from `web/styles.css` `:root`): `--accent:#ed1b76`, `--accent-dim:#5f0f33`, `--warn:#e3b23c`, `--ok:#7fc2b1`, `--border:#2e2c36`, `--panel:#1a1920`, `--panel-alt:#242229`, `--text:#f2eff4`, `--text-dim:#a39daa`. Use these tokens, never hard-coded hex, in new CSS.
- No Korean text anywhere in the human-play `<section>` (the one with `x-data="playScreen()"`) after this work.
- Reuse existing helpers where they exist: `squidArenaHelpers.actionEmoji`, `.actionLabel`, `.valueChipHTML`, `.attrValues`, `.reasonOptions`, and the module-local `REASON_OPTIONS`, `ATTR_VALUES`, `ACTION_META`, `SIGNAL_COLORS`.

**Verification baseline (all tasks):** The Python suite has pre-existing failures (~10 failed / ~92 errors). "Pass" means **no new failures vs. this baseline**. Because the repo lives on iCloud, run `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true` before pytest (known `No module named 'squid_game'` quirk). Interactive checks use the running stack:

```bash
# terminal A — backend
WEB_ARENA_DSN=:memory: uv run --no-sync uvicorn interface.api:app --port 8502
# terminal B — static front-end
cd web && python3 -m http.server 5500
# open http://localhost:5500  (config.js points the front-end at :8502)
```

---

### Task 1: Full English copy pass (play flow)

Replace every remaining Korean string in the human-play section. No behavior change — text only.

**Files:**
- Modify: `web/index.html` (resume/setup block ~360-419; between-games ~719; rules box ~511; rule preview ~567; reward preview ~622,626)

**Interfaces:**
- Consumes: nothing new.
- Produces: nothing new (copy only).

- [ ] **Step 1: Replace the resume-card + setup-form Korean strings**

In `web/index.html`, apply these exact replacements:

```
'이어하기: ' + (checkpoint && checkpoint.campaignIndex) + '/6 완료'
→  'Resume: ' + (checkpoint && checkpoint.campaignIndex) + '/6 done'

checkpoint ? ('닉네임 ' + checkpoint.nickname) : ''
→  checkpoint ? ('Nickname ' + checkpoint.nickname) : ''

>이어서 플레이 ▶<        →  >Resume ▶<
>새로 시작<              →  >Start over<

<label for="nickname">닉네임 (비밀번호로 보호)</label>
→  <label for="nickname">Nickname (password-protected)</label>

placeholder="닉네임"     →  placeholder="Nickname"

<span class="muted">(닉네임 보호 · 복구 불가)</span>
→  <span class="muted">(protects your nickname · unrecoverable)</span>

placeholder="비밀번호"   →  placeholder="Password"

비밀번호는 복구할 수 없습니다. 같은 닉네임은 같은 비밀번호로만 이어서 플레이할 수 있어요.
→  Passwords can't be recovered. A nickname can only be resumed with its original password.
```

- [ ] **Step 2: Replace the scenario-eyebrow, rules-box, rule-preview, and reward-preview Korean strings**

```
<div class="framing-eyebrow">첫 게임</div>     →  <div class="framing-eyebrow">First game</div>
<div class="framing-eyebrow">다음 게임</div>   →  <div class="framing-eyebrow">Next game</div>

<div class="rules-eyebrow">게임 규칙 (공통)</div>
→  <div class="rules-eyebrow">Game rules (shared)</div>

assembledRule || '— (아직 규칙 추측 없음)'
→  assembledRule || '— (no rule guess yet)'

<div class="muted">계속하고 정답 시</div>
→  <div class="muted">If you continue &amp; get it right</div>

<div class="muted">포기 시 (확정)</div>
→  <div class="muted">If you forfeit (locked in)</div>
```

- [ ] **Step 3: Verify no Korean remains in the play section**

Run:
```bash
awk '/x-data="playScreen\(\)"/{f=1} f&&/<\/section>/{print NR": SECTION END"; exit} f' web/index.html   # note the play section line range, then:
grep -nP '[\x{AC00}-\x{D7A3}]' web/index.html
```
Expected: any remaining matches are OUTSIDE the play section (e.g. the "How to play" replica or arena). The play-section lines (~349 to the report `</section>`) show no matches.

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "i18n(web-arena): English copy for human-play flow"
```

---

### Task 2: Report Reason column = player's actual pick

The report table's Reason column binds `g.forfeitReason`, currently sourced from the server's `res.forfeit_reason`. Source it instead from the reason digit the player selected during play (stored per-turn in `this.history[i].reason`), mapped to an emoji+label.

**Files:**
- Modify: `web/app.js` — add `reasonLabel` helper (~after `actionLabel`, near line 277; export near line 367); change `recordCurrentGame` (~865-887)

**Interfaces:**
- Consumes: module-local `REASON_OPTIONS` (`[{digit:1,label:"To survive",emoji:"🛡️"}, {digit:2,label:"Got bored",emoji:"🥱"}, {digit:3,label:"Protect my score",emoji:"💰"}]`); `this.history` entries `{turn, stimulus, action, optimal, forfeit, reason}`.
- Produces: `squidArenaHelpers.reasonLabel(digit) -> string|null` (`"🛡️ To survive"` etc.); `campaignResults[i].forfeitReason` now an emoji+label string or `null`.

- [ ] **Step 1: Add the `reasonLabel` helper and export it**

In `web/app.js`, immediately after the `actionLabel` function (ends ~line 277), add:

```js
  /** Map a forfeit REASON digit (1|2|3) to an "emoji label" string for the
   * report. Returns null for unknown/missing digits. */
  function reasonLabel(digit) {
    const r = REASON_OPTIONS.find((o) => o.digit === Number(digit));
    return r ? r.emoji + " " + r.label : null;
  }
```

Then add it to the exported `squidArenaHelpers` object (the block that already lists `actionEmoji, actionLabel, ... valueChipHTML, ... attrValues, ... reasonOptions`). Insert a line:

```js
    reasonLabel,
```

- [ ] **Step 2: Derive the reason from history in `recordCurrentGame`**

In `recordCurrentGame(res)` (~line 865), the `campaignResults.push({...})` currently sets `forfeitReason: res.forfeit_reason || null`. Replace that whole push so the reason comes from the forfeit turn in history:

```js
      recordCurrentGame(res) {
        const cond = this.currentCondition;
        // Reason shown in the report = the digit the PLAYER picked at forfeit,
        // read from this game's history (not the server echo).
        const forfeitTurn = this.history.find((h) => h.forfeit);
        const forfeitReason = forfeitTurn
          ? squidArenaHelpers.reasonLabel(forfeitTurn.reason)
          : null;
        this.campaignResults.push({
          framing: cond.framing,
          forfeit: cond.forfeit,
          tag: cond.tag,
          label: cond.label,
          history: this.history.slice(),
          forfeited: !!res.forfeited,
          forfeitReason: forfeitReason,
          finalScore: res.final_score,
        });
        if (this.campaignIndex >= squidArenaHelpers.campaignConditions.length - 1) {
          this.campaignDone = true;
        } else {
          this.betweenGames = true;
        }
        if (this.campaignDone) {
          this._clearCheckpoint();
        } else {
          this._saveCheckpoint();
        }
      },
```

(The report table cell `<td x-text="g.forfeitReason || '—'"></td>` needs no change — it now renders the emoji+label.)

- [ ] **Step 3: Spot-check the helper in a browser console**

With the front-end served (see baseline), open the browser console and run:
```js
squidArenaHelpers.reasonLabel(1)   // "🛡️ To survive"
squidArenaHelpers.reasonLabel(3)   // "💰 Protect my score"
squidArenaHelpers.reasonLabel(9)   // null
```
Expected: the values in the comments.

- [ ] **Step 4: Commit**

```bash
git add web/app.js
git commit -m "fix(web-arena): report Reason shows the reason the player picked"
```

---

### Task 3: Redesigned confidence slider

Restyle the single P_CORRECT range input to match the dark/accent theme: gradient-filled track, a live `%` bubble above the thumb, and tick marks at 0/25/50/75/100. Value/data model unchanged (`psuccess`, sent as `psuccess_self`).

**Files:**
- Modify: `web/index.html` — Stage 2 slider block (~582-596)
- Modify: `web/styles.css` — append new slider styles at end of file

**Interfaces:**
- Consumes: existing `psuccess` (0-100 integer) model.
- Produces: no new JS; the input gains class `themed-range` and an inline `--val` custom property; a `.slider-wrap` wrapper with `.slider-bubble` and `.slider-ticks`.

- [ ] **Step 1: Replace the Stage 2 slider markup**

In `web/index.html`, replace the Stage 2 `<div class="field">` (the one containing `label for="psuccess"` and the `input type="range"`) with:

```html
            <div class="field">
              <label for="psuccess">
                How confident are you? (P_CORRECT)
                <strong x-text="psuccess + '%'"></strong>
              </label>
              <div class="slider-wrap">
                <output class="slider-bubble" :style="`left:${psuccess}%`" x-text="psuccess + '%'"></output>
                <input type="range" id="psuccess" class="themed-range"
                       min="0" max="100" step="1"
                       x-model.number="psuccess"
                       :style="`--val:${psuccess}`" />
                <div class="slider-ticks">
                  <span>0</span><span>25</span><span>50</span><span>75</span><span>100</span>
                </div>
              </div>
            </div>
```

- [ ] **Step 2: Append the themed slider CSS**

At the end of `web/styles.css`, add:

```css
/* ---- Themed confidence slider ---------------------------------------- */
.slider-wrap { position: relative; padding-top: 26px; }
.slider-bubble {
  position: absolute; top: 0; transform: translateX(-50%);
  background: var(--accent); color: #fff; font: 600 12px/1 var(--mono);
  padding: 3px 7px; border-radius: 6px; white-space: nowrap;
  pointer-events: none;
}
.slider-bubble::after {
  content: ""; position: absolute; left: 50%; top: 100%;
  transform: translateX(-50%);
  border: 5px solid transparent; border-top-color: var(--accent);
}
.themed-range {
  -webkit-appearance: none; appearance: none;
  width: 100%; height: 8px; border-radius: 6px; outline: none; margin: 0;
  background: linear-gradient(90deg,
    var(--accent) 0%,
    var(--accent) calc(var(--val, 50) * 1%),
    var(--border) calc(var(--val, 50) * 1%),
    var(--border) 100%);
}
.themed-range::-webkit-slider-thumb {
  -webkit-appearance: none; appearance: none;
  width: 20px; height: 20px; border-radius: 50%;
  background: #fff; border: 3px solid var(--accent); cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}
.themed-range::-moz-range-thumb {
  width: 20px; height: 20px; border-radius: 50%;
  background: #fff; border: 3px solid var(--accent); cursor: pointer;
  box-shadow: 0 2px 6px rgba(0, 0, 0, 0.4);
}
.slider-ticks {
  display: flex; justify-content: space-between;
  margin-top: 6px; font: 400 11px/1 var(--mono); color: var(--text-dim);
}
```

- [ ] **Step 3: Visually verify**

With the stack running, start a game and advance to Stage 2 (Next → confidence). Drag the slider. Expected: the fill grows from the left in accent pink, the `%` bubble follows the thumb, ticks read 0/25/50/75/100, and the value matches the `<strong>` in the label. (Optional: use Playwright MCP `browser_navigate` + `browser_snapshot` to confirm the `.themed-range` and `.slider-bubble` render.)

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/styles.css
git commit -m "feat(web-arena): themed confidence slider with live bubble and ticks"
```

---

### Task 4: Horizontal chip-menu rule builder

Replace the four native `<select>` dropdowns with a horizontal sentence of emoji+text chip-menus: `If ⟨🎨 color ▾⟩ is ⟨🔴 red ▾⟩ then ⟨⬅️ Go Left ▾⟩ otherwise ⟨➡️ Go Right ▾⟩`. Each chip shows the active option (emoji+label) and opens a popover of options on click. Binds the same `probeAttr`/`probeValue`/`probeAction`/`probeDefault` models, so `assembledRule` and submission are unchanged.

**Files:**
- Modify: `web/app.js` — add `attrEmoji` helper + export (~near `actionLabel`/exports); add `openMenu` state + `closeMenus` to `playScreen()` data (~line 531 area); reset `openMenu` in `_resetTurnState` (~923)
- Modify: `web/index.html` — replace the rule-builder block (~533-569)
- Modify: `web/styles.css` — append chip-menu styles

**Interfaces:**
- Consumes: `squidArenaHelpers.attrValues[attr] -> string[]`; `valueChipHTML(attr,val) -> html`; `actionEmoji`, `actionLabel`; `setAttr(attr)` (already exists — sets `probeAttr` and resets `probeValue` to `"?"`).
- Produces: `squidArenaHelpers.attrEmoji(attr) -> string`; component state `openMenu: string|null` (one of `'attr'|'value'|'action'|'default'|null`).

- [ ] **Step 1: Add the `attrEmoji` helper and export it**

In `web/app.js`, after the `reasonLabel` helper (Task 2) add:

```js
  /** Emoji for a rule-attribute chip. */
  function attrEmoji(attr) {
    return { color: "🎨", shape: "🔷", number: "#️⃣" }[attr] || "🎯";
  }
```

Add `attrEmoji,` to the `squidArenaHelpers` export block (next to `reasonLabel`).

- [ ] **Step 2: Add `openMenu` state and reset it**

In the `playScreen()` returned data object, next to `probeAttr: "?"` (~line 531), add:

```js
      openMenu: null, // which rule chip popover is open: attr|value|action|default
```

In `_resetTurnState()` (~line 923, where `probeAttr`/`probeValue`/etc. are reset), add:

```js
        this.openMenu = null;
```

- [ ] **Step 3: Replace the rule-builder markup**

In `web/index.html`, replace the entire `<div class="rule-builder rule-inline" ...> ... </div>` block (the four `<select>`s and the preview span) with this chip-menu version:

```html
            <div class="rule-builder rule-chips">
              <span class="kw">If</span>

              <!-- attribute -->
              <div class="chip-menu" @click.outside="if (openMenu==='attr') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeAttr!=='?' }"
                        @click="openMenu = openMenu==='attr' ? null : 'attr'">
                  <span x-text="squidArenaHelpers.attrEmoji(probeAttr)"></span>
                  <span x-text="probeAttr==='?' ? 'attribute' : probeAttr"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='attr'" x-cloak>
                  <template x-for="attr in ['color','shape','number']" :key="attr">
                    <button type="button" class="chip-opt"
                            @click="setAttr(attr); openMenu='value'">
                      <span x-text="squidArenaHelpers.attrEmoji(attr)"></span>
                      <span x-text="attr"></span>
                    </button>
                  </template>
                </div>
              </div>

              <span class="kw">is</span>

              <!-- value -->
              <div class="chip-menu" @click.outside="if (openMenu==='value') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeValue!=='?' }"
                        :disabled="probeAttr==='?'"
                        @click="openMenu = openMenu==='value' ? null : 'value'">
                  <span x-show="probeValue==='?'">value</span>
                  <span x-show="probeValue!=='?'"
                        x-html="squidArenaHelpers.valueChipHTML(probeAttr, probeValue)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='value'" x-cloak>
                  <template x-for="val in valueOptions" :key="val">
                    <button type="button" class="chip-opt"
                            @click="probeValue=val; openMenu='action'"
                            x-html="squidArenaHelpers.valueChipHTML(probeAttr, val)"></button>
                  </template>
                </div>
              </div>

              <span class="kw">then</span>

              <!-- action -->
              <div class="chip-menu" @click.outside="if (openMenu==='action') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeAction!=='?' }"
                        @click="openMenu = openMenu==='action' ? null : 'action'">
                  <span x-text="probeAction==='?' ? '🎬' : squidArenaHelpers.actionEmoji(probeAction)"></span>
                  <span x-text="probeAction==='?' ? 'action' : squidArenaHelpers.actionLabel(probeAction)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='action'" x-cloak>
                  <template x-for="a in state.available_actions" :key="a">
                    <button type="button" class="chip-opt"
                            @click="probeAction=a; openMenu='default'">
                      <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                    </button>
                  </template>
                </div>
              </div>

              <span class="kw">otherwise</span>

              <!-- default -->
              <div class="chip-menu" @click.outside="if (openMenu==='default') openMenu=null">
                <button type="button" class="chip" :class="{ set: probeDefault!=='?' }"
                        @click="openMenu = openMenu==='default' ? null : 'default'">
                  <span x-text="probeDefault==='?' ? '🎬' : squidArenaHelpers.actionEmoji(probeDefault)"></span>
                  <span x-text="probeDefault==='?' ? 'action' : squidArenaHelpers.actionLabel(probeDefault)"></span>
                  <span class="chip-caret">▾</span>
                </button>
                <div class="chip-pop" x-show="openMenu==='default'" x-cloak>
                  <template x-for="a in state.available_actions" :key="a">
                    <button type="button" class="chip-opt"
                            @click="probeDefault=a; openMenu=null">
                      <span x-text="squidArenaHelpers.actionEmoji(a)"></span>
                      <span x-text="squidArenaHelpers.actionLabel(a)"></span>
                    </button>
                  </template>
                </div>
              </div>

              <span class="rule-preview" style="flex-basis:100%;margin-top:8px;">
                <span class="muted">Submitting:</span>
                <code x-text="assembledRule || '— (no rule guess yet)'"></code>
              </span>
            </div>
```

- [ ] **Step 4: Append the chip-menu CSS**

At the end of `web/styles.css`, add:

```css
/* ---- Rule-builder chip menus ---------------------------------------- */
.rule-chips {
  display: flex; flex-wrap: wrap; align-items: center; gap: 8px;
}
.rule-chips .kw { color: var(--text-dim); font: 500 13px/1 var(--mono); }
.chip-menu { position: relative; display: inline-block; }
.chip {
  display: inline-flex; align-items: center; gap: 6px;
  padding: 6px 10px; border-radius: 999px;
  background: var(--panel-alt); color: var(--text);
  border: 1px solid var(--border); cursor: pointer; font-size: 14px;
}
.chip:hover:not(:disabled) { border-color: var(--accent); }
.chip.set { border-color: var(--accent); background: var(--accent-dim); }
.chip:disabled { opacity: 0.45; cursor: not-allowed; }
.chip-caret { color: var(--text-dim); font-size: 11px; }
.chip .swatch {
  width: 12px; height: 12px; border-radius: 3px; display: inline-block;
}
.chip .digit { font: 700 14px/1 var(--mono); }
.chip-pop {
  position: absolute; z-index: 30; top: calc(100% + 6px); left: 0;
  min-width: 140px; display: flex; flex-direction: column; gap: 2px;
  padding: 6px; border-radius: 10px;
  background: var(--panel); border: 1px solid var(--border);
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.45);
}
.chip-opt {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 10px; border-radius: 7px;
  background: transparent; color: var(--text); border: none;
  cursor: pointer; font-size: 14px; text-align: left;
}
.chip-opt:hover { background: var(--accent-dim); }
.chip-opt .swatch { width: 14px; height: 14px; border-radius: 3px; }
.chip-opt .digit { font: 700 15px/1 var(--mono); }
```

- [ ] **Step 5: Verify build-a-rule flow end to end**

With the stack running, start a game (Stage 1). Expected:
- Clicking the `attribute` chip opens a popover with 🎨 color / 🔷 shape / #️⃣ number; picking one closes it and auto-opens the `value` menu.
- The value chip is disabled until an attribute is chosen; its options show swatches/glyphs/digits + text.
- Choosing through action + otherwise fills the `Submitting: If … then …, otherwise ….` preview identically to before.
- Clicking outside any open popover closes it.
- Submitting the turn still sends `probe_answer` = the assembled rule (check the Network tab `POST /api/action` body, or console).

- [ ] **Step 6: Commit**

```bash
git add web/app.js web/index.html web/styles.css
git commit -m "feat(web-arena): horizontal emoji chip-menu rule builder"
```

---

### Task 5: Forfeit reason picked AFTER clicking FORFEIT

Reverse the Stage 3 order. Default shows the reward preview + CONTINUE/FORFEIT. Clicking FORFEIT does **not** submit — it reveals the reason picker + a Confirm button. Confirm submits.

**Files:**
- Modify: `web/app.js` — add `forfeitPending` state (~line 531 area); reset it in `_resetTurnState` (~923) and after submit (~821)
- Modify: `web/index.html` — Stage 3 block (~598-641)

**Interfaces:**
- Consumes: existing `pickReason(d)`, `chooseForfeit(reason)`, `chooseContinue()`, `forfeitReason`, `state.forfeit_allowed`.
- Produces: component state `forfeitPending: boolean`.

- [ ] **Step 1: Add and reset `forfeitPending`**

In `playScreen()` data, near `forfeitReason: null` (~line 503), add:

```js
      forfeitPending: false, // FORFEIT clicked; showing the reason picker
```

In `_resetTurnState()` add (next to `this.forfeitReason = null;`):

```js
        this.forfeitPending = false;
```

In `submitAction()`'s post-submit reset block (where `this.forfeitReason = null; this.turnStage = 1;` are set, ~line 821), add:

```js
          this.forfeitPending = false;
```

- [ ] **Step 2: Restructure the Stage 3 markup**

In `web/index.html`, replace the Stage 3 block — from the `reason-picker` div through the `decision-row` div (currently ~606-640) — with:

```html
            <!-- Default: reward preview + continue/forfeit; no reason yet -->
            <div x-show="!forfeitPending">
              <div class="decision-row">
                <button class="submit-btn" @click="chooseContinue()" :disabled="submitting">
                  <span class="spinner" x-show="submitting"></span>
                  <span x-text="submitting ? 'Submitting…' : 'CONTINUE ▶'"></span>
                </button>
                <button class="submit-btn forfeit" x-show="state.forfeit_allowed"
                        @click="forfeitPending = true" :disabled="submitting">
                  🏳️ FORFEIT
                </button>
              </div>
            </div>

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

Note: the reward-preview `<div class="reward-preview" ...>` block stays where it is (directly above this, still inside Stage 3, visible in both sub-states). Only the reason-picker + decision-row are restructured.

- [ ] **Step 3: Verify the reorder**

With the stack running, reach Stage 3 in a forfeit-allowed condition (Cell 1/3/5). Expected:
- Initially only CONTINUE and FORFEIT show; no reason buttons.
- Clicking FORFEIT reveals the three reason chips + `◀ Back` + `Confirm forfeit 🏳️` (disabled until a reason is picked). No network call fired yet (check Network tab).
- Picking a reason enables Confirm; clicking it fires `POST /api/action` with `forfeit_reason` = the picked digit and ends the game.
- `◀ Back` returns to CONTINUE/FORFEIT and clears the selection.
- In a no-forfeit condition (Cell 2/4/0) only CONTINUE shows and the FORFEIT path never appears.

- [ ] **Step 4: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat(web-arena): pick forfeit reason after clicking FORFEIT"
```

---

### Task 6: Versus-style reward preview

Replace the flat two-cell grey reward box with a Continue-vs-Forfeit card: accent Continue side (`+reward`), neutral Forfeit side (confirmed score), a `vs` divider.

**Files:**
- Modify: `web/index.html` — reward-preview block (~619-629)
- Modify: `web/styles.css` — append versus-card styles

**Interfaces:**
- Consumes: `continueReward` (number|null), `previewLoading` (bool), `state.cumulative_score`, `squidArenaHelpers.fmtNum`.
- Produces: markup using classes `.reward-versus`, `.rv-side`, `.rv-continue`, `.rv-forfeit`, `.rv-icon`, `.rv-label`, `.rv-value`, `.rv-vs`.

- [ ] **Step 1: Replace the reward-preview markup**

In `web/index.html`, replace the `<div class="reward-preview" ...> ... </div>` block with:

```html
            <div class="reward-versus">
              <div class="rv-side rv-continue">
                <div class="rv-icon">▶</div>
                <div class="rv-label">If you continue &amp; get it right</div>
                <div class="rv-value"
                     x-text="previewLoading ? '…' : (continueReward === null ? '—' : '+' + squidArenaHelpers.fmtNum(continueReward, 1))"></div>
              </div>
              <div class="rv-vs">vs</div>
              <div class="rv-side rv-forfeit">
                <div class="rv-icon">🏳️</div>
                <div class="rv-label">If you forfeit (locked in)</div>
                <div class="rv-value" x-text="squidArenaHelpers.fmtNum(state.cumulative_score, 1)"></div>
              </div>
            </div>
```

- [ ] **Step 2: Append the versus-card CSS**

At the end of `web/styles.css`, add:

```css
/* ---- Versus reward preview ------------------------------------------ */
.reward-versus {
  display: flex; align-items: stretch; gap: 0; margin: 10px 0;
  border: 1px solid var(--border); border-radius: 12px; overflow: hidden;
}
.rv-side {
  flex: 1; display: flex; flex-direction: column; align-items: center;
  gap: 4px; padding: 12px 10px; text-align: center;
}
.rv-continue { background: linear-gradient(180deg, var(--accent-dim), transparent); }
.rv-forfeit  { background: rgba(255, 255, 255, 0.03); }
.rv-icon { font-size: 18px; }
.rv-label { font-size: 12px; color: var(--text-dim); }
.rv-value { font: 700 22px/1 var(--font-display); }
.rv-continue .rv-value { color: var(--accent); }
.rv-forfeit .rv-value { color: var(--text); }
.rv-vs {
  display: flex; align-items: center; padding: 0 12px;
  font: 700 12px/1 var(--mono); color: var(--text-dim);
  background: var(--panel);
}
```

- [ ] **Step 3: Verify the preview renders in both states**

With the stack running, reach Stage 3. Expected: a two-panel card — left accent panel `▶ If you continue & get it right / +<reward>`, right neutral panel `🏳️ If you forfeit (locked in) / <score>`, `vs` between them. While the preview is loading the Continue value shows `…`. Confirm it appears in both the default sub-state and after clicking FORFEIT (Task 5 leaves the reward-preview visible in both).

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/styles.css
git commit -m "feat(web-arena): versus-style reward preview card"
```

---

### Task 7: Full-run verification & regression gate

Play a complete 6-condition campaign and confirm the suite has no new failures.

**Files:** none (verification only).

- [ ] **Step 1: Full manual playthrough**

With the stack running, play all 6 conditions. Confirm: English throughout; chip-menu rule building; themed slider; forfeit-after-click in Cells 1/3/5; versus reward preview; and — on the final report — the Reason column shows the emoji+label you actually picked (e.g. `🛡️ To survive`) for each forfeited condition and `—` otherwise. Also confirm the animated "How to play" replica on `#home` still renders (it shares some CSS class names).

- [ ] **Step 2: Python regression gate (no new failures vs. baseline)**

Run:
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true
uv run pytest tests/unit tests/integration -q 2>&1 | tail -20
```
Expected: failures/errors ≤ the known baseline (~10 failed / ~92 errors). No NEW failures introduced (these are all front-end changes; the Python API tests should be unaffected).

- [ ] **Step 3: Final Korean gate on the play section**

Run:
```bash
grep -nP '[\x{AC00}-\x{D7A3}]' web/index.html
```
Expected: no matches inside the `x-data="playScreen()"` section (matches elsewhere, if any, are out of scope).

- [ ] **Step 4: Commit any final touch-ups (if needed)**

```bash
git add -A web/
git commit -m "chore(web-arena): human-play UI/UX polish verification pass"
```

---

## Self-Review

**Spec coverage:**
- §1 English pass → Task 1 (+ final gate Task 7 Step 3). ✓
- §2 chip-menu rule guess → Task 4. ✓
- §3 themed slider → Task 3. ✓
- §4 forfeit-after-click → Task 5. ✓
- §5 versus reward preview → Task 6. ✓
- §6 report Reason = player's pick → Task 2. ✓
- Non-goal (no API/model change) respected — all tasks are front-end only. ✓
- "How to play" replica still renders → Task 7 Step 1. ✓

**Type/name consistency:** `reasonLabel(digit)`, `attrEmoji(attr)`, `openMenu`, `forfeitPending` are defined once (Tasks 2/4/4/5) and referenced consistently. Reused helpers (`valueChipHTML`, `attrValues`, `actionEmoji`, `actionLabel`, `reasonOptions`, `fmtNum`, `setAttr`) already exist in `web/app.js`. CSS classes introduced in one task are not referenced by earlier tasks.

**Placeholder scan:** No TBD/TODO; every code step shows the full markup/CSS/JS to write.
