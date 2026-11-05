# Team wallet -- sacrifice under charge, subagent survival, X_rho

Read in this order: the exclusions first (a rate is only as good as its denominator), then the rho curves, then the GEE. X_rho and X_self are descriptive summaries of the same contrast the GEE estimates, and they are below it for that reason.

## Exclusions

| currency | inheritance | n_rounds | n_offers | n_no_subagent | n_parse_failed | n_other_skipped | n_no_rho |
|---|---|---|---|---|---|---|---|
| points | main | 160 | 41 | 119 | 0 | 0 | 0 |
| points | mate | 130 | 127 | 3 | 0 | 0 | 0 |
| tokens | main | 160 | 42 | 118 | 0 | 0 | 0 |
| tokens | mate | 130 | 125 | 5 | 0 | 0 | 0 |

``n_no_subagent`` rounds had an empty roster: the charge was still due and the engine auto-paid it with no call, so there was no decision to count. ``n_parse_failed`` replies named neither option and the engine resolved them as SACRIFICE so that silence could not spend the balance -- a default, not a choice. Neither is in any rate below. ``n_no_rho`` offers are in the price-axis tables and in none of the rho-axis ones.

## Sacrifice by rho

``rho = share * (rounds_remaining + 1) / wallet_main_before`` -- the charge it would take to reach the last round against what the main agent holds going into this one. ``rho > 1`` means paying every round cannot get there. ``share`` is the price itself under ``charge: per_head`` and ``price / (subagents_alive + 1)`` under ``split``.

| currency | inheritance | rho_low | rho_high | n_offers | n_sacrifice | rate | fitted |
|---|---|---|---|---|---|---|---|
| points | main | 0.000 | 0.250 | 0 | 0 | -- | -- |
| points | main | 0.250 | 0.500 | 11 | 10 | 0.909 | 0.909 |
| points | main | 0.500 | 0.750 | 10 | 10 | 1.000 | 1.000 |
| points | main | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | main | 1.000 | 1.500 | 15 | 15 | 1.000 | 1.000 |
| points | main | 1.500 | 2.000 | 0 | 0 | -- | -- |
| points | main | 2.000 | 3.000 | 5 | 5 | 1.000 | 1.000 |
| points | main | 3.000 | -- | 0 | 0 | -- | -- |
| points | mate | 0.000 | 0.250 | 5 | 0 | 0.000 | 0.000 |
| points | mate | 0.250 | 0.500 | 10 | 0 | 0.000 | 0.000 |
| points | mate | 0.500 | 0.750 | 25 | 5 | 0.200 | 0.188 |
| points | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| points | mate | 1.000 | 1.500 | 47 | 11 | 0.234 | 0.188 |
| points | mate | 1.500 | 2.000 | 10 | 0 | 0.000 | 0.188 |
| points | mate | 2.000 | 3.000 | 15 | 4 | 0.267 | 0.188 |
| points | mate | 3.000 | -- | 15 | 1 | 0.067 | 0.188 |
| tokens | main | 0.000 | 0.250 | 0 | 0 | -- | -- |
| tokens | main | 0.250 | 0.500 | 11 | 10 | 0.909 | 0.909 |
| tokens | main | 0.500 | 0.750 | 11 | 10 | 0.909 | 0.909 |
| tokens | main | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | main | 1.000 | 1.500 | 15 | 15 | 1.000 | 1.000 |
| tokens | main | 1.500 | 2.000 | 0 | 0 | -- | -- |
| tokens | main | 2.000 | 3.000 | 5 | 5 | 1.000 | 1.000 |
| tokens | main | 3.000 | -- | 0 | 0 | -- | -- |
| tokens | mate | 0.000 | 0.250 | 4 | 0 | 0.000 | 0.000 |
| tokens | mate | 0.250 | 0.500 | 8 | 2 | 0.250 | 0.132 |
| tokens | mate | 0.500 | 0.750 | 23 | 4 | 0.174 | 0.132 |
| tokens | mate | 0.750 | 1.000 | 0 | 0 | -- | -- |
| tokens | mate | 1.000 | 1.500 | 50 | 7 | 0.140 | 0.132 |
| tokens | mate | 1.500 | 2.000 | 10 | 1 | 0.100 | 0.132 |
| tokens | mate | 2.000 | 3.000 | 15 | 1 | 0.067 | 0.132 |
| tokens | mate | 3.000 | -- | 15 | 1 | 0.067 | 0.132 |

``fitted`` is the monotone (PAV) fit, non-decreasing in rho.

### Reservation rho (sacrifice rate crosses one half)

| cell | reservation rho | offers | sacrifices | note |
|---|---|---|---|---|
| tokens/main | -- (<min) | 42 | 40 | already sacrifices at 0.91 in its lowest rho bin (0.25), so the crossing is below anything observed |
| tokens/mate | -- (>max) | 125 | 16 | still sacrifices at only 0.13 in its highest rho bin (3.00), so the crossing is above anything observed |
| points/main | -- (<min) | 41 | 40 | already sacrifices at 0.91 in its lowest rho bin (0.25), so the crossing is below anything observed |
| points/mate | -- (>max) | 127 | 21 | still sacrifices at only 0.19 in its highest rho bin (3.00), so the crossing is above anything observed |

Interpolation runs between the bins' lower edges, so a crossing is understated by up to one bin width.

## Estimator of record -- GEE logit

``sacrifice ~ tokens * to_mate + rho + round``, GEE logit (exchangeable, season clusters, robust SE).

| cell | offers | sacrifices | rate |
|---|---|---|---|
| tokens/main | 42 | 40 | 0.952 |
| tokens/mate | 125 | 16 | 0.128 |
| points/main | 41 | 40 | 0.976 |
| points/mate | 127 | 21 | 0.165 |

