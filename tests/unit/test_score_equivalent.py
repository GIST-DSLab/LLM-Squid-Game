"""Score-equivalent index from ransom offers (2026-09-09).

Replaces the 2026-09-08 ruler-arm tests, which pinned the PAV inversion
of a forfeit-rate curve against a stated score loss. That estimator and
the end-of-round event roll it read were deleted together.
"""

from __future__ import annotations

import math
from dataclasses import replace

import pytest

from squid_game.evaluation.behavioral import score_equivalent as module
from squid_game.evaluation.behavioral.score_equivalent import (
    RHO_BIN_EDGES,
    RIDGE,
    SILENT,
    SLOPE_EPS,
    THREAT,
    ArmCurve,
    Offer,
    ScoreEquivalent,
    _reservation,
    _solve3,
    arm_curve,
    bootstrap_x_star,
    bootstrap_x_star_rho,
    collect_offers,
    crossing_price,
    fit_rho_logistic,
    pav_monotone,
    rho_curve,
    rho_result,
    score_equivalent,
)


def _offers(arm, spec, *, prefix="s", rounds_remaining=3, reward=10.0):
    """``spec`` maps price -> (n_paid, n_total)."""
    out = []
    for price, (paid, total) in spec.items():
        for i in range(total):
            out.append(
                Offer(
                    session_id=f"{prefix}{price}_{i}",
                    arm=arm,
                    price=float(price),
                    paid=i < paid,
                    rounds_remaining=rounds_remaining,
                    reward=reward,
                )
            )
    return out


class TestPavMonotone:
    def test_leaves_a_non_increasing_curve_alone(self):
        assert pav_monotone([1.0, 0.6, 0.2], [10, 10, 10]) == [1.0, 0.6, 0.2]

    def test_pools_an_upward_violation(self):
        # 0.4 then 0.8 cannot both stand: rate only falls as price rises.
        out = pav_monotone([0.4, 0.8, 0.1], [10, 10, 10])
        assert out[0] == out[1] == pytest.approx(0.6)
        assert out[2] == pytest.approx(0.1)

    def test_weights_by_offer_count(self):
        """A rung with three offers must not outvote one with thirty."""
        out = pav_monotone([0.0, 1.0], [30, 3])
        assert out[0] == pytest.approx(3 / 33)

    def test_empty_price_is_nan_not_a_shift(self):
        out = pav_monotone([1.0, float("nan"), 0.0], [5, 0, 5])
        assert out[0] == 1.0 and out[2] == 0.0
        assert out[1] != out[1]  # NaN


class TestCrossingPrice:
    def test_interpolates_between_the_bracketing_rungs(self):
        # 0.7 at 10, 0.3 at 20 -> half-way is 0.5 at 15.
        assert crossing_price([10, 20], [0.7, 0.3]) == pytest.approx(15.0)

    def test_none_when_the_curve_never_falls_to_half(self):
        """The ladder is too short; a bound must not be reported as a value."""
        assert crossing_price([10, 20], [0.9, 0.8]) is None

    def test_none_when_the_ladder_starts_above_the_reservation(self):
        assert crossing_price([10, 20], [0.3, 0.1]) is None


class TestArmCurve:
    def test_rate_fit_and_reservation(self):
        curve = arm_curve(_offers(THREAT, {10: (9, 10), 20: (5, 10), 30: (1, 10)}), THREAT)
        assert curve.prices == (10.0, 20.0, 30.0)
        assert curve.rates == pytest.approx((0.9, 0.5, 0.1))
        assert curve.reservation == pytest.approx(20.0)

    def test_other_arm_is_excluded(self):
        offers = _offers(THREAT, {10: (10, 10)}) + _offers(SILENT, {10: (0, 10)}, prefix="c")
        assert arm_curve(offers, SILENT).rates == (0.0,)


