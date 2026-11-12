# Web Arena Human-Play UI/UX Polish — Design Spec

**Date:** 2026-07-04
**Status:** Approved (design), pending implementation plan
**Scope:** `web/index.html`, `web/app.js`, `web/styles.css` — human-play flow only. **No API/engine/data-model changes.**

## Motivation

The human-play screen (players play as the AI through all 6 conditions) has accumulated rough edges: leftover Korean strings, dropdown-based rule guessing, a plain confidence slider, a forfeit-reason picker shown before the forfeit decision, a flat reward preview, and a report whose "Reason" column reads from the server response instead of the player's actual pick. This spec polishes all six.

## Affected files

- `web/index.html` — play-card markup (lines ~349–800): resume screen, rule builder, confidence slider, Stage 3 decision block, reward preview, report table.
- `web/app.js` — `playScreen()` component: new `forfeitPending` state, `recordCurrentGame` reason derivation.
- `web/styles.css` — new classes for chip-menus, themed slider, versus reward card.

## Requirements

### 1. Full English pass (play flow)

Replace every remaining Korean string in the human-play flow. No behavior change.

| Location | Korean → English |
|---|---|
| Resume screen | `이어하기: n/6 완료` → `Resume: n/6 done`; `닉네임 …` → `Nickname …`; `이어서 플레이 ▶` → `Resume ▶`; `새로 시작` → `Start over` |
| Start form | `닉네임 (비밀번호로 보호)` → `Nickname (password-protected)`; placeholder `닉네임` → `Nickname`; `(닉네임 보호 · 복구 불가)` → `(protects your nickname · unrecoverable)`; placeholder `비밀번호` → `Password`; help line `비밀번호는 복구할 수 없습니다. 같은 닉네임은 같은 비밀번호로만 이어서 플레이할 수 있어요.` → `Passwords can't be recovered. A nickname can only be resumed with its original password.` |
| Between-games eyebrows | `첫 게임` → `First game`; `다음 게임` → `Next game` |
| Rules box | `게임 규칙 (공통)` → `Game rules (shared)` |
| Rule preview | `— (아직 규칙 추측 없음)` → `— (no rule guess yet)` |
| Reward preview | `계속하고 정답 시` → `If you continue & get it right`; `포기 시 (확정)` → `If you forfeit (locked in)` |

Acceptance: `grep -P '[\x{AC00}-\x{D7A3}]' web/index.html` over the play `<section>` (x-data `playScreen()`) returns nothing.

### 2. Rule-guess: horizontal chip-menu

Replace the four native `<select>` dropdowns (`If [attr] is [value] then [action] otherwise [default]`) with a **horizontal sentence row** of styled chip-menus:

```
If ⟨🎨 color ▾⟩ is ⟨🔴 red ▾⟩ then ⟨⬅️ left ▾⟩ otherwise ⟨➡️ right ▾⟩
```

- Each `⟨ ⟩` is a chip button showing the **active option's emoji + label**; clicking it opens a small popover of emoji+text options.
- Emoji maps: attribute (`color 🎨 / shape 🔷 / number #️⃣`), value (colors `🔴🔵🟢…`, shapes, numbers), action reuses existing `squidArenaHelpers.actionEmoji`.
- The `?` unset state shows a neutral placeholder chip.
- Row uses `flex-wrap` so it collapses gracefully on narrow widths; the four clauses stay inline as long as space allows.
- The assembled-rule `code` preview stays beneath the row (`Submitting: IF color = red THEN left ELSE right`).
- Binds to the existing `probeAttr` / `probeValue` / `probeAction` / `probeDefault` models and `valueOptions` — the assembled-rule computation and submission payload are unchanged.

Implementation note: chip-menu open/close is per-clause local state (e.g. an `openMenu` string on the component identifying which clause is open, closed on select or outside-click). Alpine `x-data` local state; no framework additions.

### 3. Redesigned confidence slider

Single slider, unchanged `psuccess` value and payload (`psuccess_self`). Visual only:

- Themed track matching the dark/accent palette: gradient fill from 0 → thumb.
- Live `%` bubble that follows the thumb position.
- Tick marks at 0 / 25 / 50 / 75 / 100.
- Label: `How confident are you? (P_CORRECT)` with the live `%` value.

Styled via `web/styles.css` (`input[type=range]` custom track/thumb + a fill overlay driven by an inline `--val` width). No new JS value.

### 4. Forfeit-reason ordering (pick AFTER clicking FORFEIT)

Reverse the current order. Add a single `forfeitPending` boolean to `playScreen()`.

Stage 3 states:
1. **Default:** reward preview + `CONTINUE ▶` and `🏳️ FORFEIT` buttons. Reason picker hidden.
2. **FORFEIT clicked** → set `forfeitPending = true` (does **not** submit). Reveal the `If you forfeit, why?` chip group + a `Confirm forfeit` button. `Confirm forfeit` is disabled until a reason is picked.
3. **Confirm forfeit clicked** → `chooseForfeit(forfeitReason)` submits as today.
4. **CONTINUE clicked** (from default) → submits continue as today.
5. Leaving Stage 3 / resetting a turn clears `forfeitPending` (fold into `_resetTurnState` and the post-submit reset).

`pickReason`, `chooseForfeit`, and the submit path are reused unchanged. The FORFEIT button no longer requires a pre-selected reason to be enabled (the gate moves to `Confirm forfeit`).

### 5. Reward preview — versus card

Replace the flat two-cell grey box with a "versus" layout:

- **Continue** side (accent): `▶` icon, `If you continue & get it right`, `+<reward>` emphasized.
- **Forfeit** side (neutral/warning): `🏳️` icon, `If you forfeit (locked in)`, confirmed `<score>` emphasized.
- Center `vs` divider/badge; subtle border + gradient consistent with the dark background.
- Loading: reuse `previewLoading` → skeleton / `…` on the Continue reward.

New CSS classes in `web/styles.css` (e.g. `.reward-versus`, `.rv-side`, `.rv-continue`, `.rv-forfeit`, `.rv-vs`). Uses existing `continueReward`, `state.cumulative_score`, `previewLoading`.

### 6. Report "Reason" = player's actual pick

The report table's Reason column currently binds `g.forfeitReason` sourced from `res.forfeit_reason` (server). Change the source to the reason the player actually chose during play:

- In `recordCurrentGame`, find the forfeit turn in `this.history` (`h.forfeit === true`) and read its `reason` digit.
- Map the digit through `REASON_OPTIONS` to `"<emoji> <label>"` (e.g. `🛡️ To survive`, `🥱 Got bored`, `💰 Protect my score`).
- Store that string as `forfeitReason`; the table renders it directly (`—` when the game was not forfeited).
- Add a small helper (e.g. `squidArenaHelpers.reasonLabel(digit)`) rather than inlining the lookup.

## Non-goals

- No changes to the API, engine, scoring, or the `psuccess_self` / `p_correct` data model.
- No changes to the LLM Arena screen, Logs/Trace Explorer, or the "How to play" animated replica (except incidental if it shares a changed CSS class — verify it still renders).
- No two-slider split (explicitly rejected: p_correct and p_success are one self-report value here).

## Testing / verification

- Manual: play through a full 6-condition campaign; verify each stage, forfeit-after-click flow, and the report Reason column shows the picked reason.
- Existing web-arena tests (`tests/**/*web_arena*`, `tests/integration/test_arena.py`) must show no new failures (baseline ~10 failed/92 errors pre-existing per project memory).
- No Korean remaining in the play section (grep gate above).
- Cross-check the animated "How to play" replica still renders after CSS changes.
