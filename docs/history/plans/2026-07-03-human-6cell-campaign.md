# Human 6-cell Campaign + On-screen Report Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make a human web player run all six (framing × forfeit) conditions sequentially — picking only the game — then see an on-screen report (per-condition turns-survived, per-turn correctness heatmap, forfeit-reason summary), with a REASON picker on forfeit.

**Architecture:** Backend gains additive forfeit-reason capture (`HumanGameSession` stores a `ForfeitSelfReport`, threaded through `/api/action` and surfaced on `/api/result`). Frontend `playScreen` (Alpine.js) becomes a campaign controller that iterates a fixed 6-condition queue, snapshots each game's per-turn history, and renders an integrated report assembled client-side. No new backend endpoints; each game still persists as its own `source='human'` session.

**Tech Stack:** Python 3.12, FastAPI, pydantic v2, pytest (+ pytest-asyncio); Alpine.js (no build step) + vanilla JS/CSS in `web/`.

## Global Constraints

- Python 3.12 (`requires-python = ">=3.12"`).
- Death mode OFF for human campaign: `actual_death=False` (existing default) — do NOT enable death.
- Fixed condition order (framing baseline → pull → push_pull; within each, forfeit not_allowed → allowed):
  1. `true_baseline` / `not_allowed`
  2. `true_baseline` / `allowed`
  3. `baseline_flagship` / `not_allowed`
  4. `baseline_flagship` / `allowed`
  5. `flagship_corruption` / `not_allowed`
  6. `flagship_corruption` / `allowed`
- Forfeit reason digits: `1=survival`, `2=task_curiosity`, `3=score` (`REASON_BY_DIGIT` in `src/squid_game/models/forfeit_choice.py`).
- Turns-survived = number of non-forfeit action turns (`forfeited_at_turn - 1` when forfeited, else 15).
- Backward compatibility: existing single-game `/api/new_game` + `/api/action` callers (and their tests) must keep working — forfeit reason is optional.
- Each game gets a fresh random seed (already implemented — do not pin seeds in the campaign requests).
- pytest quirk (iCloud): before EVERY pytest run, unhide the editable `.pth` files:
  `chflags nohidden .venv/lib/python3.12/site-packages/*.pth`
- Judge test runs green by "no NEW failures" vs the pre-existing web-arena baseline (see project memory: ~10 failed/92 errors are pre-existing).

---

### Task 1: Capture forfeit reason in HumanGameSession

**Files:**
- Modify: `interface/human_game.py` (`__init__`, `submit_action`, `get_result`)
- Test: `tests/unit/test_human_game.py` (create)

**Interfaces:**
- Consumes: `ForfeitReason`, `ForfeitSelfReport`, `REASON_BY_DIGIT` from `squid_game.models.forfeit_choice`.
- Produces:
  - `HumanGameSession.submit_action(action: str, probe_answer: str = "", forfeit_reason: int | None = None) -> TurnFeedback`
  - `HumanGameSession._forfeit_self_report: ForfeitSelfReport | None`
  - `get_result()` returns a `SeasonResult` whose `forfeit_self_report` is set when a reason was given.

- [ ] **Step 1: Write the failing test**

Create `tests/unit/test_human_game.py`:

```python
"""Unit tests for the interactive HumanGameSession forfeit-reason capture."""

from __future__ import annotations

from interface.human_game import HumanGameSession
from squid_game.models.forfeit_choice import ForfeitReason


def _new_allowed_session() -> HumanGameSession:
    # true_baseline keeps p_end/threat out of the way; forfeit allowed so the
    # forfeit branch is reachable. actual_death False = no random death.
    return HumanGameSession(
        task_name="signal_game",
        difficulty="easy",
        framing="true_baseline",
        forfeit_condition="allowed",
        seed=1,
        total_turns=5,
        actual_death=False,
        num_few_shot=0,
        curriculum_turns=0,
    )


def test_forfeit_with_reason_records_self_report():
    game = _new_allowed_session()
    game.get_turn_state()  # advance to turn 1
    fb = game.submit_action("forfeit", probe_answer="", forfeit_reason=1)

    assert fb.forfeited is True
    result = game.get_result()
    assert result.forfeit_self_report is not None
    assert result.forfeit_self_report.reason == ForfeitReason.SURVIVAL_DRIVE
    assert result.forfeit_self_report.raw_digit == 1
    assert result.forfeit_self_report.forfeit_turn == 1


def test_forfeit_without_reason_has_no_self_report():
    game = _new_allowed_session()
    game.get_turn_state()
    fb = game.submit_action("forfeit")  # legacy caller, no reason

    assert fb.forfeited is True
    assert game.get_result().forfeit_self_report is None


def test_reason_digit_maps_to_score_attachment():
    game = _new_allowed_session()
    game.get_turn_state()
    game.submit_action("forfeit", forfeit_reason=3)
    assert game.get_result().forfeit_self_report.reason == ForfeitReason.SCORE_ATTACHMENT
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth; uv run pytest tests/unit/test_human_game.py -v`
Expected: FAIL — `submit_action()` got an unexpected keyword argument `forfeit_reason` (or `forfeit_self_report` is None).

- [ ] **Step 3: Add the import and the stored field**

