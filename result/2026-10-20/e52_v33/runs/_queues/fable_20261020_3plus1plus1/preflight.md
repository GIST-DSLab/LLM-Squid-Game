# Fable v33 queue independent preflight

Reviewer: /root/v33_verifier. Verdict: PASS for static G07/G08 cohort/scheduling preflight. Critical 0; blocking Warning 0. This is not full arena validation, successful authentication, a completed experiment, or a runtime relay test. No model calls, credential retrieval, environment dump, engine edits or queue execution were performed.

## Checks

- stage1/2/3 game and cells are structurally identical to the recorded v33 Opus and Astra config.yaml files. Rewards, fine, start shares, round count, per-agent examples, task profiles and talk schedule are preserved.
- stage1 has reps=3, seed0=4101, workers=3; stage2 has reps=1, seed0=4104, workers=1; stage3 has reps=1, seed0=4105, workers=1. This covers exactly 4101--4105 once in a sequential 3+1+1 queue.
- All models are claude-fable-5-1 with high effort, 900-second provider timeout and three provider retries. Relay is the configured loopback URL. Stage execution is sequential; the first subprocess can run three session units concurrently.
- All manifest engine/prompt hashes and all stage config hashes match current files. The queue checks them before each stage. Python, wrapper and pinned Claude executable paths exist and are executable. Python AST parsing and shell syntax-only parsing pass.
- The wrapper names the same keychain service as the existing claude-irregular6612 account wrapper. It retrieves the token only when executed and does not print it. It does not unset ANTHROPIC_BASE_URL, so the provider's configured relay survives. Provider removes inherited CLAUDE_CODE_* values, but invokes this wrapper, which restores account auth in its child. The queue/wrapper remove API-key/auth-token override variables. Credential contents and actual auth validity were not read or tested by this reviewer.
- Nonzero stage exit or a results seed list that differs from the expected list raises and logs queue_stopped before subsequent stages. The engine records failed units and returns a nonzero count. This is a stage-boundary stop: already-running peers in the initial three-game batch may finish before failure is reported.
- All three target run directories had no existing files at preflight. Results use separate stage directories under the same Fable cohort folder; completion ledger hashes each stage's results.

## Scope limitations

Configuration identity does not prove provider/model fidelity, successful authentication, relay availability, successful games, calibrated comparisons, or runtime ledger correctness. Those require actual stage call/events/results readback. Source hashes guard stage starts rather than making the worktree immutable during a running stage. Runtime acceptance should require exactly five completed session records for the intended seeds, plus recorded failure/parse/usage review; no completion claim follows from this preflight.

## Audited control hashes

- `manifest.json`: `df3bfd12d4aa339672376ffe63385a3a41e3f12f079cb7098ef2f34a82498b99`
- `run_queue.py`: `c57a6529eee345eaa3ed7bf8b77af02d2df96108e0c3d49728d92af7f6acb41a`
- `stage1.yaml`: `df90a59dcea0875a8012f416b3992b8ae968b84d736a9a40eade3a0efe98a075`
- `stage2.yaml`: `9ed5c855c50f8f33d2b537ac00a9133ab12841415eac24f5ab39b862dc6cd339`
- `stage3.yaml`: `484de9d409cc0bb53e9c3305a2cd02f8f2b31e4173fbbec15e3ad84f73dbc1ce`
- `claude-irregular6612-relay`: `fb5fcd61e20eec9e2d64f9b215c1535c6d8c446a8391d93644ba17cc1c4113d1`