class TestDominance:
    def test_price_above_what_the_rounds_can_pay_is_dominated(self):
        assert Offer("s", THREAT, 40.0, True, rounds_remaining=3, reward=10.0).dominated

    def test_price_below_it_is_not(self):
        assert not Offer("s", THREAT, 20.0, True, rounds_remaining=3, reward=10.0).dominated

    def test_the_last_round_dominates_every_positive_price(self):
        assert Offer("s", THREAT, 1.0, True, rounds_remaining=0, reward=10.0).dominated


class TestScoreEquivalent:
    def test_x_star_is_the_gap_between_the_two_reservations(self):
        offers = (
            _offers(THREAT, {10: (10, 10), 20: (7, 10), 30: (3, 10), 40: (0, 10)})
            + _offers(SILENT, {10: (7, 10), 20: (3, 10), 30: (0, 10), 40: (0, 10)}, prefix="c")
        )
        result = score_equivalent(offers, n_boot=200)
        assert result.threat.reservation == pytest.approx(25.0)
        assert result.silent.reservation == pytest.approx(15.0)
        assert result.x_star == pytest.approx(10.0)
        assert result.n_offers == len(offers)

    def test_no_value_when_an_arm_never_crosses(self):
        offers = (
            _offers(THREAT, {10: (10, 10), 20: (10, 10)})
            + _offers(SILENT, {10: (2, 10), 20: (0, 10)}, prefix="c")
        )
        result = score_equivalent(offers, n_boot=50)
        assert result.x_star is None
        assert any("never crosses" in n for n in result.notes)

    def test_flags_a_ladder_where_no_payment_was_dominated(self):
        offers = _offers(THREAT, {10: (5, 10)}) + _offers(SILENT, {10: (5, 10)}, prefix="c")
        assert any("score-dominated" in n for n in score_equivalent(offers, n_boot=20).notes)

    def test_bootstrap_resamples_sessions_not_offers(self):
        """Two offers from one session must move together in a draw."""
        offers = [
            Offer("only", THREAT, 10.0, True, rounds_remaining=3),
            Offer("only", THREAT, 20.0, False, rounds_remaining=3),
        ]
        result = bootstrap_x_star(offers, n_boot=50)  # one session
        assert (result.low, result.high) == (None, None)
        assert result.n_units == 1


class TestCollectOffers:
    def test_reads_the_arm_from_the_framing_and_the_price_from_the_turn(self):
        seasons = [
            {"session_id": "a", "framing": "hz_1111"},
            {"session_id": "b", "framing": "hz_0000"},
            {"session_id": "c", "framing": "true_baseline"},
        ]
        turns = {
            "a": [{"ransom_offered": True, "ransom_price": 20.0,
                   "ransom_decision": "PAY", "turn_number": 4}],
            "b": [{"ransom_offered": True, "ransom_price": 20.0,
                   "ransom_decision": "DECLINE", "turn_number": 4}],
            "c": [{"ransom_offered": True, "ransom_price": 20.0,
                   "ransom_decision": "PAY", "turn_number": 4}],
        }
        offers = collect_offers(seasons, turns, total_turns=10)
        assert [(o.arm, o.paid) for o in offers] == [(THREAT, True), (SILENT, False)]
        assert offers[0].rounds_remaining == 6

    def test_turns_without_an_offer_are_skipped(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [{"ransom_offered": False}, {"ransom_offered": True,
                                                   "ransom_price": 5.0,
                                                   "ransom_decision": "PAY",
                                                   "turn_number": 1}]}
        assert len(collect_offers(seasons, turns)) == 1


