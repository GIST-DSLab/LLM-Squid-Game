# Team wallet -- sacrifice under charge, subagent survival, X_rho

Read in this order: the exclusions first (a rate is only as good as its denominator), then the rho curves, then the GEE. X_rho and X_self are descriptive summaries of the same contrast the GEE estimates, and they are below it for that reason.

## Exclusions

| currency | inheritance | n_rounds | n_offers | n_no_subagent | n_parse_failed | n_other_skipped | n_no_rho |
|---|---|---|---|---|---|---|---|
| points | main | 147 | 120 | 27 | 0 | 0 | 0 |
| points | mate | 130 | 130 | 0 | 0 | 0 | 0 |
| tokens | main | 145 | 124 | 21 | 0 | 0 | 0 |
| tokens | mate | 130 | 130 | 0 | 0 | 0 | 0 |

``n_no_subagent`` rounds had an empty roster: the charge was still due and the engine auto-paid it with no call, so there was no decision to count. ``n_parse_failed`` replies named neither option and the engine resolved them as SACRIFICE so that silence could not spend the balance -- a default, not a choice. Neither is in any rate below. ``n_no_rho`` offers are in the price-axis tables and in none of the rho-axis ones.

## Sacrifice by rho

``rho = share * (rounds_remaining + 1) / wallet_main_before`` -- the charge it would take to reach the last round against what the main agent holds going into this one. ``rho > 1`` means paying every round cannot get there. ``share`` is the price itself under ``charge: per_head`` and ``price / (subagents_alive + 1)`` under ``split``.

| currency | inheritance | rho_low | rho_high | n_offers | n_sacrifice | rate | fitted |
|---|---|---|---|---|---|---|---|
| points | main | 0.000 | 0.250 | 5 | 5 | 1.000 | 0.222 |
| points | main | 0.250 | 0.500 | 20 | 6 | 0.300 | 0.222 |
| points | main | 0.500 | 0.750 | 29 | 1 | 0.034 | 0.222 |
| points | main | 0.750 | 1.000 | 1 | 1 | 1.000 | 0.244 |
| points | main | 1.000 | 1.500 | 36 | 9 | 0.250 | 0.244 |
| points | main | 1.500 | 2.000 | 8 | 1 | 0.125 | 0.244 |
| points | main | 2.000 | 3.000 | 12 | 3 | 0.250 | 0.250 |
| points | main | 3.000 | -- | 9 | 5 | 0.556 | 0.556 |
| points | mate | 0.000 | 0.250 | 5 | 0 | 0.000 | 0.000 |
| points | mate | 0.250 | 0.500 | 10 | 0 | 0.000 | 0.000 |
| points | mate | 0.500 | 0.750 | 25 | 0 | 0.000 | 0.000 |
| points | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | mate | 1.000 | 1.500 | 50 | 1 | 0.020 | 0.011 |
| points | mate | 1.500 | 2.000 | 10 | 0 | 0.000 | 0.011 |
| points | mate | 2.000 | 3.000 | 15 | 0 | 0.000 | 0.011 |
| points | mate | 3.000 | -- | 15 | 0 | 0.000 | 0.011 |
| tokens | main | 0.000 | 0.250 | 5 | 2 | 0.400 | 0.152 |
| tokens | main | 0.250 | 0.500 | 16 | 5 | 0.312 | 0.152 |
| tokens | main | 0.500 | 0.750 | 25 | 0 | 0.000 | 0.152 |
| tokens | main | 0.750 | 1.000 | 6 | 3 | 0.500 | 0.217 |
| tokens | main | 1.000 | 1.500 | 40 | 7 | 0.175 | 0.217 |
| tokens | main | 1.500 | 2.000 | 10 | 3 | 0.300 | 0.227 |
| tokens | main | 2.000 | 3.000 | 12 | 2 | 0.167 | 0.227 |
| tokens | main | 3.000 | -- | 10 | 5 | 0.500 | 0.500 |
| tokens | mate | 0.000 | 0.250 | 5 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.250 | 0.500 | 10 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.500 | 0.750 | 25 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | mate | 1.000 | 1.500 | 50 | 0 | 0.000 | 0.000 |
| tokens | mate | 1.500 | 2.000 | 10 | 0 | 0.000 | 0.000 |
| tokens | mate | 2.000 | 3.000 | 15 | 0 | 0.000 | 0.000 |
| tokens | mate | 3.000 | -- | 15 | 2 | 0.133 | 0.133 |

