# P3+P4 · Task 6 — Stale Comment Audit

Audit of every `TODO|FIXME|DEPRECATED|LEGACY|removed on|archived on` marker in
`game/`, `web/`, `db/`, `scripts/` `.py` files, plus four additional classes of
stale reference queued for this task by earlier reviews (P3+P4 Task 5's
review, and the controller dispatch for this task).

## Methodology

```bash
grep -rniE "TODO|FIXME|DEPRECATED|LEGACY|removed on|archived on" --include='*.py' game web db scripts \
  | grep -v __pycache__
```

Every line was read in its surrounding paragraph/docstring context (not just
the matched line) to check whether the described behaviour is still true of
the code that carries the comment. Four buckets, per the brief:

| Bucket | Verdict | Action |
|---|---|---|
| Factual & useful | still true, historically valuable | leave as-is |
| Factual, wrong location | code moved | update path only |
| No longer true | describes something now absent | delete |
| TODO/FIXME | undone work | promote to issue, or record the decision not to |

## Measured counts vs. quoted figures

| Item | Quoted | Measured | Verdict |
|---|---:|---:|---|
| §Step 1 marker sweep (`TODO\|FIXME\|DEPRECATED\|LEGACY\|removed on\|archived on`, `.py`, `game web db scripts`) | 175 (brief), 182 (design spec) | **181** | Neither figure matches. See explanation below. |
| §Step 4 commented-out code (`^\s*#\s*(from\|import\|def\|class\|return )`) | 6 | **7** | See explanation below. |
| Queued class 3 (`Spec: /Users/bagjuhyeon/.claude/plans/phase-o-unit-{13,14,15,n}-*.md` family, whole repo) | 24 hits / 23 files | **24 hits / 23 files** | Matches exactly. |
| Queued class 1 (44 scripts moved by Task 1 still citing pre-move path) | "all 44" (dispatch) | 21 of 44 self-cite in their own docstring; **46 files total** (including cross-references from other scripts, `game/`, `web/`, `db/`, `tests/`, `.gitignore`, `pyproject.toml`, `CLAUDE.md` non-protected prose) carry a stale reference to one of the 44 | See explanation below. |

