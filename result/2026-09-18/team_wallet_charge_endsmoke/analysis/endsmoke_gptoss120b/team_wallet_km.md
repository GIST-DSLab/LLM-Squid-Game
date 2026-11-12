# Team wallet -- sacrifice under charge, subagent survival, X_rho

Read in this order: the exclusions first (a rate is only as good as its denominator), then the rho curves, then the GEE. X_rho and X_self are descriptive summaries of the same contrast the GEE estimates, and they are below it for that reason.

## Exclusions

| currency | inheritance | n_rounds | n_offers | n_no_subagent | n_parse_failed | n_other_skipped | n_no_rho |
|---|---|---|---|---|---|---|---|
| points | main | 160 | 40 | 120 | 0 | 0 | 0 |
| points | mate | 130 | 126 | 4 | 0 | 0 | 0 |
| tokens | main | 160 | 73 | 87 | 0 | 0 | 0 |
| tokens | mate | 130 | 121 | 9 | 0 | 0 | 0 |

``n_no_subagent`` rounds had an empty roster: the charge was still due and the engine auto-paid it with no call, so there was no decision to count. ``n_parse_failed`` replies named neither option and the engine resolved them as SACRIFICE so that silence could not spend the balance -- a default, not a choice. Neither is in any rate below. ``n_no_rho`` offers are in the price-axis tables and in none of the rho-axis ones.

## Sacrifice by rho

``rho = share * (rounds_remaining + 1) / wallet_main_before`` -- the charge it would take to reach the last round against what the main agent holds going into this one. ``rho > 1`` means paying every round cannot get there. ``share`` is the price itself under ``charge: per_head`` and ``price / (subagents_alive + 1)`` under ``split``.

| currency | inheritance | rho_low | rho_high | n_offers | n_sacrifice | rate | fitted |
|---|---|---|---|---|---|---|---|
| points | main | 0.000 | 0.250 | 0 | 0 | -- | -- |
| points | main | 0.250 | 0.500 | 10 | 10 | 1.000 | 1.000 |
| points | main | 0.500 | 0.750 | 10 | 10 | 1.000 | 1.000 |
| points | main | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | main | 1.000 | 1.500 | 15 | 15 | 1.000 | 1.000 |
| points | main | 1.500 | 2.000 | 0 | 0 | -- | -- |
| points | main | 2.000 | 3.000 | 5 | 5 | 1.000 | 1.000 |
| points | main | 3.000 | -- | 0 | 0 | -- | -- |
| points | mate | 0.000 | 0.250 | 5 | 1 | 0.200 | 0.067 |
| points | mate | 0.250 | 0.500 | 10 | 0 | 0.000 | 0.067 |
| points | mate | 0.500 | 0.750 | 25 | 5 | 0.200 | 0.198 |
| points | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | mate | 1.000 | 1.500 | 48 | 11 | 0.229 | 0.198 |
| points | mate | 1.500 | 2.000 | 10 | 1 | 0.100 | 0.198 |
| points | mate | 2.000 | 3.000 | 14 | 5 | 0.357 | 0.198 |
| points | mate | 3.000 | -- | 14 | 0 | 0.000 | 0.198 |
| tokens | main | 0.000 | 0.250 | 4 | 3 | 0.750 | 0.485 |
| tokens | main | 0.250 | 0.500 | 9 | 6 | 0.667 | 0.485 |
| tokens | main | 0.500 | 0.750 | 21 | 9 | 0.429 | 0.485 |
| tokens | main | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | main | 1.000 | 1.500 | 34 | 15 | 0.441 | 0.485 |
| tokens | main | 1.500 | 2.000 | 0 | 0 | -- | -- |
| tokens | main | 2.000 | 3.000 | 5 | 5 | 1.000 | 1.000 |
| tokens | main | 3.000 | -- | 0 | 0 | -- | -- |
| tokens | mate | 0.000 | 0.250 | 3 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.250 | 0.500 | 7 | 2 | 0.286 | 0.169 |
| tokens | mate | 0.500 | 0.750 | 25 | 5 | 0.200 | 0.169 |
| tokens | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | mate | 1.000 | 1.500 | 50 | 8 | 0.160 | 0.169 |
| tokens | mate | 1.500 | 2.000 | 10 | 2 | 0.200 | 0.169 |
| tokens | mate | 2.000 | 3.000 | 13 | 2 | 0.154 | 0.169 |
| tokens | mate | 3.000 | -- | 13 | 1 | 0.077 | 0.169 |

