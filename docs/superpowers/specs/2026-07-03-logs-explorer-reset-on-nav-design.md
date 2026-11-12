# Logs/Trace Explorer — Reset on Navigation Design

**Date:** 2026-07-03
**Status:** Approved (design), pending implementation plan
**Scope:** Web Arena frontend only (`web/index.html`)

## Problem

In the Web Arena UI, the **Logs / Trace Explorer** screen remembers whatever the
user was last looking at. Open a session's trace, step to turn N, switch to
another tab (Play, Leaderboard, …), then return to Logs — the same detail view
at the same step, with the same list filters, is still showing.

Desired behavior: **every entry into the Logs tab starts fresh** — the session
list (list view), no open trace, no applied filters, and a freshly-fetched list
from the server, exactly as if the page had just been opened on `#logs`.

## Root Cause

`logsScreen` is an Alpine component mounted with `x-data="logsScreen()"` on a
`<section x-show="$store.nav.tab === 'logs'">`. Alpine's `x-show` toggles CSS
`display` only — it does **not** destroy the component. So the component
instance and all its reactive state survive tab changes:

- `view` (`"list"` | `"detail"`), `selected`, `detail`, `stepIdx` — the open
  trace and the turn being viewed
- `filterTask`, `filterFraming` — the list filters
- `human`, `llm`, `loaded` — the already-fetched list data

Because the instance is never re-created, returning to the tab shows the exact
prior state.

## Design

### Approach: `x-if` remount (chosen)

Wrap the Logs `<section>` (currently `web/index.html` lines 907–1142, the last
section inside `<main>`) in an `x-if` template keyed on the active tab, and drop
the section's own `x-show`:

```html
<template x-if="$store.nav.tab === 'logs'">
  <section x-data="logsScreen()">
    <!-- existing list-view + detail-view markup, unchanged -->
  </section>
</template>
```

With `x-if` (Alpine v3 — the project loads `alpinejs@3.x.x`), the DOM subtree and
its `x-data` component are **destroyed when the tab is left and re-created when
the tab is next entered**. Alpine runs the component's `init()` on each creation.

A brand-new `logsScreen()` instance starts from its declared field defaults,
which are exactly the reset state:

| Field | Default | Meaning |
|---|---|---|
| `view` | `"list"` | list view, not a trace detail |
| `selected` / `detail` | `null` | no open session/trace |
| `stepIdx` | `0` | first turn |
| `filterTask` / `filterFraming` | `""` | no filters |
| `human` / `llm` / `loaded` | `[]` / `[]` / `false` | empty until (re)loaded |

`init()` calls `load()`, which fetches `/api/logs` afresh. Therefore a remount is
identically "full reset + reload" with **no manual reset code**: the reset can
never drift out of sync with the field set, because it *is* a fresh construction.

### Why not a manual reset (`$watch` + `reset()`)

Keeping `x-show` and adding a watcher on `$store.nav.tab` that calls a `reset()`
method also works, and stays consistent with the rest of the app (all other
screens use `x-show`). It was rejected because `reset()` must enumerate every
state field by hand, so adding a field later silently reintroduces the bug. The
`x-if` approach is self-maintaining.

### Deliberate architectural exception

The rest of the app intentionally uses `x-show` and *persists* component state —
most notably the Model Leaderboard, one shared instance rendered on both `#home`
and `#leaderboard` specifically to avoid a re-fetch. Making Logs an `x-if`
exception is intentional and documented here: Logs is the one screen where the
user explicitly wants a clean slate on each visit.

## Scope of Changes

- **`web/index.html` only.** Wrap the Logs `<section>` in `<template x-if>`, and
  remove the section's `x-show` (visibility is now the template's job).
  `x-cloak` on the section becomes redundant under `x-if` (the element does not
  exist until shown) and is removed for cleanliness.
- **`web/app.js` — no change.** `logsScreen()`'s existing `init()`/`load()`
  already perform a fresh load; remounting alone yields the reset.
- No backend, API, or persistence change. No other screen touched.

## Side Effect (acceptable / minor improvement)

Under `x-show`, `logsScreen` mounts on page load and eagerly fetches `/api/logs`
even when the user never opens Logs. Under `x-if`, the fetch is **deferred to
first entry** of the tab — a small, welcome reduction in wasted requests. No
downside: the first-open experience is identical.

## Base State (precondition)

The working tree currently carries an in-progress, uncommitted **nav
restructure** (Home/About split, Model Leaderboard moved to `#leaderboard`,
`#models` kept as a legacy alias) across `web/app.js` and `web/index.html`. Per
the agreed sequencing, that restructure is committed first (excluding the
`web/config.js` local-dev `localhost` pointer, which must not ship) to establish
a clean base. This Logs-reset change is then made on its own branch on top of
that base. The `x-if` wrap targets the restructured section markup (the nav
store shape `$store.nav.tab === 'logs'` is unchanged by the restructure).

## Testing / Verification

No JS unit-test harness exists for the web frontend (consistent with prior
web-arena work, which verifies static markup + Alpine behavior manually). The
change is a single markup wrap. Verification:

1. **Static check** — confirm the wrapped section is well-formed (single root
   under the template; `</section>` still matched; nav link + store unchanged).
2. **Manual browser smoke** (the definitive check):
   - Enter Logs, open a session trace, step to turn N.
   - Navigate to another tab, then back to Logs → shows the **list view**, no
     open trace, **empty filters**, list **re-fetched**.
   - Apply a `task`/`framing` filter, leave, return → filters are **cleared**.
   - Confirm other tabs (Play, Leaderboard/Home, Arena) still work and that a
     direct load of `#logs` mounts and loads correctly.

## Non-Goals

- No change to what the Logs screen *displays* or how a trace is rendered.
- No change to the reset behavior of any other screen (they keep `x-show` +
  state persistence by design).
- No preservation/deep-linking of the viewed trace via the URL hash (out of
  scope; the requirement is to reset, not to make state shareable).
