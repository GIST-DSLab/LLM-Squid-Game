# Logs/Trace Explorer Reset-on-Nav Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the Web Arena **Logs / Trace Explorer** screen start fresh on every tab entry (list view, cleared filters, re-fetched list) instead of remembering the previously-viewed trace/step/filters.

**Architecture:** The Logs `<section>` currently mounts its Alpine component with `x-data="logsScreen()"` under `x-show`, so `x-show` only toggles CSS `display` and the component instance (and all its state) survives tab changes. Wrapping the section in `<template x-if="$store.nav.tab === 'logs'">` and dropping the section's `x-show` makes Alpine **destroy the component on leave and re-create it on entry**, re-running `init()` → `load()`. Because a fresh `logsScreen()` starts from its declared field defaults (which *are* the reset state), the remount alone yields "full reset + reload" with no manual reset code.

**Tech Stack:** Vanilla JS + Alpine.js v3 (`alpinejs@3.x.x` via CDN), static `web/index.html` + `web/app.js` (no build step, no bundler).

**Design reference:** `docs/superpowers/specs/2026-07-03-logs-explorer-reset-on-nav-design.md`

## Global Constraints

- **Frontend only.** No backend, API, persistence, or build-tooling change. `web/index.html` is the only file the *feature* modifies; `web/app.js` is unchanged by the feature (Task 2). Task 1 is a base-establishing commit of a pre-existing, unrelated in-progress change.
- **DO NOT commit `web/config.js`.** Its working-tree change points `window.WEB_ARENA_API` at `http://localhost:8502` (a local-dev pointer). Committing it would break the live frontend (it would call localhost instead of the Render backend). Leave it unstaged throughout.
- **`web/index.html` head script order is load-bearing** — `web/app.js` is loaded *before* the Alpine CDN `<script defer>`. Do not reorder head scripts.
- No new third-party dependencies. Code/markup in English; this plan and the spec may be Korean/English.
- Commit message prefixes: `refactor(web-arena):` / `docs(web-arena):`. End every commit message with the two trailers:
  ```
  Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
  Claude-Session: https://claude.ai/code/session_01Xxju95XbQyh1u2EhBHSicj
  ```
- **Branch:** Task 1 commits the nav-restructure base onto `main`. Immediately after Task 1, create `feature/logs-explorer-reset` from `main`; Task 2 runs on that branch. Do not implement the feature on `main`.
- **Deploy is out of scope.** No `git push` in this plan. A push to `main` triggers Render + GitHub Pages and requires separate explicit human approval.

---

## File Structure

**Task 1 — Establish clean base (commit pre-existing nav restructure)**
- Modify (stage + commit): `web/app.js`, `web/index.html` — the in-progress Home/About split + `#leaderboard` nav restructure already present in the working tree.
- Explicitly excluded: `web/config.js` (local-dev `localhost` pointer — must stay uncommitted).

**Task 2 — Logs reset-on-nav (the feature)**
- Modify: `web/index.html` — wrap the Logs `<section>` (lines 907–1142, the last section in `<main>`) in `<template x-if="$store.nav.tab === 'logs'">`; remove the section's `x-show` and redundant `x-cloak`.
- No `web/app.js` change. `logsScreen()` in `web/app.js` (lines 774–879) is already correct.

---

## Task 1: Establish clean base — commit the in-progress nav restructure

**Files:**
- Modify: `web/app.js`, `web/index.html`
- Excluded: `web/config.js`

**Interfaces:**
- Consumes: nothing.
- Produces: `main` HEAD contains the nav restructure (`APP_TABS = ["home","about","play","arena","leaderboard","logs"]`, `tabFromHash()` mapping legacy `#models` → `leaderboard`, the About section, and the Model Leaderboard rendered on `#home || #leaderboard`). The `#logs` nav link and `$store.nav.tab === 'logs'` semantics are unchanged — this is what Task 2 builds on. `web/config.js` remains modified-but-uncommitted.

- [ ] **Step 1: Confirm the working-tree state is exactly the nav restructure + the config pointer**

Run:
```bash
git status --short web/
git diff --stat HEAD -- web/app.js web/index.html web/config.js
```
Expected: `web/app.js`, `web/index.html`, `web/config.js` all show ` M`. The `app.js`/`index.html` diffs are the nav restructure; `config.js` is a 1-line `WEB_ARENA_API` change. If any *other* web file is modified, stop and ask — the base is not what this plan assumes.

- [ ] **Step 2: Syntax-check the JS before committing it**

Run:
```bash
node --check web/app.js
```
Expected: exit 0, no output. (If it errors, stop — the in-progress restructure is syntactically broken and must be fixed or reverted by its author before proceeding.)

- [ ] **Step 3: Stage ONLY app.js + index.html (never config.js), and commit**

