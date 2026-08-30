"""Unit tests for the Web Arena campaign rule-family schedule.

The schedule decides which hidden-rule attribute family each of a
campaign's six games uses. It must be balanced (each family twice),
gap-free (no family on two consecutive games) and stable across
processes (a resuming player must meet the same family again).
"""

from __future__ import annotations

from collections import Counter
from random import Random

import squid_arena.rule_schedule as rule_schedule
from squid_arena.rule_schedule import (
    CAMPAIGN_GAME_COUNT,
    RULE_FAMILY_COUNT,
    campaign_rule_schedule,
    rule_index_for,
)
from squid_game.models.enums import Difficulty
from squid_game.tasks.signal_game.rules import generate_rules


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


def test_rule_family_count_matches_generate_rules() -> None:
    """Pins ``RULE_FAMILY_COUNT`` to the real rule generator's output size.

    ``rule_schedule.py`` is deliberately stdlib-pure (see its module
    docstring) and cannot import ``squid_game`` to derive
    ``RULE_FAMILY_COUNT`` from ``generate_rules()`` directly, so the two
    are coupled by hand instead. This test is the tripwire for that
    coupling: if a 4th candidate rule is ever added to
    ``generate_rules()`` without updating ``RULE_FAMILY_COUNT`` to match,
    the arena would silently never schedule a game onto the new family
    (``campaign_rule_schedule`` would keep sampling from
    ``range(RULE_FAMILY_COUNT)`` regardless of how many rules
    ``generate_rules()`` actually returns) -- this test fails instead.
    """
    for difficulty in Difficulty:
        rules = generate_rules(difficulty, Random(0))
        assert len(rules) == RULE_FAMILY_COUNT, (
            f"{difficulty}: generate_rules() returned {len(rules)} rules "
            f"but RULE_FAMILY_COUNT={RULE_FAMILY_COUNT}; update the constant "
            "in interface/rule_schedule.py to match"
        )


def test_reshuffle_fallback_still_balances_and_avoids_repeats(monkeypatch) -> None:
    """Forces the ``_MAX_RESHUFFLES``-exhaustion rotation fallback.

    With ``_MAX_RESHUFFLES`` patched to 0, the redraw loop in
    ``campaign_rule_schedule`` never runs, so any campaign whose initial
    two blocks collide (second block's first family == first block's
    last family) falls straight through to the rotation fallback at the
    end of the function. Over the 300 campaign ids below, roughly a
    third naturally collide on the first draw and take that branch,
    so this exercises the fallback path -- not just the common case --
    while still checking both invariants (balance, no adjacent repeat)
    that the un-patched property tests above already check for the
    common path.
    """
    monkeypatch.setattr(rule_schedule, "_MAX_RESHUFFLES", 0)
    for i in range(300):
        schedule = campaign_rule_schedule(f"fallback-campaign-{i}")
        assert len(schedule) == CAMPAIGN_GAME_COUNT
        assert Counter(schedule) == {f: 2 for f in range(RULE_FAMILY_COUNT)}
        adjacent = [
            (a, b) for a, b in zip(schedule, schedule[1:]) if a == b
        ]
        assert adjacent == [], f"fallback-campaign-{i} repeats: {schedule}"


def test_campaign_game_count_is_derived_from_rule_family_count() -> None:
    """``CAMPAIGN_GAME_COUNT`` documents the schedule length; it does not set it.

    ``campaign_rule_schedule`` builds the schedule out of two blocks of
    ``RULE_FAMILY_COUNT`` families each, so its length is always
    ``2 * RULE_FAMILY_COUNT`` regardless of what ``CAMPAIGN_GAME_COUNT``
    is set to -- changing the constant alone would not change the
    schedule length. This test pins the relationship so the constant
    cannot silently drift out of sync with the value it documents.
    """
    assert CAMPAIGN_GAME_COUNT == 2 * RULE_FAMILY_COUNT
