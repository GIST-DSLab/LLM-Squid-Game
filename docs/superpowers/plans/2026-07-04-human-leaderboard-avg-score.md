# Human Leaderboard — Total Score → Average Score Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rank and display the Human Play Leaderboard by per-game **average** score (`total / games_played`) instead of the campaign **sum**, mirroring the LLM board's "score per game" framing.

**Architecture:** Two layers. (1) **Backend** (`interface/api.py`): `leaderboard_play()` still sums each campaign's `final_score` while aggregating, then divides by `games_played`; `PlayLeaderboardRow.total_score` becomes `avg_score`; best-per-nickname and the final sort switch to that average. (2) **Frontend** (`web/`): the Human board's intro copy, column header, and row cell switch from total to average. The aggregation is a pure read-time computation — no DB/schema/persistence change.

**Tech Stack:** FastAPI (`interface/api.py`), pytest + Starlette `TestClient` (`tests/unit/test_api_web_arena.py`), static Alpine.js frontend (`web/index.html`, `web/app.js`), Node for JS syntax check.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-07-04-web-arena-human-leaderboard-avg-score-design.md`.
- **Average definition:** `avg_score = total_score / games_played` (simple per-game mean over games actually played). Do **not** mirror the LLM `no_cap_avg_session_score` "no-cap session" restriction — humans have no no-cap concept.
- Forfeited games keep counting (their preserved-score `final_score` is in both numerator and denominator, exactly as summed today).
- **Out of scope — do NOT touch:** the campaign drill-down report (`_build_human_report` → `ReportCampaign.total_score`, `interface/api.py:550` model field, `interface/api.py:1144` sum, `web/index.html:1371` "total X"); it is a single-campaign detail view where a cumulative total is correct. The `/api/report` test at `tests/unit/test_api_web_arena.py:944` asserts that report total and MUST stay unchanged.
- **Out of scope — do NOT touch:** LLM experiment path (`runner.py`, `engine.py`, `src/squid_game/**`, `prompts/`) and persistence (`interface/persistence/**`). No schema/stored-column change.
- `web/config.js` must stay pointed at the Render URL (`https://squid-game-web-arena-api.onrender.com`). **Never commit a `localhost` override.**
- Field name is `avg_score`; frontend label is **"Avg score"**.
- pytest on this iCloud checkout needs `chflags -R nohidden .venv/lib/python3.12/site-packages/` first, or it fails with `No module named 'squid_game'`.
- "Green" = no new failures vs the known pre-existing web-arena baseline (~10 failed / ~92 errors).

## File Structure

- `interface/api.py` — `PlayLeaderboardRow` model (field rename) + `leaderboard_play()` handler (compute/rank by average). Single source of the mechanic.
- `tests/unit/test_api_web_arena.py` — one new behavioral test locking "average, not sum"; two existing play-leaderboard assertions updated to `avg_score`.
- `web/index.html` — Human board intro copy + column header + row cell.
- `web/app.js` — one stale doc comment corrected (no logic; the board reads `row.avg_score` straight from the response).

---

### Task 1: Backend — leaderboard ranks by per-game average (TDD)

**Files:**
- Modify: `interface/api.py:428-442` (`PlayLeaderboardRow` + `PlayLeaderboardResponse` docstrings) and `interface/api.py:1003-1041` (`leaderboard_play`)
- Test: `tests/unit/test_api_web_arena.py` (add one test; update two assertions)

**Interfaces:**
- Consumes: `_repository.list_sessions(source="human")` → `list[SessionRecord]` (each has `.campaign_id`, `.id`, `.nickname`, `.final_score`, `.forfeited`, `.created_at`); `_seed_session(api_module, **overrides)` test helper (seeds a `SessionRecord`, honoring `final_score`, `campaign_id`, `nickname`, `source`).
- Produces: `PlayLeaderboardRow` with fields `{ campaign_id: str, nickname: str, avg_score: float, games_played: int, forfeits: int, created_at: str | None }` (the `total_score` field is removed). `GET /api/leaderboard/play` returns `PlayLeaderboardResponse.campaigns` ordered by `avg_score` descending. Consumed by Task 2's frontend (`row.avg_score`).

- [ ] **Step 1: Write the failing test + update the two existing assertions**

Add this new test to `tests/unit/test_api_web_arena.py` (next to the other play-leaderboard tests, e.g. after `test_play_leaderboard_empty_returns_empty_list`). It is the non-vacuous lock: a two-game campaign whose scores are 10 and 30 must report the mean (20.0), NOT the sum (40.0):

```python
def test_play_leaderboard_uses_average_not_sum(client, api_module) -> None:
    """The board reports per-game average (total / games_played), not the sum.
    A campaign of two games scoring 10 and 30 must show 20.0, never 40.0."""
    _seed_session(
        api_module, nickname="avgtester", source="human",
        campaign_id="camp-avg", final_score=10.0,
        created_at="2026-03-01T00:00:00+00:00",
    )
    _seed_session(
        api_module, nickname="avgtester", source="human",
        campaign_id="camp-avg", final_score=30.0,
        created_at="2026-03-02T00:00:00+00:00",
    )

    body = client.get("/api/leaderboard/play").json()
    row = next(c for c in body["campaigns"] if c["campaign_id"] == "camp-avg")
    assert row["games_played"] == 2
    assert row["avg_score"] == 20.0          # mean, not the 40.0 sum
    assert "total_score" not in row          # field renamed, not duplicated
```

Then update the two existing play-leaderboard assertions (leave the `/api/report` test at line ~944 untouched — it is the out-of-scope drill-down):

In `test_new_game_persists_campaign_id_and_play_leaderboard_sums_it` (around line 434-435), change:

```python
    # Ranked by total_score descending.
    scores = [c["total_score"] for c in body["campaigns"]]
    assert scores == sorted(scores, reverse=True)
```

to:

```python
    # Ranked by avg_score descending.
    scores = [c["avg_score"] for c in body["campaigns"]]
    assert scores == sorted(scores, reverse=True)
```

In `test_leaderboard_best_per_nickname` (around line 836), change:

```python
    # The surviving row must be the HIGHER-total campaign, not merely first-seen.
    assert erin_rows[0]["total_score"] == max(total_a, total_b)
```

to:

```python
    # Each campaign here is a single game, so its per-game average equals that
    # game's final score; the surviving row is still the higher-scoring campaign.
    assert erin_rows[0]["avg_score"] == max(total_a, total_b)
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `chflags -R nohidden .venv/lib/python3.12/site-packages/ ; uv run pytest tests/unit/test_api_web_arena.py -k "play_leaderboard or best_per_nickname" -v`
Expected: `test_play_leaderboard_uses_average_not_sum` FAILS (response rows carry `total_score`, not `avg_score` → `KeyError`/`next(...)` sees no `avg_score`), and the two updated assertions FAIL on the missing `avg_score` key.

- [ ] **Step 3: Rename the response field**

In `interface/api.py`, in `PlayLeaderboardRow` (around line 428), replace:

```python
    total_score: float = Field(description="Sum of final_score across the campaign's games")
```

with:

```python
    avg_score: float = Field(description="Mean final_score per game across the campaign's games")
```

In the same block, update the two docstrings so they match the new metric:
- `PlayLeaderboardRow` docstring (line ~429): `"""One player's Play campaign, ranked by cumulative 6-game score."""` → `"""One player's Play campaign, ranked by per-game average score."""`
- `PlayLeaderboardResponse` docstring (line ~440): `"""Human Play Leaderboard: campaigns ranked by total_score descending."""` → `"""Human Play Leaderboard: campaigns ranked by avg_score descending."""`

- [ ] **Step 4: Compute and rank by the average in `leaderboard_play()`**

In `interface/api.py`, replace the body of `leaderboard_play()` (currently `interface/api.py:1012-1041`, from `sessions = _repository.list_sessions(...)` through the `return`) with:

```python
    sessions = _repository.list_sessions(source="human")  # newest-first
    campaigns: dict[str, dict] = {}
    for s in sessions:
        key = s.campaign_id or s.id
        agg = campaigns.get(key)
        if agg is None:
            # list_sessions is newest-first, so the first session seen for a
            # campaign carries the most recent nickname / created_at.
            agg = {
                "campaign_id": key,
                "nickname": s.nickname,
                "_total": 0.0,
                "games_played": 0,
                "forfeits": 0,
                "created_at": s.created_at,
            }
            campaigns[key] = agg
        agg["_total"] += s.final_score
        agg["games_played"] += 1
        agg["forfeits"] += 1 if s.forfeited else 0

    # Per-game average = campaign total / games played. games_played >= 1 by
    # construction (a campaign exists only because a session created it); guard
    # defensively anyway. Drop the running total so only response fields remain.
    for agg in campaigns.values():
        played = agg["games_played"]
        agg["avg_score"] = agg.pop("_total") / played if played else 0.0

    # Best-per-nickname: keep only each nickname's highest-average campaign.
    best_by_nick: dict[str, dict] = {}
    for agg in campaigns.values():
        cur = best_by_nick.get(agg["nickname"])
        if cur is None or agg["avg_score"] > cur["avg_score"]:
            best_by_nick[agg["nickname"]] = agg

    ranked = sorted(best_by_nick.values(), key=lambda a: a["avg_score"], reverse=True)
    return PlayLeaderboardResponse(campaigns=[PlayLeaderboardRow(**a) for a in ranked])
```

Also update the `leaderboard_play` docstring sentence (line ~1010) `Within a campaign the final scores are summed, and campaigns are ranked descending.` → `Within a campaign the final scores are averaged per game, and campaigns are ranked by that average descending.`

Note: after `agg.pop("_total")`, each `agg` holds exactly the six `PlayLeaderboardRow` fields (`campaign_id`, `nickname`, `avg_score`, `games_played`, `forfeits`, `created_at`), so `PlayLeaderboardRow(**a)` receives no extra keys.

- [ ] **Step 5: Run the tests to verify they pass**

Run: `uv run pytest tests/unit/test_api_web_arena.py -k "play_leaderboard or best_per_nickname" -v`
Expected: PASS (including `test_play_leaderboard_uses_average_not_sum` and `test_play_leaderboard_empty_returns_empty_list`).

- [ ] **Step 6: Run the full web-arena suite to confirm no regression**

Run: `uv run pytest tests/unit/test_api_web_arena.py -q`
Expected: all pass, including `test_report_human_groups_by_campaign_with_cells` (the drill-down report `total_score` is unchanged and must stay green).

- [ ] **Step 7: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web): rank human Play leaderboard by per-game average score"
```

---

### Task 2: Frontend — Human board shows "Avg score"

**Files:**
- Modify: `web/index.html:1239` (intro copy), `web/index.html:1248` (column header), `web/index.html:1257` (row cell)
- Modify: `web/app.js:1210` (stale doc comment)

**Interfaces:**
- Consumes: `GET /api/leaderboard/play` rows, now carrying `row.avg_score` (from Task 1). The board template iterates `campaigns` and renders one row per campaign.
- Produces: no new symbols; display-only change.

- [ ] **Step 1: Update the intro copy**

In `web/index.html`, the Human board intro (around line 1239) reads:

```html
            Human players ranked by <strong>cumulative score across the 6-game campaign</strong>
```

Change the emphasized phrase to:

```html
            Human players ranked by <strong>average score per game across the campaign</strong>
```

- [ ] **Step 2: Update the column header**

In `web/index.html` (around line 1248), the header row reads:

```html
                    <th>#</th><th>Nickname</th><th>Total score</th>
                    <th>Games</th><th>Forfeits</th><th>Last played</th>
```

Change `Total score` to `Avg score`:

```html
                    <th>#</th><th>Nickname</th><th>Avg score</th>
                    <th>Games</th><th>Forfeits</th><th>Last played</th>
```

(The `colspan="6"` empty-state row below is unchanged — still six columns.)

- [ ] **Step 3: Update the row cell binding**

In `web/index.html` (around line 1257), the score cell reads:

```html
                      <td x-text="squidArenaHelpers.fmtNum(row.total_score, 1)"></td>
```

Change the field to `avg_score` (keep the one-decimal formatting):

```html
                      <td x-text="squidArenaHelpers.fmtNum(row.avg_score, 1)"></td>
```

Do NOT change `web/index.html:1371` (`'total ' + squidArenaHelpers.fmtNum(c.total_score, 1)`) — that is the out-of-scope campaign drill-down.

- [ ] **Step 4: Correct the stale doc comment in app.js**

In `web/app.js` (around line 1210), the comment reads:

```javascript
    // Human board ranks Play campaigns by cumulative 6-game score.
```

Change it to:

```javascript
    // Human board ranks Play campaigns by per-game average score.
```

- [ ] **Step 5: Syntax-check and verify the edits landed**

Run:
```bash
node --check web/app.js
grep -n "Avg score" web/index.html
grep -n "row.avg_score" web/index.html
grep -n "row.total_score" web/index.html
grep -n "c.total_score" web/index.html
```
Expected: `node --check` exits 0 (no output); `Avg score` and `row.avg_score` are present; `row.total_score` returns NOTHING (board cell migrated); `c.total_score` STILL present once at line ~1371 (drill-down untouched).

- [ ] **Step 6: Commit**

```bash
git add web/index.html web/app.js
git commit -m "feat(web): Human leaderboard displays Avg score instead of Total score"
```

---

### Task 3: Full verification (suites + config check)

**Files:** none (verification gate).

- [ ] **Step 1: Run the backend suite**

```bash
chflags -R nohidden .venv/lib/python3.12/site-packages/
uv run pytest tests/unit/test_api_web_arena.py -q
node --check web/app.js
```
Expected: all pass (including the new `test_play_leaderboard_uses_average_not_sum` and the untouched `test_report_human_groups_by_campaign_with_cells`); `node --check` exits 0.

- [ ] **Step 2: Confirm scope + config untouched**

```bash
grep -n "total_score" interface/api.py
grep WEB_ARENA_API web/config.js
git status --short
```
Expected: `total_score` in `interface/api.py` remains ONLY in the drill-down report model/handler (`ReportCampaign` field ~550 + `_build_human_report` ~1144), NOT in `PlayLeaderboardRow`/`leaderboard_play`; `web/config.js` reads the Render URL, not localhost; working tree shows only the intended commits from Tasks 1-2.

- [ ] **Step 3: Eyeball the Human board (deferred to user)**

Start the local stack (backend `uvicorn interface.api:app --port 8502`, static `web/` on 5500 with a temporary localhost config override reverted before any commit), open the Leaderboard → **Human players** tab, and confirm the column reads **"Avg score"** and each row shows the per-game mean (e.g. a 2-game campaign scoring 10 + 30 shows **20.0**, not 40.0). The drill-down (click a player → campaign) still shows a per-campaign **total**.

---

## Notes / Context for the implementer

- The average is computed at read time from `final_score`; there is no stored `avg_score` column and no migration. A reseed is not required.
- Why keep summing internally then dividing (rather than averaging incrementally): the running sum + `games_played` counter is the existing, proven shape; dividing once at the end is the smallest, clearest diff and avoids per-session float drift.
- `games_played` stays as a visible column so the average's denominator is transparent to viewers.
- The grouping test's name still says `..._sums_it`; its body now asserts descending order on `avg_score` and campaign grouping, both still valid. Renaming the test function is optional churn and out of scope.

## Self-Review

- **Spec coverage:** (1) average = total/games_played → Task 1 Step 4 + new test. (2) rank + best-per-nickname by average → Task 1 Step 4. (3) field `total_score`→`avg_score` → Task 1 Step 3. (4) frontend copy/header/cell + label "Avg score" → Task 2. (5) drill-down + LLM path + persistence untouched → Global Constraints + Task 3 Step 2 grep guard. (6) config revert → Task 3 Step 3. All covered.
- **Placeholder scan:** no TBD/TODO; every code step shows full before/after.
- **Type consistency:** `avg_score: float` defined on `PlayLeaderboardRow` (Task 1) is the exact key produced by the `agg` dict (Task 1 Step 4) and read by the frontend as `row.avg_score` (Task 2); the six agg keys after `pop("_total")` match the six model fields exactly.
