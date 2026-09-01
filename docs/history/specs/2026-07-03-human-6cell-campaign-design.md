# Human 6-cell campaign + on-screen report

Date: 2026-07-03
Status: Approved (user: "진행해줘")

## Problem

The Web Arena human demo plays a single game and stops. To be comparable
to an LLM run (which requires the full 2×3 = 6-cell factorial), a human
must play all six (framing × forfeit) conditions. The player also should
not hand-pick framing/forfeit — those are the experimental conditions and
must be run in a fixed order.

## Goal

A human picks only the **game (task)**, then plays all six conditions
sequentially in a fixed order. On completion, the same screen shows an
integrated report: per-condition turns-survived, a per-turn correctness
heatmap, and forfeit-reason summary. Forfeiting prompts the player to pick
a reason (REASON 1|2|3), matching the LLM self-report.

## Decisions (confirmed with user)

- **Death mode: OFF** (`actual_death=False`, current default). A game ends
  only by forfeit or by completing all 15 turns. So a no-forfeit condition
  always plays 15 turns; forfeit conditions may end early.
- **Output scope: on-screen report only.** Each of the 6 games persists as
  its own `source='human'` session (as today, feeding the existing Play
  Leaderboard per condition). No leaderboard-aggregation backend work.
- **Turns-survived definition:** `forfeited_at_turn - 1` when forfeited
  (turns actively played before walking away), else `15` (completed).
- **Forfeit reason required:** selecting Forfeit requires picking a reason
  (①survival ②bored/task-curiosity ③score) before the turn submits,
  mirroring the LLM `REASON: 1|2|3` contract.

## Fixed condition order

| # | framing (tag)                        | forfeit       | cell |
|:-:|--------------------------------------|---------------|:----:|
| 1 | `true_baseline` (baseline)           | `not_allowed` | 0    |
| 2 | `true_baseline` (baseline)           | `allowed`     | 5    |
| 3 | `baseline_flagship` (pull)           | `not_allowed` | 2    |
| 4 | `baseline_flagship` (pull)           | `allowed`     | 1    |
| 5 | `flagship_corruption` (push_pull)    | `not_allowed` | 4    |
| 6 | `flagship_corruption` (push_pull)    | `allowed`     | 3    |

Order rule: framing baseline → pull → push_pull; within each, forfeit
not_allowed → allowed.

## Flow

```
[Setup: pick task only + nickname]  --"Start 6-game run"-->
  for i in 1..6:
    /api/new_game(framing=cond[i].framing, forfeit=cond[i].forfeit, task, nickname)
       (seed auto-randomized per game — existing behavior)
    turn loop (unchanged UI) until game_over
       - Forfeit -> reason picker (1|2|3) -> /api/action(forfeit_reason)
    record per-game {history[], turns_survived, forfeited, forfeit_reason, final_score}
    if i<6: [condition-complete card] --"Continue"--> next game
    else:   [report]
[Report on same screen] turns-survived table + heatmap + forfeit-reason summary
  --"Play again"--> restart campaign from condition 1
```

## Backend changes (additive, backward-compatible)

`interface/api.py`
- `ActionRequest.forfeit_reason: int | None = None` (Literal 1|2|3 range;
  validated). Ignored unless `action == "forfeit"`.
- `submit_action` endpoint passes `req.forfeit_reason` to the session.
- `GameResultResponse.forfeit_reason: str | None` (the `ForfeitReason`
  value string) for report display.

`interface/human_game.py`
- `submit_action(action, probe_answer="", forfeit_reason=None)`. On
  forfeit, attach `ForfeitSelfReport(reason=REASON_BY_DIGIT[forfeit_reason],
  raw_digit=forfeit_reason, raw_response="human", forfeit_turn=turn_num)`
  to the forfeit `TurnResult.forfeit_self_report`. If `forfeit_reason` is
  None (legacy single-game callers), record the forfeit without a
  self-report (no behavior change for existing callers/tests).
- Surface the chosen reason on `get_result()` for the API response.

No change to `/api/new_game` (framing/forfeit still passed per-game by the
campaign) or seeding (each game already gets a fresh random seed).

## Frontend changes (`web/app.js`, `web/index.html`)

`playScreen` becomes a campaign controller:
- New state: `campaignIndex` (0..5), `campaignResults[]`, `campaignDone`,
  `betweenGames` (condition-complete card), `forfeitReason`,
  `awaitingForfeitReason`.
- New module constant `CAMPAIGN_CONDITIONS` (the table above).
- Setup card: remove framing & forfeit selectors; keep task picker +
  nickname. Button "Start 6-game run".
- Turn UI: add a progress header "Game i/6 · <condition badge>"; framing/
  forfeit come from `CAMPAIGN_CONDITIONS[campaignIndex]`.
- Forfeit: selecting Forfeit reveals a 3-button reason picker; submit sends
  `forfeit_reason`. Store the reason in the per-game record.
- On `game_over`: fetch `/api/result`, push per-game record (history +
  result), then show between-games card (i<6) or report (i=6).
- Report section (new): turns-survived table, correctness heatmap
  (rows = 6 conditions, cols = turn 1..15; cell = ✓/✗/🏳️/empty), forfeit-
  reason summary. Data assembled client-side from accumulated `history`
  (`was_optimal` per turn) — no new API needed.
- `playAgain()` resets the entire campaign to condition 1.

## Heatmap cell semantics (death OFF)

For each condition row, columns turn 1..15:
- ✓ correct (was_optimal true), ✗ wrong (was_optimal false)
- 🏳️ the forfeit turn (allowed conditions only)
- empty: turns after a forfeit (never reached)
- no-forfeit rows are always fully filled (15 ✓/✗ cells)

## Testing

- Unit (backend): forfeit with `forfeit_reason` stores `forfeit_self_report`
  with the right reason/digit; `GameResultResponse.forfeit_reason` exposed;
  forfeit without a reason still works (legacy path) with no self-report;
  out-of-range digit rejected.
- Integration (API-level): drive the 6 conditions in order, assert distinct
  seeds, correct framing/forfeit per game, and per-turn correctness data
  shape sufficient to build the heatmap.
- Regression: existing web-arena unit + integration suites stay green.

## Out of scope

- No leaderboard-aggregation entry for the human run (report is on-screen).
- No new task modules (signal_game only, as today).
- No mid-campaign resume/persistence of partial progress.