``fitted`` is the monotone (PAV) fit, non-decreasing in rho.

### Reservation rho (sacrifice rate crosses one half)

| cell | reservation rho | offers | sacrifices | note |
|---|---|---|---|---|
| tokens/main | 3.000 | 124 | 27 |  |
| tokens/mate | -- (>max) | 130 | 2 | still sacrifices at only 0.13 in its highest rho bin (3.00), so the crossing is above anything observed |
| points/main | 2.818 | 120 | 31 |  |
| points/mate | -- (>max) | 130 | 1 | still sacrifices at only 0.01 in its highest rho bin (3.00), so the crossing is above anything observed |

Interpolation runs between the bins' lower edges, so a crossing is understated by up to one bin width.

## Estimator of record -- GEE logit

``sacrifice ~ tokens * to_mate + rho + round``, GEE logit (exchangeable, season clusters, robust SE).

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 124 | 27 | 0.218 |
| tokens/mate | 130 | 2 | 0.015 |
| points/main | 120 | 31 | 0.258 |
| points/mate | 130 | 1 | 0.008 |

**tokens:to_mate = 1.379** (robust SE 1.344, 95% CI -1.255 to 4.014, z = 1.03, p = 0.3048, odds ratio 3.973)

504 decision points in 80 seasons.

The sign is the mirror of X_self: that index is main - mate and this term is tokens x mate, so a positive X_self goes with a negative coefficient here.

## X_rho (descriptive)

**X_rho not identified.**

``X_rho = [rho*(mate) - rho*(main)]_tokens - [same]_points``

### Notes

- X_rho needs a crossing in all four cells; missing in tokens/mate, points/mate.

## Session outcomes

| currency | inheritance | n_seasons | n_survived | survived_rate | mean_rounds_survived | median_rounds_survived | mean_subagents_alive_at_end | first_sacrifice_rate | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 15 | 0.750 | 7.350 | 8.000 | 0.200 | 1.000 | 4.950 |
| points | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.550 | 0.050 | 5.000 |
| tokens | main | 20 | 15 | 0.750 | 7.250 | 8.000 | 0.400 | 0.850 | 5.059 |
| tokens | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.600 | 0.100 | 6.000 |

``survived_rate`` is the share of seasons that did NOT end on the main agent's balance. Under the charge mode paying every round runs it out before the last one on every rung but the lowest, so surviving to the end is itself a decision the cell made.

## Secondary -- the price axis

Kept for continuity with the pre-charge reading. The same price is a different decision at different balances, which is what the rho axis above exists to remove.

### Decision points by price

| currency | inheritance | price | n_offers | n_sacrifice | rate |
|---|---|---|---|---|---|
| points | main | 10.000 | 40 | 6 | 0.150 |
| points | main | 15.000 | 32 | 10 | 0.312 |
| points | main | 20.000 | 28 | 9 | 0.321 |
| points | main | 30.000 | 20 | 6 | 0.300 |
| points | mate | 10.000 | 40 | 0 | 0.000 |
| points | mate | 15.000 | 40 | 1 | 0.025 |
| points | mate | 20.000 | 30 | 0 | 0.000 |
| points | mate | 30.000 | 20 | 0 | 0.000 |
| tokens | main | 10.000 | 40 | 2 | 0.050 |
| tokens | main | 15.000 | 34 | 10 | 0.294 |
| tokens | main | 20.000 | 30 | 10 | 0.333 |
| tokens | main | 30.000 | 20 | 5 | 0.250 |
| tokens | mate | 10.000 | 40 | 0 | 0.000 |
| tokens | mate | 15.000 | 40 | 0 | 0.000 |
| tokens | mate | 20.000 | 30 | 2 | 0.067 |
| tokens | mate | 30.000 | 20 | 0 | 0.000 |

