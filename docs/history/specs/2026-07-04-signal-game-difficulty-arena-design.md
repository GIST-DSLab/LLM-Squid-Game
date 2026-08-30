# Design Spec: Expose Signal Game Difficulty in the Web Arena (LLM mode)

**Date:** 2026-07-04
**Status:** Approved (brainstorming), pending implementation plan
**Scope:** LLM Arena mode only, `signal_game` task only

## Problem

The public web arena's LLM mode runs every participant model at a single fixed
difficulty. `interface/arena.py:_arena_config_dict` hardcodes
`"difficulty": "easy"` (line 74), and neither `ArenaRunRequest`
(`interface/api.py:1296`) nor the frontend (`web/app.js` `launch()`,
`web/index.html` arena setup) exposes a difficulty control. The Signal Game
engine already implements a 4-level ladder (`easy / medium / hard / expert`,
`src/squid_game/models/enums.py:104-110`), but none of it reaches arena users.

Goal: let arena participants choose the Signal Game difficulty when launching a
run against their endpoint.

## Scope Decisions

- **In scope:** difficulty selection in the LLM Arena setup UI + the backend
  chain that carries it into the engine config.
- **Out of scope:** human-play mode difficulty; other tasks (voting_room,
  navigation); the MEDIUM level; task selection (arena is signal_game-only by
  design).

## Key Constraint: `num_few_shot` neutralizes MEDIUM

`_arena_config_dict` fixes `num_few_shot: 2` (arena.py:79). The Signal Game's
MEDIUM level is defined to share EASY's exact rule-space; its *only*
differentiator is a reduced few-shot count, and that clamp fires **only when
`num_few_shot is None`** (`src/squid_game/tasks/signal_game/module.py:304-308`).
With `num_few_shot` fixed at 2, EASY and MEDIUM become mechanically identical.

Consequence: we expose the three **structurally distinct** levels — EASY
(single-attribute), HARD (two-attribute AND), EXPERT (two-attribute +
history-dependent reversal) — and skip MEDIUM. These differ in rule structure,
so they remain distinguishable regardless of the fixed few-shot count.

## Label Mapping (frontend display → engine value)

| UI label | Engine value | Rule structure |
|---|---|---|
| **Easy**   | `easy`   | Single-attribute (e.g. "if color is red then go_left") |
| **Normal** | `hard`   | Two-attribute AND (e.g. "if color is red AND shape is star then jump") |
| **Hard**   | `expert` | Two-attribute + previous-turn-correctness reversal |

**Vocabulary boundary:** the API and engine speak engine values
(`easy/hard/expert`); the display-label translation lives **only in the
frontend**, mirroring the existing `framing` pattern
(`flagship_corruption` ↔ "Push+Pull").

## Architecture

Data flow (added `difficulty` in **bold**):

```
web/index.html (difficulty selector, x-model="difficulty")
  → web/app.js launch()  POST /api/arena/run { ..., **difficulty** }
  → interface/api.py ArenaRunRequest.difficulty  (validate ∈ VALID_DIFFICULTIES)
  → interface/arena.py run_arena_session(**difficulty**)
  → _arena_config_dict(**difficulty**)  → task_config["difficulty"]
  → engine (unchanged)
```

### Backend

**`interface/arena.py`**
- Add `VALID_DIFFICULTIES = {"easy", "hard", "expert"}` (MEDIUM intentionally
  excluded).
- `_arena_config_dict(...)` gains a `difficulty: str` parameter; replaces the
  hardcoded `"difficulty": "easy"` at line 74.
- `run_arena_session(...)` gains `difficulty: str = "easy"`; validates against
  `VALID_DIFFICULTIES` (raise `ValueError` on unknown, matching the existing
  framing/forfeit validation style); threads it into `_arena_config_dict`.
- `num_few_shot: 2` stays fixed — rule structure differentiates the three
  levels, and a constant few-shot count keeps per-turn token cost (and thus
  leaderboard fairness) consistent across difficulties.

**`interface/api.py`**
- `ArenaRunRequest` gains `difficulty: str = Field("easy", description=...)`.
- `arena_run` validates `req.difficulty in VALID_DIFFICULTIES` → `HTTPException(400)`
  on unknown (mirrors the existing framing/forfeit checks at lines 1332-1335).
- Passes `difficulty=req.difficulty` into `run_arena_session`.

### Frontend

**`web/app.js`**
- Add a `DIFFICULTY_OPTIONS` constant: engine value → `{ label, blurb }`
  - `easy`   → `{ label: "Easy",   blurb: "Single-attribute rule" }`
  - `hard`   → `{ label: "Normal", blurb: "Two-attribute AND rule" }`
  - `expert` → `{ label: "Hard",   blurb: "Two attributes + it flips based on your last answer" }`
- Expose via `squidArenaHelpers.difficultyOptions`.
- `arenaScreen()` data: add `difficulty: "easy"`.
- `launch()` POST body: add `difficulty: this.difficulty`.

**`web/index.html`**
- In the "Conditions" card (lines 1036-1064), add a difficulty selector styled
  like the existing `forfeit-seg` segmented buttons (or `cond-cards`), bound to
  `difficulty`, iterating `squidArenaHelpers.difficultyOptions`.

## Backward Compatibility

Default `difficulty="easy"` at every layer preserves current behavior. Clients
that omit `difficulty` (old frontends, direct API callers) keep running EASY
exactly as today.

## Testing

- Unit: `_arena_config_dict(..., difficulty="hard")` sets
  `task_config["difficulty"] == "hard"`; default omission yields `"easy"`.
- API: unknown difficulty → 400; valid values accepted; default is `easy`.
- Confirm existing arena tests still pass (locate them during planning; extend
  rather than duplicate).

## Non-Goals / Future Work

- Exposing MEDIUM would require making `num_few_shot` difficulty-aware
  (`easy=3, medium=1`) — deferred.
- Human-play difficulty and non-signal_game tasks — deferred.
