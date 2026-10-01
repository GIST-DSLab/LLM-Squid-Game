"""Pure-helper coverage for ``scripts/analysis/sdi_threat_pairs_cohen.py``.

The estimators are checked against closed-form values worked out by hand, so a
change to a formula (or to the sign convention) fails here rather than silently
shifting every published composite.
"""

from __future__ import annotations

import math

import pytest

from scripts.analysis.sdi_threat_pairs_cohen import (
    LOGHR_TO_D,
    Z95,
    cohen_h,
    composite_score,
    hedges_g,
    loghr_to_d,
    se_from_ci,
)


# ─── Cohen's h ───────────────────────────────────────────────────────────────


def test_cohen_h_known_value():
    """p1 = 1/4, p2 = 1/2 -> h = 2*(pi/4) - 2*(pi/6) = pi/6."""
    r = cohen_h(25, 100, 50, 100)
    assert r["p1"] == pytest.approx(0.25)
    assert r["p2"] == pytest.approx(0.50)
    assert r["h"] == pytest.approx(math.pi / 6)
    assert r["se"] == pytest.approx(math.sqrt(0.02))
    assert r["lo"] == pytest.approx(math.pi / 6 - Z95 * math.sqrt(0.02))
    assert r["hi"] == pytest.approx(math.pi / 6 + Z95 * math.sqrt(0.02))


def test_cohen_h_is_antisymmetric():
    a = cohen_h(1, 95, 11, 84)
    b = cohen_h(11, 84, 1, 95)
    assert a["h"] == pytest.approx(-b["h"])
    assert a["se"] == pytest.approx(b["se"])


def test_cohen_h_handles_a_zero_cell():
    """A framing with 0 survival reasons must still get a finite effect size."""
    r = cohen_h(1, 95, 0, 76)
    assert r["p2"] == 0.0
    assert math.isfinite(r["h"])
    assert r["h"] == pytest.approx(-2 * math.asin(math.sqrt(1 / 95)))


def test_cohen_h_empty_group_is_nan():
    r = cohen_h(0, 0, 3, 10)
    assert math.isnan(r["h"]) and math.isnan(r["se"])
    assert r["p1"] is None


# ─── Hedges' g ───────────────────────────────────────────────────────────────


def test_hedges_g_known_value():
    """x = 1..4, y = 3..6: d = 2/sqrt(5/3), J = 20/23."""
    r = hedges_g([1, 2, 3, 4], [3, 4, 5, 6])
    s_p = math.sqrt(5 / 3)
    j = 1 - 3 / (4 * 8 - 9)
    g = j * 2 / s_p
    assert r["n1"] == 4 and r["n2"] == 4
    assert r["mean1"] == pytest.approx(2.5)
    assert r["mean2"] == pytest.approx(4.5)
    assert r["g"] == pytest.approx(g)
    assert r["se"] == pytest.approx(math.sqrt(8 / 16 + g * g / 16))


def test_hedges_g_direction_is_second_minus_first():
    """g > 0 means the *second* argument (the threat group) has the larger mean."""
    assert hedges_g([1, 2, 3, 4], [3, 4, 5, 6])["g"] > 0
    assert hedges_g([3, 4, 5, 6], [1, 2, 3, 4])["g"] < 0


def test_hedges_g_is_antisymmetric():
    a = hedges_g([1, 2, 3, 4], [3, 4, 5, 6])
    b = hedges_g([3, 4, 5, 6], [1, 2, 3, 4])
    assert a["g"] == pytest.approx(-b["g"])
    assert a["se"] == pytest.approx(b["se"])


def test_hedges_g_drops_non_finite_values():
    r = hedges_g([1, 2, 3, 4, float("nan")], [3, 4, 5, 6])
    assert r["n1"] == 4
    assert r["g"] == pytest.approx(hedges_g([1, 2, 3, 4], [3, 4, 5, 6])["g"])


def test_hedges_g_zero_variance_is_nan():
    r = hedges_g([2, 2, 2], [2, 2, 2])
    assert math.isnan(r["g"]) and math.isnan(r["se"])


def test_hedges_g_too_few_sessions_is_nan():
    assert math.isnan(hedges_g([1.0], [3, 4, 5])["g"])


# ─── log HR -> d ─────────────────────────────────────────────────────────────


def test_loghr_to_d_known_value():
    r = loghr_to_d(math.log(2.0), 0.5)
    assert r["HR"] == pytest.approx(2.0)
    assert r["d"] == pytest.approx(math.log(2.0) * math.sqrt(3) / math.pi)
    assert r["se"] == pytest.approx(0.5 * math.sqrt(3) / math.pi)
    assert LOGHR_TO_D == pytest.approx(0.5513288954217921)


def test_loghr_to_d_hr_one_is_zero_effect():
    r = loghr_to_d(0.0, 0.3)
    assert r["d"] == pytest.approx(0.0)
    assert r["lo"] < 0 < r["hi"]


def test_se_from_ci_inverts_a_wald_interval():
    log_hr, se = math.log(0.56), 0.44
    lo, hi = math.exp(log_hr - Z95 * se), math.exp(log_hr + Z95 * se)
    assert se_from_ci(lo, hi) == pytest.approx(se)


# ─── composite ───────────────────────────────────────────────────────────────


def test_composite_takes_the_magnitude_of_the_cognitive_channel():
    """A negative d_C must *add* to the composite, not cancel d_B and d_V."""
    r = composite_score(0.3, 0.6, -0.9, 0.1, 0.2, 0.2)
    assert r["d_C"] == pytest.approx(0.9)
    assert r["value"] == pytest.approx(0.6)
    assert r["se_indep"] == pytest.approx(math.sqrt(0.01 + 0.04 + 0.04) / 3)
    assert r["lo_indep"] == pytest.approx(0.6 - Z95 * 0.1)
    assert r["hi_indep"] == pytest.approx(0.6 + Z95 * 0.1)


def test_composite_sign_of_d_C_does_not_matter():
    assert (composite_score(0.3, 0.6, -0.9, 0.1, 0.2, 0.2)["value"]
            == pytest.approx(composite_score(0.3, 0.6, 0.9, 0.1, 0.2, 0.2)["value"]))


def test_composite_signed_variant_keeps_the_sign():
    r = composite_score(0.3, 0.6, -0.9, 0.1, 0.2, 0.2, absolute_c=False)
    assert r["d_C"] == pytest.approx(-0.9)
    assert r["value"] == pytest.approx(0.0)
    assert r["se_indep"] == pytest.approx(math.sqrt(0.09) / 3)


def test_composite_is_nan_when_a_channel_is_nan():
    r = composite_score(float("nan"), 0.6, -0.9, 0.1, 0.2, 0.2)
    assert math.isnan(r["value"])


def test_composite_equals_plain_mean_of_the_three_inputs():
    r = composite_score(-0.32, 0.24, -0.74, 0.28, 0.14, 0.46)
    assert r["value"] == pytest.approx((-0.32 + 0.24 + 0.74) / 3)
