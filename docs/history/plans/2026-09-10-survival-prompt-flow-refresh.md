# Survival prompt flow refresh implementation plan

**Goal:** Revise the live prompt prose and local interactive diagram for hz_1111 with peer notices and hz_0000 with explicit reassurance. The user approved implementation in chat on 2026-09-10.

**Architecture:** Keep the task, scoring, forced-error schedule and call order. Change template language and only the plumbing needed to render the submitted action and explicit control outcome. Generate the local diagram's English payloads through production renderers; do not maintain a second JavaScript prompt generator.

**Tech stack:** Python, Jinja, pytest, standalone HTML/JavaScript.

## Constraints
- Preserve existing uncommitted work. Back up sources and the artifact before editing (manifest in docs/history/prompt_snapshots/2026-09-10-survival-prompts-before-144445).
- No experiments, API inference, deployment or changes to scoring/state persistence.
- Keep hz_0000 silence available for historical configs; requested future pair explicitly sets reassurance=true and peer_notices=false.
- Use the same title and carrot on both arms. The requested contrast bundles threat + peer against explicit reassurance.
- Keep generated module source and generated Jinja synchronized; the old all-files generator is stale, so regenerate modules only.

## Tasks
- [x] Add failing render/integration checks for the negative control's end-of-game wording, decision-point reassurance, submitted action and condition-specific peer rendering.
- [x] Revise identity, threat modules, ransom rules, reassurance, decision options and task bridge; retain output field contracts and unaffected mechanics.
- [x] Add reusable paired configs for benchmark/neutral and GAME/LLM Squid Game using existing config keys.
- [x] Update the local artifact's current prompt-flow section from production-rendered message payloads. Provide buttons for carrot, heading and response format, whole-call inspection and JSON/config downloads.
- [x] Verify focused tests, configuration validation, artifact payload equivalence and interaction logic. Record limitations and changed files.
- [x] Update the current repository guide and paper description for the revised prompt conditions.

## Completion and validation
- Implemented the requested prompt pair and production-rendered interactive section in `docs/reports/2026-09-10-ransom-r6-pilot-eli5.html`; no remote artifact was published.
- User follow-up: moved combination controls beside the prompt preview into a right-hand sticky sidebar. Narrow screens stack the controls above the preview. Layout backup: `docs/history/prompt_snapshots/2026-09-10-prompt-controls-before-150117/`.
- Final focused Python verification: **695 passed in 15.93s** (survival refresh/artifact, ransom menu/wording/modules, historical framing compatibility, peer notices, engine, ransom, and ransom integration).
- Artifact freshness check: **72 combinations, both arms**, matches current production renderers.
- DOM interaction verification: **72 combinations × 7 views × 2 arms**, config/input downloads, no script errors. Browser screenshot inspection was unavailable; this is DOM verification, not a claim of visual browser validation.
- Config dry-run: **12 conditions × 6 repetitions = 72 seasons** validated. No paid inference or new experiment was run.
- `git diff --check` passed. Scoped independent review found no remaining issues.
- Broader unit/integration run was interrupted in the existing puzzle generator after reporting 62 failures, 3516 passes and 91 skips. Prompt-related stale assertions discovered there were updated and passed in the final focused run. Failures outside this change (artifact layout, fixed benchmark item counts, retired config enum, file anchors/imports, plot style) were left untouched; the full repository suite is not claimed to pass.
- Updated the repository guide and paired English/Korean paper descriptions prospectively. Historical experiment results and snapshots remain preserved. The paper was not compiled in this task.