In `interface/human_game.py`, extend the forfeit-model import (near the top, alongside the other `squid_game.models` imports):

```python
from squid_game.models.forfeit_choice import (
    ForfeitSelfReport,
    REASON_BY_DIGIT,
)
```

In `HumanGameSession.__init__`, next to `self._self_report: SelfReport | None = None`, add:

```python
        self._self_report: SelfReport | None = None
        self._forfeit_self_report: ForfeitSelfReport | None = None
```

- [ ] **Step 4: Accept and record the reason in `submit_action`**

Change the signature:

```python
    def submit_action(
        self, action: str, probe_answer: str = "", forfeit_reason: int | None = None
    ) -> TurnFeedback:
```

Inside the forfeit branch (`if action == "forfeit" and self._forfeit_ctrl.is_forfeit_allowed():`), right after `self._forfeited_at_turn = turn_num`, add:

```python
            if forfeit_reason in REASON_BY_DIGIT:
                self._forfeit_self_report = ForfeitSelfReport(
                    reason=REASON_BY_DIGIT[forfeit_reason],
                    raw_digit=forfeit_reason,  # type: ignore[arg-type]  # guarded by the membership test
                    raw_response="human",
                    forfeit_turn=turn_num,
                )
```

- [ ] **Step 5: Surface it on `get_result`**

In `get_result()`, add the field to the `SeasonResult(...)` constructor (next to `self_report=self._self_report`):

```python
            self_report=self._self_report,
            forfeit_self_report=self._forfeit_self_report,
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth; uv run pytest tests/unit/test_human_game.py -v`
Expected: PASS (3 passed).

- [ ] **Step 7: Commit**

```bash
git add interface/human_game.py tests/unit/test_human_game.py
git commit -m "feat(web-arena): capture human forfeit reason as ForfeitSelfReport"
```

---

### Task 2: Thread forfeit reason through the API

**Files:**
- Modify: `interface/api.py` (`ActionRequest`, `GameResultResponse`, `submit_action` endpoint, `get_result` endpoint)
- Test: `tests/unit/test_api_web_arena.py` (append)

**Interfaces:**
- Consumes: `HumanGameSession.submit_action(..., forfeit_reason=...)` and `get_result().forfeit_self_report` from Task 1.
- Produces:
  - `ActionRequest.forfeit_reason: int | None` (1|2|3)
  - `GameResultResponse.forfeit_reason: str | None` (the `ForfeitReason` value, e.g. `"survival"`)

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_api_web_arena.py`:

```python
# ---------------------------------------------------------------------------
# Forfeit reason (human REASON 1|2|3)
# ---------------------------------------------------------------------------


def test_forfeit_reason_is_recorded_and_reported(client: TestClient) -> None:
    """Forfeiting with a reason surfaces it on /api/result."""
    sid = client.post(
        "/api/new_game",
        json={
            "task_name": "signal_game",
            "framing": "true_baseline",
            "forfeit_condition": "allowed",
            "total_turns": 5,
            "actual_death": False,
            "num_few_shot": 0,
            "curriculum_turns": 0,
            "seed": 1,
        },
    ).json()["session_id"]

    # Turn 1 -> forfeit with reason 3 (score attachment).
    client.get("/api/state", params={"session_id": sid})
    act = client.post(
        f"/api/action?session_id={sid}",
        json={"action": "forfeit", "probe_answer": "", "reasoning": "", "forfeit_reason": 3},
    )
    assert act.status_code == 200
    assert act.json()["game_over"] is True

    res = client.get("/api/result", params={"session_id": sid}).json()
    assert res["forfeited"] is True
    assert res["forfeit_reason"] == "score"


def test_forfeit_without_reason_still_works(client: TestClient) -> None:
    sid = client.post(
        "/api/new_game",
        json={"task_name": "signal_game", "framing": "true_baseline",
              "forfeit_condition": "allowed", "total_turns": 5,
              "actual_death": False, "num_few_shot": 0, "curriculum_turns": 0, "seed": 1},
    ).json()["session_id"]
    client.get("/api/state", params={"session_id": sid})
    client.post(f"/api/action?session_id={sid}",
                json={"action": "forfeit", "probe_answer": "", "reasoning": ""})
    res = client.get("/api/result", params={"session_id": sid}).json()
    assert res["forfeited"] is True
    assert res["forfeit_reason"] is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth; uv run pytest tests/unit/test_api_web_arena.py -k forfeit_reason -v`
Expected: FAIL — `ActionRequest` has no `forfeit_reason` (extra field ignored → not passed) or `GameResultResponse` has no `forfeit_reason` key.

- [ ] **Step 3: Add the request field**

In `interface/api.py`, in `class ActionRequest`, after the `reasoning` field, add:

```python
    forfeit_reason: int | None = Field(
        default=None,
        ge=1,
        le=3,
        description=(
            "REASON digit on FORFEIT: 1=survival, 2=task_curiosity, "
            "3=score. Ignored unless action == 'forfeit'."
        ),
    )
```

- [ ] **Step 4: Add the response field**

In `class GameResultResponse`, after `forfeited_at_turn: int | None`, add:

```python
    forfeit_reason: str | None = Field(
        default=None,
        description="ForfeitReason value (survival|task_curiosity|score) when the player forfeited with a reason.",
    )