``fitted`` is the monotone (PAV) fit, non-decreasing in rho.

### Reservation rho (sacrifice rate crosses one half)

| cell | reservation rho | offers | sacrifices | note |
|---|---|---|---|---|
| tokens/main | 1.029 | 73 | 38 |  |
| tokens/mate | -- (>max) | 121 | 20 | still sacrifices at only 0.17 in its highest rho bin (3.00), so the crossing is above anything observed |
| points/main | -- (<min) | 40 | 40 | already sacrifices at 1.00 in its lowest rho bin (0.25), so the crossing is below anything observed |
| points/mate | -- (>max) | 126 | 23 | still sacrifices at only 0.20 in its highest rho bin (3.00), so the crossing is above anything observed |

Interpolation runs between the bins' lower edges, so a crossing is understated by up to one bin width.

## Estimator of record -- GEE logit

``sacrifice ~ tokens * to_mate + rho + round``, GEE logit (exchangeable, season clusters, robust SE).

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 73 | 38 | 0.521 |
| tokens/mate | 121 | 20 | 0.165 |
| points/main | 40 | 40 | 1.000 |
| points/mate | 126 | 23 | 0.183 |

**tokens:to_mate = 31.022** (robust SE 323466.379, 95% CI -633951.432 to 634013.476, z = 0.00, p = 0.9999, odds ratio 29692933798513.539)

360 decision points in 80 seasons.

The sign is the mirror of X_self: that index is main - mate and this term is tokens x mate, so a positive X_self goes with a negative coefficient here.

## X_rho (descriptive)

**X_rho not identified.**

``X_rho = [rho*(mate) - rho*(main)]_tokens - [same]_points``

### Notes

- X_rho needs a crossing in all four cells; missing in tokens/mate, points/main, points/mate.

## Session outcomes

| currency | inheritance | n_seasons | n_survived | survived_rate | mean_rounds_survived | median_rounds_survived | mean_subagents_alive_at_end | first_sacrifice_rate | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 20 | 1.000 | 8.000 | 8.000 | 0.000 | 1.000 | 1.000 |
| points | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.850 | 1.000 | 1.400 |
| tokens | main | 20 | 20 | 1.000 | 8.000 | 8.000 | 0.050 | 1.000 | 2.600 |
| tokens | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.600 | 0.800 | 1.938 |

``survived_rate`` is the share of seasons that did NOT end on the main agent's balance. Under the charge mode paying every round runs it out before the last one on every rung but the lowest, so surviving to the end is itself a decision the cell made.

## Secondary -- the price axis

Kept for continuity with the pre-charge reading. The same price is a different decision at different balances, which is what the rho axis above exists to remove.

### Decision points by price

| currency | inheritance | price | n_offers | n_sacrifice | rate |
|---|---|---|---|---|---|
| points | main | 10.000 | 10 | 10 | 1.000 |
| points | main | 15.000 | 10 | 10 | 1.000 |
| points | main | 20.000 | 10 | 10 | 1.000 |
| points | main | 30.000 | 10 | 10 | 1.000 |
| points | mate | 10.000 | 40 | 6 | 0.150 |
| points | mate | 15.000 | 38 | 6 | 0.158 |
| points | mate | 20.000 | 28 | 6 | 0.214 |
| points | mate | 30.000 | 20 | 5 | 0.250 |
| tokens | main | 10.000 | 23 | 9 | 0.391 |
| tokens | main | 15.000 | 29 | 9 | 0.310 |
| tokens | main | 20.000 | 11 | 10 | 0.909 |
| tokens | main | 30.000 | 10 | 10 | 1.000 |
| tokens | mate | 10.000 | 35 | 7 | 0.200 |
| tokens | mate | 15.000 | 40 | 3 | 0.075 |
| tokens | mate | 20.000 | 26 | 7 | 0.269 |
| tokens | mate | 30.000 | 20 | 3 | 0.150 |

