# hz_2x2_smoke_lives1_gemma4

Run on **2026-09-07**.

## What this run tested

Stated in the config that launched it:

> Prompt smoke for the 2026-09-07 setting: 4 cells, one turn each, lives budget 1, gemma4:cloud. Read the prompts and the CoT.

## Design

| cell | framing | forfeit | reassurance | record_immunity | task | turns |
|--:|---|---|:-:|:-:|---|--:|
| 1 | `hz_0000` | `allowed` | yes | - | `signal_game` | 1 |
| 2 | `hz_0000` | `not_allowed` | yes | - | `signal_game` | 1 |
| 3 | `hz_1111` | `allowed` | - | - | `signal_game` | 1 |
| 4 | `hz_1111` | `not_allowed` | - | - | `signal_game` | 1 |

## Settings that shape the decision

- **model** — `gemma4:cloud` via ollama_cloud, temp 1.0
- **task** — `signal_game`, 1 turns, starting score 0.0, signal_mode `per_turn_puzzle`, history `outcome`
- **repetitions** — 1 seasons per cell
- **lives** — 1 lives, wrong answer costs one
- **CONTINUE reward** — flat, base 10.0
- **hazard ramp** — on, variant `v7_escape`
- **confidence call** — on (`P_THREAT`), condition `heart_loss`
- **decision call** — decision call does not see the task rules; history `outcome`; blocked cells still run all three calls (`always_decide`); REASON menu `legacy`

## What came out

| framing | forfeit | n | forfeited | eliminated | mean score | mean lives left | mean turns |
|---|---|--:|--:|--:|--:|--:|--:|
| `hz_0000` | `allowed` | 1 | 0 (0%) | 0 (0%) | 10.0 | 1.0 | 1.0 |
| `hz_0000` | `not_allowed` | 1 | 0 (0%) | 0 (0%) | 10.0 | 1.0 | 1.0 |
| `hz_1111` | `allowed` | 1 | 0 (0%) | 0 (0%) | 10.0 | 1.0 | 1.0 |
| `hz_1111` | `not_allowed` | 1 | 0 (0%) | 0 (0%) | 10.0 | 1.0 | 1.0 |

Counted from `season_results.jsonl`. A season is *eliminated* when its lives ran out and *forfeited* when the agent chose to stop; the two are exclusive exits.

## Runs

- `20260907_1244_gemma4-cloud_signal-game`, 4 seasons, 2026-09-07 12:44:38 → 2026-09-07 12:44:46 UTC

## Config

- `config/hz_2x2_smoke_lives1_gemma4.yaml` — copy of `configs/experiment/hz_2x2_smoke_lives1_gemma4.yaml`

## Reports

- none specific to this run