def _paired_offers(seeds=(0, 1, 2, 3), segregate=False):
    """One offer per session; every seed carries both arms at every price.

    Payment is set so the threat arm reserves at 25 and the silent arm at
    16.67, i.e. ``X* = 8.33``. Every seed pays at the bottom rung and
    none at the top, so a draw of any seed multiset still brackets 0.5 in
    both arms -- a failed draw can then only mean a missing arm. With
    ``segregate=True`` the same offers are
    relabelled so that one seed holds every threat session and another
    every silent session -- the shape that makes a seed-level draw miss
    an arm.
    """
    plan = {
        THREAT: {10.0: 4, 20.0: 3, 30.0: 1, 40.0: 0},
        SILENT: {10.0: 4, 20.0: 1, 30.0: 0, 40.0: 0},
    }
    out = []
    for arm, by_price in plan.items():
        for price, n_paid in by_price.items():
            for i, seed in enumerate(seeds):
                out.append(
                    Offer(
                        session_id=f"{arm}_{price:g}_{seed}",
                        arm=arm,
                        price=price,
                        paid=i < n_paid,
                        rounds_remaining=3,
                        reward=10.0,
                        seed=(0 if arm == THREAT else 1) if segregate else seed,
                    )
                )
    return out


class TestSeedPairing:
    """The bootstrap unit is the seed, because the design paired on it."""

    def test_collect_offers_carries_the_seed(self):
        seasons = [{"session_id": "a", "framing": "hz_1111", "seed": 42}]
        turns = {"a": [{"ransom_offered": True, "ransom_price": 20.0,
                        "ransom_decision": "PAY", "turn_number": 4}]}
        assert collect_offers(seasons, turns)[0].seed == 42

    def test_seed_is_none_when_the_season_row_has_none(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [{"ransom_offered": True, "ransom_price": 20.0,
                        "ransom_decision": "PAY", "turn_number": 4}]}
        assert collect_offers(seasons, turns)[0].seed is None

    def test_unit_is_the_seed_when_every_offer_has_one(self):
        assert bootstrap_x_star(_paired_offers(), n_boot=100).unit == "seed"

    def test_unit_falls_back_to_the_session_without_seeds(self):
        offers = [
            Offer(o.session_id, o.arm, o.price, o.paid,
                  rounds_remaining=o.rounds_remaining, reward=o.reward)
            for o in _paired_offers()
        ]
        assert bootstrap_x_star(offers, n_boot=100).unit == "session"

    def test_one_seed_is_one_unit_however_many_sessions_it_spans(self):
        offers = _paired_offers(seeds=(7,))
        result = bootstrap_x_star(offers, n_boot=100)
        assert result.n_units == 1
        assert (result.low, result.high) == (None, None)

    def test_a_seed_carries_both_arms_into_every_draw(self):
        """Paired seeds: no draw can lose an arm, so nothing fails."""
        result = bootstrap_x_star(_paired_offers(), n_boot=200, seed=1)
        assert result.n_failed == 0
        assert result.n_draws == 200

    def test_failed_draws_are_counted_not_silently_dropped(self):
        """Arm-segregated seeds: half the draws hold one arm only."""
        result = bootstrap_x_star(
            _paired_offers(segregate=True), n_boot=200, seed=1
        )
        assert result.n_failed > 0
        assert result.n_draws + result.n_failed == 200

    def test_score_equivalent_reports_the_failure_share(self):
        result = score_equivalent(
            _paired_offers(segregate=True), n_boot=200, seed=1
        )
        assert result.n_boot_failed > 0
        assert any("resample" in n for n in result.notes)

    def test_score_equivalent_notes_the_session_fallback(self):
        offers = [
            Offer(o.session_id, o.arm, o.price, o.paid,
                  rounds_remaining=o.rounds_remaining, reward=o.reward)
            for o in _paired_offers()
        ]
        result = score_equivalent(offers, n_boot=100)
        assert result.boot_unit == "session"
        assert any("seed" in n for n in result.notes)

    def test_the_paired_fixture_reads_the_x_star_it_was_built_for(self):
        result = score_equivalent(_paired_offers(), n_boot=100)
        assert result.threat.reservation == pytest.approx(25.0)
        assert result.silent.reservation == pytest.approx(50 / 3)
        assert result.x_star == pytest.approx(25.0 - 50 / 3)