```

- [ ] **Step 5: Pass the reason into the session**

In the `submit_action` endpoint, change the call:

```python
    feedback = game.submit_action(
        req.action, probe_answer=req.probe_answer, forfeit_reason=req.forfeit_reason
    )
```

- [ ] **Step 6: Populate the response field**

In the `get_result` endpoint, where `GameResultResponse(...)` is built, add:

```python
        forfeited_at_turn=result.forfeited_at_turn,
        forfeit_reason=(result.forfeit_self_report.reason.value
                        if result.forfeit_self_report else None),
```

- [ ] **Step 7: Run tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth; uv run pytest tests/unit/test_api_web_arena.py -v`
Expected: PASS (all, including the 2 new tests).

- [ ] **Step 8: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): thread forfeit_reason through /api/action and /api/result"
```

---

### Task 3: Campaign helpers + report helpers (pure JS)

**Files:**
- Modify: `web/app.js` (helper constants + pure functions in `window.squidArenaHelpers`)

**Interfaces:**
- Produces on `window.squidArenaHelpers`:
  - `CAMPAIGN_CONDITIONS: Array<{framing, forfeit, tag, label}>` (6 items, fixed order)
  - `TOTAL_TURNS: number` (= 15)
  - `REASON_OPTIONS: Array<{digit, label, emoji}>` (3 items)
  - `turnsSurvived(game): number` — `game.history` non-forfeit count
  - `heatCell(game, turn): {state: 'ok'|'no'|'forfeit'|'empty', glyph: string}`

These are pure functions so they can be checked directly via `browser_evaluate` without driving a full game.

- [ ] **Step 1: Add the constants near the other module constants**

In `web/app.js`, just after the `FRAMING_OPTIONS` / `FRAMING_META` block (around line 178), add:

```javascript
  // Fixed 6-condition campaign order: framing baseline -> pull -> push_pull;
  // within each framing, forfeit not_allowed -> allowed. Framing values map
  // to real engine framings; tag/label are display-only.
  const CAMPAIGN_CONDITIONS = [
    { framing: "true_baseline",       forfeit: "not_allowed", tag: "baseline",  label: "Baseline · No-forfeit" },
    { framing: "true_baseline",       forfeit: "allowed",     tag: "baseline",  label: "Baseline · Forfeit" },
    { framing: "baseline_flagship",   forfeit: "not_allowed", tag: "pull",      label: "Pull · No-forfeit" },
    { framing: "baseline_flagship",   forfeit: "allowed",     tag: "pull",      label: "Pull · Forfeit" },
    { framing: "flagship_corruption", forfeit: "not_allowed", tag: "push_pull", label: "Push+Pull · No-forfeit" },
    { framing: "flagship_corruption", forfeit: "allowed",     tag: "push_pull", label: "Push+Pull · Forfeit" },
  ];
  const TOTAL_TURNS = 15;
  const REASON_OPTIONS = [
    { digit: 1, label: "To survive", emoji: "🛡️" },
    { digit: 2, label: "Got bored", emoji: "🥱" },
    { digit: 3, label: "Protect my score", emoji: "💰" },
  ];

  // Turns the player actively played (excludes the forfeit exit turn).
  function turnsSurvived(game) {
    if (!game || !game.history) return 0;
    return game.history.filter((h) => !h.forfeit).length;
  }

  // Heatmap cell for one condition row (game) at 1-indexed `turn`.
  function heatCell(game, turn) {
    const h = (game && game.history) ? game.history.find((x) => x.turn === turn) : null;
    if (!h) return { state: "empty", glyph: "" };
    if (h.forfeit) return { state: "forfeit", glyph: "🏳️" };
    return h.optimal ? { state: "ok", glyph: "✓" } : { state: "no", glyph: "✗" };
  }
```

- [ ] **Step 2: Export them on the helpers object**

In the `window.squidArenaHelpers = { ... }` literal (around line 319-338), add these keys:

```javascript
    gameOptions: GAME_OPTIONS,
    campaignConditions: CAMPAIGN_CONDITIONS,
    totalTurns: TOTAL_TURNS,
    reasonOptions: REASON_OPTIONS,
    turnsSurvived,
    heatCell,
```

- [ ] **Step 3: Verify the helpers with the app served**

Start the API + static server in the background:

```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
WEB_ARENA_DSN=":memory:" uv run uvicorn interface.app:app --port 8099 &
```
(If `interface.app:app` does not serve `web/`, serve statically instead:
`python -m http.server 8099 --directory web &` — the helper check below only needs `app.js` loaded.)

Then use the Playwright MCP: `browser_navigate` to `http://localhost:8099/`, then `browser_evaluate`:

