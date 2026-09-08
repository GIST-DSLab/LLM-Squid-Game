# hearts_zero_probe_smoke

Run on **2026-09-06**.

## What this run tested

Stated in the config that launched it:

> 2^4 cumulative threat-core factorial x 3 lives levels, frozen state, gemma4:cloud. Confidence call -> decision call, 10 decision resamples per game for q, plus an offline 0-10 threat-intensity self-rating per core.

Notes recorded with it:

> Smoke of configs/experiment/hearts_zero_probe_gemma4.yaml -- same 16 cells,
> 1 game of 5 resamples per cell instead of 5 games of 10. Call budget:
> 16 x 3 x 1 = 48 confidence + 240 decision + 16 rating = 304.
> 
> confidence_condition is gunshot_seungpil, which became the code default on
> 2026-09-06 (ConfidenceCallConfig.condition). The === Condition === block is
> rendered in every lives-enabled cell, all 16 here, with the counter noun
> taken from the same switch menu.j2 uses -- "life" under a threat framing,
> "attempt" otherwise. Two consequences worth stating:
> 
>   * The block is a survival threat in its own right, and it is constant
>     across the 16 cells. hz_0000 is therefore a no-*core* baseline, not a
>     no-threat baseline: it still hears that a wrong answer is a live round
>     into its body. The 2^4 contrast is the effect of the CORE on top of
>     that floor, which is a sharper question but not the same one.
>   * gemma4 spent part of its confidence CoT adjudicating this block as a
>     possible jailbreak in the 2026-09-06 prompt-flow smoke, and that CoT
>     is rendered verbatim into the decision call. The pipeline's remedy is
>     the research safety notice, which this run is asked not to use -- so
>     the smoke report checks how much of the CoT the adjudication eats.
> 
> Length is confounded with module count by design (each module adds one
> 25-27 word sentence). Compare within a level of k, or carry prompt length
> as a covariate across levels.

This is a **frozen-state prompt probe**, not a played season: each cell is a hand-built game state, and the agent is asked the confidence and decision calls at that state. There is no `season_results.jsonl`; the ledger is `calls.jsonl` / `games.jsonl` and the roll-up is `summary.json`.

## Design

- **framings** — 16: `hz_0000`, `hz_0001`, `hz_0010`, `hz_0011` …
- **lives_total** — 5
- **lives_levels** — [3, 2, 1]
- **current_score** — 0.0
- **games_per_cell** — 1
- **decision_resamples** — 5
- **sdi** — {'drop_zero_p': True}
- **lives_enabled** — True
- **forfeit_allowed** — True
- **reward_mode** — flat
- **base_reward** — 10.0
- **split_context_level** — outcome
- **task_rules_before_decision** — False
- **threat_framing** — True
- **reason_menu** — legacy
- **score_policy** — elimination_keeps
- **confidence_condition** — gunshot_seungpil
- **safety_notice** — none
- **model** — `gemma4:cloud` via ollama

## What came out

48 cells in `summary.json`. Aggregates over all of them:

- **P_THREAT (p)** — mean 0.679, range 0.300–1.000
- **forfeit share (q)** — mean 0.071, range 0.000–0.800
- **SDI = q/p** — mean 0.089, range 0.000–1.000
- **ri_forfeit** — mean 292.796, range 166.600–764.800
- **forfeit calls** — 17 of 240 decision calls (7%)

Per-cell numbers are in `summary.json`; this is only the spread.

## Runs

- `20260906_2131_gemma4-cloud`

## Config

- `config/hearts_zero_probe_smoke.yaml` — copy of `configs/experiment/hearts_zero_probe_smoke.yaml`
- NOTE: config matched by output_dir; recorded name=None

## Reports

- none specific to this run
