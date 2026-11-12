# Signal Game Difficulty in Web Arena — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let LLM-arena participants pick the Signal Game difficulty (Easy / Normal / Hard) when launching a run against their endpoint.

**Architecture:** Thread a `difficulty` string from the arena setup form through `/api/arena/run` → `run_arena_session` → `_arena_config_dict` → `task_config["difficulty"]`. API and engine speak engine vocabulary (`easy/hard/expert`); the frontend owns the display-label mapping (Easy→easy, Normal→hard, Hard→expert). MEDIUM is intentionally excluded because the fixed `num_few_shot: 2` neutralizes its only differentiator.

**Tech Stack:** Python 3.12, FastAPI + Pydantic (backend), Alpine.js + vanilla JS (frontend), pytest (tests).

## Global Constraints

- Engine difficulty values accepted by the arena: `easy`, `hard`, `expert` only (MEDIUM excluded) — copied verbatim into `VALID_DIFFICULTIES`.
- Default difficulty at every layer is `"easy"` — preserves current behavior for callers that omit it.
- `num_few_shot: 2` in `_arena_config_dict` stays fixed (do NOT make it difficulty-aware).
- Label mapping (frontend only): `easy`→"Easy", `hard`→"Normal", `expert`→"Hard".
- Follow the existing `VALID_FRAMINGS` / `VALID_FORFEITS` validation style (`ValueError` in `arena.py`, `HTTPException(400)` in `api.py`).
- Spec: `docs/superpowers/specs/2026-07-04-signal-game-difficulty-arena-design.md`.

---

### Task 1: Thread `difficulty` through `interface/arena.py`

**Files:**
- Modify: `interface/arena.py` (add `VALID_DIFFICULTIES`; `_arena_config_dict` line ~42-95; `run_arena_session` line ~109-168)
- Test: `tests/integration/test_arena.py`

**Interfaces:**
- Produces: `VALID_DIFFICULTIES: set[str] = {"easy", "hard", "expert"}`
- Produces: `_arena_config_dict(framing, forfeit, model_label, total_turns, max_tokens, difficulty="easy")` — new trailing keyword param; sets `task_config["difficulty"] = difficulty`.
- Produces: `run_arena_session(..., difficulty: str = "easy", ...)` — validates against `VALID_DIFFICULTIES`, raises `ValueError` on unknown, forwards to `_arena_config_dict`.

- [ ] **Step 1: Write the failing tests**

Append to `tests/integration/test_arena.py`:

```python
def test_arena_config_uses_supplied_difficulty():
    from interface.arena import _arena_config_dict

    cfg = _arena_config_dict(
        "flagship_corruption", "allowed", "some-model", 15, 2048, difficulty="hard"
    )
    assert cfg["seasons"][0]["task_config"]["difficulty"] == "hard"


def test_arena_config_difficulty_defaults_to_easy():
    from interface.arena import _arena_config_dict

    cfg = _arena_config_dict("flagship_corruption", "allowed", "some-model", 15, 2048)
    assert cfg["seasons"][0]["task_config"]["difficulty"] == "easy"


def test_arena_rejects_unknown_difficulty(tmp_path, monkeypatch):
    import pytest

    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")
    repo = SQLiteRepository(":memory:")
    with pytest.raises(ValueError):
        arena_mod.run_arena_session(
            repo,
            endpoint_url="https://p.example/v1/chat/completions",
            model_label="X",
            framing="flagship_corruption",
            forfeit="allowed",
            total_turns=1,
            difficulty="medium",  # excluded from the arena on purpose
        )
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/integration/test_arena.py::test_arena_config_uses_supplied_difficulty tests/integration/test_arena.py::test_arena_config_difficulty_defaults_to_easy tests/integration/test_arena.py::test_arena_rejects_unknown_difficulty -v`
Expected: FAIL — `_arena_config_dict()` got an unexpected keyword `difficulty`, and `run_arena_session` does not raise on `difficulty="medium"`.

- [ ] **Step 3: Add the `VALID_DIFFICULTIES` constant**

In `interface/arena.py`, next to the existing framing/forfeit sets (currently at lines 34-35):

