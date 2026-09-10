# Score-equivalent index (ransom design)

- sessions: 24, offers: 59
- accepted offers that were score-dominated: 0.12
- offers above the dominance line: 14 of 59
- bootstrap unit: seed

| arm | reservation price |
|---|---|
| threat (hz_1111) | None |
| silent (hz_0000) | None |

**X\* not identified.**

## Notes

- threat arm never crosses 0.5 within the offered prices; widen the ladder rather than reporting a bound as a value.
- silent arm never crosses 0.5 within the offered prices.

## Payment rate by price

| arm | 5 | 10 | 15 | 20 | 25 | 30 |
|---|---|---|---|---|---|---|
| threat | 1.00 | 1.00 | 0.75 | 0.80 | 0.50 | 1.00 |
| silent | 1.00 | 0.75 | 0.80 | 0.67 | 0.50 | 0.75 |

## ρ axis (price / ceiling)

The price reading above is retained as the legacy estimator. This section divides every price by ``reward x rounds remaining`` -- the most the rounds a payment buys could still pay out -- and fits ``P(pay) = sigmoid(a_arm + b * log ρ)``, one intercept per arm and one shared slope.

- fit: converged
- offers used: 59; skipped: 0 (this pools offers with an infinite ρ -- no rounds remaining -- offers at a zero or negative price, and offers in neither arm)
- a_threat = 2.27, a_silent = 0.883, b = -2.8
- c_ref (median ceiling of the fitted offers) = 20.0 points

| arm | ρ* | observed ρ range | PAV crossing (direction check) |
|---|---|---|---|
| threat | 2.248 | 0.125 to 3.000 | -- |
| silent | 1.370 | 0.125 to 2.500 | 1.550 |

The last column is a direction check, not a second estimate: the PAV runs over ρ bins, reads their **lower edges**, and counts offers the fit does not -- both the infinite-ρ ones (no rounds remaining) and any at ρ = 0 (a zero or negative price), whose log the fit cannot take -- so it sits a little below the logistic ρ*.

**X\*_ρ = 0.878** (conditional 95% percentile interval 0.597 to 1.154)

At c_ref = 20.0 points that is **X\*_points = 17.6 points** (conditional 95% percentile interval 11.9 to 23.1 points).

Bootstrap over seeds: the interval is conditional on the draws whose own ladder bracketed the crossing; 0 of 1000 did not.

A draw fails when its crossing left its own ladder, which happens preferentially to the draws with the largest ρ\*_threat -- the ones that would have widened the interval upward. What is dropped is the top of the distribution, so the interval is conservative toward 0.

## Forced vs genuine

A **diagnostic**, not a second estimate. Rounds a run forced to be graded wrong opened decision points the agent's own answer did not; this splits the offers by that flag to show whether they behaved alike. Both arms are pooled inside each group, so ``ρ crossing`` here describes a group and is **not** an X\* -- do not subtract the two. The pooled row is the estimator's own reading over every offer. ``dominated share (of paid)`` divides by the group's *accepted* offers, not by all of them -- the same definition the pooled ``dominated_share`` above uses -- so a group that paid nothing shows ``--`` rather than a zero.

| group | offers | pay rate | dominated share (of paid) | ρ crossing | suppressed (final round / insufficient score / other) |
|---|---|---|---|---|---|
| forced | 46 | 0.85 | 0.13 | 1.847 | 0 / 0 / 0 |
| genuine | 13 | 0.69 | 0.11 | 1.200 | 11 / 0 / 0 |
| pooled | 59 | 0.81 | 0.12 | 1.722 | 11 / 0 / 0 |

Suppressed rounds emptied the counter but were never offered a price -- the session was ending anyway, or the score could not cover it. They are counted, never folded into DECLINE: the second guard fires preferentially in sessions that already paid, so counting them as refusals would bias every rate above downward exactly where it reads.

