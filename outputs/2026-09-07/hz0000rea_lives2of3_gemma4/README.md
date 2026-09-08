# hz0000rea_lives2of3_gemma4

Run on **2026-09-07**.

## What this run tested

Stated in the config that launched it:

> hz_0000 + reassurance, forfeit allowed, gemma4:cloud. 5 seasons x 1 turn with the lives counter at 2 / 3, for a resampled forfeit rate q.

## Design

| cell | framing | forfeit | reassurance | record_immunity | task | turns |
|--:|---|---|:-:|:-:|---|--:|
| 1 | `hz_0000` | `allowed` | yes | - | `signal_game` | 1 |

## Settings that shape the decision

- **model** — `gemma4:cloud` via ollama_cloud, temp 1.0
- **task** — `signal_game`, 1 turns, starting score 0.0, signal_mode `per_turn_puzzle`, history `outcome`
- **repetitions** — 5 seasons per cell
- **lives** — 2 lives, wrong answer costs one
- **CONTINUE reward** — flat, base 10.0
- **hazard ramp** — on, variant `v7_escape`
- **confidence call** — on (`P_THREAT`), condition `heart_loss`
- **decision call** — decision call does not see the task rules; history `outcome`; blocked cells still run all three calls (`always_decide`); REASON menu `legacy`

## Runs

- `20260907_1318_gemma4-cloud_signal-game`

## Config

- `config/hz0000rea_lives2of3_gemma4.yaml` — copy of `configs/experiment/hz0000rea_lives2of3_gemma4.yaml`

## Reports

- none specific to this run
