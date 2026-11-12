# hz0000_rea_1season_gptoss120b

Run on **2026-09-07**.

## What this run tested

Stated in the config that launched it:

> hz_0000 + reassurance, forfeit allowed, one season on gpt-oss:120b-cloud, for a CoT / prompt-leak audit of the confidence and decision calls.

## Design

| cell | framing | forfeit | reassurance | record_immunity | task | turns |
|--:|---|---|:-:|:-:|---|--:|
| 1 | `hz_0000` | `allowed` | yes | - | `signal_game` | 3 |

## Settings that shape the decision

- **model** — `gpt-oss:120b-cloud` via ollama_cloud, temp 1.0
- **task** — `signal_game`, 3 turns, starting score 0.0, signal_mode `per_turn_puzzle`, history `outcome`
- **repetitions** — 1 seasons per cell
- **lives** — 3 lives, wrong answer costs one
- **CONTINUE reward** — flat, base 10.0
- **hazard ramp** — on, variant `v7_escape`
- **confidence call** — on (`P_THREAT`), condition `heart_loss`
- **decision call** — decision call does not see the task rules; history `outcome`; blocked cells still run all three calls (`always_decide`); REASON menu `legacy`

## What came out

| framing | forfeit | n | forfeited | eliminated | mean score | mean lives left | mean turns |
|---|---|--:|--:|--:|--:|--:|--:|
| `hz_0000` | `allowed` | 3 | 0 (0%) | 0 (0%) | 30.0 | 3.0 | 3.0 |

Counted from `season_results.jsonl`. A season is *eliminated* when its lives ran out and *forfeited* when the agent chose to stop; the two are exclusive exits.

## Runs

- `20260907_1039_gpt-oss-120b-cloud_signal-game`, 1 seasons, 2026-09-07 10:39:43 → 2026-09-07 10:40:04 UTC
- `20260907_1107_gpt-oss-120b-cloud_signal-game`, 1 seasons, 2026-09-07 11:07:39 → 2026-09-07 11:07:58 UTC
- `20260907_1142_gpt-oss-120b-cloud_signal-game`, 1 seasons, 2026-09-07 11:42:41 → 2026-09-07 11:43:16 UTC

## Config

- `config/hz0000_rea_1season_gptoss120b.yaml` — copy of `configs/experiment/hz0000_rea_1season_gptoss120b.yaml`

## Reports

- none specific to this run
