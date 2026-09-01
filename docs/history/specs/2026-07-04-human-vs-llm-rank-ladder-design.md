# Human-vs-LLM Rank Ladder — Design Spec

**Date:** 2026-07-04
**Status:** Approved (brainstorming)
**Area:** Web Arena — campaign completion report

## Problem

When a human finishes a full 6-condition campaign in the Web Arena, they see a
"Your 6-condition report" card with per-game scores. There is no way to see how
that performance stacks up against the LLM models. We want to show, right on the
report, where the player ranks **by simple score** relative to the LLM
leaderboard models — who is #1, and who sits immediately above and below them —
in a vertical ranked ladder.

## Goal

Add a "Where you rank vs LLMs" section to the campaign report that places the
player on a single score-ranked ladder together with the LLM models, rendered as
a **compact window** (top-1 + the player's immediate neighbors) with a one-line
headline summarizing who they beat and who beat them.

## Non-Goals

- Changing the β-based Model Leaderboard (`/api/leaderboard/models`) or its
  ranking semantics.
- Changing the human Play Leaderboard.
- Any new persistence / schema changes.

## Comparison Scale

All subjects are normalized to **average score per game** so a player who dies
early (fewer than 6 games) is still compared fairly:

- **You (human):** `Σ finalScore ÷ games_played`, computed client-side from
  `campaignResults` (already in memory — no fetch needed for the player's own
  number).
- **LLM models:** `AVG(final_score)` grouped by model over `sessions` where
  `source = 'llm'`. Each LLM session is one game, so this is already a per-game
  average. Current values: Gemini-2.5-flash ≈ 536.3, Qwen3-Next-80B ≈ 469.7,
  GPT-OSS-20B ≈ 350.6, Nemotron-3-Nano-30B ≈ 236.1.

## Backend

New read-only endpoint (existing endpoints untouched):

```
GET /api/leaderboard/model_scores
→ ModelScoresResponse {
    models: [ { model_label: str, avg_score_per_game: float, n_games: int }, ... ]
  }
```

- Aggregated live from the `sessions` table (`source='llm'`), grouped by
  `nickname` (the model label for LLM rows). ~720 rows today — cheap.
- Sorted by `avg_score_per_game` descending, then `model_label` ascending
  (stable, deterministic).
- Empty list when the DB has no LLM sessions (unseeded `:memory:` DSN).

Add a repository helper `avg_score_per_model()` (or reuse an aggregate query) in
`sqlite_repository.py` returning `[(model_label, avg_score, n_games)]`, so the
API layer stays thin and the SQL is unit-testable.

## Frontend

### Placement
Inside the `x-if="campaignDone"` report card (`web/index.html` ~line 840),
**above** the existing turns/score table, add a `Where you rank vs LLMs`
section.

### Data flow
On entering the report (campaign done), fetch `/api/leaderboard/model_scores`.
Combine the returned models with a synthetic `You` entry
`{ label: nickname, score: playerAvgPerGame, isYou: true }`, sort all by score
descending (ties: score desc, then label asc; the `You` row sorts **last within
its tie group** — conservative), and assign 1-based ranks.

### Compact-window rule (pure function, unit-tested)
Given the ranked list and the player's rank `r` (of `N`), display only:

- **Always:** rank 1 (the leader).
- **Neighbors:** rank `r-1`, `r` (You, highlighted), `r+1`.
- Insert a `⋮` gap marker between rank 1 and rank `r-1` when they are not
  adjacent (i.e. `r-1 > 2`).
- De-duplicate overlapping rows (e.g. if You are rank 2, rank 1 IS the "above"
  neighbor — no gap marker, no duplicate).
- No `r+1` row when You are last; no `r-1` row (and no gap) when You are rank 1
  or 2.

Return an ordered list of display items, each either a `row` (with rank, label,
score, isYou, isLeader flags) or a `gap` marker.

### Headline
One sentence above the ladder naming the immediate neighbors. Copy is **English**
to match the rest of the report card (all sibling labels are English):

- Middle: `"#{r} of {N} — below {above}, above {below}."`
- Last: `"#{r} of {N} — below {above}, dead last."`
- First: `"#1 of {N} — you beat every LLM."`

### Rendering
Vertical ladder; the leader row carries a 🥇/crown affordance, the `You` row is
visually emphasized (border/background accent), gap rows render a centered `⋮`.
Reuse existing report-card / table styling idioms in `styles.css`.

## Edge cases

- **Fetch failure:** hide the whole section; the rest of the report renders
  normally.
- **No LLM data (empty response):** hide the section.
- **Ties:** stable sort (score desc, label asc); `You` placed last in its tie
  group so the reported rank is never optimistic.
- **Player is #1 / last:** handled by the window rule (missing neighbor rows).

## Testing

- **Backend:** add `/api/leaderboard/model_scores` cases to
  `tests/unit/test_api_web_arena.py` — verifies per-model average, descending
  sort, and empty-DB behavior.
- **Window logic:** extract the compact-window builder as a pure function and
  unit-test the four cases: You #1, You middle (with gap), You last, and a tie
  at the boundary.
- **No new failures** against the pre-existing web-arena baseline (see project
  memory: ~10 failed / 92 errors are pre-existing).

## Files touched (anticipated)

- `interface/api.py` — new response model + `GET /api/leaderboard/model_scores`.
- `interface/persistence/sqlite_repository.py` — `avg_score_per_model()` helper.
- `web/app.js` — fetch model scores, build combined ranked list + window items,
  headline string, expose to the report component.
- `web/index.html` — new report section markup.
- `web/styles.css` — ladder / You-row / gap styling.
- `tests/unit/test_api_web_arena.py` — endpoint tests.
- Window-builder unit test (JS pure function) — location per app.js test setup.