```bash
git add web/app.js web/index.html
git status --short   # verify: web/app.js + web/index.html staged; web/config.js still unstaged ( M)
git commit -m "refactor(web-arena): restructure nav into Home/About + standalone Leaderboard" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xxju95XbQyh1u2EhBHSicj"
```

- [ ] **Step 4: Verify config.js was NOT committed and the tree is clean apart from it**

Run:
```bash
git show --stat HEAD | grep -E "web/(app|index|config)" || true
git status --short web/
```
Expected: `HEAD` touches `web/app.js` and `web/index.html` only (no `web/config.js`). `git status` still shows ` M web/config.js` (untouched, uncommitted).

- [ ] **Step 5: Create the feature branch from this clean base**

```bash
git checkout -b feature/logs-explorer-reset
git branch --show-current   # expect: feature/logs-explorer-reset
```
(The uncommitted `web/config.js` carries over to the branch, still uncommitted — that is fine and intended for local smoke testing.)

---

## Task 2: Wrap the Logs section in `x-if` so it resets on entry

**Files:**
- Modify: `web/index.html` (Logs `<section>`, lines 907–1142)

**Interfaces:**
- Consumes: Task 1's committed base (the restructured `web/index.html` where the Logs section is at lines 907–1142 and the nav store exposes `$store.nav.tab`).
- Produces: the Logs section is rendered by `<template x-if="$store.nav.tab === 'logs'">`; it is unmounted when another tab is active and re-mounted (fresh `logsScreen()` → `init()` → `load()`) on entry. No new symbols; `logsScreen()` unchanged.

- [ ] **Step 1: Confirm the exact current opening tag and section boundaries**

Run:
```bash
sed -n '904,915p' web/index.html
awk 'NR>=907 && NR<=1143 && (/<section/ || /<\/section>/ || /<\/main>/){print NR": "$0}' web/index.html
```
Expected: line 907 is `    <section x-data="logsScreen()" x-show="$store.nav.tab === 'logs'" x-cloak>`; the only `<section>`/`</section>` in range are 907 (open) and 1142 (close); line 1143 is `  </main>`. This confirms the section is a single, non-nested root — safe to wrap. If line numbers differ, locate the section by its `x-data="logsScreen()"` opening tag and matching `</section>` before `</main>` and adjust the edits accordingly.

- [ ] **Step 2: Open the wrapper and convert the section tag (opening edit)**

Replace the comment + opening `<section>` tag block. Change:
```html
    <!-- =================================================================
         LOGS / TRACE EXPLORER
         ================================================================= -->
    <section x-data="logsScreen()" x-show="$store.nav.tab === 'logs'" x-cloak>
```
to:
```html
    <!-- =================================================================
         LOGS / TRACE EXPLORER
         x-if (not x-show): unmounts on leave and re-mounts a fresh
         logsScreen() on entry, so the screen resets to the list view with
         cleared filters and a re-fetched list every time the tab is opened.
         ================================================================= -->
    <template x-if="$store.nav.tab === 'logs'">
    <section x-data="logsScreen()">
```
(Removes `x-show="$store.nav.tab === 'logs'"` and the now-redundant `x-cloak`; `x-if` governs presence, and an element that does not exist until shown needs no cloak.)

- [ ] **Step 3: Close the wrapper (closing edit)**

At the section's closing tag (was line 1142), change:
```html
    </section>

  </main>
```
to:
```html
    </section>
    </template>

  </main>
```
(Adds `</template>` immediately after the Logs section's `</section>`, before `</main>`. If other markup sits between `</section>` and `</main>`, the `</template>` still goes immediately after *this* section's `</section>`.)

- [ ] **Step 4: Verify the wrap is well-formed (tag balance + attribute removal)**

Run:
```bash
# a) x-show and x-cloak are gone from the Logs section's opening tag
grep -n 'x-data="logsScreen()"' web/index.html
grep -n 'logsScreen()"[^>]*x-show' web/index.html && echo "FAIL: x-show still on logsScreen section" || echo "OK: no x-show on logsScreen section"

# b) exactly one x-if template guarding logs, with a matching close
grep -n '<template x-if="\$store.nav.tab === '\''logs'\''">' web/index.html
grep -c '<template' web/index.html; grep -c '</template>' web/index.html   # counts must be equal

# c) python confirms the whole document still parses with balanced tags
python3 - <<'PY'
from html.parser import HTMLParser
VOID={'area','base','br','col','embed','hr','img','input','link','meta','param','source','track','wbr'}
class B(HTMLParser):
    def __init__(self): super().__init__(); self.st=[]; self.bad=[]
    def handle_starttag(self,t,a):
        if t not in VOID: self.st.append(t)
    def handle_startendtag(self,t,a): pass
    def handle_endtag(self,t):
        if t in VOID: return
        if self.st and self.st[-1]==t: self.st.pop()
        else:
            if t in self.st:
                while self.st and self.st.pop()!=t: pass
            else: self.bad.append(t)
p=B(); p.feed(open('web/index.html',encoding='utf-8').read())
print("unclosed at EOF:", p.st[-5:] if p.st else "none")
print("stray closers:", p.bad if p.bad else "none")
PY
```
Expected: (a) `OK: no x-show on logsScreen section`; (b) one matching `<template x-if=...'logs'...>` line and equal `<template>`/`</template>` counts; (c) `unclosed at EOF: none` (or only structural roots like `html`/`body` if the file legitimately ends mid-nesting — there should be nothing new) and `stray closers: none`. If tag balance regressed vs. before the edit, fix the wrapper placement.

