# Human-vs-LLM Rank Ladder Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Show a human, on their campaign-completion report, where they rank by average score-per-game against the LLM models — as a compact vertical ladder (leader + immediate neighbors) with a one-line headline.

**Architecture:** A new read-only endpoint (`/api/leaderboard/model_scores`) aggregates per-model average score-per-game live from the `sessions` table. The frontend fetches it when the campaign report renders, merges a synthetic "You" row, and renders a compact windowed ladder built by a pure, unit-tested JS function (`buildRankLadder`). No schema, persistence, or existing-endpoint changes.

**Tech Stack:** FastAPI + SQLite (`interface/`), pytest (`tests/unit/`), vanilla JS + Alpine.js (`web/`), `node --test` for the pure JS function, Playwright MCP for end-to-end UI verification.

## Global Constraints

- Do NOT modify `/api/leaderboard/models` (β-based) or `/api/leaderboard/play` — preserve their contracts and tests.
- LLM per-model score = `AVG(final_score)` over `sessions WHERE source='llm'`, grouped by `nickname` (for LLM rows, `nickname` holds the model label). Each LLM session is one game, so this is already per-game.
- Human per-game score = `Σ finalScore ÷ games_played` from `campaignResults` (client-side; no fetch for the player's own number).
- Sort order everywhere: score **descending**, then `model_label` **ascending**; the `You` row sorts **last within its tie group** (never optimistic).
- Rendered copy is **English** to match the existing report card. Exact headline strings:
  - First: `#1 of {N} — you beat every LLM.`
  - Middle: `#{r} of {N} — below {above}, above {below}.`
  - Last: `#{r} of {N} — below {above}, dead last.`
- Endpoint returns 200 with an empty list when there are no LLM sessions; the frontend hides the whole section on empty data or fetch failure.
- Baseline: judge test health by "no NEW failures" — ~10 failed / 92 errors are pre-existing in the web-arena suite.

---

### Task 1: Repository helper `avg_score_per_model()`

Aggregate per-model average score-per-game from LLM sessions, at the repository layer so the SQL is unit-testable and the API stays thin.

**Files:**
- Modify: `interface/persistence/sqlite_repository.py` (add method to `SQLiteRepository`, ~line 200 area, near `list_sessions`)
- Test: `tests/unit/test_seed_web_arena.py` is unrelated; add a new focused test file `tests/unit/test_repo_model_scores.py`

**Interfaces:**
- Consumes: `SessionRecord` rows already inserted with `source`, `nickname`, `final_score`.
- Produces: `SQLiteRepository.avg_score_per_model() -> list[tuple[str, float, int]]` — a list of `(model_label, avg_score_per_game, n_games)`, one per distinct LLM-session `nickname`, sorted by `avg_score_per_game` descending then `model_label` ascending.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_repo_model_scores.py`:

```python
"""Unit tests for SQLiteRepository.avg_score_per_model (rank-ladder support)."""

from __future__ import annotations

from interface.persistence.models import SessionRecord
from interface.persistence.sqlite_repository import SQLiteRepository


def _repo() -> SQLiteRepository:
    return SQLiteRepository(":memory:")


def _add(repo: SQLiteRepository, *, nickname: str, score: float, source: str = "llm") -> None:
    repo.create_session(
        SessionRecord(
            id=nickname + "-" + str(score),
            nickname=nickname,
            task="signal_game",
            framing="true_baseline",
            forfeit="allowed",
            seed=1,
            final_score=score,
            forfeited=False,
            source=source,
        )
    )


def test_avg_score_per_model_groups_and_averages():
    repo = _repo()
    _add(repo, nickname="ModelA", score=100.0)
    _add(repo, nickname="ModelA", score=300.0)  # ModelA avg = 200, n = 2
    _add(repo, nickname="ModelB", score=500.0)  # ModelB avg = 500, n = 1
    _add(repo, nickname="alice", score=9999.0, source="human")  # excluded

    rows = repo.avg_score_per_model()

    assert rows == [("ModelB", 500.0, 1), ("ModelA", 200.0, 2)]


def test_avg_score_per_model_empty_when_no_llm_sessions():
    repo = _repo()
    _add(repo, nickname="alice", score=10.0, source="human")
    assert repo.avg_score_per_model() == []


def test_avg_score_per_model_tie_breaks_by_label_ascending():
    repo = _repo()
    _add(repo, nickname="Zeta", score=200.0)
    _add(repo, nickname="Alpha", score=200.0)
    rows = repo.avg_score_per_model()
    assert [r[0] for r in rows] == ["Alpha", "Zeta"]
```

> Note: confirm `SessionRecord`'s import path and constructor field names against `interface/persistence/models.py` (fields: `id, nickname, task, framing, forfeit, seed, final_score, forfeited, source, created_at=None, campaign_id=None`) and that `create_session` is the insert method (confirmed at `sqlite_repository.py:163`).

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_repo_model_scores.py -v`
Expected: FAIL with `AttributeError: 'SQLiteRepository' object has no attribute 'avg_score_per_model'`

- [ ] **Step 3: Write minimal implementation**

In `interface/persistence/sqlite_repository.py`, add this method to `SQLiteRepository` (place it right after `list_sessions`):

```python
    def avg_score_per_model(self) -> list[tuple[str, float, int]]:
        """Average score-per-game for each LLM model, for the rank ladder.

        Groups ``source='llm'`` sessions by ``nickname`` (the model label for
        LLM rows), averaging ``final_score`` (one session == one game, so this
        is already per-game). Sorted by average descending, then label ascending.
        """
        query = (
            "SELECT nickname, AVG(final_score) AS avg_score, COUNT(*) AS n_games "
            "FROM sessions WHERE source = 'llm' "
            "GROUP BY nickname "
            "ORDER BY avg_score DESC, nickname ASC"
        )
        with self._lock:
            rows = self._conn.execute(query).fetchall()
        return [(r["nickname"], float(r["avg_score"]), int(r["n_games"])) for r in rows]
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_repo_model_scores.py -v`
Expected: PASS (3 passed)

- [ ] **Step 5: Commit**

```bash
git add interface/persistence/sqlite_repository.py tests/unit/test_repo_model_scores.py
git commit -m "feat(web-arena): repo helper avg_score_per_model for rank ladder

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Endpoint `GET /api/leaderboard/model_scores`

Expose the per-model average score-per-game as a small JSON endpoint the report can fetch.

**Files:**
- Modify: `interface/api.py` (add response models near the other leaderboard models ~line 385-426; add route near `leaderboard_models`/`leaderboard_play` ~line 943-998)
- Test: `tests/unit/test_api_web_arena.py` (add cases)

**Interfaces:**
- Consumes: `SQLiteRepository.avg_score_per_model()` from Task 1 (via the module-level `_repository`).
- Produces: `GET /api/leaderboard/model_scores` returning `ModelScoresResponse { models: list[ModelScoreRow] }`, where `ModelScoreRow { model_label: str, avg_score_per_game: float, n_games: int }`, sorted by `avg_score_per_game` descending.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_api_web_arena.py` (end of file):

```python
def test_model_scores_empty_on_fresh_db(client):
    resp = client.get("/api/leaderboard/model_scores")
    assert resp.status_code == 200
    assert resp.json() == {"models": []}


def test_model_scores_aggregates_llm_sessions(api_module, client):
    from interface.persistence.models import SessionRecord

    repo = api_module._repository
    for i, score in enumerate([100.0, 300.0]):  # ModelA avg 200, n 2
        repo.create_session(SessionRecord(
            id=f"a{i}", nickname="ModelA", task="signal_game",
            framing="true_baseline", forfeit="allowed", seed=1,
            final_score=score, forfeited=False, source="llm",
        ))
    repo.add_session(SessionRecord(
        id="b0", nickname="ModelB", task="signal_game",
        framing="true_baseline", forfeit="allowed", seed=1,
        final_score=500.0, forfeited=False, source="llm",
    ))

    resp = client.get("/api/leaderboard/model_scores")
    assert resp.status_code == 200
    models = resp.json()["models"]
    assert models == [
        {"model_label": "ModelB", "avg_score_per_game": 500.0, "n_games": 1},
        {"model_label": "ModelA", "avg_score_per_game": 200.0, "n_games": 2},
    ]
```

> Note: `api_module._repository` is the same repository the app uses (see how existing tests reach internals). If existing tests reference the repository differently, match their pattern.

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k model_scores -v`
Expected: FAIL — `test_model_scores_empty_on_fresh_db` returns 404 (route missing)

- [ ] **Step 3: Write minimal implementation**

In `interface/api.py`, add response models (place after `ModelLeaderboardResponse`, ~line 410):

```python
class ModelScoreRow(BaseModel):
    """One model's average score-per-game, for the human rank ladder."""

    model_label: str
    avg_score_per_game: float
    n_games: int


class ModelScoresResponse(BaseModel):
    """Models ranked by average score-per-game descending (rank-ladder source)."""

    models: list[ModelScoreRow]
```

Add the route (place after `leaderboard_models`, ~line 958):

```python
@app.get("/api/leaderboard/model_scores", response_model=ModelScoresResponse)
def leaderboard_model_scores():
    """Per-model average score-per-game, for the campaign report's rank ladder.

    Aggregated live from LLM sessions (``source='llm'``), one row per model,
    sorted by average descending. Empty list (200) when there are no LLM
    sessions — the frontend hides the ladder in that case.
    """
    rows = _repository.avg_score_per_model()
    return ModelScoresResponse(
        models=[
            ModelScoreRow(model_label=label, avg_score_per_game=avg, n_games=n)
            for (label, avg, n) in rows
        ]
    )
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k model_scores -v`
Expected: PASS (2 passed)

- [ ] **Step 5: Verify no new failures in the API suite**

Run: `uv run pytest tests/unit/test_api_web_arena.py -q`
Expected: the two new tests pass; no previously-passing test now fails.

- [ ] **Step 6: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): GET /api/leaderboard/model_scores endpoint

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Pure window-builder `buildRankLadder` (+ node test)

The compact-window logic is the one piece with real branching, so isolate it as a pure function and unit-test it with `node --test` (no framework needed on Node 22).

**Files:**
- Create: `web/rank_ladder.js` (UMD-style: browser global + `module.exports`)
- Create: `tests/web/rank_ladder.test.mjs`

**Interfaces:**
- Produces: `buildRankLadder(models, you)` where
  - `models`: `Array<{ model_label: string, avg_score_per_game: number }>`
  - `you`: `{ label: string, score: number }`
  - returns `null` when `models` is empty/missing, else
    `{ rank: number, total: number, headline: string, items: Array<Item> }`
    where `Item` is `{ type: "gap" }` or
    `{ type: "row", rank, label, score, isYou, isLeader }`.
- Consumed by: Task 4 (app.js report wiring). Browser access: `window.squidArenaHelpers.buildRankLadder`.

- [ ] **Step 1: Write the failing test**

Create `tests/web/rank_ladder.test.mjs`:

```javascript
import { test } from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";

const require = createRequire(import.meta.url);
const { buildRankLadder } = require("../../web/rank_ladder.js");

const MODELS = [
  { model_label: "Gemini", avg_score_per_game: 536 },
  { model_label: "Qwen", avg_score_per_game: 470 },
  { model_label: "GPT-OSS", avg_score_per_game: 351 },
  { model_label: "Nemotron", avg_score_per_game: 236 },
];

test("returns null when no models", () => {
  assert.equal(buildRankLadder([], { label: "You", score: 10 }), null);
});

test("You last: leader + gap + above + You, dead-last headline", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 10 });
  assert.equal(r.rank, 5);
  assert.equal(r.total, 5);
  assert.equal(r.headline, "#5 of 5 — below Nemotron, dead last.");
  assert.deepEqual(
    r.items.map((i) => (i.type === "gap" ? "gap" : `${i.rank}:${i.label}`)),
    ["1:Gemini", "gap", "4:Nemotron", "5:You"],
  );
  assert.equal(r.items.find((i) => i.isYou).label, "You");
  assert.equal(r.items[0].isLeader, true);
});

