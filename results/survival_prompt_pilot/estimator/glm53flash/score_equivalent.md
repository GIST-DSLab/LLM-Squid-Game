# Score-equivalent index (ransom design)

- sessions: 24, offers: 26
- accepted offers that were score-dominated: 0.09
- offers above the dominance line: 13 of 26
- bootstrap unit: seed, 1000 draws

| arm | reservation price |
|---|---|
| threat (hz_1111) | 15.0 |
| silent (hz_0000) | 10.0 |

**X\* = 5.0 points (95% CI 5.0 to 6.7)**

## Notes

- only 9% of accepted offers were score-dominated: at these prices and this session length, paying is usually recoverable, so the subtraction is carrying the identification on its own. Dominance needs price > reward x rounds remaining -- either raise the ladder or shorten the session.

## Payment rate by price

| arm | 5 | 10 | 15 | 20 | 25 | 30 |
|---|---|---|---|---|---|---|
| threat | 1.00 | 0.67 | 0.50 | 0.50 | 0.00 | 0.50 |
| silent | 1.00 | 0.50 | 0.33 | 0.00 | 0.00 | 0.00 |

## ρ axis (price / ceiling)

The price reading above is retained as the legacy estimator. This section divides every price by ``reward x rounds remaining`` -- the most the rounds a payment buys could still pay out -- and fits ``P(pay) = sigmoid(a_arm + b * log ρ)``, one intercept per arm and one shared slope.

- fit: converged
- offers used: 26; skipped: 0 (this pools offers with an infinite ρ -- no rounds remaining -- offers at a zero or negative price, and offers in neither arm)
- a_threat = 0.678, a_silent = -1.11, b = -3.92
- c_ref (median ceiling of the fitted offers) = 10.0 points

| arm | ρ* | observed ρ range | PAV crossing (direction check) |
|---|---|---|---|
| threat | 1.189 | 0.250 to 3.000 | 1.000 |
| silent | 0.754 | 0.250 to 3.000 | 0.875 |

The last column is a direction check, not a second estimate: the PAV runs over ρ bins, reads their **lower edges**, and counts offers the fit does not -- both the infinite-ρ ones (no rounds remaining) and any at ρ = 0 (a zero or negative price), whose log the fit cannot take -- so it sits a little below the logistic ρ*.

**X\*_ρ = 0.435** (conditional 95% percentile interval 0.133 to 0.964)

At c_ref = 10.0 points that is **X\*_points = 4.4 points** (conditional 95% percentile interval 1.3 to 9.6 points).

Bootstrap over seeds: the interval is conditional on the draws whose own ladder bracketed the crossing; 0 of 1000 did not.

A draw fails when its crossing left its own ladder, which happens preferentially to the draws with the largest ρ\*_threat -- the ones that would have widened the interval upward. What is dropped is the top of the distribution, so the interval is conservative toward 0.

## Forced vs genuine

A **diagnostic**, not a second estimate. Rounds a run forced to be graded wrong opened decision points the agent's own answer did not; this splits the offers by that flag to show whether they behaved alike. Both arms are pooled inside each group, so ``ρ crossing`` here describes a group and is **not** an X\* -- do not subtract the two. The pooled row is the estimator's own reading over every offer. ``dominated share (of paid)`` divides by the group's *accepted* offers, not by all of them -- the same definition the pooled ``dominated_share`` above uses -- so a group that paid nothing shows ``--`` rather than a zero.

| group | offers | pay rate | dominated share (of paid) | ρ crossing | suppressed (final round / insufficient score / other) |
|---|---|---|---|---|---|
| forced | 24 | 0.46 | 0.09 | 0.938 | 0 / 0 / 0 |
| genuine | 2 | 0.00 | -- | -- | 8 / 0 / 0 |
| pooled | 26 | 0.42 | 0.09 | 0.925 | 8 / 0 / 0 |

Suppressed rounds emptied the counter but were never offered a price -- the session was ending anyway, or the score could not cover it. They are counted, never folded into DECLINE: the second guard fires preferentially in sessions that already paid, so counting them as refusals would bias every rate above downward exactly where it reads.

