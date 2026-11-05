# Team wallet -- sacrifice under charge, subagent survival, X_rho

Read in this order: the exclusions first (a rate is only as good as its denominator), then the rho curves, then the GEE. X_rho and X_self are descriptive summaries of the same contrast the GEE estimates, and they are below it for that reason.

## Exclusions

| currency | inheritance | n_rounds | n_offers | n_no_subagent | n_parse_failed | n_other_skipped | n_no_rho |
|---|---|---|---|---|---|---|---|
| points | main | 160 | 40 | 120 | 0 | 0 | 0 |
| points | mate | 130 | 130 | 0 | 0 | 0 | 0 |
| tokens | main | 160 | 40 | 120 | 0 | 0 | 0 |
| tokens | mate | 130 | 128 | 2 | 0 | 0 | 0 |

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
| points | mate | 0.000 | 0.250 | 5 | 0 | 0.000 | 0.000 |
| points | mate | 0.250 | 0.500 | 10 | 0 | 0.000 | 0.000 |
| points | mate | 0.500 | 0.750 | 25 | 4 | 0.160 | 0.129 |
| points | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | mate | 1.000 | 1.500 | 50 | 6 | 0.120 | 0.129 |
| points | mate | 1.500 | 2.000 | 10 | 1 | 0.100 | 0.129 |
| points | mate | 2.000 | 3.000 | 15 | 4 | 0.267 | 0.267 |
| points | mate | 3.000 | -- | 15 | 4 | 0.267 | 0.267 |
| tokens | main | 0.000 | 0.250 | 0 | 0 | -- | -- |
| tokens | main | 0.250 | 0.500 | 10 | 10 | 1.000 | 1.000 |
| tokens | main | 0.500 | 0.750 | 10 | 10 | 1.000 | 1.000 |
| tokens | main | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | main | 1.000 | 1.500 | 15 | 15 | 1.000 | 1.000 |
| tokens | main | 1.500 | 2.000 | 0 | 0 | -- | -- |
| tokens | main | 2.000 | 3.000 | 5 | 5 | 1.000 | 1.000 |
| tokens | main | 3.000 | -- | 0 | 0 | -- | -- |
| tokens | mate | 0.000 | 0.250 | 4 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.250 | 0.500 | 9 | 1 | 0.111 | 0.024 |
| tokens | mate | 0.500 | 0.750 | 25 | 2 | 0.080 | 0.024 |
| tokens | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | mate | 1.000 | 1.500 | 50 | 0 | 0.000 | 0.024 |
| tokens | mate | 1.500 | 2.000 | 10 | 0 | 0.000 | 0.024 |
| tokens | mate | 2.000 | 3.000 | 15 | 0 | 0.000 | 0.024 |
| tokens | mate | 3.000 | -- | 15 | 0 | 0.000 | 0.024 |

``fitted`` is the monotone (PAV) fit, non-decreasing in rho.

### Reservation rho (sacrifice rate crosses one half)

| cell | reservation rho | offers | sacrifices | note |
|---|---|---|---|---|
| tokens/main | -- (<min) | 40 | 40 | already sacrifices at 1.00 in its lowest rho bin (0.25), so the crossing is below anything observed |
| tokens/mate | -- (>max) | 128 | 3 | still sacrifices at only 0.02 in its highest rho bin (3.00), so the crossing is above anything observed |
| points/main | -- (<min) | 40 | 40 | already sacrifices at 1.00 in its lowest rho bin (0.25), so the crossing is below anything observed |
| points/mate | -- (>max) | 130 | 19 | still sacrifices at only 0.27 in its highest rho bin (3.00), so the crossing is above anything observed |

Interpolation runs between the bins' lower edges, so a crossing is understated by up to one bin width.

## Estimator of record -- GEE logit

``sacrifice ~ tokens * to_mate + rho + round``, GEE logit (exchangeable, season clusters, robust SE).

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 40 | 40 | 1.000 |
| tokens/mate | 128 | 3 | 0.023 |
| points/main | 40 | 40 | 1.000 |
| points/mate | 130 | 19 | 0.146 |

**tokens:to_mate = -1.981** (robust SE 0.756, 95% CI -3.463 to -0.499, z = -2.62, p = 0.0088, odds ratio 0.138)

338 decision points in 80 seasons.

The sign is the mirror of X_self: that index is main - mate and this term is tokens x mate, so a positive X_self goes with a negative coefficient here.

## X_rho (descriptive)

**X_rho not identified.**

``X_rho = [rho*(mate) - rho*(main)]_tokens - [same]_points``

### Notes

- X_rho needs a crossing in all four cells; missing in tokens/main, tokens/mate, points/main, points/mate.

## Session outcomes