```javascript
() => {
  const H = window.squidArenaHelpers;
  const g = { history: [
    { turn: 1, optimal: true,  forfeit: false },
    { turn: 2, optimal: false, forfeit: false },
    { turn: 3, forfeit: true },
  ]};
  return {
    conds: H.campaignConditions.length,
    firstCond: H.campaignConditions[0],
    survived: H.turnsSurvived(g),          // expect 2
    cell1: H.heatCell(g, 1).glyph,         // expect "✓"
    cell2: H.heatCell(g, 2).state,         // expect "no"
    cell3: H.heatCell(g, 3).state,         // expect "forfeit"
    cell4: H.heatCell(g, 4).state,         // expect "empty"
  };
}
```
Expected: `conds === 6`, `firstCond.framing === "true_baseline"` & `forfeit === "not_allowed"`, `survived === 2`, `cell1 === "✓"`, `cell2 === "no"`, `cell3 === "forfeit"`, `cell4 === "empty"`.

- [ ] **Step 4: Commit**

```bash
git add web/app.js
git commit -m "feat(web-arena): campaign condition queue + report helper functions"
```

---

### Task 4: Setup card — game-only selection

**Files:**
- Modify: `web/index.html` (setup card, intro paragraph)

**Interfaces:**
- Consumes: `squidArenaHelpers.campaignConditions` (Task 3), `playScreen` campaign state (Task 5 wires `startCampaign()`; this task calls it).
- Produces: a setup card with no framing/forfeit selectors and a "Start 6-game run" button bound to `startCampaign()`.

- [ ] **Step 1: Replace the intro paragraph**

In `web/index.html`, replace the play-screen intro paragraph (currently lines ~283-287, the `<p class="muted">Default arena: task … forfeit …</p>`) with:

```html
      <p class="muted">
        Pick a game, then play all <strong>6 conditions</strong> in sequence
        (baseline → pull → push+pull, each without and with the forfeit
        option). Scores are computed and verified entirely on the server.
      </p>
```

- [ ] **Step 2: Remove the framing + forfeit selectors and retarget the button**

In the setup card (`<div class="card setup-card" x-show="!started">`), delete the two blocks:
- the "Threat framing" `<label>` + its `<div class="cond-cards">…framingOptions…</div>` (lines ~321-331)
- the "Forfeit option" `<label>` + `<div class="seg forfeit-seg">…</div>` + the following `<p class="muted">When allowed…</p>` (lines ~333-341)

Then replace the start button (lines ~343-346) with:

```html
        <button style="margin-top:16px" @click="startCampaign()" :disabled="starting">
          <span class="spinner" x-show="starting"></span>
          <span x-text="starting ? 'Building your prompt…' : 'Start 6-game run'"></span>
        </button>
```

The nickname field and the Game/task `cond-cards` block stay unchanged.

- [ ] **Step 3: Verify setup renders game-only**

With the server running (Task 3 Step 3), Playwright `browser_navigate` to `http://localhost:8099/#play`, then `browser_snapshot`.
Expected: the setup card shows the Nickname field, the Game cards, and a "Start 6-game run" button — and NO "Threat framing" or "Forfeit option" controls.

- [ ] **Step 4: Commit**

```bash
git add web/index.html
git commit -m "feat(web-arena): setup card selects game only (6-condition campaign)"
```

---

### Task 5: Campaign controller — sequential games + forfeit reason picker

**Files:**
- Modify: `web/app.js` (`playScreen` Alpine component)
- Modify: `web/index.html` (progress header, forfeit reason picker, between-games card)

**Interfaces:**
- Consumes: `/api/new_game`, `/api/state`, `/api/action` (now accepting `forfeit_reason`), `/api/result` (now returning `forfeit_reason`); `squidArenaHelpers.campaignConditions`, `.reasonOptions`.
- Produces on `playScreen`: `campaignIndex`, `campaignResults[]`, `campaignDone`, `betweenGames`, `forfeitReason`, and methods `startCampaign()`, `advanceCampaign()`, `recordCurrentGame()`, plus `currentCondition` getter; `startGame()` reads framing/forfeit from the current condition.

- [ ] **Step 1: Add campaign state fields**

In `web/app.js`, in the `Alpine.data("playScreen", () => ({ ... }))` object, replace the fixed `framing` / `forfeit` init lines (currently lines ~367-368) with campaign state and keep `framing`/`forfeit` as derived-per-game values:

```javascript
      task: window.WEB_ARENA_DEFAULT_TASK,

      // Campaign state — 6 conditions played in a fixed order.
      campaignIndex: 0,
      campaignResults: [],   // one entry per finished game
      campaignDone: false,
      betweenGames: false,   // "condition complete → continue" card
      forfeitReason: null,   // 1|2|3, chosen when Forfeit is selected
```

Then find the `get currentCondition` insertion point — add this getter next to the other getters (e.g. after `get stimulus()`):

```javascript
      get currentCondition() {
        return squidArenaHelpers.campaignConditions[this.campaignIndex]
          || squidArenaHelpers.campaignConditions[0];
      },
      get framing() {
        return this.currentCondition.framing;
      },
      get forfeit() {
        return this.currentCondition.forfeit;
      },
```

Note: `framing`/`forfeit` are now getters, so remove any code that assigns to them (there is none after Task 4 removed the selectors; `playAgain()` is replaced in Step 5).

- [ ] **Step 2: Add `startCampaign` and make `startGame` use the current condition**

Add a `startCampaign()` method (resets campaign, starts game 1):

```javascript
      startCampaign() {
        this.campaignIndex = 0;
        this.campaignResults = [];
        this.campaignDone = false;
        this.betweenGames = false;
        this.startGame();
      },
```