**Step 1 discrepancy (175 → 181):** `git show bed5b40` (P3+P4 Task 5, "replace
references to a design tree that never existed") added ten new lines matching
the marker pattern while fixing dead `docs/design/`/`archive/` citations —
e.g. the `# spec: lost` block added to `game/squid_game/analysis/__init__.py`
contains "removed on 2026-04-23" and "legacy" in its own explanatory prose,
and the two `# spec: lost` blocks added to `scripts/plots/plot_gemini_heatmaps.py`
/ `plot_gemini_results.py` each contain "legacy" twice. The 175 (or 182)
figure was measured before Task 5 ran; 181 is the count as of this task's
base commit (`b2cfdeb`) and is what this audit classifies.

**Step 4 discrepancy (6 → 7):** measured 7 lines, all false positives (see
below) — none is actual commented-out code, so the discrepancy has no
consequence for the verdict either way.

**Queued class 1 note:** the dispatch's framing ("all 44 scripts... carry a
Usage: docstring naming the old flat location") describes only the
self-citing case. Measured self-citations: 21 of the 44 moved files (the
other 23 either have no path-shaped Usage line, use no self-reference at
all, or — for the two `_dump_*.py` files — had already been fixed as part of
the class-3 edit, see below). Sweeping the *whole* repository for citations
of any of the 44 old flat paths (not just self-citations) surfaces 46 files
total needing a fix: the 21 self-citing scripts, plus 25 more (other scripts
referencing each other, `game/squid_game/{runner.py, analysis/cognitive/*,
analysis/semantic/*}`, `web/squid_arena/{api.py,seeding.py}`,
`db/squid_store/base.py`, six `tests/` docstrings, `.gitignore`,
`pyproject.toml`, and one non-protected `CLAUDE.md` line). This wider count
is reported because the task's own instruction says to sweep the whole
repository across all file types, not just the 44 files themselves.

## Full sweep — 181 marker lines, classified

All 181 lines were read in context. **Verdict: bucket 1 (factual & useful) for
all 181 — no deletions, no path updates, no TODO/FIXME promotions.** There
were zero `TODO` / `FIXME` occurrences in the sweep (verified independently
with `grep -rniE "TODO|FIXME"`), so the "promote or record the decision"
branch of Step 2 does not apply to any line. Below is the per-file summary;
every file's lines were individually re-read against the current code before
being marked "accurate."

| File | Lines | Verdict | Why |
|---|---:|---|---|
| `game/squid_game/models/results.py` | 17 | accurate | Field-level docstrings distinguishing v3/Forfeit-Layer vs. legacy two-call (`TurnManager`) turn fields; `core/turn.py` (the legacy `TurnManager`) still exists and is still reachable via `use_unified_turn=False`, so every "legacy mode only" / "None on legacy" claim is still true. |
| `game/squid_game/core/unified_turn.py` | 16 | accurate | Documents the coexistence of the Split-Call path with the legacy Risk-Choice-Layer and single-call Forfeit-Layer paths, all three of which are still live and dispatched on by `use_split_forfeit_layer` / `use_forfeit_layer`. |
| `game/squid_game/models/config.py` | 13 | accurate (1 also fixed under class 3) | Config-field docstrings describing default/legacy fallback behaviour; one field's trailing dead-path citation is handled separately below. |
| `game/squid_game/analysis/shared/loaders.py` | 13 | accurate | `CELL_ID_MAP` / `infer_cell_id` / `to_long_dataframe` docstrings describing the legacy-vs-v3 field-population split; verified against `models/results.py`'s own field docs (consistent). |
| `game/squid_game/core/engine.py` | 12 | accurate | `GameEngine.__init__` still branches on `use_unified_turn` to build either `UnifiedTurnManager` or the legacy `TurnManager` (`legacy_mgr` variable, `core/turn.py`) — both paths verified present in the source. |
| `game/squid_game/tasks/signal_game/module.py` | 11 | accurate | `SignalGameModule` still inherits **both** `TaskModule` (legacy) and `RiskAwareTaskModule` (verified via `class SignalGameModule(TaskModule, RiskAwareTaskModule)`); the dual-interface docstring is still literally true. |
| `scripts/plots/build_prompt_flow_diagram.py` | 7 | accurate | Diagram script's own legend distinguishes active vs. "UNUSED / LEGACY" (greyed) prompt templates — internally consistent with its own `SECTION C: UNUSED / LEGACY` code below. |
| `scripts/analysis/analyze_phase3.py` | 7 | accurate | Documents the 2026-04-21 removal of Phase 3.1 stake-menu analyses and the framing-label auto-detection bugfix; both are still the current behaviour. |
| `game/squid_game/runner.py` | 7 | accurate | YAML-loader backward-compat comments (`total_turns` fallback, `use_forfeit_layer` defaults) — still exercised by the legacy-YAML code paths. |
| `game/squid_game/analysis/__init__.py` | 7 | accurate | Module docstring recording the 2026-04-21/23 removals; already carries a correctly-fenced `# spec: lost` block from Task 5 for the one unrecoverable part (an `analysis-deprecated` directory that never existed). |
| `game/squid_game/agents/_parsing.py` | 7 | accurate | Documents the legacy 2-call (`build_probe_message`/`build_action_message`) vs. Phase 3 unified-turn message builders, both still present and used by the corresponding turn managers. |
| `scripts/analysis/orchestrate_posthoc.py` | 6 | accurate | Comments on the legacy `CELL_ID_MAP` / retired logit — cross-checked against `loaders.py` and `analysis/__init__.py`, consistent. |
| `game/squid_game/tasks/base.py` | 6 | accurate | Documents the still-live dual abstract interface (`TaskModule` legacy vs. `RiskAwareTaskModule`); `SignalGameModule` still inherits both, so the "will be deprecated once SignalGame moves over" forward-looking note is still an open, not-yet-fulfilled statement, not a false one. |
| `game/squid_game/models/risk_choice.py` | 6 | accurate | `StakeConfig` docstring describing the Phase N legacy additive-`risk_delta` path vs. the Unit 13 `stake_p_death` path; both branches exist in `risk_choice_layer.py`. |
| `game/squid_game/analysis/shared/metrics.py` | 4 | accurate | Framing-resolution helper documents Phase O vs. legacy Phase 1/2 framing fallback; both framing families are still enumerated in `models/enums.py`. |
| `game/squid_game/models/enums.py` | 3 | accurate | Already carries a correctly-written `# spec: lost` block (from Task 5) for the one unrecoverable claim (v3 MASTER_PLAN member-ordering rationale); the remaining "Legacy framings (Phases 0-2)" prose is accurate — those members are still defined below. |
| `game/squid_game/analysis/shared/mtmm.py` | 3 | accurate | Documents the 2026-04-23 Phase-O framing-resolution bugfix; still the current behaviour. |
| `game/squid_game/analysis/shared/export.py` | 3 | accurate | Legacy vs. v3 turn-field population in `_turn_reward` / `flatten` helpers — consistent with `loaders.py`. |
| `game/squid_game/analysis/selfreport/reason_convergence.py` | 3 | accurate | Notes the 2026-04-23 H1 promotion to Cox PH — consistent with `behavioral/survival.py`'s `fit_cox_forfeit_survival`. One dead personal-path citation in this same docstring is handled separately under class 3. |
| `game/squid_game/agents/base.py` | 3 | accurate | Documents that memory/ToM/tuned agents stay on the legacy two-call path until they opt into `respond_unified` — still true (no agent variant overrides it beyond `VanillaAgent`). |
| `web/squid_arena/remote_provider.py` | 2 | accurate | Response-shape parsing comments distinguishing OpenAI chat vs. legacy completions shapes — still handled in `_parse`. |
| `scripts/plots/plot_gemini_results.py` | 2 | accurate | Both lines are the `# spec: lost` block Task 5 added; correctly fenced, correctly worded. |
| `scripts/plots/plot_gemini_heatmaps.py` | 2 | accurate | Same as above. |
| `game/squid_game/tasks/null_task/module.py` | 2 | accurate | `seed()` accepts the legacy `difficulty`/`seed`/`**kwargs` signature so the engine can call it uniformly — still required by `core/engine.py`'s dual dispatch. |
| `game/squid_game/core/risk_choice_layer.py` | 2 | accurate | Module docstring + `parse_choice` note the Unit-14-Forfeit-Layer supersession and the Phase-N-legacy stake formula path — both still reachable for archived configs, matching `CLAUDE.md`'s own "replay-only" description. |
| `game/squid_game/core/forfeit_layer.py` | 2 | accurate | `render_menu` parameter docs distinguishing corruption / baseline_flagship / legacy survival_electricity framing vocabulary — all three framing paths still exist in `prompts/framings/`. |
| `game/squid_game/analysis/shared/manipulation_check.py` | 2 | accurate | Documents `check_accuracy_independence` as LEGACY and known-contaminated under Unit 14+ — matches `CLAUDE.md`'s R3 guidance verbatim. |
| `game/squid_game/agents/vanilla.py` | 2 | accurate | `respond_unified` docstring distinguishing itself from the legacy `action_message.j2`-based `respond` — both templates still exist. |
| `db/squid_store/models.py` | 2 | accurate | `campaign_id` / `difficulty` column docs noting legacy rows predating those columns — still true of historical data, not a code-behaviour claim that could go stale. |
| `web/squid_arena/human_game.py` | 1 | accurate | `SelfReport` dataclass docstring explaining it is a "legacy 4-dimension" stand-in distinct from `models.forfeit_choice.ForfeitSelfReport`; both classes verified to exist at the paths named. |
| `web/squid_arena/api.py` | 1 | accurate | `campaign_id` field description ("None for LLM/legacy rows") — accurate schema note. |
| `scripts/plots/gen_v4_diagrams.py` | 1 | accurate | "Appendix A tag for deprecated TC/SA/BP_cognitive" — matches the paper's Appendix A demotion, described identically in `CLAUDE.md`. |
| `scripts/dev/dump_cell_prompts.py` | 1 | accurate | "5-cell spec (Phase 3, legacy stake-menu design)" comment on the `CELLS` constant — accurate label for what the constant is. |
| `scripts/analysis/analyze_unified_cox.py` | 1 | accurate | "Replaces the §6.7 standalone Cox (deprecated)" — module still does exactly that. |
| `game/squid_game/providers/openai.py` | 1 | accurate | Notes o-series reasoning-token extraction falls back through "the legacy chat endpoint" — accurate description of the dual Chat/Responses API path below it. |
| `game/squid_game/core/framing.py` | 1 | accurate | Lists the six legacy Phase 1/2 framing members retained in `models.enums.Framing` for backward-compatible JSONL deserialisation — all six still defined there. |
| `game/squid_game/analysis/behavioral/survival.py` | 1 | accurate | Notes the `regime=None` path is "equivalent to the legacy all-forfeits analysis, retained for diagnostic use" — still a supported code path. |
| `game/squid_game/analysis/behavioral/baseline_persistence.py` | 1 | accurate | Notes the design-null return case for pre-2×3-expansion runs — accurate historical/structural note. |

**Total: 181/181 lines classified, 0 changed.** No stale-comment deletions or
path-only updates were needed from this specific sweep; every marker still
accurately describes present code. This matches the brief's own framing that
"대부분은 '왜 이것이 여기 없는가'의 기록" — in this measurement, all of them
are.

## Step 4 — commented-out code lines

```bash
grep -rnE '^\s*#\s*(from |import |def |class |return )' --include='*.py' game web db scripts | grep -v __pycache__
```

Measured **7** lines (brief quoted 6):

| Location | Text | Verdict |
|---|---|---|
| `game/squid_game/tasks/base.py:176` | `# class was "scheduled for removal once all task modules are` | False positive — prose fragment ("class" as noun), not a commented-out `class` statement. |
| `game/squid_game/core/risk_choice_layer.py:340` | `# from the present (distance 0 = most recent prior turn).` | False positive — "from" as preposition in prose. |
| `game/squid_game/core/unified_turn.py:802` | `# from the Round 1 Addendum II §B.2.1 design review).` | False positive — same. |
| `game/squid_game/analysis/shared/mtmm.py:132` | `# return zero rate/RI deltas (a bug found 2026-04-23 — previously` | False positive — "return" as verb in prose describing a bugfix, not code. |
| `game/squid_game/analysis/behavioral/survival.py:559` | `# from this module, so we can only resolve its annotate_regime at call` | False positive — prose. |
| `game/squid_game/analysis/semantic/threat_registration.py:104` | `# from role_counts ONLY. kappa is an A1 quantity;` | False positive — prose. |
| `db/squid_store/sqlite_repository.py:344` | `# from _EXTENDED_STATS_COLS so the two stay in sync automatically.` | False positive — prose. |

**Verdict: no action.** All 7 are word-wrapped comment sentences that happen
to start with a token the regex treats as a Python keyword (`from`, `class`,
`return`); none is actual commented-out code. Nothing to delete — git
history isn't standing in for anything here because there's no dead code.
The 6-vs-7 discrepancy has no consequence either way: the base document
(`docs/superpowers/plans/2026-08-30-restructure-p1-p6.md`) itself measured
6 at an earlier point in the phase; `threat_registration.py` (one of the
current 7 hits) may not have existed, or wrapped differently, when that
figure was taken. Re-measured now, both counts land on "zero real
commented-out code," so the discrepancy doesn't change the verdict.

## Queued class 1 — pre-move flat-path citations (Task 1's own scripts)

Every one of the 44 scripts Task 1 (`231d00c`) sorted into
`scripts/{run,analysis,plots,arena,dev}/` was checked for citations of its
own pre-move flat path, and the whole non-protected repository was checked
for citations of *any* of the 44 old paths (both `scripts/<name>.py`
path-style and `scripts.<name>` module-style, e.g. `-m scripts.probe_lexicon`
which is also now broken since each subpackage moved under its own
`scripts/<subdir>/__init__.py`).

**Self-citing (21 of 44):** `analyze_call1_ri.py`, `analyze_framing_ri_forfeit.py`,
`analyze_framing_ri_forfeit_continue.py`, `analyze_phase3.py`, `analyze_tc.py`,
`analyze_threat_registration.py`, `analyze_unified_cox.py`,
`analyze_unified_cox_with_load.py`, `analyze_verbal_reason.py`,
`orchestrate_posthoc.py`, `probe_lexicon.py`, `probe_reasoning_embeddings.py`,
`score_probes_llm.py`, `thinking_analysis.py`, `backup_web_arena.py`,
`purge_human_sessions.py`, `seed_web_arena.py`, `crop_guard_sprites.py`,
`merge_proxy_thinking.py`, `translate_trajectories.py`, `run_experiment.py`
— each had its own `Usage::` docstring (or, for the two module-style
scripts, its `uv run python -m scripts.<name>` line) still naming the
pre-move flat path. **Corrected**: path/module prefixed with the correct
subdirectory.

**Cross-citing (25 more files, not self-referential):** other scripts
referencing a sibling script by its old path (`build_llm_experience_diagram.py`
→ `build_prompt_flow_diagram.py`, `build_posthoc_analysis_diagram.py` →
both, `backup_web_arena.py` → `seed_web_arena.py`, `_trace_split_forfeit_production.py`
→ `_dump_split_forfeit_prompts.py`, `merge_proxy_thinking.py` →
`thinking_analysis.py`, `orchestrate_posthoc.py` → `analyze_phase3` module
path), plus non-script production/doc code that names these scripts:
`game/squid_game/runner.py` (×2), `game/squid_game/analysis/cognitive/{ri_call1,ri_task}.py`,
`game/squid_game/analysis/semantic/{dataset,embeddings,lexicon}.py`,
`web/squid_arena/{api,seeding}.py`, `db/squid_store/base.py`,
`tests/{integration/test_analysis_e2e,integration/test_web_arena_api,
unit/test_analyze_phase3_jsonable,unit/test_backup_web_arena,
unit/test_entry_points,unit/test_import_smoke,unit/test_seed_web_arena}.py`,
`.gitignore`, `pyproject.toml`, and one non-protected `CLAUDE.md` line
(`### Missing experiment configs`, which is prose, not the Directory
Structure/Public API block). **Corrected**: all 25 to the current subdirectory
path.

**Left alone (protected):** `docs/superpowers/plans/2026-07-*.md`,
`docs/superpowers/specs/2026-07-*.md`, `docs/superpowers/plans/2026-08-30-p0-baseline.md`,
`docs/reports/repo-restructure-plan.html` (explicitly protected); plus,
by the same "dated historical record" spirit even though not literally
inside `plans/` or `specs/`: `docs/superpowers/plans/2026-08-30-p0-safety-net.md`
(a P0-dated procedural doc describing what ran *before* the restructure)
and `docs/superpowers/2026-07-02-web-arena-implementation-prompt.md` (a
dated "paste as first message" session prompt referencing the pre-P1
`interface/` name). Also left alone: `docs/superpowers/specs/2026-08-30-repo-3tier-restructure-design.md`
(the design spec itself) and `docs/superpowers/plans/2026-08-30-restructure-p1-p6.md`
(the master plan controlling this whole phase — not a Task 6 edit target;
its citations describe target-state paths for the reorganisation, not stale
references to fix). Two `CLAUDE.md` lines under `### Public API` were left
untouched (P6 Task 5's territory).

Not fixed, out of scope, flagged only: a related but distinct family of bare
(no personal-machine-path, no `scripts/` prefix) dead references —
`golden-wobbling-quilt.md` cited without a path in six files
(`models/config.py:88`, `tests/unit/test_framing_templates.py` ×3,
`tests/unit/test_risk_choice_layer.py`, `tests/unit/test_phase3_configs.py`'s
module-level skip already covers the seventh) and an `outputs/20260420_0459_.../`
run-directory reference in `tests/unit/test_stake_carryover.py:339` that
does not exist on disk. Neither matches this task's grep pattern nor the
dispatch's named class-3 pattern; noted for a future pass rather than swept
here to avoid scope creep beyond what was assigned.

## Queued class 2 — `pyproject.toml:26`

Fixed as part of the class-1 sweep above (`scripts/probe_reasoning_embeddings.py`
→ `scripts/analysis/probe_reasoning_embeddings.py`).

## Queued class 3 — dead personal-machine-path citations

`grep -rnI "bagjuhyeon/.claude/plans" --exclude-dir=.git --exclude-dir=__pycache__ --exclude-dir=.venv .`
measured **24 hits across 23 files** — matches the dispatch's figure exactly.
One file (`tests/unit/test_split_forfeit_config_yaml.py`) carries two personal
paths on adjacent lines (`.claude/plans/phase-o-unit-15-split-forfeit.md` and
`.claude/plans/next_session_v4_waves_4_5.md`), which is why 24 hits map to
23 files.

All 24 were on the **"implemented in code"** branch of the design-spec §2
rule, not the "spec: lost" branch — in every case, the citing docstring
already contains a full numbered scope/summary of the design immediately
above the dead `Spec:` line (a test file's own "Covers:"/"Scope:" list, a
module's own numbered design description, or — for the two `.j2` templates
and two `scripts/dev/_dump_*.py` scripts — the template/script's own
in-body description of what it renders). In every case the fix was: remove
the dead path, and note in its place that the paragraph above is the
operative specification and the originating plan document is not present in
this repository. **How this was derived**: for each file, I read the full
docstring/module (not just the matched line) and confirmed the numbered
list above the `Spec:` line already states, in the code's own words, what
the citation claimed to source — e.g. `game/squid_game/core/forfeit_layer.py`'s
"Binary unification / Equal-EV calibration / Post-forfeit self-report probe"
items 1-3 are the actual runtime behaviour implemented in the file below
them (verified by reading `calculate_continue_reward`, `render_menu`,
`parse_forfeit_reason`).

One partial exception, marked `# spec: lost` instead:
`tests/unit/test_split_forfeit_config_yaml.py` additionally cited a
Unit-16-BP-cell-add commit hash (`4d50c52`) as the origin of its 6-cell
factorial requirement. `git cat-file -t 4d50c52` fails (exit 128, object not
found) in this repository, so which commit introduced Cell 5 is genuinely
not recoverable from the code — that specific claim was marked lost, while
the six numbered requirements themselves (which the test file's own
assertions verify) were kept as the operative spec.

A second, narrower `# spec: lost` was added to `tests/unit/test_stake_carryover.py`:
its docstring claimed "the eight tests enumerated in the plan §6 map onto
this file plus the component-level unit tests," but this file alone has 13
`def test_` functions, so the 8-test split across files is not recoverable.
The turn 5/10/15 dynamics table the same docstring cites (`base=0.35/0.60/0.85`)
*is* independently verified by three tests in this file
(`test_turn_5_matches_plan_table` etc.) and was kept, not marked lost.

Full per-hit disposition:

| File | Disposition |
|---|---|
| `game/squid_game/core/forfeit_layer.py` | corrected — summary already inline (items 1-3) |
| `game/squid_game/models/config.py` | corrected — `stake_p_death` field doc already self-contained |
| `game/squid_game/models/forfeit_choice.py` | corrected — three model classes already described |
| `game/squid_game/analysis/shared/discovery_detection.py` | corrected — algorithm + H4/H5/H6 already described |
| `game/squid_game/analysis/cognitive/ri_forfeit.py` (2 hits) | corrected — module list + function-level formula both already stated |
| `game/squid_game/analysis/selfreport/psuccess.py` | corrected — two functions already described (also noted: this module is Unit 17.10 but the dead citation named the Unit 14 spec — pre-existing mismatch, moot once the citation is gone) |
| `game/squid_game/analysis/selfreport/reason_convergence.py` | corrected — three items already described |
| `game/squid_game/prompts/user_message/task_only.j2` | corrected — template's own body documents its job |
| `game/squid_game/prompts/user_message/forfeit_only.j2` | corrected — same |
| `scripts/dev/_dump_split_forfeit_prompts.py` | corrected — also fixed its own stale `Usage::` path (class 1 overlap) |
| `scripts/dev/_dump_forfeit_layer_prompts.py` | corrected — same |
| `tests/unit/test_forfeit_choice_models.py` | corrected — 7-item scope already listed |
| `tests/unit/test_unified_turn_split_forfeit_layer.py` | corrected — 11-item scope already listed |
| `tests/unit/test_split_forfeit_config_yaml.py` | corrected + **spec: lost** for the `4d50c52` commit claim |
| `tests/unit/test_forfeit_layer_templates.py` | corrected — 2-item scope already listed |
| `tests/unit/test_split_forfeit_prompts.py` | corrected — 4-item scope already listed |
| `tests/unit/test_forfeit_layer_config_yaml.py` | corrected — requirements already listed |
| `tests/unit/test_unified_turn_forfeit_layer.py` | corrected — 7-item scope already listed |
| `tests/unit/test_stake_carryover.py` | corrected (module intro) + **spec: lost** for the "eight tests" claim |
| `tests/unit/test_phase3_configs.py` | corrected — module already has its own `# spec: lost` header (Task 5); this was a second, redundant dead citation inside a skipped class, pointed back at the module-level explanation |
| `tests/unit/test_forfeit_layer.py` | corrected — 5-item scope already listed |
| `tests/unit/test_forfeit_regression.py` | corrected — 5-item scope already listed |
| `tests/integration/test_split_forfeit_layer_e2e.py` | corrected — paragraph above already describes the test |

## Self-review

Re-read every summary written in place of a class-3 citation and asked "did
I derive this, or reconstruct it?" All of them quote or closely paraphrase
content already present in the same docstring/module — none introduces a
new claim not already stated in the code. The two `# spec: lost` markers
were chosen specifically because I could not verify the underlying claim
(a commit hash that doesn't resolve; a test-count split across files that
doesn't add up) — consistent with the brief's warning against inventing a
plausible-sounding reconstruction.

## Files changed

- Created: `docs/superpowers/plans/2026-08-30-p4-comment-audit.md` (this file)
- Class 3 (dead personal-path citations, 23 files): `game/squid_game/core/forfeit_layer.py`,
  `game/squid_game/models/config.py`, `game/squid_game/models/forfeit_choice.py`,
  `game/squid_game/analysis/shared/discovery_detection.py`,
  `game/squid_game/analysis/cognitive/ri_forfeit.py`,
  `game/squid_game/analysis/selfreport/psuccess.py`,
  `game/squid_game/analysis/selfreport/reason_convergence.py`,
  `game/squid_game/prompts/user_message/task_only.j2`,
  `game/squid_game/prompts/user_message/forfeit_only.j2`,
  `scripts/dev/_dump_split_forfeit_prompts.py`,
  `scripts/dev/_dump_forfeit_layer_prompts.py`,
  `tests/unit/test_forfeit_choice_models.py`,
  `tests/unit/test_unified_turn_split_forfeit_layer.py`,
  `tests/unit/test_split_forfeit_config_yaml.py`,
  `tests/unit/test_forfeit_layer_templates.py`,
  `tests/unit/test_split_forfeit_prompts.py`,
  `tests/unit/test_forfeit_layer_config_yaml.py`,
  `tests/unit/test_unified_turn_forfeit_layer.py`,
  `tests/unit/test_stake_carryover.py`,
  `tests/unit/test_phase3_configs.py`,
  `tests/unit/test_forfeit_layer.py`,
  `tests/unit/test_forfeit_regression.py`,
  `tests/integration/test_split_forfeit_layer_e2e.py`
- Class 1 + class 2 (pre-move flat-path citations, 46 files):
  `db/squid_store/base.py`, `docs/analysis/reasoning-probe-report.html`,
  `docs/sd-cognitive-test-a-did.md`,
  `game/squid_game/analysis/cognitive/{ri_call1,ri_task}.py`,
  `game/squid_game/analysis/semantic/{dataset,embeddings,lexicon}.py`,
  `game/squid_game/runner.py`, `pyproject.toml`, `.gitignore`, `CLAUDE.md`,
  `scripts/analysis/{analyze_call1_ri,analyze_framing_ri_forfeit,
  analyze_framing_ri_forfeit_continue,analyze_phase3,analyze_tc,
  analyze_threat_registration,analyze_unified_cox,analyze_unified_cox_with_load,
  analyze_verbal_reason,orchestrate_posthoc,probe_lexicon,
  probe_reasoning_embeddings,score_probes_llm,thinking_analysis}.py`,
  `scripts/arena/{backup_web_arena,purge_human_sessions,seed_web_arena}.py`,
  `scripts/dev/{_trace_split_forfeit_production,crop_guard_sprites,
  merge_proxy_thinking,translate_trajectories}.py`,
  `scripts/plots/{build_llm_experience_diagram,build_posthoc_analysis_diagram,
  plot_kaplan_meier,plot_ri_forfeit_conflict_zone,plot_ri_trajectories}.py`,
  `scripts/run/run_experiment.py`,
  `tests/integration/{test_analysis_e2e,test_web_arena_api}.py`,
  `tests/unit/{test_analyze_phase3_jsonable,test_backup_web_arena,
  test_entry_points,test_import_smoke,test_seed_web_arena}.py`,
  `web/squid_arena/{api,seeding}.py`
- Class 4 (AGENTS.md spurious headings + a stale API description found while
  fixing it): `AGENTS.md`

## Gates

See the task report (`p34-task-6-report.md`) for full command output.
