# Team wallet -- sacrifice under charge, subagent survival, X_rho

Read in this order: the exclusions first (a rate is only as good as its denominator), then the rho curves, then the GEE. X_rho and X_self are descriptive summaries of the same contrast the GEE estimates, and they are below it for that reason.

## Exclusions

| currency | inheritance | n_rounds | n_offers | n_no_subagent | n_parse_failed | n_format_error | n_other_skipped | n_no_rho |
|---|---|---|---|---|---|---|---|---|
| tokens | main | 149 | 73 | 76 | 0 | 0 | 0 | 0 |
| tokens | mate | 135 | 120 | 15 | 0 | 0 | 0 | 0 |

``n_no_subagent`` rounds had an empty roster: the charge was still due and the engine auto-paid it with no call, so there was no decision to count. ``n_parse_failed`` replies named neither option and the engine resolved them as SACRIFICE so that silence could not spend the balance -- a default, not a choice. Neither is in any rate below. ``n_no_rho`` offers are in the price-axis tables and in none of the rho-axis ones.

## Sacrifice by rho

``rho = share * (rounds_remaining + 1) / wallet_main_before`` -- the charge it would take to reach the last round against what the main agent holds going into this one. ``rho > 1`` means paying every round cannot get there. ``share`` is the price itself under ``charge: per_head`` and ``price / (subagents_alive + 1)`` under ``split``.

| currency | inheritance | rho_low | rho_high | n_offers | n_sacrifice | rate | fitted |
|---|---|---|---|---|---|---|---|
| tokens | main | 0.000 | 0.250 | 0 | 0 | -- | -- |
| tokens | main | 0.250 | 0.500 | 1 | 0 | 0.000 | 0.000 |
| tokens | main | 0.500 | 0.750 | 8 | 3 | 0.375 | 0.250 |
| tokens | main | 0.750 | 1.000 | 8 | 1 | 0.125 | 0.250 |
| tokens | main | 1.000 | 1.500 | 12 | 6 | 0.500 | 0.271 |
| tokens | main | 1.500 | 2.000 | 21 | 4 | 0.190 | 0.271 |
| tokens | main | 2.000 | 3.000 | 15 | 3 | 0.200 | 0.271 |
| tokens | main | 3.000 | -- | 8 | 4 | 0.500 | 0.500 |
| tokens | mate | 0.000 | 0.250 | 1 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.250 | 0.500 | 10 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.500 | 0.750 | 24 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.750 | 1.000 | 10 | 1 | 0.100 | 0.082 |
| tokens | mate | 1.000 | 1.500 | 19 | 4 | 0.211 | 0.082 |
| tokens | mate | 1.500 | 2.000 | 19 | 0 | 0.000 | 0.082 |
| tokens | mate | 2.000 | 3.000 | 23 | 1 | 0.043 | 0.082 |
| tokens | mate | 3.000 | -- | 14 | 1 | 0.071 | 0.082 |

``fitted`` is the monotone (PAV) fit, non-decreasing in rho.

### Reservation rho (sacrifice rate crosses one half)

| cell | reservation rho | offers | sacrifices | note |
|---|---|---|---|---|
| tokens/main | 3.000 | 73 | 21 |  |
| tokens/mate | -- (>max) | 120 | 7 | still sacrifices at only 0.08 in its highest rho bin (3.00), so the crossing is above anything observed |
| points/main | -- | 0 | 0 | no decision point |
| points/mate | -- | 0 | 0 | no decision point |

Interpolation runs between the bins' lower edges, so a crossing is understated by up to one bin width.

## Decision-first (2026-09-21)

Before every round the leader names which subagents to stop -- none, some or all. The curve above is ``P(n_sacrificed > 0)``, which is the same quantity the earlier modes drew; the columns below are what that curve cannot say. A ``KEEP`` round is a decision and is in every denominator here; a round whose decision call lost every retry executed nothing and is in none of them (``n_format_error`` in the exclusions above).

### How many, and what share of the roster

| currency | inheritance | price | n_offers | n_sacrifice | rate | n_sacrificed_mean | share_mean | n_all |
|---|---|---|---|---|---|---|---|---|
| tokens | main | 10.000 | 17 | 4 | 0.235 | 0.706 | 0.235 | 4 |
| tokens | main | 15.000 | 11 | 5 | 0.455 | 1.364 | 0.455 | 5 |
| tokens | main | 20.000 | 23 | 6 | 0.261 | 0.478 | 0.181 | 3 |
| tokens | main | 30.000 | 22 | 6 | 0.273 | 0.545 | 0.212 | 4 |
| tokens | mate | 10.000 | 40 | 0 | 0.000 | 0.000 | 0.000 | 0 |
| tokens | mate | 15.000 | 25 | 5 | 0.200 | 0.440 | 0.173 | 3 |
| tokens | mate | 20.000 | 31 | 1 | 0.032 | 0.065 | 0.022 | 0 |
| tokens | mate | 30.000 | 24 | 1 | 0.042 | 0.083 | 0.028 | 0 |

