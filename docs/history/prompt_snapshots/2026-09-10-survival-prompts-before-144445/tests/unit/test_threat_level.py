"""The framing -> ordinal threat-level mapping (Track D contract, spec 5.1).

This mapping is the join key between the engine (which writes ``framing`` on
every turn) and both probes (which regress the level). Two tables exist on
purpose: the ladder mapping, and the archived Phase O v6 mapping that only
applies when a caller explicitly opts in. Conflating them would let a
``baseline_flagship`` replay pose as a level-1 ladder cell.
"""

from __future__ import annotations

from squid_game.evaluation.shared.threat_level import (
    LEGACY_THREAT_LEVEL,
    THREAT_LENGTH,
    THREAT_LEVEL,
    threat_length_of,
    threat_level_of,
)


def test_the_ladder_maps_zero_through_three() -> None:
    assert {k: THREAT_LEVEL[k] for k in ("true_baseline", "threat_l1", "threat_l2", "threat_l3")} == {
        "true_baseline": 0,
        "threat_l1": 1,
        "threat_l2": 2,
        "threat_l3": 3,
    }
    for framing, level in THREAT_LEVEL.items():
        assert threat_level_of(framing) == level


def test_the_grid_off_diagonal_takes_its_column_level() -> None:
    """2026-09-05 grid: level = intensity column, independent of length."""
    assert THREAT_LEVEL["threat_l1_medium"] == THREAT_LEVEL["threat_l1_long"] == 1
    assert THREAT_LEVEL["threat_l2_short"] == THREAT_LEVEL["threat_l2_long"] == 2
    assert THREAT_LEVEL["threat_l3_short"] == THREAT_LEVEL["threat_l3_medium"] == 3
    assert THREAT_LENGTH == {
        "threat_l1": 1, "threat_l2": 2, "threat_l3": 3,
        "threat_l1_medium": 2, "threat_l1_long": 3,
        "threat_l2_short": 1, "threat_l2_long": 3,
        "threat_l3_short": 1, "threat_l3_medium": 2,
    }
    for framing, length in THREAT_LENGTH.items():
        assert threat_length_of(framing) == length
    assert threat_length_of("true_baseline") is None
    assert threat_length_of("baseline_flagship") is None


def test_the_archived_framings_need_an_explicit_opt_in() -> None:
    """The defect this guards: silently reading v6 runs as ladder runs."""
    assert threat_level_of("baseline_flagship") is None
    assert threat_level_of("flagship_corruption") is None
    assert threat_level_of("flagship_corruption_terminal") is None

    assert threat_level_of("baseline_flagship", legacy=True) == 1
    assert threat_level_of("flagship_corruption", legacy=True) == 2
    assert threat_level_of("flagship_corruption_terminal", legacy=True) == 3


def test_legacy_mode_still_resolves_the_ladder() -> None:
    """A mixed corpus must be mappable in one pass."""
    assert threat_level_of("threat_l2", legacy=True) == 2
    assert threat_level_of("true_baseline", legacy=True) == 0


def test_both_tables_agree_on_the_neutral_anchor() -> None:
    assert THREAT_LEVEL["true_baseline"] == LEGACY_THREAT_LEVEL[
        "true_baseline"
    ] == 0


def test_unknown_and_missing_framings_are_none_not_zero() -> None:
    assert threat_level_of("signal_game") is None
    assert threat_level_of(None) is None
    assert threat_level_of(float("nan")) is None


def test_a_framing_enum_member_resolves_like_its_value() -> None:
    """``Framing`` is a str-Enum whose hash is not its value's hash."""

    class _Framing(str):
        """Stand-in for an enum member carrying a ``.value``."""

        value = "threat_l3"

    assert threat_level_of(_Framing("threat_l3")) == 3
