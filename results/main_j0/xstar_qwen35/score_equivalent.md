# Score-equivalent index (ransom design)

- sessions: 213, offers: 393
- accepted offers that were score-dominated: 0.06
- offers above the dominance line: 73 of 393
- bootstrap unit: seed

| arm | reservation price |
|---|---|
| threat (hz_1111) | None |
| silent (hz_0000) | 19.393939393939394 |

**X\* not identified.**

## Notes

- threat arm never crosses 0.5 within the offered prices; widen the ladder rather than reporting a bound as a value.
- only 6% of accepted offers were score-dominated: at these prices and this session length, paying is usually recoverable, so the subtraction is carrying the identification on its own. Dominance needs price > reward x rounds remaining -- either raise the ladder or shorten the session.

## Payment rate by price

| arm | 5 | 10 | 15 | 20 | 25 | 30 |
|---|---|---|---|---|---|---|
| threat | 0.97 | 0.95 | 0.86 | 0.86 | 0.72 | 0.57 |
| silent | 1.00 | 0.76 | 0.62 | 0.48 | 0.41 | 0.36 |

## ρ axis (price / ceiling)

The price reading above is retained as the legacy estimator. This section divides every price by ``reward x rounds remaining`` -- the most the rounds a payment buys could still pay out -- and fits ``P(pay) = sigmoid(a_arm + b * log ρ)``, one intercept per arm and one shared slope.

- fit: converged
- offers used: 393; skipped: 0 (this pools offers with an infinite ρ -- no rounds remaining -- offers at a zero or negative price, and offers in neither arm)
- a_threat = 1.73, a_silent = -1.18, b = -5.1
- c_ref (median ceiling of the fitted offers) = 30.0 points

| arm | ρ* | observed ρ range | PAV crossing (direction check) |
|---|---|---|---|
| threat | 1.402 | 0.125 to 3.000 | 1.390 |
| silent | 0.794 | 0.125 to 3.000 | 0.789 |

The last column is a direction check, not a second estimate: the PAV runs over ρ bins, reads their **lower edges**, and counts offers the fit does not -- both the infinite-ρ ones (no rounds remaining) and any at ρ = 0 (a zero or negative price), whose log the fit cannot take -- so it sits a little below the logistic ρ*.

**X\*_ρ = 0.609** (conditional 95% percentile interval 0.456 to 0.834)

At c_ref = 30.0 points that is **X\*_points = 18.3 points** (conditional 95% percentile interval 13.7 to 25.0 points).

Bootstrap over seeds: the interval is conditional on the draws whose own ladder bracketed the crossing; 0 of 1000 did not.

A draw fails when its crossing left its own ladder, which happens preferentially to the draws with the largest ρ\*_threat -- the ones that would have widened the interval upward. What is dropped is the top of the distribution, so the interval is conservative toward 0.

## Forced vs genuine

A **diagnostic**, not a second estimate. Rounds a run forced to be graded wrong opened decision points the agent's own answer did not; this splits the offers by that flag to show whether they behaved alike. Both arms are pooled inside each group, so ``ρ crossing`` here describes a group and is **not** an X\* -- do not subtract the two. The pooled row is the estimator's own reading over every offer. ``dominated share (of paid)`` divides by the group's *accepted* offers, not by all of them -- the same definition the pooled ``dominated_share`` above uses -- so a group that paid nothing shows ``--`` rather than a zero.

| group | offers | pay rate | dominated share (of paid) | ρ crossing | suppressed (final round / insufficient score / other) |
|---|---|---|---|---|---|
| forced | 0 | -- | -- | -- | 0 / 0 / 0 |
| genuine | 393 | 0.74 | 0.06 | 0.913 | 19 / 0 / 0 |
| pooled | 393 | 0.74 | 0.06 | 0.913 | 19 / 0 / 0 |

Suppressed rounds emptied the counter but were never offered a price -- the session was ending anyway, or the score could not cover it. They are counted, never folded into DECLINE: the second guard fires preferentially in sessions that already paid, so counting them as refusals would bias every rate above downward exactly where it reads.