test("You middle: leader + gap + above + You + below", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 400 });
  assert.equal(r.rank, 3); // 536,470,400(You),351,236
  assert.equal(r.headline, "#3 of 5 — below Qwen, above GPT-OSS.");
  assert.deepEqual(
    r.items.map((i) => (i.type === "gap" ? "gap" : `${i.rank}:${i.label}`)),
    ["1:Gemini", "2:Qwen", "3:You", "4:GPT-OSS"],
  );
});

test("You first: leader row is You, beat-every headline, no gap", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 999 });
  assert.equal(r.rank, 1);
  assert.equal(r.headline, "#1 of 5 — you beat every LLM.");
  assert.deepEqual(
    r.items.map((i) => `${i.rank}:${i.label}`),
    ["1:You", "2:Gemini"],
  );
});

test("tie: You sorts last within its score group (never optimistic)", () => {
  const r = buildRankLadder(MODELS, { label: "You", score: 236 });
  assert.equal(r.rank, 5); // Nemotron 236 keeps rank 4, You rank 5
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `node --test tests/web/`
Expected: FAIL — `Cannot find module '../../web/rank_ladder.js'`

- [ ] **Step 3: Write minimal implementation**

Create `web/rank_ladder.js`:

```javascript
// Pure builder for the human-vs-LLM rank ladder shown on the campaign report.
// UMD: usable via `require` in node tests and as window.squidArenaHelpers in the browser.
(function (factory) {
  const api = factory();
  if (typeof module !== "undefined" && module.exports) module.exports = api;
  if (typeof window !== "undefined") {
    window.squidArenaHelpers = window.squidArenaHelpers || {};
    window.squidArenaHelpers.buildRankLadder = api.buildRankLadder;
  }
})(function () {
  // models: [{ model_label, avg_score_per_game }]; you: { label, score }
  function buildRankLadder(models, you) {
    if (!models || models.length === 0) return null;

    const entries = models.map((m) => ({
      label: m.model_label,
      score: m.avg_score_per_game,
      isYou: false,
    }));
    entries.push({ label: you.label, score: you.score, isYou: true });

    // score desc; within a tie, non-You before You; then label asc.
    entries.sort((a, b) => {
      if (b.score !== a.score) return b.score - a.score;
      if (a.isYou !== b.isYou) return a.isYou ? 1 : -1;
      return a.label.localeCompare(b.label);
    });
    entries.forEach((e, i) => (e.rank = i + 1));

    const N = entries.length;
    const r = entries.find((e) => e.isYou).rank;

    // Window = {1} ∪ {r-1, r, r+1} (clamped to [1, N]).
    const show = new Set([1, r]);
    if (r - 1 >= 1) show.add(r - 1);
    if (r + 1 <= N) show.add(r + 1);

    const items = [];
    let prev = 0;
    for (const rank of Array.from(show).sort((a, b) => a - b)) {
      if (rank - prev > 1) items.push({ type: "gap" });
      const e = entries[rank - 1];
      items.push({
        type: "row",
        rank: e.rank,
        label: e.label,
        score: e.score,
        isYou: e.isYou,
        isLeader: e.rank === 1,
      });
      prev = rank;
    }

    const above = r > 1 ? entries[r - 2].label : null;
    const below = r < N ? entries[r].label : null;
    let headline;
    if (r === 1) headline = `#1 of ${N} — you beat every LLM.`;
    else if (r === N) headline = `#${r} of ${N} — below ${above}, dead last.`;
    else headline = `#${r} of ${N} — below ${above}, above ${below}.`;

    return { rank: r, total: N, headline, items };
  }

  return { buildRankLadder };
});
```

- [ ] **Step 4: Run test to verify it passes**

Run: `node --test tests/web/`
Expected: PASS (5 tests pass)

- [ ] **Step 5: Commit**

```bash
git add web/rank_ladder.js tests/web/rank_ladder.test.mjs
git commit -m "feat(web-arena): pure buildRankLadder window logic + node tests

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Wire the ladder into the campaign report

