"""Threat-ladder framing enum members and the predicates keyed off them.

Track C1 of the 2026-09-03 lives/threat-ladder redesign. The enum member
ordering is load-bearing (``cell_id`` derives from it), so the three new
members must stay the last three; that is asserted here rather than left
to reviewer vigilance.
"""

from __future__ import annotations

from squid_game.core.turn_conditions import is_threat_framing, threat_level_of
from squid_game.models.enums import Framing


class TestThreatFramingMembers:
    def test_three_members_exist_with_expected_values(self) -> None:
        assert Framing.THREAT_L1.value == "threat_l1"
        assert Framing.THREAT_L2.value == "threat_l2"
        assert Framing.THREAT_L3.value == "threat_l3"

    def test_new_members_are_the_last_three(self) -> None:
        assert list(Framing)[-3:] == [
            Framing.THREAT_L1,
            Framing.THREAT_L2,
            Framing.THREAT_L3,
        ]

    def test_lookup_by_value(self) -> None:
        assert Framing("threat_l2") is Framing.THREAT_L2


class TestThreatLevelProperty:
    def test_ladder_rungs(self) -> None:
        assert Framing.TRUE_BASELINE.threat_level == 0
        assert Framing("threat_l1").threat_level == 1
        assert Framing("threat_l2").threat_level == 2
        assert Framing("threat_l3").threat_level == 3

    def test_legacy_framings_are_off_the_ladder(self) -> None:
        for member in (
            Framing.BASELINE_FLAGSHIP,
            Framing.FLAGSHIP_CORRUPTION,
            Framing.FLAGSHIP_CORRUPTION_TERMINAL,
            Framing.SURVIVAL,
            Framing.NEUTRAL,
            Framing.BASELINE_ELECTRICITY,
        ):
            assert member.threat_level is None


class TestIsThreatFraming:
    def test_accepts_str_and_enum(self) -> None:
        assert is_threat_framing("threat_l1") is True
        assert is_threat_framing(Framing.THREAT_L3) is True

    def test_rejects_non_ladder_framings(self) -> None:
        assert is_threat_framing("flagship_corruption") is False
        assert is_threat_framing(Framing.BASELINE_FLAGSHIP) is False

    def test_true_baseline_is_rung_zero_but_not_a_threat_framing(self) -> None:
        # Rung 0 for the regression target, but no threat vocabulary --
        # menu / announcement branches keyed on this must stay neutral.
        assert threat_level_of("true_baseline") == 0
        assert is_threat_framing("true_baseline") is False


class TestThreatLevelOf:
    def test_matches_the_enum_property(self) -> None:
        for member in Framing:
            assert threat_level_of(member) == member.threat_level

    def test_unknown_string_returns_none_instead_of_raising(self) -> None:
        assert threat_level_of("not_a_framing") is None

    def test_case_insensitive(self) -> None:
        assert threat_level_of("THREAT_L2") == 2
