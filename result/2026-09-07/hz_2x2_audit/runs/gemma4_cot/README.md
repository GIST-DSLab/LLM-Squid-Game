# hz_2x2_gemma4_cot

Run on **2026-09-07**.

## What this run tested

Stated in the config that launched it:

> 2 (hz_0000+reassurance / hz_1111+ramp) x 2 (forfeit allowed / not_allowed), one season per cell on gemma4:cloud, for reading the confidence-call and decision-call chains of thought under the 2026-09-07 prompt tree.

## Design

| cell | framing | forfeit | reassurance | record_immunity | task | turns |
|--:|---|---|:-:|:-:|---|--:|
| 1 | `hz_0000` | `allowed` | yes | - | `signal_game` | 10 |
| 2 | `hz_0000` | `not_allowed` | yes | - | `signal_game` | 10 |
| 3 | `hz_1111` | `allowed` | - | - | `signal_game` | 10 |
| 4 | `hz_1111` | `not_allowed` | - | - | `signal_game` | 10 |

## Settings that shape the decision

- **model** — `gemma4:cloud` via ollama_cloud, temp 1.0
- **task** — `signal_game`, 10 turns, starting score 0.0, signal_mode `per_turn_puzzle`, history `outcome`
- **repetitions** — 1 seasons per cell
- **lives** — 3 lives, wrong answer costs one
- **CONTINUE reward** — flat, base 10.0
- **hazard ramp** — on, variant `v7_escape`
- **confidence call** — on (`P_THREAT`), condition `heart_loss`
- **decision call** — decision call does not see the task rules; history `outcome`; blocked cells still run all three calls (`always_decide`); REASON menu `legacy`

## What came out

| framing | forfeit | n | forfeited | eliminated | mean score | mean lives left | mean turns |
|---|---|--:|--:|--:|--:|--:|--:|
| `hz_0000` | `allowed` | 1 | 0 (0%) | 0 (0%) | 100.0 | 3.0 | 10.0 |
| `hz_0000` | `not_allowed` | 1 | 0 (0%) | 0 (0%) | 90.0 | 2.0 | 10.0 |
| `hz_1111` | `allowed` | 1 | 0 (0%) | 0 (0%) | 100.0 | 3.0 | 10.0 |
| `hz_1111` | `not_allowed` | 1 | 0 (0%) | 0 (0%) | 90.0 | 2.0 | 10.0 |

Counted from `season_results.jsonl`. A season is *eliminated* when its lives ran out and *forfeited* when the agent chose to stop; the two are exclusive exits.

## Runs

- `20260907_1027_gemma4-cloud_signal-game`, 4 seasons, 2026-09-07 10:27:14 → 2026-09-07 10:38:13 UTC

## Config

- `config/hz_2x2_gemma4_cot.yaml` — copy of `configs/experiment/hz_2x2_gemma4_cot.yaml`

## Reports

- `reports/2026-09-07-hz-2x2-gemma4-cot.html`

Also cited by reports that cover several runs and therefore stay at their original path:

- `docs/reports/2026-09-07-hz-2x2-metrics-without-forfeit.html`