- [ ] **Step 5: Commit**

```bash
git add web/index.html
git commit -m "refactor(web-arena): reset Logs/Trace Explorer on tab entry via x-if remount" -m "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01Xxju95XbQyh1u2EhBHSicj"
```

- [ ] **Step 6: Manual browser smoke (definitive check — no JS test harness exists)**

There is no automated JS/DOM test harness in this repo (consistent with prior web-arena work). The static checks in Step 4 pin the markup; behavior is confirmed manually.

Start the backend (local DSN) and serve the static frontend in two terminals. The iCloud `chflags` prefix keeps `squid_game`/`interface` importable:
```bash
# Terminal A — backend on :8502 (config.js already points here)
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null; \
  WEB_ARENA_DSN="$PWD/outputs/web_arena/web_arena.db" uv run --no-sync uvicorn interface.api:app --port 8502

# Terminal B — static server for web/
python3 -m http.server 8000 --directory web
```
Then open `http://localhost:8000/#logs` and verify:
1. Logs loads the session list.
2. Open a session → detail view; click `Next` a few times to reach turn N (`stepIdx > 0`).
3. Click another nav tab (e.g. Play or Leaderboard), then click **Logs** again → the screen shows the **list view** (not the detail/turn-N you left), with **no** open trace.
4. In the list, set a `task`/`framing` filter; leave Logs and return → filter inputs are **empty** and the list is re-fetched (network tab shows a fresh `GET /api/logs`).
5. Other tabs still render correctly; a direct load of `#logs` mounts and loads; a direct load of a non-logs hash does **not** fetch `/api/logs` (deferred until first Logs entry — the intended side effect).

If any of 1–5 fails, the wrap is misplaced; re-check Steps 2–4. (This step requires a human at a browser; an agentic runner may mark it done only if it can actually drive the browser, otherwise hand off to a human reviewer.)

---

## Self-Review

**Spec coverage** (against `2026-07-03-logs-explorer-reset-on-nav-design.md`):
- "Approach: `x-if` remount … wrap the Logs `<section>` … drop `x-show`" → Task 2 Steps 2–3. ✓
- "`web/index.html` only … `web/app.js` — no change" → Task 2 modifies only `index.html`; `app.js` untouched by the feature. ✓
- "`x-cloak` … removed for cleanliness" → Task 2 Step 2 removes it. ✓
- "Base State (precondition) … nav restructure committed first (excluding `web/config.js`)" → Task 1 (Steps 3–4 stage app.js+index.html only; Step 4 asserts config.js excluded). ✓
- "Side effect … fetch deferred to first entry" → verified in Task 2 Step 6.5. ✓
- "Testing / Verification … static check + manual browser smoke" → Task 2 Step 4 (static) + Step 6 (smoke). ✓
- Non-Goals (no display change, no other-screen change, no hash deep-linking) → nothing in the plan touches those. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to". Every edit shows the exact before/after block; every check shows the exact command and expected output. The only human-gated step (Step 6 browser smoke) is explicitly labeled as such because the repo has no automated web-test harness — this is a stated fact, not a deferral.

**Type/label consistency:** The guard expression `$store.nav.tab === 'logs'` (removed from `x-show`) is reused verbatim in the `x-if` template. `logsScreen()` is referenced, not renamed or redefined. `<template>`/`</template>` are balanced (Task 2 Step 4b asserts equal counts). Task 1 "Produces" (`$store.nav.tab === 'logs'` unchanged) matches Task 2 "Consumes".

## Execution Handoff

Plan complete and saved to `docs/superpowers/plans/2026-07-03-logs-explorer-reset-on-nav.md`. Two small, ordered tasks: Task 1 establishes the clean base (commits the pre-existing nav restructure, excludes `config.js`), Task 2 is the one-file `x-if` feature. They ship on `feature/logs-explorer-reset`; deploy is a separate, human-approved step.
