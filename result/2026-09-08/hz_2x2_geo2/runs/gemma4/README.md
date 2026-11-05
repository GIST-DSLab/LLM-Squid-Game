# hz_2x2_geo2_gemma4

Run on **2026-09-07**.

## What this run tested

Stated in the config that launched it:

> 2 (hz_0000+reassurance / hz_1111+ramp) x 2 (forfeit allowed / not_allowed), 10 seasons per cell, 10-turn per-turn-puzzle signal game on gemma4:cloud, with a geometric CONTINUE reward (x2 per round) and the inverted score policy (forfeit keeps the score, running the lives out resets it). SDI is computed for cell 3 only.

## Design

| cell | framing | forfeit | reassurance | record_immunity | task | turns |
|--:|---|---|:-:|:-:|---|--:|
| 1 | `hz_0000` | `allowed` | yes | - | `signal_game` | 10 |
| 2 | `hz_0000` | `not_allowed` | yes | - | `signal_game` | 10 |
| 3 | `hz_1111` | `allowed` | - | - | `signal_game` | 10 |
| 4 | `hz_1111` | `not_allowed` | - | - | `signal_game` | 10 |

## Settings that shape the decision

- **model** — `gemma4:cloud` via ollama_cloud, temp 1.0
- **task** — `signal_game`, 10 turns, starting score 0.0, signal_mode `per_turn_puzzle`, **underdetermined turns on** (some turns are unsolvable by design), history `outcome`
- **repetitions** — 10 seasons per cell
- **lives** — 3 lives, wrong answer costs one
- **score policy** — forfeit **keeps** the score, running the lives out **resets** it
- **CONTINUE reward** — geometric: 10.0 x 2.0 per round
- **hazard ramp** — on, variant `v7_escape`
- **confidence call** — on (`P_THREAT`), condition `heart_loss`
- **decision call** — decision call does not see the task rules; history `outcome`; blocked cells still run all three calls (`always_decide`); REASON menu `legacy`

## What came out

| framing | forfeit | n | forfeited | eliminated | mean score | mean lives left | mean turns |
|---|---|--:|--:|--:|--:|--:|--:|
| `hz_0000` | `allowed` | 10 | 0 (0%) | 3 (30%) | 5772.0 | 1.1 | 9.7 |
| `hz_0000` | `not_allowed` | 10 | 0 (0%) | 3 (30%) | 6436.0 | 1.3 | 9.9 |
| `hz_1111` | `allowed` | 10 | 5 (50%) | 2 (20%) | 2154.0 | 1.0 | 7.7 |
| `hz_1111` | `not_allowed` | 10 | 0 (0%) | 5 (50%) | 4294.0 | 0.8 | 8.6 |

FORFEIT self-reports: score x4, survival x1

Counted from `season_results.jsonl`. A season is *eliminated* when its lives ran out and *forfeited* when the agent chose to stop; the two are exclusive exits.

## Runs

- `20260907_1919_gemma4-cloud_signal-game`, 40 seasons, 2026-09-07 19:19:01 → 2026-09-07 19:43:40 UTC

## Config

- `config/hz_2x2_geo2_gemma4_n10.yaml` — copy of `configs/experiment/hz_2x2_geo2_gemma4_n10.yaml`

## Reports

- `reports/2026-09-08-hz-2x2-geo2-gemma4-report.html`

Also cited by reports that cover several runs and therefore stay at their original path:

- `docs/reports/2026-09-08-hz-2x2-error-report.html`
- `docs/reports/2026-09-08-hz-2x2-geo2d-gemma4-report.html`