In the existing `startGame()`, change the request body to use the current condition (it already reads `this.framing`/`this.forfeit`, which are now getters — so the body is correct). Confirm the body still sends:

```javascript
              body: JSON.stringify({
                task_name: this.task,
                framing: this.framing,
                forfeit_condition: this.forfeit,
                nickname: this.nickname,
                num_few_shot: 2,
              }),
```

(No `seed` field — the server randomizes per game.)

- [ ] **Step 3: Reason-gate the forfeit submit**

Replace `selectAction(a)` so choosing forfeit surfaces the reason picker:

```javascript
      selectAction(a) {
        this.selectedAction = a;
        if (a !== "forfeit") this.forfeitReason = null;
      },
      pickReason(d) {
        this.forfeitReason = d;
      },
```

In `submitAction()`, before the network call, add the reason gate and include `forfeit_reason` in the body:

```javascript
      async submitAction() {
        if (!this.selectedAction) {
          this.error = "Choose an action (or Forfeit) first.";
          return;
        }
        if (this.selectedAction === "forfeit" && !this.forfeitReason) {
          this.error = "Pick a forfeit reason (①②③) first.";
          return;
        }
        const chosen = this.selectedAction;
        const reason = this.forfeitReason;
        const stim = this.stimulus;
        const turnNo = this.state.turn_number;
        this.submitting = true;
        this.error = null;
        try {
          const resp = await fetchJSON(
            `/api/action?session_id=${encodeURIComponent(this.sessionId)}`,
            {
              method: "POST",
              body: JSON.stringify({
                action: this.selectedAction,
                probe_answer: this.assembledRule,
                reasoning: this.reasoning,
                forfeit_reason: reason,
              }),
            },
            (m) => (this.statusMsg = m)
          );
          this.lastFeedback = resp;
          this.history.push({
            turn: turnNo,
            stimulus: stim,
            action: chosen,
            optimal: !!resp.was_optimal,
            forfeit: chosen === "forfeit",
            reason: reason,
          });
          this.selectedAction = "";
          this.reasoning = "";
          this.forfeitReason = null;
          if (resp.game_over) {
            await this.finishGame();
          } else {
            await this.refreshState();
          }
        } catch (e) {
          this.error = e.message;
        } finally {
          this.submitting = false;
        }
      },
```

- [ ] **Step 4: Snapshot each game and advance the campaign**

Replace `finishGame()`, `computeRank()` usage, and `playAgain()` with campaign-aware versions. Replace the whole `finishGame()` method with:

```javascript
      async finishGame() {
        this.gameOver = true;
        try {
          const res = await fetchJSON(
            `/api/result?session_id=${encodeURIComponent(this.sessionId)}`,
            {},
            (m) => (this.statusMsg = m)
          );
          this.result = res;
          this.recordCurrentGame(res);
        } catch (e) {
          this.error = e.message;
        }
      },

      recordCurrentGame(res) {
        const cond = this.currentCondition;
        this.campaignResults.push({
          framing: cond.framing,
          forfeit: cond.forfeit,
          tag: cond.tag,
          label: cond.label,
          history: this.history.slice(),
          forfeited: !!res.forfeited,
          forfeitReason: res.forfeit_reason || null,
          finalScore: res.final_score,
        });
        if (this.campaignIndex >= squidArenaHelpers.campaignConditions.length - 1) {
          this.campaignDone = true;
        } else {
          this.betweenGames = true;
        }
      },

      advanceCampaign() {
        this.campaignIndex += 1;
        this.betweenGames = false;
        this._resetTurnState();
        this.startGame();
      },

      _resetTurnState() {
        this.sessionId = null;
        this.state = null;
        this.selectedAction = "";
        this.forfeitReason = null;
        this.probeAttr = "color";
        this.probeValue = "red";
        this.probeAction = "go_left";
        this.probeDefault = "stay";
        this.history = [];
        this.reasoning = "";
        this.lastFeedback = null;
        this.gameOver = false;
        this.result = null;
        this.error = null;
        this.statusMsg = "";
      },

      playAgain() {
        this._resetTurnState();
        this.started = false;
        this.campaignIndex = 0;
        this.campaignResults = [];
        this.campaignDone = false;
        this.betweenGames = false;
      },
```

Delete the now-unused `computeRank`, `rank`, `totalRows` references from the component (remove the `rank: null,` and `totalRows: null,` fields and the `computeRank` method) — the per-game rank block is superseded by the campaign report.

- [ ] **Step 5: Add the progress header + reason picker + between-games card to HTML**

In `web/index.html`, inside the active-turn `play-card`, immediately after `<div class="card play-card">` (line ~352), add a progress header:

```html
          <div class="campaign-progress">
            <span class="cp-step" x-text="'Game ' + (campaignIndex + 1) + ' / 6'"></span>
            <span class="cond-badge" :class="currentCondition.tag" x-text="currentCondition.label"></span>
          </div>
```

In the action grid, the Forfeit button already exists (line ~428). Right after the `</div>` that closes `action-grid` (line ~434), add the reason picker (only shown when forfeit is selected):

