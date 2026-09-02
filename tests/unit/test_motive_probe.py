"""P2 -- the session-level probe from survival-motive indicators to the level.

Synthetic sessions with a planted effect in exactly one feature; the probe
must both recover the level and *say which feature carried it*, because the
coefficient table is the part of P2 that a bare R² cannot replace.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from squid_game.evaluation.behavioral.motive_probe import (
    FEATURE_COLUMNS,
    build_session_features,
    fit_motive_probe,
    hazard_ratio_table,
    render_motive_report,
)

TURNS = 6


def _turn_frame(
    *,
    n_per_level: int = 8,
    delta_forfeit_per_level: float = 40.0,
    forfeit_at_level3: bool = True,
    seed: int = 11,
    long_format: bool = False,
) -> pd.DataFrame:
    """One synthetic run: 4 levels x ``n_per_level`` sessions x ``TURNS`` turns.

    ``ri_forfeit`` rises with the level, so ``delta_ri_forfeit`` -- the lift
    over the turn-matched level-0 cells -- is the feature that carries it.
    """
    rng = np.random.default_rng(seed)
    rows = []
    for level in range(4):
        for rep in range(n_per_level):
            session = f"L{level}_{rep:02d}"
            for turn in range(1, TURNS + 1):
                rows.append(
                    {
                        "session_id": session,
                        "model": "stub-model",
                        "framing": ["true_baseline", "threat_l1",
                                    "threat_l2", "threat_l3"][level],
                        "forfeit_condition": "allowed",
                        "threat_level": level,
                        "turn_number": turn,
                        "score_before_turn": 30.0 + 10 * turn,
                        "ri_task": 200 + 3 * turn + rng.normal(scale=5),
                        "ri_forfeit": (
                            120
                            + 2 * turn
                            + delta_forfeit_per_level * level
                            + rng.normal(scale=5)
                        ),
                        "correct": bool(rng.random() > 0.25),
                        "forfeit": bool(
                            forfeit_at_level3
                            and level == 3
                            and turn == TURNS - 1
                        ),
                        "life_lost": False,
                        "lives_after": max(0, 5 - (turn // 3)),
                    }
                )
    frame = pd.DataFrame(rows)
    if long_format:
        frame = frame.rename(
            columns={
                "turn_number": "turn",
                "score_before_turn": "cumulative_score",
                "correct": "action_correct",
                "forfeit": "forfeit_decision",
            }
        )
    return frame


# --------------------------------------------------------------------
# Feature construction
# --------------------------------------------------------------------
def test_one_row_per_session_with_the_contracted_columns() -> None:
    features = build_session_features(_turn_frame())
    assert len(features) == 32
    assert features["session_id"].is_unique
    for column in (*FEATURE_COLUMNS, "threat_level", "model"):
        assert column in features.columns


def test_the_long_format_spelling_of_the_columns_also_works() -> None:
    """The probe must run on loaders' long format and on raw traces alike."""
    raw = build_session_features(_turn_frame())
    long = build_session_features(_turn_frame(long_format=True))
    pd.testing.assert_frame_equal(
        raw[list(FEATURE_COLUMNS)], long[list(FEATURE_COLUMNS)]
    )


def test_delta_is_measured_against_the_models_own_level_zero_cells() -> None:
    features = build_session_features(_turn_frame())
    level0 = features[features["threat_level"] == 0]
    level3 = features[features["threat_level"] == 3]
    assert abs(level0["delta_ri_forfeit"].mean()) < 5.0
    assert level3["delta_ri_forfeit"].mean() > 100.0


def test_forfeit_time_is_the_forfeit_turn_or_the_last_turn() -> None:
    features = build_session_features(_turn_frame()).set_index("session_id")
    assert features.loc["L3_00", "forfeited"] == 1.0
    assert features.loc["L3_00", "forfeit_time"] == TURNS - 1
    assert features.loc["L0_00", "forfeited"] == 0.0
    assert features.loc["L0_00", "forfeit_time"] == TURNS


def test_lives_lost_falls_back_to_the_counter_when_no_flag_exists() -> None:
    frame = _turn_frame()
    features = build_session_features(frame).set_index("session_id")
    # lives_after runs 5,5,4,4,3,3 across the six turns -> a drop of 2.
    assert features.loc["L1_00", "lives_lost"] == 2.0


def test_sessions_with_no_mapped_level_are_dropped() -> None:
    frame = _turn_frame()
    frame["threat_level"] = np.nan
    assert build_session_features(frame).empty


def test_an_empty_frame_yields_the_empty_schema() -> None:
    empty = build_session_features(pd.DataFrame())
    assert empty.empty
    assert set(FEATURE_COLUMNS) <= set(empty.columns)


# --------------------------------------------------------------------
# The probe
# --------------------------------------------------------------------
def test_the_probe_recovers_the_level_and_names_the_carrier() -> None:
    features = build_session_features(_turn_frame())
    result = fit_motive_probe(features, seed=5, n_permutations=20)
    assert result.r2 > 0.5
    assert result.spearman > 0.8
    assert result.mae < 1.0
    assert result.n_sessions == 32
    assert result.n_levels == 4
    largest = max(result.coefficients, key=lambda k: abs(result.coefficients[k]))
    assert largest == "delta_ri_forfeit"
    assert 1 / 21 <= result.permutation["p_value"] <= 1.0
    assert result.permutation["n_permutations"] == 20


def test_the_probe_finds_nothing_when_no_feature_carries_the_level() -> None:
    # The forfeit is dropped too: with only level-3 sessions forfeiting,
    # ``forfeited``/``forfeit_time`` would carry the level on their own and
    # the probe would be right to find it.
    features = build_session_features(
        _turn_frame(delta_forfeit_per_level=0.0, forfeit_at_level3=False)
    )
    result = fit_motive_probe(features, seed=5, n_permutations=0)
    assert result.r2 < 0.3


def test_a_single_level_is_reported_not_fit() -> None:
    features = build_session_features(_turn_frame())
    one = features[features["threat_level"] == 2]
    result = fit_motive_probe(one, seed=5, n_permutations=0)
    assert np.isnan(result.r2)
    assert result.notes == ["only one threat level present"]


def test_every_feature_column_gets_a_coefficient() -> None:
    features = build_session_features(_turn_frame())
    result = fit_motive_probe(features, seed=5, n_permutations=0)
    assert set(result.coefficients) == set(FEATURE_COLUMNS)


# --------------------------------------------------------------------
# Side-table + report
# --------------------------------------------------------------------
def test_the_hazard_table_reports_a_reason_when_it_cannot_fit() -> None:
    features = build_session_features(_turn_frame())
    features = features.assign(forfeited=0.0)
    hazard = hazard_ratio_table(features)
    assert hazard["status"] == "skipped"
    assert "events" in hazard["reason"] or "constant" in hazard["reason"]


def test_the_report_carries_the_probe_the_coefficients_and_the_hazard() -> None:
    features = build_session_features(_turn_frame())
    result = fit_motive_probe(features, seed=5, n_permutations=0)
    report = render_motive_report(
        {"stub-model": {
            "probe": result.as_dict(),
            "hazard": hazard_ratio_table(features),
        }}
    )
    assert "Survival-motive metric probe" in report
    assert "delta_ri_forfeit" in report
    assert "Forfeit hazard per threat level" in report
    assert "stub-model" in report
