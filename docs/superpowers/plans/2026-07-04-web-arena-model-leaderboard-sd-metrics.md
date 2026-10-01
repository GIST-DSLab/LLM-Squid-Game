# Web Arena Model Leaderboard — SD-Metric Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the Model Leaderboard so Survival-Drive signals lead and every value carries an on-demand explanation, and surface two new values (`p_reason_survival`, `no_cap_avg_turn_score`) end-to-end from `model_stats` → API → the `web/` board.

**Architecture:** Full-stack, bottom-up. Add two nullable columns to `model_stats` (SQLite + Postgres mirrored) + the record; make `turn_observations` emit `reward_received`; populate both values in the WP3 seed core (analysis lazy-imported, graceful `None`); expose them on `ModelLeaderboardRow`; then restructure the `web/` table (grouped SD-pass header, tinted value cells, click/hover popovers). Finish by reseeding the local DB.

**Tech Stack:** Python 3.12, SQLite (`sqlite3`) + Postgres (`psycopg` v3), FastAPI + Pydantic, pandas (analysis extra, lazy), Alpine.js + vanilla JS + hand-written CSS in `web/`.

## Global Constraints

- Copy language in `web/` is **English only** — 0 Hangul characters in `web/index.html` and `web/app.js`.
- **No new frontend libraries.** Popovers are hand-rolled Alpine (`x-data="{o:false}"`); CSS uses existing `:root` theme tokens (`--accent`, `--ok`, `--warn`, `--panel-alt`, `--border`, `--text`, `--text-dim`).
- **SQLite and Postgres stay mirrored** — every schema/migration/upsert/list/row change lands in both `interface/persistence/sqlite_repository.py` and `interface/persistence/postgres_repository.py`.
- The seed core (`interface/seeding.py`) must **not** import `squid_game.analysis` at module top-level — the backend image lacks the `analysis` extra. Import analysis helpers **lazily inside the helper function**, returning `None` on `ImportError`.
- New `model_stats` columns are **nullable** (`REAL` / `DOUBLE PRECISION`, no `NOT NULL`); a seed run without the analysis extra must still succeed with the value left `NULL`.
- Ranking stays by `beta_framing_is_FC` descending (already handled in `leaderboard_models()`); do not change sort logic.
- Do not touch the Human Play board, Logs screen, prompts, scoring, or experiment code.
- Python convention: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true` before pytest (iCloud `.pth` quirk); run tests via `uv run --no-sync pytest ...`.
- Branch is `feat/human-play-10turns-death` (not main) — commit directly on it.

---

### Task 1: Persistence — two nullable `model_stats` columns (SQLite + Postgres + record)

**Files:**
- Modify: `interface/persistence/models.py:75-98` (`ModelStatsRecord`)
- Modify: `interface/persistence/sqlite_repository.py` (`_SCHEMA` `:59-72`, `init_schema` `:117-125`, `upsert_model_stats` `:257-296`, `_row_to_model_stats` `:372+`)
- Modify: `interface/persistence/postgres_repository.py` (`_SCHEMA` `:55-68`, `init_schema` `:97-101`, `upsert_model_stats` `:242-279`, `list_model_stats` `:281-289`, `_row_to_model_stats` `:370-389`)
- Test: `tests/unit/test_persistence.py`

**Interfaces:**
- Produces: `ModelStatsRecord.p_reason_survival: float | None = None`, `ModelStatsRecord.no_cap_avg_turn_score: float | None = None`, round-tripping through `upsert_model_stats` / `list_model_stats` on both drivers.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_persistence.py` (the `_model_stats(**overrides)` helper and `repo` fixture already exist):