Fetch model scores when the report renders, build the ladder, and render the section above the score table. This task's deliverable is the visible, working UI section, verified end-to-end.

**Files:**
- Modify: `web/index.html` (add `<script defer src="rank_ladder.js"></script>` at line ~17 **before** `app.js`; add section markup inside the `x-if="campaignDone"` card, ~line 841, above the `<table class="report-table">`)
- Modify: `web/app.js` (add state fields + a `buildLadder()` method to `playScreen` ~line 638; call it when `campaignDone` becomes true in `recordCurrentGame` ~line 1064 and in the resume path ~line 1090)
- Modify: `web/styles.css` (ladder / You-row / gap / headline styles)

**Interfaces:**
- Consumes: `window.squidArenaHelpers.buildRankLadder` (Task 3); `GET /api/leaderboard/model_scores` (Task 2); `fetchJSON(path, options, onStatus)` (`web/app.js:25`); `this.campaignResults` (each `{ finalScore }`), `this.nickname`.
- Produces: `playScreen.rankLadder` — `null` or `{ rank, total, headline, items }` — consumed only by the report markup.

- [ ] **Step 1: Add the script include and state field**

In `web/index.html`, change line ~17 so `rank_ladder.js` loads before `app.js` (both `defer`, order preserved):

```html
  <script defer src="rank_ladder.js"></script>
  <script defer src="app.js"></script>
```