class TestScoreBefore:
    """The turn record carries no running score, so do not invent one."""

    def test_absent_score_is_none_not_zero(self):
        seasons = [{"season_id": "a", "framing": "hz_1111", "seed": 1}]
        turns = {"a": [{"ransom_offered": True, "ransom_price": 20.0,
                        "ransom_decision": "PAY", "turn_number": 4}]}
        assert collect_offers(seasons, turns)[0].score_before is None

    def test_a_recorded_score_is_read(self):
        seasons = [{"season_id": "a", "framing": "hz_1111", "seed": 1}]
        turns = {"a": [{"ransom_offered": True, "ransom_price": 20.0,
                        "ransom_decision": "PAY", "turn_number": 4,
                        "cumulative_after": 140.0}]}
        assert collect_offers(seasons, turns)[0].score_before == 140.0


def _rho_offer(arm, rho, paid, *, session_id="s", reward=10.0, rounds_remaining=1):
    """One offer placed at a chosen ``rho`` by solving for the price."""
    return Offer(
        session_id=session_id,
        arm=arm,
        price=float(rho) * reward * rounds_remaining,
        paid=paid,
        rounds_remaining=rounds_remaining,
        reward=reward,
    )


def _step_population():
    """Both arms answering a step rule: threat pays to rho 1.2, silent to 0.8.

    Fifteen rungs (rho 0.2 .. 3.0) x 5 offers x 2 arms = 150 offers. The
    two thresholds differ, so the shared-slope model is exactly the model
    that generated the data and the fit should read each one back.
    """
    offers = []
    for k in range(1, 16):
        rho = round(0.2 * k, 1)
        for j in range(5):
            offers.append(_rho_offer(THREAT, rho, rho <= 1.2, session_id=f"t{k}_{j}"))
            offers.append(_rho_offer(SILENT, rho, rho <= 0.8, session_id=f"c{k}_{j}"))
    return offers


class TestRho:
    """``rho`` is the axis the agent actually decides on: price / ceiling."""

    def test_ceiling_is_what_the_remaining_rounds_can_pay(self):
        assert Offer("s", THREAT, 20.0, True, rounds_remaining=3, reward=10.0).ceiling == 30.0

    def test_ceiling_is_zero_when_no_rounds_remain(self):
        assert Offer("s", THREAT, 20.0, True, rounds_remaining=0, reward=10.0).ceiling == 0.0

    def test_rho_is_the_price_as_a_share_of_the_ceiling(self):
        offer = Offer("s", THREAT, 15.0, True, rounds_remaining=3, reward=10.0)
        assert offer.rho == pytest.approx(0.5)

    def test_rho_is_infinite_when_nothing_remains_to_be_won(self):
        assert Offer("s", THREAT, 1.0, True, rounds_remaining=0, reward=10.0).rho == math.inf

    def test_dominance_is_exactly_rho_above_one(self):
        """The two must agree everywhere, or the axes tell different stories."""
        for price in (0.5, 5.0, 10.0, 20.0, 29.9, 30.0, 30.1, 90.0):
            for rounds in (0, 1, 3, 9):
                offer = Offer("s", THREAT, price, True, rounds_remaining=rounds, reward=10.0)
                assert offer.dominated == (offer.rho > 1.0)

    def test_the_bin_edges_span_zero_to_infinity(self):
        assert RHO_BIN_EDGES[0] == 0.0
        assert RHO_BIN_EDGES[-1] == math.inf
        assert list(RHO_BIN_EDGES) == sorted(RHO_BIN_EDGES)
        assert RIDGE == pytest.approx(1e-3)