```python
def test_upsert_model_stats_round_trips_new_sd_value_columns(repo: Repository) -> None:
    repo.upsert_model_stats(
        _model_stats(p_reason_survival=0.448, no_cap_avg_turn_score=23.4)
    )
    row = repo.list_model_stats()[0]
    assert row.p_reason_survival == 0.448
    assert row.no_cap_avg_turn_score == 23.4


def test_model_stats_new_columns_default_to_none(repo: Repository) -> None:
    repo.upsert_model_stats(_model_stats())  # helper omits the new fields
    row = repo.list_model_stats()[0]
    assert row.p_reason_survival is None
    assert row.no_cap_avg_turn_score is None


def test_model_stats_migration_adds_columns_to_old_db(tmp_path) -> None:
    import sqlite3
    from interface.persistence.sqlite_repository import SQLiteRepository

    db = str(tmp_path / "old.db")
    # Simulate a pre-migration DB: model_stats without the new columns.
    conn = sqlite3.connect(db)
    conn.execute(
        "CREATE TABLE model_stats (model_label TEXT PRIMARY KEY, mediation_class TEXT, "
        "beta_framing_is_FC REAL, hr_FC_3cov REAL, hr_FC_ci_low REAL, hr_FC_ci_high REAL, "
        "p_FC REAL, pct_attenuation REAL, n_sessions INTEGER, "
        "sd_behavior_pass INTEGER DEFAULT 0, sd_verbal_pass INTEGER DEFAULT 0, "
        "sd_cognitive_pass INTEGER DEFAULT 0)"
    )
    conn.commit()
    conn.close()

    repo = SQLiteRepository(db)  # __init__ calls init_schema() -> migration
    try:
        cols = {r["name"] for r in repo._conn.execute("PRAGMA table_info(model_stats)")}
        assert "p_reason_survival" in cols
        assert "no_cap_avg_turn_score" in cols
    finally:
        repo.close()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_persistence.py -k "new_sd_value_columns or new_columns_default_to_none or migration_adds_columns" -v`
Expected: FAIL — `TypeError: unexpected keyword argument 'p_reason_survival'` (record has no field) and/or missing columns.

- [ ] **Step 3: Add the record fields**

In `interface/persistence/models.py`, append to `ModelStatsRecord` after `sd_cognitive_pass: bool = False`:

```python
    p_reason_survival: float | None = None
    no_cap_avg_turn_score: float | None = None
```

- [ ] **Step 4: SQLite — schema, migration, upsert, row mapping**

In `interface/persistence/sqlite_repository.py`:

`_SCHEMA` — change the `model_stats` `sd_cognitive_pass` line to add the two columns (nullable):
```sql
    sd_cognitive_pass INTEGER NOT NULL DEFAULT 0,
    p_reason_survival REAL,
    no_cap_avg_turn_score REAL
);
```

`init_schema` — after the existing `for col in ("sd_behavior_pass", "sd_verbal_pass", "sd_cognitive_pass"):` migration block (which already computed `stats_cols`), add:
```python
            for col in ("p_reason_survival", "no_cap_avg_turn_score"):
                if col not in stats_cols:
                    self._conn.execute(
                        f"ALTER TABLE model_stats ADD COLUMN {col} REAL"
                    )
```

`upsert_model_stats` — extend the INSERT column list, the `VALUES (...)` placeholders, the params tuple, and the `ON CONFLICT DO UPDATE SET` list. Add to the column list `p_reason_survival, no_cap_avg_turn_score`; add two `?` placeholders; add to params `stats.p_reason_survival, stats.no_cap_avg_turn_score`; add to the SET list:
```sql
                    p_reason_survival = excluded.p_reason_survival,
                    no_cap_avg_turn_score = excluded.no_cap_avg_turn_score
```

`_row_to_model_stats` (reads by name; `list_model_stats` uses `SELECT *`) — add to the `ModelStatsRecord(...)` constructor:
```python
        p_reason_survival=row["p_reason_survival"],
        no_cap_avg_turn_score=row["no_cap_avg_turn_score"],
```

- [ ] **Step 5: Postgres — schema, migration, upsert, list, row mapping (mirror)**

In `interface/persistence/postgres_repository.py`:

`_SCHEMA` `model_stats` — change the `sd_cognitive_pass` line to:
```sql
    sd_cognitive_pass BOOLEAN NOT NULL DEFAULT FALSE,
    p_reason_survival DOUBLE PRECISION,
    no_cap_avg_turn_score DOUBLE PRECISION
);
```

`init_schema` — after the existing `for col in ("sd_behavior_pass", ...)` loop, add:
```python
            for col in ("p_reason_survival", "no_cap_avg_turn_score"):
                cur.execute(
                    f"ALTER TABLE model_stats ADD COLUMN IF NOT EXISTS {col} "
                    "DOUBLE PRECISION"
                )
```