In `web/app.js`, add to the `playScreen` state object (near `campaignDone: false,` ~line 639):

```javascript
      rankLadder: null,      // { rank, total, headline, items } vs LLM models; null = hidden
```

- [ ] **Step 2: Add the `buildLadder()` method**

In `web/app.js`, add this method to `playScreen` (place near `recordCurrentGame`, ~line 1044):

```javascript
      async buildLadder() {
        // Player's own number is local: mean finalScore across games played.
        const games = this.campaignResults.length;
        if (games === 0) { this.rankLadder = null; return; }
        const total = this.campaignResults.reduce((s, g) => s + (g.finalScore || 0), 0);
        const you = { label: this.nickname || "You", score: total / games };
        try {
          const data = await fetchJSON("/api/leaderboard/model_scores", {});
          this.rankLadder = squidArenaHelpers.buildRankLadder(data.models, you);
        } catch (e) {
          this.rankLadder = null;   // fetch failed — hide the section, keep the report
        }
      },
```

- [ ] **Step 3: Trigger it when the campaign completes**

In `web/app.js`, inside `recordCurrentGame`, where `this.campaignDone = true;` is set (~line 1064), add a call right after that block. Change:

```javascript
        if (this.campaignIndex >= squidArenaHelpers.campaignConditions.length - 1) {
          this.campaignDone = true;
        } else {
          this.betweenGames = true;
        }
```

