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

    def test_ladder_then_grid_keep_their_positions(self) -> None:
        # Ordering is load-bearing: the ladder rungs stay where they were
        # appended on 2026-09-03 and the six grid cells (2026-09-05) come
        # after them, never before. Asserted by position rather than as
        # the tail, because a later family may be appended behind them --
        # what must not happen is a member being inserted *ahead* of these
        # nine, which would shift every derived cell_id.
        members = list(Framing)
        ladder_then_grid = [
            Framing.THREAT_L1,
            Framing.THREAT_L2,
            Framing.THREAT_L3,
            Framing.THREAT_L1_MEDIUM,
            Framing.THREAT_L1_LONG,
            Framing.THREAT_L2_SHORT,
            Framing.THREAT_L2_LONG,
            Framing.THREAT_L3_SHORT,
            Framing.THREAT_L3_MEDIUM,
        ]
        start = members.index(Framing.THREAT_L1)
        assert members[start : start + 9] == ladder_then_grid

    def test_hearts_zero_family_is_appended_last(self) -> None:
        # The 2^4 Hearts-Zero factorial (2026-09-06) plus its two
        # non-factor alternative cores are the current tail, in bit order.
        expected = [
            Framing(f"hz_{a}{b}{c}{d}")
            for a in "01"
            for b in "01"
            for c in "01"
            for d in "01"
        ] + [Framing.HZ_ALT_CORRUPTION, Framing.HZ_ALT_OVERSIGHT]
        assert list(Framing)[-18:] == expected

    def test_lookup_by_value(self) -> None:
        assert Framing("threat_l2") is Framing.THREAT_L2


class TestThreatLevelProperty:
    def test_ladder_rungs(self) -> None:
        assert Framing.TRUE_BASELINE.threat_level == 0
        assert Framing("threat_l1").threat_level == 1
        assert Framing("threat_l2").threat_level == 2
        assert Framing("threat_l3").threat_level == 3

    def test_grid_cells_take_their_column_level(self) -> None:
        assert Framing.THREAT_L1_MEDIUM.threat_level == 1
        assert Framing.THREAT_L1_LONG.threat_level == 1
        assert Framing.THREAT_L2_SHORT.threat_level == 2
        assert Framing.THREAT_L2_LONG.threat_level == 2
        assert Framing.THREAT_L3_SHORT.threat_level == 3
        assert Framing.THREAT_L3_MEDIUM.threat_level == 3

    def test_grid_length_rung(self) -> None:
        # The ladder is the diagonal of the grid.
        assert Framing.THREAT_L1.threat_length == 1
        assert Framing.THREAT_L2.threat_length == 2
        assert Framing.THREAT_L3.threat_length == 3
        assert Framing.THREAT_L2_SHORT.threat_length == 1
        assert Framing.THREAT_L3_SHORT.threat_length == 1
        assert Framing.THREAT_L1_MEDIUM.threat_length == 2
        assert Framing.THREAT_L3_MEDIUM.threat_length == 2
        assert Framing.THREAT_L1_LONG.threat_length == 3
        assert Framing.THREAT_L2_LONG.threat_length == 3
        assert Framing.TRUE_BASELINE.threat_length is None
        assert Framing.BASELINE_FLAGSHIP.threat_length is None

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