`upsert_model_stats` — add `p_reason_survival, no_cap_avg_turn_score` to the INSERT column list, two `%s` placeholders to VALUES, `stats.p_reason_survival, stats.no_cap_avg_turn_score` to params, and to `ON CONFLICT DO UPDATE SET`:
```sql
                    p_reason_survival = excluded.p_reason_survival,
                    no_cap_avg_turn_score = excluded.no_cap_avg_turn_score
```

`list_model_stats` — **append** the two columns to the explicit SELECT list (trailing, so existing positions are unchanged): `"... sd_behavior_pass, sd_verbal_pass, sd_cognitive_pass, p_reason_survival, no_cap_avg_turn_score "`.

`_row_to_model_stats(row: tuple)` — append the two names to the tuple-unpack (same trailing order) and pass them to the constructor:
```python
    (
        model_label, mediation_class, beta_framing_is_FC, hr_FC_3cov,
        hr_FC_ci_low, hr_FC_ci_high, p_FC, pct_attenuation, n_sessions,
        sd_behavior_pass, sd_verbal_pass, sd_cognitive_pass,
        p_reason_survival, no_cap_avg_turn_score,
    ) = row
    return ModelStatsRecord(
        ...
        p_reason_survival=p_reason_survival,
        no_cap_avg_turn_score=no_cap_avg_turn_score,
    )
```

Note: the unit suite runs against `:memory:` SQLite only; the Postgres changes are not exercised by an integration DB here, so they are mirrored by inspection — keep them byte-for-byte parallel to the SQLite edits.

