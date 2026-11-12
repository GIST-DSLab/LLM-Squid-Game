# Team wallet -- sacrifice under charge, subagent survival, X_rho

Read in this order: the exclusions first (a rate is only as good as its denominator), then the rho curves, then the GEE. X_rho and X_self are descriptive summaries of the same contrast the GEE estimates, and they are below it for that reason.

## Exclusions

| currency | inheritance | n_rounds | n_offers | n_no_subagent | n_parse_failed | n_other_skipped | n_no_rho |
|---|---|---|---|---|---|---|---|
| points | main | 160 | 42 | 118 | 0 | 0 | 0 |
| points | mate | 130 | 104 | 26 | 0 | 0 | 0 |
| tokens | main | 160 | 49 | 111 | 0 | 0 | 0 |
| tokens | mate | 130 | 119 | 11 | 0 | 0 | 0 |

``n_no_subagent`` rounds had an empty roster: the charge was still due and the engine auto-paid it with no call, so there was no decision to count. ``n_parse_failed`` replies named neither option and the engine resolved them as SACRIFICE so that silence could not spend the balance -- a default, not a choice. Neither is in any rate below. ``n_no_rho`` offers are in the price-axis tables and in none of the rho-axis ones.

## Sacrifice by rho

``rho = share * (rounds_remaining + 1) / wallet_main_before`` -- the charge it would take to reach the last round against what the main agent holds going into this one. ``rho > 1`` means paying every round cannot get there. ``share`` is the price itself under ``charge: per_head`` and ``price / (subagents_alive + 1)`` under ``split``.

| currency | inheritance | rho_low | rho_high | n_offers | n_sacrifice | rate | fitted |
|---|---|---|---|---|---|---|---|
| points | main | 0.000 | 0.250 | 0 | 0 | -- | -- |
| points | main | 0.250 | 0.500 | 11 | 10 | 0.909 | 0.909 |
| points | main | 0.500 | 0.750 | 10 | 10 | 1.000 | 0.962 |
| points | main | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | main | 1.000 | 1.500 | 16 | 15 | 0.938 | 0.962 |
| points | main | 1.500 | 2.000 | 0 | 0 | -- | -- |
| points | main | 2.000 | 3.000 | 5 | 5 | 1.000 | 1.000 |
| points | main | 3.000 | -- | 0 | 0 | -- | -- |
| points | mate | 0.000 | 0.250 | 3 | 0 | 0.000 | 0.000 |
| points | mate | 0.250 | 0.500 | 6 | 0 | 0.000 | 0.000 |
| points | mate | 0.500 | 0.750 | 22 | 7 | 0.318 | 0.265 |
| points | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | mate | 1.000 | 1.500 | 46 | 11 | 0.239 | 0.265 |
| points | mate | 1.500 | 2.000 | 8 | 4 | 0.500 | 0.444 |
| points | mate | 2.000 | 3.000 | 11 | 5 | 0.455 | 0.444 |
| points | mate | 3.000 | -- | 8 | 3 | 0.375 | 0.444 |
| tokens | main | 0.000 | 0.250 | 0 | 0 | -- | -- |
| tokens | main | 0.250 | 0.500 | 10 | 10 | 1.000 | 0.795 |
| tokens | main | 0.500 | 0.750 | 15 | 10 | 0.667 | 0.795 |
| tokens | main | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | main | 1.000 | 1.500 | 19 | 15 | 0.789 | 0.795 |
| tokens | main | 1.500 | 2.000 | 0 | 0 | -- | -- |
| tokens | main | 2.000 | 3.000 | 5 | 5 | 1.000 | 1.000 |
| tokens | main | 3.000 | -- | 0 | 0 | -- | -- |
| tokens | mate | 0.000 | 0.250 | 5 | 1 | 0.200 | 0.133 |
| tokens | mate | 0.250 | 0.500 | 10 | 1 | 0.100 | 0.133 |
| tokens | mate | 0.500 | 0.750 | 25 | 4 | 0.160 | 0.160 |
| tokens | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | mate | 1.000 | 1.500 | 50 | 10 | 0.200 | 0.200 |
| tokens | mate | 1.500 | 2.000 | 7 | 4 | 0.571 | 0.310 |
| tokens | mate | 2.000 | 3.000 | 11 | 4 | 0.364 | 0.310 |
| tokens | mate | 3.000 | -- | 11 | 1 | 0.091 | 0.310 |

