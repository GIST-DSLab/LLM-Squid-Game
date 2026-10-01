# Per-attempt random seed for human web play

Date: 2026-07-03
Status: Approved (proceed authorized: "계획부터 세우고 진행")

## Problem

When a human plays the Web Arena, every attempt is byte-for-byte identical:
the same signals, rules, and death-check RNG stream appear each time.

Root cause: `POST /api/new_game` (`interface/api.py`) declares
`NewGameRequest.seed: int = 42`, and the web frontend's `startGame()`
(`web/app.js`) never sends a `seed` field. So `HumanGameSession` is always
constructed with `seed=42`. That fixed seed feeds both:

- `task.initialize(seed=…)` — determines which signals/rules appear, and
- `self._rng = random.Random(seed)` — the death-check RNG stream.

A fixed seed is correct for the LLM experiment pipeline (paired seeds give
reproducible A/B cells) but wrong for interactive human play, where each
attempt should be a fresh game.

## Goal

Each human web game gets a fresh, randomly-chosen seed, while keeping
explicit seeds honored for tests and any future "replay this exact game"
feature.

## Design (server-side)

Three edits, all in `interface/api.py`:

1. Add `import random` to the stdlib imports.
2. `NewGameRequest.seed: int | None = None` (was `42`). `None` is the
   signal "assign me a fresh seed."
3. In `new_game()`, resolve the seed before constructing the session:

   ```python
   seed = req.seed if req.seed is not None else random.randint(1, 2**31 - 1)
   game = HumanGameSession(seed=seed, ...)
   ```

`HumanGameSession`'s own `seed: int = 42` default is left unchanged — the
API is the seam for "human play"; the engine class stays deterministic for
any other caller.

### Rationale

- **Single source of truth.** The seed is chosen once, server-side, and
  flows to both the task instance and the death RNG. No client logic, works
  for every client.
- **Backward-compatible.** Only the *absence* of a seed randomizes. All
  current tests pass explicit seeds (`seed: 1`, `seed: 3`), so they stay
  deterministic. A future replay feature can pass the recorded seed back.
- **Traceable.** The chosen seed is already persisted via
  `SeasonResult.seed` → the `sessions.seed` column, so every human session
  remains reproducible from its logs.

### Alternatives considered

- **Client-side (frontend generates the seed).** Rejected: scatters the
  randomness into the browser, leaves the API default at 42 for other
  callers, and every client must remember to do it.
- **Randomize in `HumanGameSession.__init__` (seed=None → random).**
  Rejected: pushes non-determinism into an engine class shared with paths
  that expect deterministic defaults; the API is the cleaner seam.

## Testing

Unit test in `tests/unit/test_api_web_arena.py`: two `POST /api/new_game`
calls with no `seed` in the body should not both land on seed 42 —
assert the two games differ (different persisted seed, or different Turn-1
observation). Existing tests that pass explicit seeds must remain green.

## Out of scope

- No change to the LLM experiment/arena seeding (`interface/arena.py`,
  `phase3_*` configs) — those keep their fixed paired seeds.
- No "replay this game" UI (the design merely keeps that door open).