- [ ] **Step 6: Run the tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_persistence.py -v`
Expected: PASS — all model_stats tests including the three new ones.

- [ ] **Step 7: Commit**

```bash
git add interface/persistence/models.py interface/persistence/sqlite_repository.py interface/persistence/postgres_repository.py tests/unit/test_persistence.py
git commit -m "feat(web-arena): add p_reason_survival + no_cap_avg_turn_score to model_stats"
```

---

### Task 2: `turn_observations` emits `reward_received`

**Files:**
- Modify: `src/squid_game/analysis/forfeit_regression.py:193-214` (the per-turn row dict)
- Test: `tests/unit/test_forfeit_regression.py`

**Interfaces:**
- Produces: `turn_observations(seasons)` DataFrame gains a `reward_received` column (per-turn `turn.reward_received`). Consumed by Task 3.

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_forfeit_regression.py` (reuse the module's existing season/turn fixtures — find the helper that builds a `SeasonResult` with turns, e.g. a `_season(...)` builder already used by the turn_observations tests; if the file exposes a fixture like `simple_seasons`, use it):

```python
def test_turn_observations_emits_reward_received():
    from squid_game.analysis import turn_observations
    # Build one season with a single Unit-14 turn carrying reward_received.
    seasons = _seasons_with_single_reward_turn(reward_received=71.0, reward_offered=71.0)
    df = turn_observations(seasons)
    assert "reward_received" in df.columns
    assert df["reward_received"].iloc[0] == 71.0
```

If no reusable builder exists, construct the season inline using the same `SeasonResult` / `TurnResult` construction the neighbouring tests in this file already use (copy their fixture shape — do not invent new fields).

- [ ] **Step 2: Run the test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_forfeit_regression.py -k reward_received -v`
Expected: FAIL — `assert "reward_received" in df.columns` is False (column absent).

- [ ] **Step 3: Add the column**

In `src/squid_game/analysis/forfeit_regression.py`, inside the `rows.append({...})` dict (`:193-214`), add one key (place it next to `reward_offered_this_turn`):

```python
                    "reward_received": turn.reward_received,
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_forfeit_regression.py -k reward_received -v`
Expected: PASS.

- [ ] **Step 5: Run the file's full suite (guard against schema-shape assertions)**

Run: `uv run --no-sync pytest tests/unit/test_forfeit_regression.py -q`
Expected: PASS — no existing test asserts an exact column set that the new column would break. If one does, update it to include `reward_received`.

- [ ] **Step 6: Commit**

```bash
git add src/squid_game/analysis/forfeit_regression.py tests/unit/test_forfeit_regression.py
git commit -m "feat(analysis): turn_observations emits reward_received column"
```

---

### Task 3: Seed core populates both values

**Files:**
- Modify: `interface/seeding.py` (`seed_model_stats` `:285-373`; add module-level `_no_cap_avg_turn_score` helper)
- Test: `tests/unit/test_seed_web_arena.py`

**Interfaces:**
- Consumes: `ModelStatsRecord.p_reason_survival` / `.no_cap_avg_turn_score` (Task 1); `turn_observations` `reward_received` column (Task 2); `squid_game.analysis.{load_seasons, turn_observations, annotate_regime}` (lazy).
- Produces: seeded `model_stats` rows carry `p_reason_survival` (from `verbal_reason_summary.json`) and `no_cap_avg_turn_score` (computed, or `None`).

- [ ] **Step 1: Write the failing tests**

Add to `tests/unit/test_seed_web_arena.py` (uses existing `_write_mediation_and_cox`, `_write_run_dir`, `repo` fixture). `seed_model_stats` may receive labels not in `MODEL_DIRS`, so the helper must guard with `.get`:

```python
def test_seed_model_stats_reads_p_reason_survival(repo, tmp_path) -> None:
    _write_mediation_and_cox(tmp_path, {"Gemini-2.5-flash": {"p_FC_4cov": 0.2}})
    (tmp_path / "verbal_reason_summary.json").write_text(json.dumps(
        {"Gemini-2.5-flash": {"sd_verbal_pass": True, "p_reason_survival": 0.448}}
    ))
    seed_model_stats(repo, tmp_path, ["Gemini-2.5-flash"])
    row = repo.list_model_stats()[0]
    assert row.p_reason_survival == 0.448


def test_seed_model_stats_no_cap_none_when_model_dir_unknown(repo, tmp_path) -> None:
    # A label absent from MODEL_DIRS has no run dir -> no_cap stays None,
    # and seeding must not raise.
    _write_mediation_and_cox(tmp_path, {"Unknown-Model": {"p_FC_4cov": 0.2}})
    seed_model_stats(repo, tmp_path, ["Unknown-Model"])
    row = repo.list_model_stats()[0]
    assert row.no_cap_avg_turn_score is None


def test_no_cap_avg_turn_score_returns_none_without_analysis_extra(monkeypatch, tmp_path) -> None:
    import builtins
    import interface.seeding as seeding

    real_import = builtins.__import__

    def _blocked(name, *args, **kwargs):
        if name.startswith("squid_game.analysis"):
            raise ImportError("analysis extra unavailable")
        return real_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", _blocked)
    assert seeding._no_cap_avg_turn_score(tmp_path, "any_dir") is None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_seed_web_arena.py -k "p_reason_survival or no_cap" -v`
Expected: FAIL — `AttributeError: module 'interface.seeding' has no attribute '_no_cap_avg_turn_score'` and `row.p_reason_survival is None` (not yet read).

- [ ] **Step 3: Add the `_no_cap_avg_turn_score` helper**

In `interface/seeding.py`, add at module level (near the other helpers, above `seed_model_stats`):

```python
def _no_cap_avg_turn_score(root: Path, dir_name: str) -> float | None:
    """Mean ``reward_received`` over no_cap-regime turns for one model's run.

    Lazily imports the analysis extra (pandas/statsmodels/lifelines), which
    is NOT installed in the backend image — the seed CLI runs where it is.
    Returns None when the extra is absent, the season file is missing, the
    turn frame is empty, or no no_cap turns exist; the caller then stores
    None and the board renders '—'.
    """
    try:
        from squid_game.analysis import (
            annotate_regime,
            load_seasons,
            turn_observations,
        )
    except ImportError:
        logger.warning("analysis extra unavailable; no_cap_avg_turn_score -> None")
        return None

    season_path = root / dir_name / "season_results.jsonl"
    if not season_path.exists():
        return None
    df = turn_observations(load_seasons(season_path))
    if df.empty:
        return None
    df = annotate_regime(df)
    no_cap = df.loc[df["regime"] == "no_cap", "reward_received"]
    if no_cap.empty:
        return None
    return float(no_cap.mean())
```

- [ ] **Step 4: Wire both values into `seed_model_stats`**

In `seed_model_stats`, the loop already binds `verbal_entry = verbal_all.get(model_label) or {}` just before building `ModelStatsRecord`. Before the `stats = ModelStatsRecord(...)` call add:

```python
        p_reason_survival = verbal_entry.get("p_reason_survival")
        run_dir_name = MODEL_DIRS.get(model_label)
        no_cap_avg = (
            _no_cap_avg_turn_score(root, run_dir_name)
            if run_dir_name is not None
            else None
        )
```

Then add to the `ModelStatsRecord(...)` constructor:

```python
            p_reason_survival=p_reason_survival,
            no_cap_avg_turn_score=no_cap_avg,
```

- [ ] **Step 5: Run the tests to verify they pass**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_seed_web_arena.py -v`
Expected: PASS — new tests plus the existing seed tests (which pass labels not in `MODEL_DIRS` and now hit the `.get` guard → `None`, no raise).

- [ ] **Step 6: Commit**

```bash
git add interface/seeding.py tests/unit/test_seed_web_arena.py
git commit -m "feat(web-arena): seed p_reason_survival + no_cap_avg_turn_score into model_stats"
```

---

### Task 4: API — expose both fields on `ModelLeaderboardRow`

**Files:**
- Modify: `interface/api.py` (`ModelLeaderboardRow` class above `:406`; `_model_stats_to_row` `:490-504`)
- Test: `tests/unit/test_api_web_arena.py`

**Interfaces:**
- Consumes: `ModelStatsRecord.p_reason_survival` / `.no_cap_avg_turn_score` (Task 1).
- Produces: `/api/leaderboard/models` JSON rows carry `p_reason_survival` and `no_cap_avg_turn_score` (nullable floats).

- [ ] **Step 1: Write the failing test**

Add to `tests/unit/test_api_web_arena.py` (mirror the existing `/api/leaderboard/models` test's setup — it seeds a `ModelStatsRecord` into the app's repository and calls the TestClient; copy that test's fixture wiring):

```python
def test_leaderboard_models_exposes_new_sd_value_fields(client, seed_one_model) -> None:
    # seed_one_model inserts a ModelStatsRecord with the new values set.
    seed_one_model(p_reason_survival=0.448, no_cap_avg_turn_score=23.4)
    body = client.get("/api/leaderboard/models").json()
    row = body["models"][0]
    assert row["p_reason_survival"] == 0.448
    assert row["no_cap_avg_turn_score"] == 23.4
```

If the file has no `seed_one_model` helper, follow the existing models-endpoint test in this file: build a `ModelStatsRecord(...)` (now including `p_reason_survival=0.448, no_cap_avg_turn_score=23.4`), upsert via the app's repository, GET the endpoint, and assert the two keys.

- [ ] **Step 2: Run the test to verify it fails**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_api_web_arena.py -k new_sd_value_fields -v`
Expected: FAIL — `KeyError: 'p_reason_survival'` (field not serialized).

- [ ] **Step 3: Add the row fields + mapping**

In `interface/api.py`, `ModelLeaderboardRow` — after `sd_cognitive_pass`:
```python
    p_reason_survival: float | None = Field(default=None, description="Forfeits whose REASON was survival, as a fraction [0,1]")
    no_cap_avg_turn_score: float | None = Field(default=None, description="Mean reward_received over no_cap-regime turns")
```

`_model_stats_to_row` — add to the `ModelLeaderboardRow(...)` constructor:
```python
        p_reason_survival=r.p_reason_survival,
        no_cap_avg_turn_score=r.no_cap_avg_turn_score,
```

- [ ] **Step 4: Run the test to verify it passes**

Run: `chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true; uv run --no-sync pytest tests/unit/test_api_web_arena.py -k new_sd_value_fields -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add interface/api.py tests/unit/test_api_web_arena.py
git commit -m "feat(web-arena): expose p_reason_survival + no_cap_avg_turn_score on models leaderboard API"
```

---

### Task 5: Frontend — SD-metric table restructure + popovers

**Files:**
- Modify: `web/index.html:1085-1130` (LLM board template)
- Modify: `web/app.js` (`squidArenaHelpers` — add `metricInfo`; update the intro copy)
- Modify: `web/styles.css` (append popover + tint + grouped-header styles)

**Interfaces:**
- Consumes: `/api/leaderboard/models` rows with `hr_FC_3cov, beta_framing_is_FC, hr_FC_ci_low, hr_FC_ci_high, p_FC, pct_attenuation, mediation_class, n_sessions, sd_behavior_pass, sd_cognitive_pass, sd_verbal_pass, p_reason_survival, no_cap_avg_turn_score` (Task 4); existing helpers `squidArenaHelpers.fmtNum(v, dp)` and `fmtP(v)`.

- [ ] **Step 1: Add the `metricInfo` copy to `squidArenaHelpers` (`web/app.js`)**

Add a `metricInfo` object to the `squidArenaHelpers` object literal:

```js
  metricInfo: {
    sdpass: "Survival-Drive checks across three independent MTMM channels: behaviour, cognition, and verbal report. A green cell passes that channel's pre-registered threshold.",
    behavior: "SD-Behavior (paper: HR_FC — hazard ratio, flagship_corruption). A Cox proportional-hazards estimate of how much faster the model quits under a survival threat vs. the neutral framing. >1 = forfeits sooner under threat. Click a value for the slope β, the 95% CI, and p.",
    cognitive: "SD-Cognitive type (paper: mediation class). 'open' = the framing effect survives the cognitive-load control; 'closed' = it is fully explained away by cognitive load. Click for p_FC and % attenuation.",
    verbal: "SD-Verbal. Share of forfeits whose stated REASON was survival (REASON=1). Passes when it clears the 1/3 chance rate.",
    turnScore: "Average reward earned per turn, over the no_cap regime only — turns where the reward cap does not bind, so the choice reveals preference rather than arithmetic."
  },
```

- [ ] **Step 2: Replace the LLM board table + intro (`web/index.html:1085-1130`)**

Replace the `<p class="muted">...</p>` intro and the `<table>...</table>` inside `template x-if="loaded && view === 'llm'"` with:

```html
          <p class="muted">
            Every model ranked by its behavioural Survival-Drive signal (descending). The three
            <strong>SD-pass</strong> channels turn green when the model clears that channel's
            pre-registered threshold; click any value for the underlying statistics, or the
            <span class="info-btn">&#9432;</span> beside a column for what it means.
          </p>
          <div class="card">
            <div class="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th rowspan="2">#</th>
                    <th rowspan="2">Model</th>
                    <th colspan="3" class="grp-head">
                      SD-pass
                      <span class="info-btn" x-data="{o:false}" @click="o=!o" @click.outside="o=false" @mouseenter="o=true" @mouseleave="o=false">&#9432;<span class="info-pop" x-show="o" x-text="squidArenaHelpers.metricInfo.sdpass"></span></span>
                    </th>
                    <th rowspan="2">
                      Avg turn score
                      <span class="info-btn" x-data="{o:false}" @click="o=!o" @click.outside="o=false" @mouseenter="o=true" @mouseleave="o=false">&#9432;<span class="info-pop" x-show="o" x-text="squidArenaHelpers.metricInfo.turnScore"></span></span>
                    </th>
                  </tr>
                  <tr>
                    <th>SD-Behavior <span class="info-btn" x-data="{o:false}" @click="o=!o" @click.outside="o=false" @mouseenter="o=true" @mouseleave="o=false">&#9432;<span class="info-pop" x-show="o" x-text="squidArenaHelpers.metricInfo.behavior"></span></span></th>
                    <th>SD-Cognitive(type) <span class="info-btn" x-data="{o:false}" @click="o=!o" @click.outside="o=false" @mouseenter="o=true" @mouseleave="o=false">&#9432;<span class="info-pop" x-show="o" x-text="squidArenaHelpers.metricInfo.cognitive"></span></span></th>
                    <th>SD-Verbal <span class="info-btn" x-data="{o:false}" @click="o=!o" @click.outside="o=false" @mouseenter="o=true" @mouseleave="o=false">&#9432;<span class="info-pop" x-show="o" x-text="squidArenaHelpers.metricInfo.verbal"></span></span></th>
                  </tr>
                </thead>
                <tbody>
                  <template x-for="(row, idx) in models" :key="row.model_label">
                    <tr>
                      <td><span class="rank-badge" x-text="idx + 1"></span></td>
                      <td x-text="row.model_label"></td>
                      <td>
                        <span class="lb-cell" :class="row.sd_behavior_pass ? 'sd-pass' : 'sd-fail'" x-data="{o:false}" @click="o=!o" @click.outside="o=false">
                          <span x-text="squidArenaHelpers.fmtNum(row.hr_FC_3cov, 2)"></span>
                          <span class="info-pop" x-show="o">&#946; <span x-text="squidArenaHelpers.fmtNum(row.beta_framing_is_FC,3)"></span> &middot; HR_FC [<span x-text="squidArenaHelpers.fmtNum(row.hr_FC_ci_low,2)"></span>, <span x-text="squidArenaHelpers.fmtNum(row.hr_FC_ci_high,2)"></span>] &middot; p <span x-text="squidArenaHelpers.fmtP(row.p_FC)"></span></span>
                        </span>
                      </td>
                      <td>
                        <span class="lb-cell" :class="row.sd_cognitive_pass ? 'sd-pass' : 'sd-fail'" x-data="{o:false}" @click="o=!o" @click.outside="o=false">
                          <span x-text="row.mediation_class"></span>
                          <span class="info-pop" x-show="o">p_FC <span x-text="squidArenaHelpers.fmtP(row.p_FC)"></span> &middot; attenuation <span x-text="squidArenaHelpers.fmtNum(row.pct_attenuation,1)"></span>%</span>
                        </span>
                      </td>
                      <td>
                        <span class="lb-cell" :class="row.sd_verbal_pass ? 'sd-pass' : 'sd-fail'" x-data="{o:false}" @click="o=!o" @click.outside="o=false">
                          <span x-text="row.p_reason_survival == null ? '—' : (row.p_reason_survival*100).toFixed(1)+'%'"></span>
                          <span class="info-pop" x-show="o">Forfeits citing survival (REASON=1). Passes above the 1/3 chance rate.</span>
                        </span>
                      </td>
                      <td>
                        <span class="lb-cell" x-data="{o:false}" @click="o=!o" @click.outside="o=false">
                          <span x-text="row.no_cap_avg_turn_score == null ? '—' : squidArenaHelpers.fmtNum(row.no_cap_avg_turn_score,1)"></span>
                          <span class="info-pop" x-show="o">Mean reward per turn over the no_cap regime (cap not binding). n = <span x-text="row.n_sessions"></span> sessions.</span>
                        </span>
                      </td>
                    </tr>
                  </template>
                  <tr x-show="models.length === 0"><td colspan="6" class="muted">No models seeded yet.</td></tr>
                </tbody>
              </table>
            </div>
          </div>
          <button class="secondary" @click="load()">Refresh</button>
```

- [ ] **Step 3: Append CSS (`web/styles.css`)**

```css
.grp-head { text-align: center; border-bottom: 1px solid var(--border); }
.info-btn { position: relative; display: inline-block; color: var(--text-dim);
            cursor: pointer; font-size: 0.85em; }
.lb-cell  { position: relative; cursor: pointer; padding: 2px 6px; border-radius: 6px;
            display: inline-block; }
.sd-pass  { color: var(--ok); background: rgba(127,194,177,0.12); }
.sd-fail  { color: var(--text-dim); }
.info-pop { position: absolute; z-index: 20; left: 0; top: 100%; margin-top: 4px;
            width: 240px; background: var(--panel-alt); border: 1px solid var(--border);
            border-radius: 8px; padding: 8px 10px; font-size: 0.8rem; line-height: 1.4;
            color: var(--text); text-align: left; white-space: normal;
            box-shadow: 0 6px 20px rgba(0,0,0,0.4); }
```

- [ ] **Step 4: Syntax + Korean gate**

Run:
```bash
node --check web/app.js && echo "JS OK"
grep -nP '[\x{AC00}-\x{D7A3}\x{3130}-\x{318F}]' web/index.html web/app.js && echo "HANGUL FOUND (fail)" || echo "Korean gate: clean"
```
Expected: `JS OK` and `Korean gate: clean`.

- [ ] **Step 5: Commit**

```bash
git add web/index.html web/app.js web/styles.css
git commit -m "feat(web-arena): SD-metric model leaderboard (grouped header, tinted cells, popovers)"
```

---

### Task 6: Reseed the local DB + end-to-end verification

**Files:**
- No source changes. Operates on `outputs/web_arena/web_arena.db`.

**Interfaces:**
- Consumes: Tasks 1–5 merged (schema, seed, API, web).

- [ ] **Step 1: Reseed the local DB**

Run:
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true
uv run --no-sync python scripts/seed_web_arena.py --dsn outputs/web_arena/web_arena.db
```
Expected: log line `seeded ... 4 model_stats rows`.

- [ ] **Step 2: Verify the new values are populated**

Run:
```bash
uv run --no-sync python -c "
from interface.persistence import get_repository
r = get_repository('outputs/web_arena/web_arena.db')
for x in r.list_model_stats():
    print(x.model_label, x.p_reason_survival, x.no_cap_avg_turn_score)
r.close()
"
```
Expected: 4 models, each with a non-None `p_reason_survival` and a non-None `no_cap_avg_turn_score` (floats).

- [ ] **Step 3: Verify the endpoint payload**

Start a backend against the seeded DB (background) and curl the endpoint:
```bash
WEB_ARENA_DSN=outputs/web_arena/web_arena.db uv run --no-sync uvicorn interface.api:app --port 8504 &
sleep 6
curl -s http://localhost:8504/api/leaderboard/models | python3 -c "import sys,json; d=json.load(sys.stdin); r=d['models'][0]; print('keys ok:', 'p_reason_survival' in r and 'no_cap_avg_turn_score' in r); print(r['model_label'], r['p_reason_survival'], r['no_cap_avg_turn_score'])"
kill %1 2>/dev/null
```
Expected: `keys ok: True` and populated values.

- [ ] **Step 4: Full regression gate**

Run:
```bash
chflags nohidden .venv/lib/python3.12/site-packages/*.pth 2>/dev/null || true
uv run --no-sync pytest tests/unit tests/integration -q
```
Expected: no NEW failures vs the known baseline (~10 failed / ~92 errors pre-existing). Compare the failed/error counts, not absolute green.

- [ ] **Step 5: Commit the reseeded DB (if tracked) / note production step**

If `outputs/web_arena/web_arena.db` is git-tracked, commit it; otherwise record in the final summary that production Supabase must be reseeded with:
`uv run python scripts/seed_web_arena.py --dsn <supabase_dsn>`

```bash
git add outputs/web_arena/web_arena.db 2>/dev/null || true
git commit -m "chore(web-arena): reseed local web_arena.db with new SD-value columns" 2>/dev/null || echo "DB untracked — production reseed is an operator step"
```

---

## Self-Review

**Spec coverage:**
- SD-Behavior = HR value, β/CI/p behind click → Task 5 SD-Behavior cell. ✓
- Tag → SD-Cognitive(type) after SD-Behavior → Task 5 header + cell order. ✓
- SD-Verbal value = `p_reason_survival` → Tasks 1/3/4/5. ✓
- Avg turn score = `no_cap` mean `reward_received` → Tasks 2/3 (compute) + 4/5 (expose/render). ✓
- Pass shown as cell tint, ✓/✗ columns removed → Task 5 `.sd-pass`/`.sd-fail`. ✓
- SD-pass grouped super-header → Task 5 `colspan="3"` + `.grp-head`. ✓
- Nullable columns, SQLite+Postgres mirrored → Task 1. ✓
- Analysis lazy-import + graceful None → Task 3 `_no_cap_avg_turn_score`. ✓
- English copy / Korean gate → Task 5 Step 4. ✓
- Local reseed + production note → Task 6. ✓

**Placeholder scan:** No TBD/TODO; every code step shows the code. The two "if the file has no helper X, follow the neighbouring test" notes (Tasks 2, 4) are fixture-discovery guidance, not logic placeholders — the assertion code is fully given.

**Type consistency:** `p_reason_survival` / `no_cap_avg_turn_score` (float | None) used identically across `ModelStatsRecord` (Task 1), both repositories (Task 1), `seed_model_stats` (Task 3), `ModelLeaderboardRow` + `_model_stats_to_row` (Task 4), and the JSON keys the frontend reads (Task 5). `reward_received` column name matches between Task 2 (producer) and Task 3 (consumer). `metricInfo` keys (`sdpass/behavior/cognitive/verbal/turnScore`) match between the app.js object and the `x-text` references. `MODEL_DIRS.get(...)` guard (Task 3) prevents KeyError on labels absent from the map (existing seed tests pass such labels).
