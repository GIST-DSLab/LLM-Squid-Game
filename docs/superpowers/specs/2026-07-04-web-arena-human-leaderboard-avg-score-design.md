# Web Arena Human Leaderboard — Total Score → Average Score (Design)

**Date:** 2026-07-04
**Status:** Approved (user, 2026-07-04)

## Problem

The Human Play Leaderboard currently ranks players by the **sum** of `final_score`
across a campaign's 6 games (`total_score`). The LLM leaderboard, by contrast,
ranks by an **average** session score. We want the human board to use an average
too, so the two boards are conceptually comparable ("score per game" rather than
"score for the whole run").

## Goal

Change the Human Play Leaderboard's aggregation, ranking, and display from
**total campaign score** to **per-game average score**, mirroring the LLM board's
"score per game" spirit.

## Definition (decided)

**Average = `total_score / games_played`** — the simple mean of `final_score`
over the games actually played in the campaign.

- Partial campaigns (fewer than 6 games) are handled naturally: divide by the
  number of games played, not by a fixed 6.
- We do **not** mirror the LLM's `no_cap_avg_session_score` "no-cap session"
  restriction. That restriction filters EV-distorted sessions for analysis; the
  human board is a participation/engagement board where a reward cap almost never
  binds, so the simple mean is clearer and sufficient.
- Forfeited games keep counting: a forfeit game's `final_score` (the preserved
  score `S`) is included in both the numerator and the denominator, exactly as it
  is counted today in the sum.

## Scope

### In scope
1. **Backend** (`interface/api.py`)
   - `PlayLeaderboardRow`: replace the `total_score` field with **`avg_score`**
     (per-game average). Keep `games_played`, `forfeits`, `created_at`. Keeping
     `games_played` in the row makes the average's denominator transparent to the
     viewer.
   - `leaderboard_play()`: still sum `final_score` per campaign while aggregating,
     then compute `avg_score = total / games_played` per campaign.
     - **Best-per-nickname:** keep each nickname's highest-**average** campaign
       (was highest-total).
     - **Sort:** by `avg_score` descending.
     - `games_played >= 1` is guaranteed by construction (a campaign exists only
       because it has at least one session), so no division by zero; add a
       defensive guard regardless.
2. **Frontend** (`web/index.html`, Human players board)
   - Intro copy: "cumulative score across the 6-game campaign" →
     "average score per game across the campaign".
   - Column header: `Total score` → `Avg score`.
   - Row cell: `row.total_score` → `row.avg_score` (keep the existing
     `fmtNum(…, 1)` one-decimal formatting).
   - The other columns (Games / Forfeits / Last played), the `colspan=6` empty
     row, and the ranking order (top-down = server order) are unchanged.
3. **Tests** (`tests/unit/test_api_web_arena.py`)
   - Update the three play-leaderboard assertions (around lines 435, 836, 944):
     `total_score` → `avg_score`, expected values recomputed as per-game averages.
   - The rank-inversion test (~836) asserts the nickname's highest-**average**
     campaign wins (recompute the expected winner under the average metric).

### Out of scope (deliberately unchanged)
- **Campaign drill-down report** (`_build_human_report` →
  `ReportCampaign.total_score`, and `index.html` "total X" per campaign): this is
  the detail view of a *single* campaign, where a cumulative total is the correct,
  meaningful quantity. It stays as a total. (User-confirmed.)
- **LLM experiment path** (`runner.py`, `engine.py`, `src/squid_game/**`,
  `prompts/`): untouched. The aggregation is a pure read-time computation.
- **Persistence layer / DB schema** (`interface/persistence/**`): untouched. No
  stored column changes — the average is computed on the fly from `final_score`,
  exactly as the sum is today.

## Interfaces

- `PlayLeaderboardRow` (response model): `{ campaign_id, nickname, avg_score:
  float, games_played: int, forfeits: int, created_at: str | None }`. The
  `total_score` field is removed and replaced by `avg_score`.
- `GET /api/leaderboard/play`: same route and response envelope
  (`PlayLeaderboardResponse.campaigns`), rows now carry `avg_score` and are
  ordered by it descending.

## Naming

Use `avg_score` / label **"Avg score"** (not the LLM's
`no_cap_avg_session_score`) — humans have no no-cap concept, so a plain name is
clearer and avoids implying a restriction that isn't applied.

## Testing strategy

Backend behavior is locked by the existing `TestClient`-driven play-leaderboard
tests in `tests/unit/test_api_web_arena.py`. Update them to the average metric
(field name + recomputed expected values + rank-inversion winner). Frontend is
static Alpine markup with no unit test; verified by `node --check web/app.js`
(app.js is not touched here, so this is a no-op guard) and a visual eyeball of the
Human board on the deployed/local stack (deferred to the user, as with prior
human-board work).

## Global constraints (carried from prior human-arena work)

- `web/config.js` stays pointed at the Render URL; never commit a localhost
  override.
- pytest on this iCloud checkout needs
  `chflags -R nohidden .venv/lib/python3.12/site-packages/` first.
- "Green" = no new failures vs the known pre-existing web-arena baseline
  (~10 failed / ~92 errors); this change should add/keep the play-leaderboard
  tests green with no new failures.