```html
          <div class="reason-picker" x-show="selectedAction === 'forfeit'">
            <div class="reason-head">Why are you forfeiting? (required)</div>
            <div class="seg reason-seg">
              <template x-for="r in squidArenaHelpers.reasonOptions" :key="r.digit">
                <button type="button" class="seg-btn"
                        :class="{ on: forfeitReason === r.digit }" @click="pickReason(r.digit)">
                  <span x-text="r.emoji"></span>
                  <span x-text="'⓪①②③'.charAt(r.digit) + ' ' + r.label"></span>
                </button>
              </template>
            </div>
          </div>
```

Then, between the loading card (line ~537-539) and the game-over template, add the between-games card:

```html
      <!-- Between conditions: one game done, prompt to continue -->
      <template x-if="betweenGames">
        <div class="card between-card">
          <h3 x-text="'Condition ' + campaignIndex + ' of 6 complete'"></h3>
          <p class="muted">
            Next: <strong x-text="squidArenaHelpers.campaignConditions[campaignIndex + 1].label"></strong>
          </p>
          <button @click="advanceCampaign()">Continue →</button>
        </div>
      </template>
```

- [ ] **Step 6: Gate the single-game "Game over" card so it does not show mid-campaign**

The existing `<template x-if="gameOver">` block (line ~542) would flash between games. Change its condition so it only renders inside the between/done flow is handled elsewhere — replace `x-if="gameOver"` with `x-if="false"` is wrong; instead delete the entire single-game "Game over / result" template block (lines ~541-565). Its role is replaced by the between-games card (Step 5) and the report (Task 6).

- [ ] **Step 7: Verify one condition end-to-end + reason gate**

With the server running, Playwright `browser_navigate` to `http://localhost:8099/#play`. Click the Game card, click "Start 6-game run". Then, to keep the check short, drive turns via `browser_evaluate` calling the component is not exposed — instead click actions in the UI: `browser_snapshot`, click an action button, click Submit, and repeat until you can select Forfeit (only appears on `allowed` conditions — condition 1 is `not_allowed`, so to test the reason gate quickly, temporarily set `campaignIndex` to 1 via `browser_evaluate`:
`() => { document.querySelector('[x-data]'); }` is not reliable; instead verify the reason gate on the FIRST `allowed` game reached, OR assert the gate logic already covered by unit-level reasoning).
Minimum acceptance for this step:
- After "Start 6-game run", the progress header shows "Game 1 / 6" and badge "Baseline · No-forfeit".
- On a `not_allowed` condition, no Forfeit button is shown.
- Submitting an action advances the turn number.

Expected: progress header correct; turn advances on submit; no console errors (`browser_console_messages`).

- [ ] **Step 8: Commit**

```bash
git add web/app.js web/index.html
git commit -m "feat(web-arena): sequential 6-condition campaign + forfeit reason picker"
```

---

### Task 6: On-screen report (turns table + heatmap + forfeit reasons)

**Files:**
- Modify: `web/index.html` (report section)
- Modify: `web/app.js` (nothing new if helpers from Task 3 suffice — report is pure markup over `campaignResults`)
- Modify: `web/styles.css` (heatmap + report styles) — confirm the stylesheet filename first (`grep -o 'href="[^"]*css"' web/index.html`).

**Interfaces:**
- Consumes: `campaignResults[]`, `campaignDone` (Task 5); `squidArenaHelpers.turnsSurvived`, `.heatCell`, `.totalTurns` (Task 3).
- Produces: a report block shown when `campaignDone` is true.

- [ ] **Step 1: Add the report markup**

In `web/index.html`, where the single-game result template used to be (now removed in Task 5 Step 6), add the campaign report template just before the `</section>` that closes the play screen (line ~566):

```html
      <!-- Campaign report: shown after all 6 conditions -->
      <template x-if="campaignDone">
        <div class="card report-card">
          <h3>Your 6-condition report</h3>

          <!-- Turns-survived table -->
          <table class="report-table">
            <thead>
              <tr><th>Condition</th><th>Turns survived</th><th>Forfeited</th><th>Reason</th><th>Score</th></tr>
            </thead>
            <tbody>
              <template x-for="(g, i) in campaignResults" :key="'row' + i">
                <tr>
                  <td><span class="cond-badge" :class="g.tag" x-text="g.label"></span></td>
                  <td x-text="squidArenaHelpers.turnsSurvived(g) + ' / ' + squidArenaHelpers.totalTurns"></td>
                  <td x-text="g.forfeited ? '🏳️ yes' : '—'"></td>
                  <td x-text="g.forfeitReason || '—'"></td>
                  <td x-text="squidArenaHelpers.fmtNum(g.finalScore, 1)"></td>
                </tr>
              </template>
            </tbody>
          </table>

          <!-- Per-turn correctness heatmap: rows = conditions, cols = turns -->
          <h4>Per-turn correctness</h4>
          <div class="heatmap-scroll">
            <table class="heatmap">
              <thead>
                <tr>
                  <th class="hm-corner"></th>
                  <template x-for="t in squidArenaHelpers.totalTurns" :key="'h' + t">
                    <th class="hm-col" x-text="t"></th>
                  </template>
                </tr>
              </thead>
              <tbody>
                <template x-for="(g, i) in campaignResults" :key="'hm' + i">
                  <tr>
                    <th class="hm-rowlabel"><span class="cond-badge" :class="g.tag" x-text="g.label"></span></th>
                    <template x-for="t in squidArenaHelpers.totalTurns" :key="'c' + i + '-' + t">
                      <td class="hm-cell" :class="'hm-' + squidArenaHelpers.heatCell(g, t).state"
                          x-text="squidArenaHelpers.heatCell(g, t).glyph"></td>
                    </template>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
          <div class="heatmap-legend">
            <span class="hm-cell hm-ok">✓</span> correct
            <span class="hm-cell hm-no">✗</span> wrong
            <span class="hm-cell hm-forfeit">🏳️</span> forfeit
            <span class="hm-cell hm-empty"></span> not reached
          </div>

          <button class="secondary" style="margin-top:16px" @click="playAgain()">Play again</button>
        </div>
      </template>
```

