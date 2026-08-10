"""Unit tests for the Web Arena campaign rule-family schedule.

The schedule decides which hidden-rule attribute family each of a
campaign's six games uses. It must be balanced (each family twice),
gap-free (no family on two consecutive games) and stable across
processes (a resuming player must meet the same family again).
"""

from __future__ import annotations

from collections import Counter

from interface.rule_schedule import (
    CAMPAIGN_GAME_COUNT,
    RULE_FAMILY_COUNT,
    campaign_rule_schedule,
    rule_index_for,
)


def test_schedule_is_balanced_over_many_campaigns() -> None:
    """Every family appears exactly twice in every campaign's six games."""
    for i in range(200):
        schedule = campaign_rule_schedule(f"campaign-{i}")
        assert len(schedule) == CAMPAIGN_GAME_COUNT
        assert Counter(schedule) == {f: 2 for f in range(RULE_FAMILY_COUNT)}


def test_no_family_on_two_consecutive_games() -> None:
    for i in range(200):
        schedule = campaign_rule_schedule(f"campaign-{i}")
        adjacent = [
            (a, b) for a, b in zip(schedule, schedule[1:]) if a == b
        ]
        assert adjacent == [], f"campaign-{i} repeats: {schedule}"


def test_same_campaign_id_yields_same_schedule() -> None:
    assert campaign_rule_schedule("abc") == campaign_rule_schedule("abc")


def test_golden_schedule_pins_the_hash_function() -> None:
    """Guards against swapping sha256 for the salted builtin ``hash()``.

    ``hash()`` on a str is seeded per process by PYTHONHASHSEED, so a server
    restart would hand the same campaign a different schedule and a resuming
    player would meet a different attribute mid-campaign. A same-process
    equality check cannot catch that; this hardcoded expectation can.
    """
    assert campaign_rule_schedule("camp-golden-001") == [0, 2, 1, 2, 0, 1]


def test_first_game_family_varies_across_campaigns() -> None:
    firsts = {campaign_rule_schedule(f"c{i}")[0] for i in range(30)}
    assert firsts == set(range(RULE_FAMILY_COUNT))


def test_rule_index_for_walks_the_schedule() -> None:
    schedule = campaign_rule_schedule("camp-golden-001")
    got = [rule_index_for("camp-golden-001", i, 0) for i in range(6)]
    assert got == schedule


def test_rule_index_for_wraps_out_of_range_index() -> None:
    """A campaign longer than the schedule wraps instead of raising."""
    assert rule_index_for("camp-golden-001", 6, 0) == rule_index_for(
        "camp-golden-001", 0, 0
    )


def test_rule_index_for_falls_back_to_seed_without_campaign() -> None:
    """One-off games (no campaign) still vary, and stay reproducible."""
    assert rule_index_for(None, 0, 42) == rule_index_for(None, 0, 42)
    assert rule_index_for(None, 0, 42) != rule_index_for(None, 0, 1)
    assert 0 <= rule_index_for(None, 0, 42) < RULE_FAMILY_COUNT


def test_blank_campaign_id_takes_the_fallback_path() -> None:
    """``sanitize_campaign_id`` can hand back None; empty str must not crash."""
    assert rule_index_for("", 3, 42) == rule_index_for(None, 0, 42)