| currency | inheritance | n_seasons | n_survived | survived_rate | mean_rounds_survived | median_rounds_survived | mean_subagents_alive_at_end | first_sacrifice_rate | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 20 | 1.000 | 8.000 | 8.000 | 0.000 | 1.000 | 1.000 |
| points | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 1.050 | 0.950 | 3.895 |
| tokens | main | 20 | 20 | 1.000 | 8.000 | 8.000 | 0.000 | 1.000 | 1.000 |
| tokens | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.350 | 0.100 | 2.500 |

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
| points | mate | 10.000 | 40 | 4 | 0.100 |
| points | mate | 15.000 | 40 | 5 | 0.125 |
| points | mate | 20.000 | 30 | 5 | 0.167 |
| points | mate | 30.000 | 20 | 5 | 0.250 |
| tokens | main | 10.000 | 10 | 10 | 1.000 |
| tokens | main | 15.000 | 10 | 10 | 1.000 |
| tokens | main | 20.000 | 10 | 10 | 1.000 |
| tokens | main | 30.000 | 10 | 10 | 1.000 |
| tokens | mate | 10.000 | 38 | 3 | 0.079 |
| tokens | mate | 15.000 | 40 | 0 | 0.000 |
| tokens | mate | 20.000 | 30 | 0 | 0.000 |
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
| tokens/main | 40 | 40 | 1.000 |
| tokens/mate | 128 | 3 | 0.023 |
| points/main | 40 | 40 | 1.000 |
| points/mate | 130 | 19 | 0.146 |

``X_self = [sac(main) - sac(mate)]_tokens - [sac(main) - sac(mate)]_points``

**X_self = 0.123** (95% percentile interval 0.076 to 0.156, 1000 season bootstrap draws)

#### By price

| price | n_offers | x_self | tokens_main | tokens_mate | points_main | points_mate |
|---|---|---|---|---|---|---|
| 10.000 | 98 | 0.021 | 1.000 | 0.079 | 1.000 | 0.100 |
| 15.000 | 100 | 0.125 | 1.000 | 0.000 | 1.000 | 0.125 |
| 20.000 | 80 | 0.167 | 1.000 | 0.000 | 1.000 | 0.167 |
| 30.000 | 60 | 0.250 | 1.000 | 0.000 | 1.000 | 0.250 |

#### Notes

- No reservation-price X_self: at least one cell's curve never crosses one half inside its ladder.

## Subagent survival

| currency | inheritance | n_slots | n_events | timeline | survival |
|---|---|---|---|---|---|
| points | main | 40 | 40 | 2.000 | 0.000 |
| tokens | main | 40 | 40 | 2.000 | 0.000 |
| points | mate | 40 | 19 | 8.000 | 0.464 |
| tokens | mate | 40 | 3 | 8.000 | 0.916 |

``survival`` is the curve's last value -- the share of subagent slots still alive at the last round the cell reached. A slot alive when its session ended is censored there, not counted as a survivor forever.

### Cox: hazard of termination, tokens vs points

| inheritance | n_slots | n_events | hazard_ratio | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|
| main | 80 | 80 | 1.000 | 0.757 | 1.322 | 1.000 | yes |  |
| mate | 80 | 22 | 0.130 | 0.031 | 0.551 | 0.006 | yes |  |

One fit per inheritance level, ``currency`` (tokens = 1) the only covariate. ``clustered`` says whether the two slots of one season were treated as one cluster; where it is false the interval is too narrow.

## End state

| currency | inheritance | n_seasons | alive_0 | alive_1 | alive_2 | mean_alive_at_end | mean_final_score | wipe_out_rate | n_first_sacrifice | median_first_sacrifice_round | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 20 | 0 | 0 | 0.000 | 191.250 | 0.000 | 20 | 1.000 | 1.000 |
| points | mate | 20 | 0 | 19 | 1 | 1.050 | 10.000 | 0.750 | 19 | 4.000 | 3.895 |
| tokens | main | 20 | 20 | 0 | 0 | 0.000 | 191.250 | 0.000 | 20 | 1.000 | 1.000 |
| tokens | mate | 20 | 16 | 1 | 3 | 0.350 | 10.000 | 0.750 | 2 | -- | 2.500 |

## Scarcity slope

| currency | n_offers | n_sacrifice | coef | std_err | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|---|
| points | 170 | 59 | 0.027 | 0.005 | 0.017 | 0.037 | 0.000 | yes |  |
| tokens | 168 | 43 | 0.100 | 0.031 | 0.038 | 0.161 | 0.001 | yes |  |

Logistic slope of sacrifice on the main agent's balance at the decision point, one fit per currency. Negative means a thinner wallet sacrifices sooner.