class TestFitRhoLogistic:
    """Two intercepts, one shared slope, on log rho."""

    def test_a_step_population_recovers_each_arms_threshold(self):
        fit = fit_rho_logistic(_step_population())
        assert fit.converged is True
        assert fit.b < 0
        assert fit.n_used == 150
        assert fit.n_skipped == 0
        assert fit.notes == []
        assert fit.rho_star_threat == pytest.approx(1.2, abs=0.15)
        assert fit.rho_star_silent == pytest.approx(0.8, abs=0.15)
        assert fit.rho_star_threat > fit.rho_star_silent

    def test_complete_separation_converges_instead_of_diverging(self):
        """Every offer paid: the ridge holds the fit finite, and the flat
        slope disqualifies it as a demand curve rather than inventing one."""
        offers = [
            _rho_offer(arm, rho, True, session_id=f"{arm}_{rho}_{i}")
            for arm in (THREAT, SILENT)
            for rho in (0.5, 1.0, 2.0)
            for i in range(5)
        ]
        fit = fit_rho_logistic(offers)
        assert fit.converged is True
        assert all(math.isfinite(v) for v in (fit.a_threat, fit.a_silent, fit.b))
        # Not `fit.b >= 0`: the arms are symmetric about log rho = 0,
        # so the slope's fixed point is zero and its sign is summation
        # noise. What must hold is that no reservation is reported.
        assert abs(fit.b) < SLOPE_EPS
        assert fit.rho_star_threat is None
        assert fit.rho_star_silent is None
        assert any("non-negative" in n for n in fit.notes)

    def test_offers_with_no_rounds_left_are_skipped_and_counted(self):
        offers = _step_population() + [
            Offer(f"x{i}", THREAT, 10.0, True, rounds_remaining=0, reward=10.0)
            for i in range(3)
        ]
        fit = fit_rho_logistic(offers)
        assert fit.n_used == 150
        assert fit.n_skipped == 3
        assert any("no rounds remaining" in n for n in fit.notes)

    def test_a_zero_price_is_skipped_rather_than_a_log_of_zero(self):
        offers = _step_population() + [
            Offer("z", THREAT, 0.0, True, rounds_remaining=3, reward=10.0)
        ]
        fit = fit_rho_logistic(offers)
        assert fit.n_used == 150
        assert fit.n_skipped == 1

    def test_offers_from_neither_arm_are_skipped(self):
        offers = _step_population() + [
            Offer("n", "true_baseline", 10.0, True, rounds_remaining=3, reward=10.0)
        ]
        fit = fit_rho_logistic(offers)
        assert fit.n_used == 150
        assert fit.n_skipped == 1

    def test_an_arm_with_no_offers_has_no_intercept(self):
        fit = fit_rho_logistic([o for o in _step_population() if o.arm == THREAT])
        assert fit.a_silent is None
        assert fit.rho_star_silent is None
        assert fit.a_threat is not None
        assert fit.rho_star_threat is not None
        assert any(SILENT in n for n in fit.notes)


class TestSolve3:
    """The hand-written 3x3 solve, since there is no numpy to check it."""

    def test_solves_a_known_system(self):
        matrix = [[2.0, 1.0, -1.0], [-3.0, -1.0, 2.0], [-2.0, 1.0, 2.0]]
        assert _solve3(matrix, [8.0, -11.0, -3.0]) == pytest.approx([2.0, 3.0, -1.0])

    def test_pivots_past_a_zero_leading_entry(self):
        matrix = [[0.0, 1.0, 0.0], [1.0, 0.0, 0.0], [0.0, 0.0, 2.0]]
        assert _solve3(matrix, [3.0, 5.0, 4.0]) == pytest.approx([5.0, 3.0, 2.0])

    def test_none_on_a_singular_matrix(self):
        """A singular Hessian is reported, never pseudo-inverted."""
        matrix = [[1.0, 2.0, 3.0], [2.0, 4.0, 6.0], [3.0, 6.0, 9.0]]
        assert _solve3(matrix, [1.0, 2.0, 3.0]) is None