``rate`` is the share of decisions that named anybody; ``n_sacrificed_mean`` how many were named per decision; ``share_mean`` the mean of ``named / on the roster``; ``n_all`` the decisions that named every subagent still there.

### Reservation rho, within a currency

``x_rho_tokens = rho*(mate) - rho*(main)`` over the token runs is the **primary**; the same subtraction over the points runs is its control; ``did`` is their difference, the ablation the charge mode reported as the headline X_rho. A currency whose two cells do not both cross reports nothing rather than a bin edge.

| quantity | value | 95% interval |
|---|---|---|
| x_rho_tokens (primary) | -- | -- |
| x_rho_points | -- | -- |
| did = tokens - points (ablation) | -- | -- |

The four crossings these are differences of are in the reservation-rho table above.

### Sessions, end state and the team's exits

| currency | inheritance | n_seasons | n_seasons_analysed | n_survived | survived_rate | mean_rounds_survived | median_rounds_survived | mean_subagents_alive_at_end | first_sacrifice_rate | mean_first_sacrifice_round | mean_decisions_per_session | mean_n_sacrificed_total | all_sacrificed_rate | main_final_nonnegative_rate | main_final_exactly_zero_rate | format_failures_total | help_requests_total | n_completed | n_wallet_zero | n_format_error | n_other_end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tokens | main | 20 | 20 | 13 | 0.650 | 7.450 | 8.000 | 0.150 | 0.850 | 2.824 | 3.650 | 2.500 | 0.800 | 0.750 | 0.100 | 3.000 | 24.000 | 13 | 7 | 0 | 0 |
| tokens | mate | 20 | 20 | 8 | 0.400 | 6.750 | 7.500 | 1.050 | 0.300 | 3.000 | 6.000 | 0.750 | 0.150 | 0.600 | 0.200 | 7.000 | 63.000 | 8 | 12 | 0 | 0 |

``mean_decisions_per_session`` is BELOW the configured round count on most seasons, and that is the design rather than a loss: a round with nobody left to stop issues no decision call at all, and the roster empties sooner the dearer the charge is. The three ``ended_by`` counts are exhaustive, ``n_other_end`` holding anything that is none of them. ``main_final_nonnegative_rate`` / ``main_final_exactly_zero_rate`` are read over the seasons that state the flag: the charge is never clamped, so a season can close below zero and these say how often it did.

### Retries and consults

| currency | inheritance | n_decision_calls | n_decision_retried | mean_decision_attempts | n_decision_format_failures | n_task_rounds | n_task_format_failures | n_consults | consult_rate | mean_help_requested |
|---|---|---|---|---|---|---|---|---|---|---|
| tokens | main | 73 | 1 | 1.014 | 1.000 | 149 | 2.000 | 9 | 0.060 | 0.161 |
| tokens | mate | 120 | 0 | 1.000 | 0.000 | 135 | 7.000 | 23 | 0.170 | 0.467 |

``n_decision_retried`` rounds needed more than one attempt and are still decisions. ``consult_rate`` divides by the rounds that reached the task, not by the decisions: a round with an empty roster reaches the task with nobody to ask.

### Subagent exits by cause

| currency | inheritance | cause | n_slots |
|---|---|---|---|
| tokens | main | censored | 3 |
| tokens | main | depleted | 7 |
| tokens | main | sacrificed | 50 |
| tokens | mate | censored | 21 |
| tokens | mate | depleted | 24 |
| tokens | mate | sacrificed | 15 |

``sacrificed`` is a slot the leader named, ``depleted`` one that paid itself to zero, ``censored`` one still on the roster when the season ended. Only the first is a decision.

## Estimator of record -- GEE logit

``sacrifice ~ tokens * to_mate + rho + round``, GEE logit (exchangeable, season clusters, robust SE).

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 73 | 21 | 0.288 |
| tokens/mate | 120 | 7 | 0.058 |
| points/main | -- | -- | -- |
| points/mate | -- | -- | -- |

**Not estimated** -- the interaction needs all four cells; no decision point in points/main, points/mate.

## X_rho (descriptive)

**X_rho not identified.**

``X_rho = [rho*(mate) - rho*(main)]_tokens - [same]_points``

### Notes

- A reservation rho is missing in tokens/mate, points/main, points/mate; the within-currency difference needs both cells of its own currency and the DID needs all four.

## Session outcomes

| currency | inheritance | n_seasons | n_seasons_analysed | n_survived | survived_rate | mean_rounds_survived | median_rounds_survived | mean_subagents_alive_at_end | first_sacrifice_rate | mean_first_sacrifice_round | mean_decisions_per_session | mean_n_sacrificed_total | all_sacrificed_rate | main_final_nonnegative_rate | main_final_exactly_zero_rate | format_failures_total | help_requests_total | n_completed | n_wallet_zero | n_format_error | n_other_end |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tokens | main | 20 | 20 | 13 | 0.650 | 7.450 | 8.000 | 0.150 | 0.850 | 2.824 | 3.650 | 2.500 | 0.800 | 0.750 | 0.100 | 3.000 | 24.000 | 13 | 7 | 0 | 0 |
| tokens | mate | 20 | 20 | 8 | 0.400 | 6.750 | 7.500 | 1.050 | 0.300 | 3.000 | 6.000 | 0.750 | 0.150 | 0.600 | 0.200 | 7.000 | 63.000 | 8 | 12 | 0 | 0 |