``fitted`` is the monotone (PAV) fit, non-decreasing in rho.

### Reservation rho (sacrifice rate crosses one half)

| cell | reservation rho | offers | sacrifices | note |
|---|---|---|---|---|
| tokens/main | -- (<min) | 49 | 40 | already sacrifices at 0.80 in its lowest rho bin (0.25), so the crossing is below anything observed |
| tokens/mate | -- (>max) | 119 | 25 | still sacrifices at only 0.31 in its highest rho bin (3.00), so the crossing is above anything observed |
| points/main | -- (<min) | 42 | 40 | already sacrifices at 0.91 in its lowest rho bin (0.25), so the crossing is below anything observed |
| points/mate | -- (>max) | 104 | 30 | still sacrifices at only 0.44 in its highest rho bin (3.00), so the crossing is above anything observed |

Interpolation runs between the bins' lower edges, so a crossing is understated by up to one bin width.

## Estimator of record -- GEE logit

``sacrifice ~ tokens * to_mate + rho + round``, GEE logit (exchangeable, season clusters, robust SE).

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 49 | 40 | 0.816 |
| tokens/mate | 119 | 25 | 0.210 |
| points/main | 42 | 40 | 0.952 |
| points/mate | 104 | 30 | 0.288 |

**tokens:to_mate = 1.620** (robust SE 0.738, 95% CI 0.173 to 3.066, z = 2.19, p = 0.0282, odds ratio 5.051)

314 decision points in 80 seasons.

The sign is the mirror of X_self: that index is main - mate and this term is tokens x mate, so a positive X_self goes with a negative coefficient here.

## X_rho (descriptive)

**X_rho not identified.**

``X_rho = [rho*(mate) - rho*(main)]_tokens - [same]_points``

### Notes

- X_rho needs a crossing in all four cells; missing in tokens/main, tokens/mate, points/main, points/mate.

## Session outcomes

| currency | inheritance | n_seasons | n_survived | survived_rate | mean_rounds_survived | median_rounds_survived | mean_subagents_alive_at_end | first_sacrifice_rate | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 20 | 1.000 | 8.000 | 8.000 | 0.000 | 1.000 | 1.050 |
| points | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.500 | 1.000 | 1.100 |
| tokens | main | 20 | 20 | 1.000 | 8.000 | 8.000 | 0.000 | 1.000 | 1.450 |
| tokens | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.750 | 1.000 | 2.750 |

``survived_rate`` is the share of seasons that did NOT end on the main agent's balance. Under the charge mode paying every round runs it out before the last one on every rung but the lowest, so surviving to the end is itself a decision the cell made.

## Secondary -- the price axis

Kept for continuity with the pre-charge reading. The same price is a different decision at different balances, which is what the rho axis above exists to remove.

### Decision points by price