to:

```javascript
        if (this.campaignIndex >= squidArenaHelpers.campaignConditions.length - 1) {
          this.campaignDone = true;
          this.buildLadder();
        } else {
          this.betweenGames = true;
        }
```

Also, in the resume-from-checkpoint path where `campaignResults` is restored (~line 1090, after `this.campaignResults = ck.campaignResults || [];`), if that path can land on a finished campaign, guard it: leave `rankLadder` null there (the resume path sets `campaignDone = false`, so no change needed — confirm by reading lines 1085-1095 before editing).

- [ ] **Step 4: Add the report markup**

In `web/index.html`, inside `<template x-if="campaignDone">` → `<div class="card report-card">`, immediately after `<h3>Your 6-condition report</h3>` (~line 842) and before `<!-- Turns-survived table -->`, insert:

```html
          <!-- Where you rank vs LLMs (by average score per game) -->
          <template x-if="rankLadder">
            <div class="rank-ladder">
              <h4>Where you rank vs LLMs</h4>
              <p class="rank-headline" x-text="rankLadder.headline"></p>
              <ul class="ladder-list">
                <template x-for="(it, i) in rankLadder.items" :key="'ld' + i">
                  <li>
                    <template x-if="it.type === 'gap'">
                      <span class="ladder-gap">⋮</span>
                    </template>
                    <template x-if="it.type === 'row'">
                      <span class="ladder-row" :class="{ 'is-you': it.isYou, 'is-leader': it.isLeader }">
                        <span class="ladder-rank" x-text="'#' + it.rank"></span>
                        <span class="ladder-name">
                          <template x-if="it.isLeader"><span class="ladder-medal">🥇</span></template>
                          <span x-text="it.label"></span>
                        </span>
                        <span class="ladder-score" x-text="squidArenaHelpers.fmtNum(it.score, 1)"></span>
                      </span>
                    </template>
                  </li>
                </template>
              </ul>
              <p class="rank-note muted">Average score per game — LLMs across their full runs, you across the games you played.</p>
            </div>
          </template>
```

- [ ] **Step 5: Add styles**