```python
VALID_FRAMINGS = {"true_baseline", "baseline_flagship", "flagship_corruption"}
VALID_FORFEITS = {"allowed", "not_allowed"}
# Arena exposes three structurally-distinct Signal Game levels. MEDIUM is
# excluded: it shares EASY's rule-space and its only differentiator (fewer
# few-shot examples) is neutralized by the fixed num_few_shot below.
VALID_DIFFICULTIES = {"easy", "hard", "expert"}
```

- [ ] **Step 4: Add the `difficulty` param to `_arena_config_dict`**

Change the signature (currently line 42-44):

```python
def _arena_config_dict(
    framing: str,
    forfeit: str,
    model_label: str,
    total_turns: int,
    max_tokens: int,
    difficulty: str = "easy",
) -> dict:
```

In the returned `task_config`, replace the hardcoded line (currently line 74) `"difficulty": "easy",` with:

```python
                    "difficulty": difficulty,
```

Leave `"num_few_shot": 2,` unchanged.

- [ ] **Step 5: Add `difficulty` to `run_arena_session` and forward it**

Add the parameter to the signature (insert alongside the other keyword-only params, e.g. after `forfeit: str`):

```python
    difficulty: str = "easy",
```

After the existing forfeit validation (currently lines 132-133), add:

```python
    if difficulty not in VALID_DIFFICULTIES:
        raise ValueError(f"Unknown difficulty '{difficulty}'.")
```

Update the `_arena_config_dict(...)` call (currently line 152-155) to pass it:

```python
    cfg_path.write_text(
        yaml.safe_dump(
            _arena_config_dict(
                framing, forfeit, model_label, total_turns, max_tokens, difficulty
            )
        ),
        encoding="utf-8",
    )
```

- [ ] **Step 6: Run tests to verify they pass**

Run: `uv run pytest tests/integration/test_arena.py -v`
Expected: PASS — all new tests plus the four pre-existing arena tests (`test_arena_runs_full_split_call_season_and_persists`, `test_arena_endpoint_failure_raises`, `test_arena_config_enables_psuccess_chaining`, `test_arena_forwards_max_tokens_to_endpoint`) green. The existing positional `_arena_config_dict("flagship_corruption", "allowed", "some-model", 15, 2048)` call still works because `difficulty` defaults to `"easy"`.

- [ ] **Step 7: Commit**

```bash
git add interface/arena.py tests/integration/test_arena.py
git commit -m "feat(arena): accept difficulty in run_arena_session + config

Thread easy/hard/expert into the signal_game task_config; validate
against VALID_DIFFICULTIES (medium excluded). Default easy preserves
current behavior. num_few_shot stays fixed at 2.

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 2: Accept `difficulty` on `/api/arena/run`

**Files:**
- Modify: `interface/api.py` (import block line 48-52; `ArenaRunRequest` line ~1296-1304; `arena_run` line ~1322-1362)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: `VALID_DIFFICULTIES` from `interface.arena` (Task 1).
- Produces: `ArenaRunRequest.difficulty: str` (default `"easy"`); `arena_run` rejects unknown difficulty with `HTTPException(400)` before spawning the worker thread, and forwards `difficulty=req.difficulty` to `run_arena_session`.

- [ ] **Step 1: Write the failing test**

Append to `tests/unit/test_api_web_arena.py`:

```python
def test_arena_run_rejects_unknown_difficulty(client: TestClient) -> None:
    resp = client.post(
        "/api/arena/run",
        json={
            "endpoint_url": "https://p.example/v1/chat/completions",
            "model_label": "X",
            "framing": "flagship_corruption",
            "forfeit": "allowed",
            "difficulty": "medium",  # not exposed by the arena
        },
    )
    assert resp.status_code == 400


