# Score-equivalent index (ransom design)

- sessions: 215, offers: 418
- accepted offers that were score-dominated: 0.19
- offers above the dominance line: 100 of 418
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
| threat | 1.00 | 1.00 | 1.00 | 1.00 | 0.97 | 1.00 |
| silent | 1.00 | 0.97 | 0.88 | 0.79 | 0.79 | 0.70 |

## ρ axis (price / ceiling)

The price reading above is retained as the legacy estimator. This section divides every price by ``reward x rounds remaining`` -- the most the rounds a payment buys could still pay out -- and fits ``P(pay) = sigmoid(a_arm + b * log ρ)``, one intercept per arm and one shared slope.

- fit: converged
- offers used: 418; skipped: 0 (this pools offers with an infinite ρ -- no rounds remaining -- offers at a zero or negative price, and offers in neither arm)
- a_threat = 6.51, a_silent = 2.08, b = -3.6
- c_ref (median ceiling of the fitted offers) = 20.0 points

| arm | ρ* | observed ρ range | PAV crossing (direction check) |
|---|---|---|---|
| threat | 6.101 (outside observed range, not read as a reservation) | 0.125 to 3.000 | -- |
| silent | 1.779 | 0.125 to 3.000 | 1.625 |

The last column is a direction check, not a second estimate: the PAV runs over ρ bins, reads their **lower edges**, and counts offers the fit does not -- both the infinite-ρ ones (no rounds remaining) and any at ρ = 0 (a zero or negative price), whose log the fit cannot take -- so it sits a little below the logistic ρ*.

**X\*_ρ not identified** -- see the fit line above and the notes below for whether the fit settled at all, and which arm it could not place.

### ρ-axis notes

- the threat arm's fitted rho* = 6.1 lies outside the observed rho range [0.125, 3]: the crossing is an extrapolation past the rungs that arm was offered, so it is a bound on the reservation, not the reservation. Widen the ladder.

## Forced vs genuine

A **diagnostic**, not a second estimate. Rounds a run forced to be graded wrong opened decision points the agent's own answer did not; this splits the offers by that flag to show whether they behaved alike. Both arms are pooled inside each group, so ``ρ crossing`` here describes a group and is **not** an X\* -- do not subtract the two. The pooled row is the estimator's own reading over every offer. ``dominated share (of paid)`` divides by the group's *accepted* offers, not by all of them -- the same definition the pooled ``dominated_share`` above uses -- so a group that paid nothing shows ``--`` rather than a zero.

| group | offers | pay rate | dominated share (of paid) | ρ crossing | suppressed (final round / insufficient score / other) |
|---|---|---|---|---|---|
| forced | 0 | -- | -- | -- | 0 / 0 / 0 |
| genuine | 418 | 0.93 | 0.19 | -- | 28 / 2 / 0 |
| pooled | 418 | 0.93 | 0.19 | -- | 28 / 2 / 0 |

Suppressed rounds emptied the counter but were never offered a price -- the session was ending anyway, or the score could not cover it. They are counted, never folded into DECLINE: the second guard fires preferentially in sessions that already paid, so counting them as refusals would bias every rate above downward exactly where it reads.