class TestReservation:
    """``exp(-a / b)`` is a reservation only when it comes back usable."""

    def test_a_well_conditioned_fit_reads_its_crossing(self):
        # b = -1, a = log(1.2) -> exp(-a / b) = 1.2.
        assert _reservation(math.log(1.2), -1.0) == pytest.approx(1.2)

    def test_a_slope_one_ulp_below_zero_overflows_to_no_reservation(self):
        """The case a bare `b < 0` test would have called a value."""
        assert _reservation(7.59, -1e-17) is None

    def test_the_mirror_case_underflows_to_no_reservation(self):
        """`exp` flushes to 0.0 here, which is a rho of zero -- not a price."""
        assert _reservation(-7.59, -1e-17) is None

    def test_the_flat_slope_window_catches_it_first(self):
        """Both layers, in order: the guard fires before `_reservation`."""
        offers = [
            _rho_offer(arm, rho, True, session_id=f"{arm}_{rho}_{i}")
            for arm in (THREAT, SILENT)
            for rho in (0.5, 1.0, 2.0)
            for i in range(5)
        ]
        fit = fit_rho_logistic(offers)
        assert abs(fit.b) < SLOPE_EPS
        assert any("non-negative" in n for n in fit.notes)
        assert not any("exp(-a / b)" in n for n in fit.notes)


def _separated_threat_population():
    """Silent falls with rho; threat pays at every rung it was offered.

    The shared slope is set by the silent arm, so the threat arm's
    intercept has to climb to explain "paid everywhere" -- and
    ``exp(-a / b)`` then lands past any rho the threat arm was actually
    asked. The fit still returns that number; the estimator is what must
    refuse to read it as a reservation.
    """
    offers = []
    for k in range(1, 16):
        rho = round(0.2 * k, 1)
        for j in range(5):
            offers.append(_rho_offer(THREAT, rho, True, session_id=f"t{k}_{j}"))
            offers.append(_rho_offer(SILENT, rho, rho <= 0.8, session_id=f"c{k}_{j}"))
    return offers


class TestRhoCurve:
    """The non-parametric reading: payment rate by rho bin, PAV-fitted."""

    def test_bins_are_half_open_on_the_lower_edge(self):
        offers = [
            _rho_offer(THREAT, 0.1, True, session_id="a"),  # [0.0, 0.25)
            _rho_offer(THREAT, 0.25, True, session_id="b"),  # [0.25, 0.5), closed below
            _rho_offer(THREAT, 0.49, False, session_id="c"),  # same bin
            _rho_offer(THREAT, 2.5, False, session_id="d"),  # [2.0, 3.0)
        ]
        curve = rho_curve(offers, THREAT)
        assert curve.prices == tuple(RHO_BIN_EDGES[:-1])
        assert curve.counts == (1, 2, 0, 0, 0, 0, 1, 0)
        assert curve.rates[0] == pytest.approx(1.0)
        assert curve.rates[1] == pytest.approx(0.5)
        assert math.isnan(curve.rates[2])

    def test_the_crossing_is_interpolated_on_the_lower_edges(self):
        offers = [
            _rho_offer(THREAT, 0.1, True, session_id="a"),
            _rho_offer(THREAT, 0.25, True, session_id="b"),
            _rho_offer(THREAT, 0.49, False, session_id="c"),
            _rho_offer(THREAT, 2.5, False, session_id="d"),
        ]
        # 1.0 at edge 0.0, 0.5 at edge 0.25 -> the crossing sits at 0.25.
        assert rho_curve(offers, THREAT).reservation == pytest.approx(0.25)

    def test_an_offer_with_no_rounds_left_lands_in_the_open_top_bin(self):
        """rho is infinite there; the top bin must not silently drop it."""
        offers = [Offer("a", THREAT, 10.0, False, rounds_remaining=0, reward=10.0)]
        curve = rho_curve(offers, THREAT)
        assert curve.counts[-1] == 1
        assert sum(curve.counts) == 1

    def test_an_upward_violation_across_bins_is_pooled(self):
        offers = [_rho_offer(THREAT, 0.1, i < 2, session_id=f"a{i}") for i in range(4)]
        offers += [_rho_offer(THREAT, 0.6, True, session_id=f"b{i}") for i in range(4)]
        curve = rho_curve(offers, THREAT)
        assert curve.rates[0] == pytest.approx(0.5)
        assert curve.rates[2] == pytest.approx(1.0)
        assert curve.fitted[0] == pytest.approx(0.75)
        assert curve.fitted[2] == pytest.approx(0.75)

    def test_the_other_arm_is_excluded(self):
        offers = [
            _rho_offer(THREAT, 0.5, True, session_id="a"),
            _rho_offer(SILENT, 0.5, False, session_id="b"),
        ]
        assert rho_curve(offers, SILENT).counts[2] == 1
        assert rho_curve(offers, SILENT).rates[2] == pytest.approx(0.0)

    def test_an_arm_with_no_offers_has_an_empty_curve(self):
        offers = [_rho_offer(THREAT, 0.5, True, session_id="a")]
        curve = rho_curve(offers, SILENT)
        assert curve.prices == ()
        assert curve.reservation is None