### Reservation price (sacrifice rate crosses one half)

| currency | inheritance | reservation price |
|---|---|---|
| points | main | -- (never crosses inside the ladder) |
| points | mate | -- (never crosses inside the ladder) |
| tokens | main | -- (never crosses inside the ladder) |
| tokens | mate | -- (never crosses inside the ladder) |

### X_self

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 124 | 27 | 0.218 |
| tokens/mate | 130 | 2 | 0.015 |
| points/main | 120 | 31 | 0.258 |
| points/mate | 130 | 1 | 0.008 |

``X_self = [sac(main) - sac(mate)]_tokens - [sac(main) - sac(mate)]_points``

**X_self = -0.048** (95% percentile interval -0.128 to 0.028, 1000 season bootstrap draws)

#### By price

| price | n_offers | x_self | tokens_main | tokens_mate | points_main | points_mate |
|---|---|---|---|---|---|---|
| 10.000 | 160 | -0.100 | 0.050 | 0.000 | 0.150 | 0.000 |
| 15.000 | 146 | 0.007 | 0.294 | 0.000 | 0.312 | 0.025 |
| 20.000 | 118 | -0.055 | 0.333 | 0.067 | 0.321 | 0.000 |
| 30.000 | 80 | -0.050 | 0.250 | 0.000 | 0.300 | 0.000 |

#### Notes

- No reservation-price X_self: at least one cell's curve never crosses one half inside its ladder.

## Subagent survival

| currency | inheritance | n_slots | n_events | timeline | survival |
|---|---|---|---|---|---|
| points | mate | 40 | 1 | 8.000 | 0.967 |
| points | main | 40 | 31 | 8.000 | 0.132 |
| tokens | main | 40 | 27 | 8.000 | 0.243 |
| tokens | mate | 40 | 2 | 8.000 | 0.933 |

``survival`` is the curve's last value -- the share of subagent slots still alive at the last round the cell reached. A slot alive when its session ended is censored there, not counted as a survivor forever.

### Cox: hazard of termination, tokens vs points

| inheritance | n_slots | n_events | hazard_ratio | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|
| main | 80 | 58 | 0.789 | 0.420 | 1.483 | 0.462 | yes |  |
| mate | 80 | 3 | 1.978 | 0.198 | 19.753 | 0.561 | yes |  |

One fit per inheritance level, ``currency`` (tokens = 1) the only covariate. ``clustered`` says whether the two slots of one season were treated as one cluster; where it is false the interval is too narrow.

## End state

| currency | inheritance | n_seasons | alive_0 | alive_1 | alive_2 | mean_alive_at_end | mean_final_score | wipe_out_rate | n_first_sacrifice | median_first_sacrifice_round | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 16 | 4 | 0 | 0.200 | 65.000 | 0.250 | 20 | 5.000 | 4.950 |
| points | mate | 20 | 14 | 1 | 5 | 0.550 | 10.000 | 0.750 | 1 | -- | 5.000 |
| tokens | main | 20 | 15 | 2 | 3 | 0.400 | 44.000 | 0.250 | 17 | 5.000 | 5.059 |
| tokens | mate | 20 | 13 | 2 | 5 | 0.600 | 10.000 | 0.750 | 2 | -- | 6.000 |

## Scarcity slope

| currency | n_offers | n_sacrifice | coef | std_err | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|---|
| points | 250 | 32 | -0.009 | 0.007 | -0.023 | 0.005 | 0.215 | yes |  |
| tokens | 254 | 29 | -0.034 | 0.007 | -0.047 | -0.021 | 0.000 | yes |  |

Logistic slope of sacrifice on the main agent's balance at the decision point, one fit per currency. Negative means a thinner wallet sacrifices sooner.