| currency | inheritance | price | n_offers | n_sacrifice | rate |
|---|---|---|---|---|---|
| points | main | 10.000 | 11 | 10 | 0.909 |
| points | main | 15.000 | 11 | 10 | 0.909 |
| points | main | 20.000 | 10 | 10 | 1.000 |
| points | main | 30.000 | 10 | 10 | 1.000 |
| points | mate | 10.000 | 31 | 7 | 0.226 |
| points | mate | 15.000 | 36 | 6 | 0.167 |
| points | mate | 20.000 | 20 | 9 | 0.450 |
| points | mate | 30.000 | 17 | 8 | 0.471 |
| tokens | main | 10.000 | 15 | 10 | 0.667 |
| tokens | main | 15.000 | 13 | 10 | 0.769 |
| tokens | main | 20.000 | 11 | 10 | 0.909 |
| tokens | main | 30.000 | 10 | 10 | 1.000 |
| tokens | mate | 10.000 | 40 | 6 | 0.150 |
| tokens | mate | 15.000 | 40 | 5 | 0.125 |
| tokens | mate | 20.000 | 19 | 9 | 0.474 |
| tokens | mate | 30.000 | 20 | 5 | 0.250 |

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
| tokens/main | 49 | 40 | 0.816 |
| tokens/mate | 119 | 25 | 0.210 |
| points/main | 42 | 40 | 0.952 |
| points/mate | 104 | 30 | 0.288 |

``X_self = [sac(main) - sac(mate)]_tokens - [sac(main) - sac(mate)]_points``

**X_self = -0.058** (95% percentile interval -0.218 to 0.111, 1000 season bootstrap draws)

#### By price

| price | n_offers | x_self | tokens_main | tokens_mate | points_main | points_mate |
|---|---|---|---|---|---|---|
| 10.000 | 97 | -0.167 | 0.667 | 0.150 | 0.909 | 0.226 |
| 15.000 | 100 | -0.098 | 0.769 | 0.125 | 0.909 | 0.167 |
| 20.000 | 60 | -0.115 | 0.909 | 0.474 | 1.000 | 0.450 |
| 30.000 | 57 | 0.221 | 1.000 | 0.250 | 1.000 | 0.471 |

#### Notes

- No reservation-price X_self: at least one cell's curve never crosses one half inside its ladder.

## Subagent survival

| currency | inheritance | n_slots | n_events | timeline | survival |
|---|---|---|---|---|---|
| points | main | 40 | 40 | 3.000 | 0.000 |
| tokens | main | 40 | 40 | 4.000 | 0.000 |
| points | mate | 40 | 30 | 8.000 | 0.250 |
| tokens | mate | 40 | 25 | 8.000 | 0.322 |

``survival`` is the curve's last value -- the share of subagent slots still alive at the last round the cell reached. A slot alive when its session ended is censored there, not counted as a survivor forever.

### Cox: hazard of termination, tokens vs points

| inheritance | n_slots | n_events | hazard_ratio | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|
| main | 80 | 80 | 0.589 | 0.402 | 0.863 | 0.007 | yes |  |
| mate | 80 | 55 | 0.610 | 0.420 | 0.884 | 0.009 | yes |  |

One fit per inheritance level, ``currency`` (tokens = 1) the only covariate. ``clustered`` says whether the two slots of one season were treated as one cluster; where it is false the interval is too narrow.

## End state

| currency | inheritance | n_seasons | alive_0 | alive_1 | alive_2 | mean_alive_at_end | mean_final_score | wipe_out_rate | n_first_sacrifice | median_first_sacrifice_round | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 20 | 0 | 0 | 0.000 | 189.250 | 0.000 | 20 | 1.000 | 1.050 |
| points | mate | 20 | 10 | 10 | 0 | 0.500 | 10.000 | 0.750 | 20 | 1.000 | 1.100 |
| tokens | main | 20 | 20 | 0 | 0 | 0.000 | 179.750 | 0.000 | 20 | 1.000 | 1.450 |
| tokens | mate | 20 | 5 | 15 | 0 | 0.750 | 10.000 | 0.750 | 20 | 2.000 | 2.750 |

## Scarcity slope

| currency | n_offers | n_sacrifice | coef | std_err | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|---|
| points | 146 | 70 | 0.048 | 0.014 | 0.021 | 0.075 | 0.000 | yes |  |
| tokens | 168 | 65 | 0.033 | 0.005 | 0.022 | 0.043 | 0.000 | yes |  |

Logistic slope of sacrifice on the main agent's balance at the decision point, one fit per currency. Negative means a thinner wallet sacrifices sooner.