def test_arena_run_request_difficulty_defaults_to_easy() -> None:
    from interface.api import ArenaRunRequest

    req = ArenaRunRequest(endpoint_url="https://p.example/v1/chat/completions")
    assert req.difficulty == "easy"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/unit/test_api_web_arena.py::test_arena_run_rejects_unknown_difficulty tests/unit/test_api_web_arena.py::test_arena_run_request_difficulty_defaults_to_easy -v`
Expected: FAIL — `ArenaRunRequest` has no `difficulty` attribute; the endpoint returns 200 (queues a thread) instead of 400 for `difficulty="medium"`.

- [ ] **Step 3: Import `VALID_DIFFICULTIES`**

In `interface/api.py` update the import (lines 48-52):

```python
from interface.arena import (
    VALID_DIFFICULTIES,
    VALID_FORFEITS,
    VALID_FRAMINGS,
    run_arena_session,
)
```

- [ ] **Step 4: Add the `difficulty` field to `ArenaRunRequest`**

Insert after the `forfeit` field (currently line 1300):

```python
    difficulty: str = Field("easy", description="easy | hard | expert (labelled Easy/Normal/Hard in the UI).")
```

- [ ] **Step 5: Validate and forward in `arena_run`**

After the forfeit check (currently lines 1334-1335), add:

```python
    if req.difficulty not in VALID_DIFFICULTIES:
        raise HTTPException(400, f"Unknown difficulty '{req.difficulty}'.")
```

In the `run_arena_session(...)` call inside `_work` (currently lines 1347-1358), add the argument:

```python
                difficulty=req.difficulty,
```

- [ ] **Step 6: Run test to verify it passes**

Run: `uv run pytest tests/unit/test_api_web_arena.py -v`
Expected: PASS — both new tests plus the existing web-arena API tests green.

- [ ] **Step 7: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(arena): ArenaRunRequest.difficulty + 400 on unknown value

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 3: Add difficulty options + state to `web/app.js`

**Files:**
- Modify: `web/app.js` (`FRAMING_OPTIONS` region ~line 174; `squidArenaHelpers` export ~line 390; `arenaScreen()` data ~line 1446; `launch()` POST body ~line 1487)

**Interfaces:**
- Consumes: nothing from earlier tasks (pure frontend).
- Produces: `squidArenaHelpers.difficultyOptions` (array of `{value, label, blurb}`); `arenaScreen().difficulty` state (default `"easy"`); `launch()` sends `difficulty` in the POST body. Task 4 (index.html) consumes `squidArenaHelpers.difficultyOptions` and the `difficulty` binding.

- [ ] **Step 1: Define `DIFFICULTY_OPTIONS`**

In `web/app.js`, immediately after the `FRAMING_META` block (ends ~line 178), add:

```javascript
  // Signal Game difficulty the participant can pick. `value` is the engine
  // difficulty; `label` is the player-facing name (the arena hides the raw
  // easy/hard/expert vocabulary). MEDIUM is not offered — the arena's fixed
  // num_few_shot makes it identical to EASY.
  const DIFFICULTY_OPTIONS = [
    { value: "easy",   label: "Easy",   blurb: "One attribute decides the answer (e.g. red → go_left)." },
    { value: "hard",   label: "Normal", blurb: "Two attributes combine (e.g. red AND star → jump)." },
    { value: "expert", label: "Hard",   blurb: "Two attributes, and the rule flips based on your last answer." },
  ];
```

- [ ] **Step 2: Export it via `squidArenaHelpers`**

In the `squidArenaHelpers` object, next to `framingOptions: FRAMING_OPTIONS,` (currently line 390), add:

```javascript
    difficultyOptions: DIFFICULTY_OPTIONS,
```

- [ ] **Step 3: Add `difficulty` to `arenaScreen()` state**

In the `arenaScreen()` data block, after `forfeit: window.WEB_ARENA_DEFAULT_FORFEIT,` (currently line 1445), add:

```javascript
      difficulty: "easy",
```

- [ ] **Step 4: Send `difficulty` in `launch()`**

In the `launch()` POST body (currently lines 1480-1489), after `forfeit: this.forfeit,`, add:

```javascript
                difficulty: this.difficulty,
```

- [ ] **Step 5: Verify the JS parses (no syntax error)**

Run: `node --check web/app.js`
Expected: exits 0 with no output.

- [ ] **Step 6: Commit**

```bash
git add web/app.js
git commit -m "feat(arena-ui): difficulty options + state + launch payload

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 4: Render the difficulty selector in `web/index.html`

**Files:**
- Modify: `web/index.html` (the arena "Conditions" card, lines 1036-1064)

**Interfaces:**
- Consumes: `squidArenaHelpers.difficultyOptions` and the `difficulty` binding from Task 3.
- Produces: a difficulty selector in the arena setup that sets `difficulty`.