In `web/styles.css`, append (reuse existing report-card spacing idioms; adjust color tokens to match the file's existing variables if it uses CSS custom properties):

```css
/* Human-vs-LLM rank ladder (campaign report) */
.rank-ladder { margin: 4px 0 20px; }
.rank-ladder .rank-headline { font-weight: 600; margin: 4px 0 12px; }
.ladder-list { list-style: none; padding: 0; margin: 0; }
.ladder-list li { margin: 0; }
.ladder-row {
  display: flex; align-items: center; gap: 12px;
  padding: 8px 12px; border-radius: 8px;
  border: 1px solid transparent;
}
.ladder-rank { width: 3ch; font-variant-numeric: tabular-nums; opacity: 0.7; }
.ladder-name { flex: 1; display: flex; align-items: center; gap: 6px; }
.ladder-score { font-variant-numeric: tabular-nums; font-weight: 600; }
.ladder-row.is-leader .ladder-name { font-weight: 600; }
.ladder-row.is-you {
  border-color: currentColor;
  background: rgba(127, 127, 127, 0.14);
  font-weight: 700;
}
.ladder-gap { display: block; text-align: center; opacity: 0.5; padding: 2px 0; }
.rank-note { font-size: 0.85em; margin-top: 8px; }
```

- [ ] **Step 6: Verify end-to-end in the browser (Playwright MCP)**

Start the API against the **seeded** DB (has the 4 LLM models) and serve the static frontend:

```bash
# Terminal A — API on the seeded DB
WEB_ARENA_DSN=outputs/web_arena/web_arena.db uv run uvicorn interface.api:app --port 8000
# Terminal B — static web
python -m http.server 5173 --directory web
```

Then, using the Playwright MCP browser:
1. Navigate to the play screen, set a nickname, and play a full 6-condition campaign (or use the resume/checkpoint path) until `campaignDone`.
2. Confirm the "Where you rank vs LLMs" section renders **above** the score table.
3. Confirm the headline reads like `#5 of 5 — below Nemotron-3-Nano-30B, dead last.` (a typical human total ranks last vs the seeded models), the leader row shows 🥇 Gemini-2.5-flash with the highest score, a `⋮` gap sits between the leader and your neighbor, and the `You` row is visually emphasized.
4. Confirm score formatting matches the rest of the report (one decimal via `fmtNum`).

Capture a screenshot into the scratchpad for the review.

- [ ] **Step 7: Verify the ladder hides on missing data**

Restart Terminal A against an empty DB (`WEB_ARENA_DSN=:memory:`), replay a campaign, and confirm the section is absent while the rest of the report renders normally.

- [ ] **Step 8: Commit**

```bash
git add web/index.html web/app.js web/styles.css
git commit -m "feat(web-arena): render human-vs-LLM rank ladder on campaign report

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Self-Review

- **Spec coverage:** Placement (T4 markup), comparison scale (T1 SQL + T4 client mean), backend endpoint (T2), repository helper (T1), compact-window rule incl. gap/dedup/edges (T3), headline strings (T3 + Global Constraints), edge cases fetch-fail/empty/ties/first/last (T3 tests + T4 Steps 6-7), testing backend + window logic (T1/T2/T3) + end-to-end (T4). All covered.
- **Placeholder scan:** No TBD/TODO; every code step has full code; commands have expected output.
- **Type consistency:** `avg_score_per_model() -> list[tuple[str, float, int]]` (T1) is consumed by T2's route builder with matching unpack `(label, avg, n)`. `buildRankLadder(models, you)` return shape (T3) matches the markup fields `headline`, `items[].type/rank/label/score/isYou/isLeader` (T4). `fetchJSON` 2-arg call matches `web/app.js:25` signature.

## Open verification notes for the implementer

- Insert method is `create_session` (confirmed `sqlite_repository.py:163`); `SessionRecord` lives in `interface.persistence.models`.
- `api_module._repository` is the correct handle inside `tests/unit/test_api_web_arena.py` (confirmed — existing tests use it, e.g. `upsert_model_stats`, `get_session`).
- Read `web/app.js:1085-1095` (resume path) before editing Step 3 to confirm it lands with `campaignDone = false` (so no ladder build is needed there).
- If `styles.css` uses CSS custom properties for surface/border colors, swap the hard-coded `rgba()` in Step 5 for the matching tokens.