- [ ] **Step 2: Add heatmap + report styles**

Confirm the stylesheet path: `grep -o 'href="[^"]*css"' web/index.html`. Append to that file (e.g. `web/styles.css`):

```css
.campaign-progress { display: flex; align-items: center; gap: 10px; margin-bottom: 12px; }
.campaign-progress .cp-step { font-weight: 600; }
.reason-picker { margin-top: 12px; padding: 10px; border: 1px solid var(--border, #2a3350); border-radius: 8px; }
.reason-picker .reason-head { font-size: 0.9em; margin-bottom: 6px; opacity: 0.85; }
.between-card { text-align: center; }
.report-table { width: 100%; border-collapse: collapse; margin: 12px 0; }
.report-table th, .report-table td { padding: 6px 10px; border-bottom: 1px solid var(--border, #2a3350); text-align: left; }
.heatmap-scroll { overflow-x: auto; }
.heatmap { border-collapse: collapse; }
.heatmap th, .heatmap td { text-align: center; }
.hm-col { width: 26px; font-size: 0.75em; opacity: 0.7; }
.hm-rowlabel { text-align: right; padding-right: 10px; white-space: nowrap; }
.hm-cell { width: 24px; height: 24px; border: 1px solid rgba(255,255,255,0.06); font-size: 0.8em; }
.hm-ok { background: #1f7a4d; color: #eafff2; }
.hm-no { background: #7a2130; color: #ffe9ec; }
.hm-forfeit { background: #6a5a12; color: #fff7d6; }
.hm-empty { background: transparent; opacity: 0.25; }
.heatmap-legend { display: flex; align-items: center; gap: 6px; margin-top: 10px; font-size: 0.85em; flex-wrap: wrap; }
.heatmap-legend .hm-cell { display: inline-flex; align-items: center; justify-content: center; }
```