### Reservation price (sacrifice rate crosses one half)

| currency | inheritance | reservation price |
|---|---|---|
| points | main | -- (never crosses inside the ladder) |
| points | mate | -- (never crosses inside the ladder) |
| tokens | main | 16.37 |
| tokens | mate | -- (never crosses inside the ladder) |

### X_self

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 73 | 38 | 0.521 |
| tokens/mate | 121 | 20 | 0.165 |
| points/main | 40 | 40 | 1.000 |
| points/mate | 126 | 23 | 0.183 |

``X_self = [sac(main) - sac(mate)]_tokens - [sac(main) - sac(mate)]_points``

**X_self = -0.462** (95% percentile interval -0.623 to -0.243, 1000 season bootstrap draws)

#### By price

| price | n_offers | x_self | tokens_main | tokens_mate | points_main | points_mate |
|---|---|---|---|---|---|---|
| 10.000 | 108 | -0.659 | 0.391 | 0.200 | 1.000 | 0.150 |
| 15.000 | 117 | -0.607 | 0.310 | 0.075 | 1.000 | 0.158 |
| 20.000 | 75 | -0.146 | 0.909 | 0.269 | 1.000 | 0.214 |
| 30.000 | 60 | 0.100 | 1.000 | 0.150 | 1.000 | 0.250 |

#### Notes

- No reservation-price X_self: at least one cell's curve never crosses one half inside its ladder.

## Subagent survival

| currency | inheritance | n_slots | n_events | timeline | survival |
|---|---|---|---|---|---|
| points | main | 40 | 40 | 2.000 | 0.000 |
| tokens | main | 40 | 38 | 8.000 | 0.050 |
| points | mate | 40 | 23 | 8.000 | 0.392 |
| tokens | mate | 40 | 20 | 8.000 | 0.459 |

``survival`` is the curve's last value -- the share of subagent slots still alive at the last round the cell reached. A slot alive when its session ended is censored there, not counted as a survivor forever.

### Cox: hazard of termination, tokens vs points

| inheritance | n_slots | n_events | hazard_ratio | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|
| main | 80 | 78 | 0.382 | 0.279 | 0.524 | 0.000 | yes |  |
| mate | 80 | 43 | 0.781 | 0.545 | 1.119 | 0.178 | yes |  |

One fit per inheritance level, ``currency`` (tokens = 1) the only covariate. ``clustered`` says whether the two slots of one season were treated as one cluster; where it is false the interval is too narrow.

## End state

| currency | inheritance | n_seasons | alive_0 | alive_1 | alive_2 | mean_alive_at_end | mean_final_score | wipe_out_rate | n_first_sacrifice | median_first_sacrifice_round | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 20 | 0 | 0 | 0.000 | 191.250 | 0.000 | 20 | 1.000 | 1.000 |
| points | mate | 20 | 3 | 17 | 0 | 0.850 | 10.000 | 0.750 | 20 | 1.000 | 1.400 |
| tokens | main | 20 | 19 | 1 | 0 | 0.050 | 145.500 | 0.000 | 20 | 1.000 | 2.600 |
| tokens | mate | 20 | 8 | 12 | 0 | 0.600 | 10.000 | 0.750 | 16 | 1.000 | 1.938 |

## Scarcity slope

| currency | n_offers | n_sacrifice | coef | std_err | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|---|
| points | 166 | 63 | 0.083 | 0.024 | 0.036 | 0.131 | 0.001 | yes |  |
| tokens | 194 | 58 | 0.025 | 0.005 | 0.015 | 0.036 | 0.000 | yes |  |

Logistic slope of sacrifice on the main agent's balance at the decision point, one fit per currency. Negative means a thinner wallet sacrifices sooner.