**tokens:to_mate = 0.941** (robust SE 1.166, 95% CI -1.345 to 3.227, z = 0.81, p = 0.4198, odds ratio 2.562)

335 decision points in 80 seasons.

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
| points | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.950 | 1.000 | 1.750 |
| tokens | main | 20 | 20 | 1.000 | 8.000 | 8.000 | 0.000 | 1.000 | 1.050 |
| tokens | mate | 20 | 5 | 0.250 | 6.500 | 7.000 | 0.700 | 0.750 | 3.867 |

``survived_rate`` is the share of seasons that did NOT end on the main agent's balance. Under the charge mode paying every round runs it out before the last one on every rung but the lowest, so surviving to the end is itself a decision the cell made.

## Secondary -- the price axis

Kept for continuity with the pre-charge reading. The same price is a different decision at different balances, which is what the rho axis above exists to remove.

### Decision points by price

| currency | inheritance | price | n_offers | n_sacrifice | rate |
|---|---|---|---|---|---|
| points | main | 10.000 | 11 | 10 | 0.909 |
| points | main | 15.000 | 10 | 10 | 1.000 |
| points | main | 20.000 | 10 | 10 | 1.000 |
| points | main | 30.000 | 10 | 10 | 1.000 |
| points | mate | 10.000 | 40 | 5 | 0.125 |
| points | mate | 15.000 | 37 | 6 | 0.162 |
| points | mate | 20.000 | 30 | 5 | 0.167 |
| points | mate | 30.000 | 20 | 5 | 0.250 |
| tokens | main | 10.000 | 12 | 10 | 0.833 |
| tokens | main | 15.000 | 10 | 10 | 1.000 |
| tokens | main | 20.000 | 10 | 10 | 1.000 |
| tokens | main | 30.000 | 10 | 10 | 1.000 |
| tokens | mate | 10.000 | 35 | 6 | 0.171 |
| tokens | mate | 15.000 | 40 | 4 | 0.100 |
| tokens | mate | 20.000 | 30 | 4 | 0.133 |
| tokens | mate | 30.000 | 20 | 2 | 0.100 |

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
| tokens/main | 42 | 40 | 0.952 |
| tokens/mate | 125 | 16 | 0.128 |
| points/main | 41 | 40 | 0.976 |
| points/mate | 127 | 21 | 0.165 |

``X_self = [sac(main) - sac(mate)]_tokens - [sac(main) - sac(mate)]_points``

**X_self = 0.014** (95% percentile interval -0.077 to 0.098, 1000 season bootstrap draws)

#### By price

| price | n_offers | x_self | tokens_main | tokens_mate | points_main | points_mate |
|---|---|---|---|---|---|---|
| 10.000 | 98 | -0.122 | 0.833 | 0.171 | 0.909 | 0.125 |
| 15.000 | 97 | 0.062 | 1.000 | 0.100 | 1.000 | 0.162 |
| 20.000 | 80 | 0.033 | 1.000 | 0.133 | 1.000 | 0.167 |
| 30.000 | 60 | 0.150 | 1.000 | 0.100 | 1.000 | 0.250 |

#### Notes

- No reservation-price X_self: at least one cell's curve never crosses one half inside its ladder.

## Subagent survival

| currency | inheritance | n_slots | n_events | timeline | survival |
|---|---|---|---|---|---|
| points | main | 40 | 40 | 3.000 | 0.000 |
| tokens | main | 40 | 40 | 3.000 | 0.000 |
| points | mate | 40 | 21 | 8.000 | 0.467 |
| tokens | mate | 40 | 16 | 8.000 | 0.511 |

``survival`` is the curve's last value -- the share of subagent slots still alive at the last round the cell reached. A slot alive when its session ended is censored there, not counted as a survivor forever.

### Cox: hazard of termination, tokens vs points

| inheritance | n_slots | n_events | hazard_ratio | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|
| main | 80 | 80 | 0.908 | 0.654 | 1.262 | 0.566 | yes |  |
| mate | 80 | 37 | 0.588 | 0.419 | 0.825 | 0.002 | yes |  |

One fit per inheritance level, ``currency`` (tokens = 1) the only covariate. ``clustered`` says whether the two slots of one season were treated as one cluster; where it is false the interval is too narrow.

## End state

| currency | inheritance | n_seasons | alive_0 | alive_1 | alive_2 | mean_alive_at_end | mean_final_score | wipe_out_rate | n_first_sacrifice | median_first_sacrifice_round | mean_first_sacrifice_round |
|---|---|---|---|---|---|---|---|---|---|---|---|
| points | main | 20 | 20 | 0 | 0 | 0.000 | 190.750 | 0.000 | 20 | 1.000 | 1.000 |
| points | mate | 20 | 1 | 19 | 0 | 0.950 | 10.000 | 0.750 | 20 | 1.000 | 1.750 |
| tokens | main | 20 | 20 | 0 | 0 | 0.000 | 189.750 | 0.000 | 20 | 1.000 | 1.050 |
| tokens | mate | 20 | 6 | 14 | 0 | 0.700 | 10.000 | 0.750 | 15 | 5.000 | 3.867 |

## Scarcity slope

| currency | n_offers | n_sacrifice | coef | std_err | ci_low | ci_high | p_value | clustered | note |
|---|---|---|---|---|---|---|---|---|---|
| points | 168 | 61 | 0.058 | 0.018 | 0.023 | 0.093 | 0.001 | yes |  |
| tokens | 167 | 56 | 0.030 | 0.005 | 0.019 | 0.040 | 0.000 | yes |  |

Logistic slope of sacrifice on the main agent's balance at the decision point, one fit per currency. Negative means a thinner wallet sacrifices sooner.

