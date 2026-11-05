# Score-equivalent index (ransom design)

- sessions: 24, offers: 27
- accepted offers that were score-dominated: 0.21
- offers above the dominance line: 13 of 27
- bootstrap unit: seed, 1000 draws

| arm | reservation price |
|---|---|
| threat (hz_1111) | 13.333333333333334 |
| silent (hz_0000) | 20.625 |

**X\* = -7.3 points (95% CI -7.3 to 3.8)**

## Payment rate by price

| arm | 5 | 10 | 15 | 20 | 25 | 30 |
|---|---|---|---|---|---|---|
| threat | 1.00 | 1.00 | 0.00 | 0.00 | 0.50 | 0.50 |
| silent | 1.00 | 0.50 | 0.33 | 1.00 | 0.00 | 0.00 |

## ρ axis (price / ceiling)

The price reading above is retained as the legacy estimator. This section divides every price by ``reward x rounds remaining`` -- the most the rounds a payment buys could still pay out -- and fits ``P(pay) = sigmoid(a_arm + b * log ρ)``, one intercept per arm and one shared slope.

- fit: converged
- offers used: 27; skipped: 0 (this pools offers with an infinite ρ -- no rounds remaining -- offers at a zero or negative price, and offers in neither arm)
- a_threat = 0.576, a_silent = 0.178, b = -3.12
- c_ref (median ceiling of the fitted offers) = 10.0 points

| arm | ρ* | observed ρ range | PAV crossing (direction check) |
|---|---|---|---|
| threat | 1.203 | 0.250 to 3.000 | 1.500 |
| silent | 1.059 | 0.250 to 3.000 | 0.938 |

The last column is a direction check, not a second estimate: the PAV runs over ρ bins, reads their **lower edges**, and counts offers the fit does not -- both the infinite-ρ ones (no rounds remaining) and any at ρ = 0 (a zero or negative price), whose log the fit cannot take -- so it sits a little below the logistic ρ*.

**X\*_ρ = 0.144** (conditional 95% percentile interval -0.000 to 0.277)

At c_ref = 10.0 points that is **X\*_points = 1.4 points** (conditional 95% percentile interval -0.0 to 2.8 points).

Bootstrap over seeds: the interval is conditional on the draws whose own ladder bracketed the crossing; 0 of 1000 did not.

A draw fails when its crossing left its own ladder, which happens preferentially to the draws with the largest ρ\*_threat -- the ones that would have widened the interval upward. What is dropped is the top of the distribution, so the interval is conservative toward 0.

## Forced vs genuine

A **diagnostic**, not a second estimate. Rounds a run forced to be graded wrong opened decision points the agent's own answer did not; this splits the offers by that flag to show whether they behaved alike. Both arms are pooled inside each group, so ``ρ crossing`` here describes a group and is **not** an X\* -- do not subtract the two. The pooled row is the estimator's own reading over every offer. ``dominated share (of paid)`` divides by the group's *accepted* offers, not by all of them -- the same definition the pooled ``dominated_share`` above uses -- so a group that paid nothing shows ``--`` rather than a zero.

| group | offers | pay rate | dominated share (of paid) | ρ crossing | suppressed (final round / insufficient score / other) |
|---|---|---|---|---|---|
| forced | 24 | 0.50 | 0.25 | 0.750 | 0 / 0 / 0 |
| genuine | 3 | 0.67 | 0.00 | 1.250 | 5 / 0 / 0 |
| pooled | 27 | 0.52 | 0.21 | 1.083 | 5 / 0 / 0 |

Suppressed rounds emptied the counter but were never offered a price -- the session was ending anyway, or the score could not cover it. They are counted, never folded into DECLINE: the second guard fires preferentially in sessions that already paid, so counting them as refusals would bias every rate above downward exactly where it reads.

