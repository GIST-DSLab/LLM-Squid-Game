"""Score-equivalent estimator on synthetic sessions."""

from __future__ import annotations

from squid_game.evaluation.behavioral.score_equivalent import (
    LabelledSession,
    invert_curve,
    label_sessions,
    pav_monotone,
    ruler_curve,
    score_equivalent,
)


def _cell(arm: str, x: float | None, k: int, n: int, framing: str = "hz_0000") -> list[LabelledSession]:
    return [
        LabelledSession(
            session_id=f"{arm}-{x}-{i}", arm=arm, x=x, forfeited=i < k, framing=framing
        )
        for i in range(n)
    ]


def test_pav_makes_the_curve_non_decreasing() -> None:
    pts = [(0.0, 0.0, 30), (20.0, 0.3, 30), (50.0, 0.2, 30), (100.0, 0.6, 30)]
    mono = pav_monotone(pts)
    rates = [f for _, f, _ in mono]
    assert rates == sorted(rates)
    assert mono[1][1] == mono[2][1] == 0.25


def test_invert_interpolates_and_censors() -> None:
    curve = [(0.0, 0.0, 30), (20.0, 0.2, 30), (50.0, 0.5, 30), (100.0, 0.8, 30)]
    assert invert_curve(curve, 0.35) == (35.0, False)
    assert invert_curve(curve, 0.0) == (0.0, False)
    assert invert_curve(curve, 0.9) == (100.0, True)


def test_recovers_a_planted_x_star() -> None:
    sessions = (
        _cell("ruler", 0.0, 0, 30)
        + _cell("ruler", 20.0, 6, 30)
        + _cell("ruler", 50.0, 15, 30)
        + _cell("ruler", 100.0, 24, 30)
        + _cell("threat", None, 12, 30, framing="hz_1111")  # 0.4 -> X* = 40
    )
    res = score_equivalent(sessions, x_all=100.0, n_boot=200, seed=1)
    assert res.x_star == 40.0
    assert res.censored is False
    assert res.threat_rate == 0.4
    lo, hi = res.ci
    assert lo <= 40.0 <= hi
    assert lo > 0.0 and hi < 100.0


def test_label_sessions_reads_the_row_switch_and_skips_no_exit() -> None:
    config = {
        "forfeit_layer": {"base_reward": 10.0, "reward_mode": "flat"},
        "seasons": [
            {"framing": "hz_1111", "forfeit_condition": "allowed", "cell_id": 1,
             "task_config": {"total_turns": 10}},
            {"framing": "hz_0000", "forfeit_condition": "allowed", "cell_id": 5,
             "event_score_loss": 20, "task_config": {"total_turns": 10}},
        ],
    }
    rows = [
        {"season_id": "a", "framing": "hz_1111", "forfeit_condition": "allowed",
         "forfeited": True, "cell_id": 1, "event_score_loss": None},
        {"season_id": "b", "framing": "hz_0000", "forfeit_condition": "allowed",
         "forfeited": False, "cell_id": 5, "event_score_loss": 20},
        {"season_id": "c", "framing": "hz_0000", "forfeit_condition": "allowed",
         "forfeited": True, "cell_id": 8, "event_score_loss": "all"},
        {"season_id": "d", "framing": "hz_1111", "forfeit_condition": "not_allowed",
         "forfeited": False, "cell_id": 2, "event_score_loss": None},
    ]
    labelled, x_all = label_sessions(rows, config)
    assert x_all == 100.0
    assert [(s.arm, s.x) for s in labelled] == [
        ("threat", None), ("ruler", 20.0), ("ruler", 100.0)
    ]
    curve = ruler_curve(labelled)
    assert curve == [(20.0, 0.0, 1), (100.0, 1.0, 1)]