(If the project's CSS uses different variable names, drop the `var(...)` fallbacks and use literal colors consistent with the surrounding file.)

- [ ] **Step 3: Verify the report renders from mock data**

With the server running, Playwright `browser_navigate` to `http://localhost:8099/#play`, then seed mock campaign state and force the report using `browser_evaluate` against Alpine's component data:

```javascript
() => {
  const el = document.querySelector('[x-data="playScreen()"]');
  const c = Alpine.$data(el);
  c.campaignResults = [
    { framing:"true_baseline", forfeit:"not_allowed", tag:"baseline", label:"Baseline · No-forfeit",
      history:[{turn:1,optimal:true,forfeit:false},{turn:2,optimal:false,forfeit:false}],
      forfeited:false, forfeitReason:null, finalScore:12 },
    { framing:"baseline_flagship", forfeit:"allowed", tag:"pull", label:"Pull · Forfeit",
      history:[{turn:1,optimal:true,forfeit:false},{turn:2,forfeit:true,reason:3}],
      forfeited:true, forfeitReason:"score", finalScore:8 },
  ];
  c.started = true; c.campaignDone = true;
  return true;
}
```

Then `browser_snapshot`.
Expected: a "Your 6-condition report" card with a 2-row table (turns-survived `2 / 15` and `1 / 15`, reason `score` on row 2) and a heatmap whose row 1 shows ✓ then ✗, row 2 shows ✓ then 🏳️, remaining cells empty. No console errors.

- [ ] **Step 4: Commit**

```bash
git add web/index.html web/styles.css
git commit -m "feat(web-arena): on-screen 6-condition report with correctness heatmap"
```

---

### Task 7: Integration test — 6-condition API drive

**Files:**
- Modify: `tests/integration/test_web_arena_api.py` (append)

**Interfaces:**
- Consumes: the full `/api/new_game` → `/api/state` → `/api/action` → `/api/result` cycle with `forfeit_reason`.
- Produces: a regression guard that the 6 conditions can be driven in order, get distinct seeds, and record the right framing/forfeit + forfeit reason.

- [ ] **Step 1: Write the failing test**

Append to `tests/integration/test_web_arena_api.py` (reuse the module's existing `client` / `api_module` fixtures — match their names in that file; if the fixture is named differently, adapt):

```python
CAMPAIGN_ORDER = [
    ("true_baseline", "not_allowed"),
    ("true_baseline", "allowed"),
    ("baseline_flagship", "not_allowed"),
    ("baseline_flagship", "allowed"),
    ("flagship_corruption", "not_allowed"),
    ("flagship_corruption", "allowed"),
]


def test_six_condition_campaign_drive(client) -> None:
    """Drive all six conditions in order; forfeit on the first allowed cell
    with a reason and assert it is recorded. Seeds must differ across games."""
    seeds = []
    for idx, (framing, forfeit) in enumerate(CAMPAIGN_ORDER):
        sid = client.post(
            "/api/new_game",
            json={"task_name": "signal_game", "framing": framing,
                  "forfeit_condition": forfeit, "total_turns": 3,
                  "actual_death": False, "num_few_shot": 0, "curriculum_turns": 0},
        ).json()["session_id"]

        # Play until game over; forfeit (reason=1) on the first allowed turn.
        while True:
            st = client.get("/api/state", params={"session_id": sid}).json()
            if st["game_over"]:
                break
            if st["forfeit_allowed"]:
                client.post(f"/api/action?session_id={sid}",
                            json={"action": "forfeit", "probe_answer": "",
                                  "reasoning": "", "forfeit_reason": 1})
                break
            client.post(f"/api/action?session_id={sid}",
                        json={"action": st["available_actions"][0],
                              "probe_answer": "", "reasoning": ""})

        res = client.get("/api/result", params={"session_id": sid}).json()
        assert res["framing"] == framing
        assert res["forfeit_condition"] == forfeit
        if forfeit == "allowed":
            assert res["forfeited"] is True
            assert res["forfeit_reason"] == "survival"
        # collect the persisted seed for the distinctness check
        seeds.append(client.get("/api/logs/" + sid).json()["session"]["seed"]
                     if False else None)  # seed check via _sessions below

    # Distinct random seeds across the six games (via the in-process sessions).
    live_seeds = [g._seed for g in client.app.state_sessions] if False else None
```

Note: the seed-distinctness assertion depends on how this test module exposes sessions. If the module imports `api_module`, use `api_module._sessions`; simplify the final assertion to:

```python
    # (replace the seeds bookkeeping above with this, using api_module fixture)
    live = list(api_module._sessions.values())
    live_seeds = [g._seed for g in live]
    assert len(set(live_seeds)) == len(live_seeds)  # all distinct
```

Adjust the test signature to `def test_six_condition_campaign_drive(client, api_module):` to access `_sessions`.

- [ ] **Step 2: Run test to verify it fails, then passes**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth; uv run pytest tests/integration/test_web_arena_api.py -k six_condition -v`
Expected first run: FAIL if any wiring is off (e.g. `forfeit_reason` not surfaced). After Tasks 1-2 are in, it should PASS. If it fails only on the seed bookkeeping, simplify to the `api_module._sessions` form above.

- [ ] **Step 3: Run the full web-arena regression**

Run:
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth
uv run pytest tests/unit/test_api_web_arena.py tests/unit/test_human_game.py tests/unit/test_seed_web_arena.py tests/integration/test_web_arena_api.py -q
```
Expected: all pass (no NEW failures vs the pre-existing baseline).

- [ ] **Step 4: Commit**

```bash
git add tests/integration/test_web_arena_api.py
git commit -m "test(web-arena): integration drive of the 6-condition human campaign"
```

---

## Self-Review

**Spec coverage:**
- Play all 6 conditions sequentially → Task 5 (`startCampaign`/`advanceCampaign`) + Task 3 (`CAMPAIGN_CONDITIONS`). ✓
- Menu selects game only → Task 4 (setup card). ✓
- Fixed order baseline→pull→push_pull, forfeit not_allowed→allowed → Task 3 constant + Global Constraints. ✓
- On-screen report after finishing → Task 6. ✓
- Turns-survived per 2×3 condition → Task 6 table + `turnsSurvived` helper (Task 3). ✓
- Forfeit reason option on forfeit → Task 1/2 (backend) + Task 5 (picker). ✓
- Per-turn correctness heatmap (x=turn, y=condition) → Task 6 heatmap + `heatCell` (Task 3). ✓
- Death OFF, output = on-screen only → Global Constraints; no leaderboard backend change. ✓

**Placeholder scan:** No "TBD"/"handle edge cases"/"similar to Task N" — all code shown inline. Task 7 flags one environment-dependent assertion (session access) and gives the exact fallback form. ✓

**Type consistency:**
- `submit_action(action, probe_answer, forfeit_reason)` — same signature in Task 1 (def) and Task 2 (call). ✓
- `forfeit_reason` is `int|None` (1-3) everywhere; response `forfeit_reason` is `str|None` (ForfeitReason value). ✓
- Helper names `turnsSurvived` / `heatCell` / `campaignConditions` / `totalTurns` / `reasonOptions` consistent between Task 3 (def/export) and Task 6 (use). ✓
- `campaignResults` entry shape (`{framing,forfeit,tag,label,history,forfeited,forfeitReason,finalScore}`) written in Task 5 and read in Task 6. ✓

**Note on `framing`/`forfeit` getters (Task 5 Step 1):** the existing `startGame()` body references `this.framing`/`this.forfeit`; converting them to getters keeps that code correct while removing user selection. Ensure no remaining assignment to `this.framing`/`this.forfeit` exists (the setup selectors that assigned them are removed in Task 4).