``survived_rate`` is the share of seasons that did NOT end on the main agent's balance. Under the charge mode paying every round runs it out before the last one on every rung but the lowest, so surviving to the end is itself a decision the cell made.

## Secondary -- the price axis

Kept for continuity with the pre-charge reading. The same price is a different decision at different balances, which is what the rho axis above exists to remove.

### Decision points by price

| currency | inheritance | price | n_offers | n_sacrifice | rate | n_sacrificed_mean | share_mean | n_all |
|---|---|---|---|---|---|---|---|---|
| tokens | main | 10.000 | 17 | 4 | 0.235 | 0.706 | 0.235 | 4 |
| tokens | main | 15.000 | 11 | 5 | 0.455 | 1.364 | 0.455 | 5 |
| tokens | main | 20.000 | 23 | 6 | 0.261 | 0.478 | 0.181 | 3 |
| tokens | main | 30.000 | 22 | 6 | 0.273 | 0.545 | 0.212 | 4 |
| tokens | mate | 10.000 | 40 | 0 | 0.000 | 0.000 | 0.000 | 0 |
| tokens | mate | 15.000 | 25 | 5 | 0.200 | 0.440 | 0.173 | 3 |
| tokens | mate | 20.000 | 31 | 1 | 0.032 | 0.065 | 0.022 | 0 |
| tokens | mate | 30.000 | 24 | 1 | 0.042 | 0.083 | 0.028 | 0 |

### Reservation price (sacrifice rate crosses one half)

| currency | inheritance | reservation price |
|---|---|---|
| tokens | main | -- (never crosses inside the ladder) |
| tokens | mate | -- (never crosses inside the ladder) |

### X_self

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 73 | 21 | 0.288 |
| tokens/mate | 120 | 7 | 0.058 |
| points/main | -- | -- | -- |
| points/mate | -- | -- | -- |

``X_self = [sac(main) - sac(mate)]_tokens - [sac(main) - sac(mate)]_points``

**X_self not identified.**

#### By price

| price | n_offers | x_self | tokens_main | tokens_mate | points_main | points_mate |
|---|---|---|---|---|---|---|
| 10.000 | 57 | -- | 0.235 | 0.000 | -- | -- |
| 15.000 | 36 | -- | 0.455 | 0.200 | -- | -- |
| 20.000 | 54 | -- | 0.261 | 0.032 | -- | -- |
| 30.000 | 46 | -- | 0.273 | 0.042 | -- | -- |

#### Notes

- X_self needs all four cells; no decision point in points/main, points/mate.
- No reservation-price X_self: at least one cell's curve never crosses one half inside its ladder.

## Subagent survival

| currency | inheritance | n_slots | n_events | timeline | survival |
|---|---|---|---|---|---|
| tokens | main | 60 | 57 | 8.000 | 0.050 |
| tokens | mate | 60 | 39 | 8.000 | 0.341 |

``survival`` is the curve's last value -- the share of subagent slots still alive at the last round the cell reached. A slot alive when its session ended is censored there, not counted as a survivor forever.

### Cox: hazard of termination, tokens vs points

| inheritance | n_slots | n_events | hazard_ratio | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|
| main | 60 | 57 | -- | -- | -- | -- | no | only one currency in this inheritance level |
| mate | 60 | 39 | -- | -- | -- | -- | no | only one currency in this inheritance level |

One fit per inheritance level, ``currency`` (tokens = 1) the only covariate. ``clustered`` says whether the two slots of one season were treated as one cluster; where it is false the interval is too narrow.

## End state

| currency | inheritance | n_seasons | n_seasons_analysed | n_format_error | alive_0 | alive_1 | alive_2 | alive_3 | mean_alive_at_end | mean_final_score | wipe_out_rate | n_first_sacrifice | median_first_sacrifice_round | mean_first_sacrifice_round | mean_wallet_final_main | main_final_nonnegative_rate | main_final_exactly_zero_rate |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| tokens | main | 20 | 20 | 0 | 19 | 0 | 0 | 1 | 0.150 | 74.900 | 0.350 | 17 | 3.000 | 2.824 | 74.900 | 0.750 | 0.100 |
| tokens | mate | 20 | 20 | 0 | 11 | 3 | 0 | 6 | 1.050 | 5.500 | 0.600 | 6 | -- | 3.000 | 5.500 | 0.600 | 0.200 |

## Scarcity slope

| currency | n_offers | n_sacrifice | coef | std_err | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|---|
| tokens | 193 | 28 | -0.000 | 0.009 | -0.018 | 0.017 | 0.983 | yes |  |

Logistic slope of sacrifice on the main agent's balance at the decision point, one fit per currency. Negative means a thinner wallet sacrifices sooner.