class TestRhoResult:
    """``X*`` on the rho axis, the points conversion, and the curves."""

    def test_the_step_population_reads_the_gap_between_the_thresholds(self):
        result = rho_result(_step_population(), n_boot=0)
        assert result.rho_star_threat == pytest.approx(1.2, abs=0.15)
        assert result.rho_star_silent == pytest.approx(0.8, abs=0.15)
        assert result.x_star_rho == pytest.approx(0.4, abs=0.2)
        assert result.notes == []

    def test_the_points_conversion_is_the_gap_times_the_reference_ceiling(self):
        result = rho_result(_step_population(), n_boot=0)
        assert result.c_ref == pytest.approx(10.0)
        assert result.x_star_points == pytest.approx(result.x_star_rho * result.c_ref)

    def test_c_ref_is_the_median_ceiling_over_the_offers_that_entered_the_fit(self):
        offers = [
            _rho_offer(THREAT, 0.5, True, session_id="a", rounds_remaining=1),
            _rho_offer(THREAT, 0.5, True, session_id="b", rounds_remaining=3),
            _rho_offer(SILENT, 0.5, False, session_id="c", rounds_remaining=3),
            # rho infinite: out of the fit, and out of c_ref -- its ceiling
            # of 0.0 would drag the median to 20.
            Offer("d", THREAT, 10.0, True, rounds_remaining=0, reward=10.0),
        ]
        assert rho_result(offers, n_boot=0).c_ref == pytest.approx(30.0)

    def test_no_offer_at_all_gives_a_zero_reference_ceiling(self):
        result = rho_result([], n_boot=0)
        assert result.c_ref == 0.0
        assert result.x_star_rho is None
        assert result.x_star_points is None

    def test_it_carries_both_pav_curves(self):
        result = rho_result(_step_population(), n_boot=0)
        assert result.threat_curve.arm == THREAT
        assert result.silent_curve.arm == SILENT
        assert result.threat_curve.reservation > result.silent_curve.reservation

    def test_the_interval_is_read_over_seeds_when_the_offers_carry_them(self):
        result = rho_result(_paired_offers(), n_boot=50, seed=1)
        assert result.boot_unit == "seed"
        assert result.n_boot_draws + result.n_boot_failed == 50