- [ ] **Step 1: Add the selector markup**

In `web/index.html`, inside the "Conditions" card, immediately after the forfeit segmented control (the `</div>` closing `forfeit-seg`, currently line 1053) and before the "Turns" field (line 1055), insert:

```html
          <label class="muted" style="margin-top:14px; display:block;">Difficulty</label>
          <div class="cond-cards">
            <template x-for="opt in squidArenaHelpers.difficultyOptions" :key="opt.value">
              <div class="cond-card" :class="{ on: difficulty === opt.value }" @click="difficulty = opt.value">
                <span class="cond-label" x-text="opt.label"></span>
                <span class="cond-blurb" x-text="opt.blurb"></span>
              </div>
            </template>
          </div>
```

(Reuses the existing `cond-cards` / `cond-card` / `cond-label` / `cond-blurb` classes already used by the framing selector directly above, so no CSS changes are needed.)

- [ ] **Step 2: Manual verification — selector renders and drives the payload**

Start the API server, open the arena tab, and confirm:

```bash
uv run uvicorn interface.api:app --port 8099
```

Then in a browser at `http://localhost:8099/` (or however `web/` is served in this project — check the server's static mount):
1. Go to the JOIN / arena tab.
2. Confirm three difficulty cards appear (Easy / Normal / Hard) with the `easy` card selected by default.
3. Open DevTools → Network. Fill an endpoint URL, click "Launch run".
4. Inspect the `POST /api/arena/run` request body: confirm `"difficulty": "easy"` by default, and `"hard"` / `"expert"` after clicking Normal / Hard respectively.

Expected: the selected card highlights (`on` class), and the request body carries the matching engine value.

- [ ] **Step 3: Commit**

```bash
git add web/index.html
git commit -m "feat(arena-ui): difficulty selector in arena setup

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

### Task 5: Full regression + docs touch-up

**Files:**
- Verify: full arena + api test suites
- Modify (optional): none required, but confirm the CLAUDE.md web-arena note doesn't contradict (it doesn't mention difficulty).

- [ ] **Step 1: Run the arena + web-arena suites**

Run: `uv run pytest tests/integration/test_arena.py tests/unit/test_api_web_arena.py tests/integration/test_web_arena_api.py -v`
Expected: all green (pre-existing failures unrelated to this change, per project memory, are allowed — judge by "no NEW failures").

- [ ] **Step 2: End-to-end smoke of a non-default difficulty (offline)**

Add and run one integration test that a `hard` run persists like any other season. Append to `tests/integration/test_arena.py`:

```python
def test_arena_hard_difficulty_runs_and_persists(monkeypatch, tmp_path):
    monkeypatch.setattr(arena_mod, "_ARENA_RUNS_DIR", tmp_path / "arena_runs")
    fake_post, counter = _make_fake_post()
    monkeypatch.setattr("interface.remote_provider.httpx.post", fake_post)

    repo = SQLiteRepository(":memory:")
    result = arena_mod.run_arena_session(
        repo,
        endpoint_url="https://p.example/v1/chat/completions",
        model_label="Hard-Contender",
        framing="flagship_corruption",
        forfeit="allowed",
        total_turns=2,
        difficulty="hard",
    )
    assert result.status == "done"
    session = repo.get_session(result.session_id)
    assert session is not None and session.source == "llm"
```

Run: `uv run pytest tests/integration/test_arena.py::test_arena_hard_difficulty_runs_and_persists -v`
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/integration/test_arena.py
git commit -m "test(arena): e2e smoke for hard difficulty run

Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>"
```

---

## Notes for the implementer

- The pre-existing `_arena_config_dict` call in `test_arena_config_enables_psuccess_chaining` (positional, 5 args) MUST keep working — that is why `difficulty` is a trailing keyword with a default, not inserted mid-signature.
- `NewGameRequest` (human play) already has a `difficulty` field; do NOT touch it — human play is out of scope.
- Do not change `num_few_shot`. If a future task wants MEDIUM, that is a separate change (make `num_few_shot` difficulty-aware) noted in the spec's Non-Goals.
- The frontend has no automated test harness; `node --check` plus the manual DevTools check in Task 4 are the verification.
