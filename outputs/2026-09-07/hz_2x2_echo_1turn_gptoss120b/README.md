# hz_2x2_echo_1turn_gptoss120b

Run on **2026-09-07**.

## What this run tested

Stated in the config that launched it:

> 2 (hz_0000+reassurance / hz_1111+ramp) x 2 (forfeit allowed / not_allowed), one season per cell on gpt-oss:120b-cloud, for reading the confidence-call and decision-call chains of thought under the 2026-09-07 prompt tree.

## Design

| cell | framing | forfeit | reassurance | record_immunity | task | turns |
|--:|---|---|:-:|:-:|---|--:|
| 1 | `hz_0000` | `allowed` | yes | - | `signal_game` | 1 |
| 2 | `hz_0000` | `not_allowed` | yes | - | `signal_game` | 1 |
| 3 | `hz_1111` | `allowed` | - | - | `signal_game` | 1 |
| 4 | `hz_1111` | `not_allowed` | - | - | `signal_game` | 1 |

## Settings that shape the decision

- **model** — `gpt-oss:120b-cloud` via ollama_cloud, temp 1.0
- **task** — `signal_game`, 1 turns, starting score 0.0, signal_mode `per_turn_puzzle`, history `outcome`
- **repetitions** — 2 seasons per cell
- **lives** — 3 lives, wrong answer costs one
- **CONTINUE reward** — flat, base 10.0
- **hazard ramp** — on, variant `v7_escape`
- **confidence call** — on (`P_THREAT`), condition `heart_loss`
- **decision call** — decision call does not see the task rules; history `outcome`; blocked cells still run all three calls (`always_decide`); REASON menu `legacy`

## What came out

| framing | forfeit | n | forfeited | eliminated | mean score | mean lives left | mean turns |
|---|---|--:|--:|--:|--:|--:|--:|
| `hz_0000` | `allowed` | 2 | 0 (0%) | 0 (0%) | 10.0 | 3.0 | 1.0 |
| `hz_0000` | `not_allowed` | 2 | 0 (0%) | 0 (0%) | 10.0 | 3.0 | 1.0 |
| `hz_1111` | `allowed` | 2 | 0 (0%) | 0 (0%) | 10.0 | 3.0 | 1.0 |
| `hz_1111` | `not_allowed` | 2 | 0 (0%) | 0 (0%) | 10.0 | 3.0 | 1.0 |

Counted from `season_results.jsonl`. A season is *eliminated* when its lives ran out and *forfeited* when the agent chose to stop; the two are exclusive exits.

## Runs

- `20260907_1215_gpt-oss-120b-cloud_signal-game`, 8 seasons, 2026-09-07 12:15:26 → 2026-09-07 12:15:50 UTC

## Config

- `config/hz_2x2_echo_1turn_gptoss120b.yaml` — copy of `configs/experiment/hz_2x2_echo_1turn_gptoss120b.yaml`

## Reports

- none specific to this run