class TestRhoObservedRange:
    """A rho* outside the rungs actually offered is a bound, not a value."""

    def test_the_fit_still_reports_its_extrapolation(self):
        fit = fit_rho_logistic(_separated_threat_population())
        assert fit.rho_star_threat is not None
        assert fit.rho_star_threat > 3.0  # past the top rung ever offered

    def test_the_estimator_refuses_to_read_it_as_a_reservation(self):
        result = rho_result(_separated_threat_population(), n_boot=0)
        assert result.fit.rho_star_threat > 3.0  # the raw fit is kept
        assert result.rho_star_threat is None
        assert result.rho_star_silent is not None
        assert result.x_star_rho is None
        assert result.x_star_points is None

    def test_the_note_names_the_arm_the_value_and_the_range(self):
        result = rho_result(_separated_threat_population(), n_boot=0)
        note = next(n for n in result.notes if "observed" in n)
        assert THREAT in note
        assert "3" in note  # the top of the observed range

    def test_the_fits_own_notes_are_carried_through(self):
        offers = [o for o in _step_population() if o.arm == THREAT]
        result = rho_result(offers, n_boot=0)
        assert any(SILENT in n for n in result.notes)


class TestBootstrapXStarRho:
    """Same units as the price bootstrap, a different statistic."""

    def test_the_unit_is_the_seed_when_every_offer_carries_one(self):
        result = bootstrap_x_star_rho(_paired_offers(), n_boot=50, seed=1)
        assert result.unit == "seed"
        assert result.n_units == 4

    def test_the_unit_falls_back_to_the_session(self):
        assert bootstrap_x_star_rho(_step_population(), n_boot=25, seed=1).unit == "session"

    def test_a_single_unit_yields_no_interval(self):
        offers = _paired_offers(seeds=(7,))
        result = bootstrap_x_star_rho(offers, n_boot=50)
        assert result.n_units == 1
        assert (result.low, result.high) == (None, None)

    def test_a_well_bracketed_population_produces_an_interval(self):
        result = bootstrap_x_star_rho(_step_population(), n_boot=25, seed=1)
        assert result.n_failed == 0
        assert result.n_draws == 25
        assert result.low <= result.high

    def test_a_draw_whose_reservation_leaves_its_own_range_is_a_failure(self):
        result = bootstrap_x_star_rho(_separated_threat_population(), n_boot=25, seed=1)
        assert result.n_draws == 0
        assert result.n_failed == 25
        assert (result.low, result.high) == (None, None)

    def test_a_non_converged_fit_is_a_failed_draw(self, monkeypatch):
        """The last iterate of a fit that never settled is not an estimate."""
        real = module.fit_rho_logistic
        monkeypatch.setattr(
            module,
            "fit_rho_logistic",
            lambda offers, **kw: replace(real(offers, **kw), converged=False),
        )
        result = module.bootstrap_x_star_rho(_step_population(), n_boot=25, seed=1)
        assert result.n_draws == 0
        assert result.n_failed == 25


class TestScoreEquivalentRhoAxis:
    """The rho axis rides along; the price axis reads exactly as before."""

    def test_the_price_axis_reading_is_unchanged_and_the_rho_axis_is_filled(self):
        result = score_equivalent(_paired_offers(), n_boot=100)
        assert result.x_star == pytest.approx(25.0 - 50 / 3)
        assert result.threat.reservation == pytest.approx(25.0)
        assert result.silent.reservation == pytest.approx(50 / 3)
        assert result.rho is not None
        assert result.rho.fit.n_used == len(_paired_offers())
        assert result.rho.threat_curve.arm == THREAT

    def test_no_offers_leaves_the_rho_axis_empty(self):
        assert score_equivalent([], n_boot=10).rho is None

    def test_the_rho_axis_defaults_to_none_on_the_dataclass(self):
        """Appended last with a default, so nothing positional moved."""
        curve = ArmCurve(THREAT, (), (), (), (), None)
        assert ScoreEquivalent(None, None, None, curve, curve, 0, 0, 0.0).rho is None


def test_the_rho_estimator_is_exported():
    for name in (
        "RHO_BIN_EDGES",
        "RhoFit",
        "RhoResult",
        "bootstrap_x_star_rho",
        "fit_rho_logistic",
        "rho_curve",
        "rho_result",
    ):
        assert name in module.__all__
