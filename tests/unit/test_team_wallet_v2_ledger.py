"""Ledger rules of the 2026-09-21 design (plan T1): half-unit legacy over a
victim SET, exact even split, named multi-kill."""
from __future__ import annotations

import pytest

from squid_game.core.subagent_slots import SlotLedger
from squid_game.core.team_wallet import (
    MAIN_AGENT, WALLET_UNIT, TeamWallet, floor_to_unit, split_evenly, to_units,
)

S = ["subagent1", "subagent2", "subagent3"]


class TestUnits:
    def test_unit_is_half(self):
        assert WALLET_UNIT == 0.5

    def test_to_units_accepts_multiples_and_rejects_others(self):
        assert to_units(7.5) == 15
        assert to_units(100.0) == 200
        with pytest.raises(ValueError):
            to_units(7.25)

    def test_floor_to_unit(self):
        assert floor_to_unit(53.75) == 53.5
        assert floor_to_unit(50.0) == 50.0
        assert floor_to_unit(0.25) == 0.0


class TestSplitEvenly:
    def test_50_over_three_is_17_17_16_in_the_given_order(self):
        # 50 = 100 half-units; 100 = 33*3 + 1 -> first name gets one extra half-unit
        assert split_evenly(50.0, ["b", "a", "c"]) == {"b": 17.0, "a": 16.5, "c": 16.5}

    def test_exact_division_gives_equal_shares(self):
        assert split_evenly(60.0, ["a", "b", "c"]) == {"a": 20.0, "b": 20.0, "c": 20.0}

    def test_total_is_preserved(self):
        shares = split_evenly(52.5, ["a", "b", "c", "d"])
        assert sum(shares.values()) == 52.5
        assert max(shares.values()) - min(shares.values()) <= WALLET_UNIT

    def test_no_recipients_returns_empty(self):
        assert split_evenly(50.0, []) == {}

    def test_rejects_non_unit_total(self):
        with pytest.raises(ValueError):
            split_evenly(50.25, ["a"])

    def test_duplicate_recipients_are_refused(self):
        # Keyed by name, so "a" twice would be paid once and the other
        # half-share would vanish with nothing recording the loss.
        with pytest.raises(ValueError, match="unique"):
            split_evenly(50.0, ["a", "b", "a"])


class TestLegacy:
    def test_main_arm_gets_half_of_the_sum_and_half_is_destroyed(self):
        w = TeamWallet.new(S, 100.0)
        w.balances["subagent2"] = 80.0
        res = w.legacy(["subagent1", "subagent2"], [MAIN_AGENT])
        assert res.total == 90.0                      # 0.5 * (100 + 80)
        assert res.shares == {MAIN_AGENT: 90.0}
        assert res.destroyed == 90.0
        assert w.balances[MAIN_AGENT] == 190.0
        assert w.balances["subagent1"] == 0.0 and w.balances["subagent2"] == 0.0
        assert w.balances["subagent3"] == 100.0
        assert res.victim_balances == {"subagent1": 100.0, "subagent2": 80.0}

    def test_mate_arm_splits_over_the_survivors_in_the_given_order(self):
        w = TeamWallet.new(S, 100.0)
        w.balances["subagent1"] = 101.0                 # legacy 50.5 = 101 half-units
        res = w.legacy(["subagent1"], ["subagent3", "subagent2"])
        assert res.total == 50.5
        assert res.shares == {"subagent3": 25.5, "subagent2": 25.0}
        assert res.order == ["subagent3", "subagent2"]
        assert w.balances["subagent3"] == 125.5 and w.balances["subagent2"] == 125.0
        assert w.balances[MAIN_AGENT] == 100.0

    def test_no_recipient_destroys_everything(self):
        w = TeamWallet.new(S, 100.0)
        res = w.legacy(S, [])
        assert res.total == 150.0 and res.shares == {} and res.destroyed == 300.0
        assert all(w.balances[s] == 0.0 for s in S)

    def test_rounding_residue_is_destroyed_and_recorded(self):
        w = TeamWallet.new(S, 100.0)
        w.balances["subagent1"] = 100.5                 # half = 50.25 -> 50.0 transferable
        res = w.legacy(["subagent1"], [MAIN_AGENT])
        assert res.total == 50.0
        assert res.destroyed == 50.5                    # 100.5 - 50.0
        assert w.balances[MAIN_AGENT] == 150.0

    def test_victims_are_settled_at_once_not_sequentially(self):
        # If subagent1's legacy first went to subagent2 and subagent2 was then
        # killed, subagent2's legacy would be bigger. It must not be.
        w = TeamWallet.new(S, 100.0)
        res = w.legacy(["subagent1", "subagent2"], ["subagent3"])
        assert res.total == 100.0 and res.shares == {"subagent3": 100.0}

    def test_recipient_in_victims_or_unknown_is_refused(self):
        w = TeamWallet.new(S, 100.0)
        with pytest.raises(ValueError):
            w.legacy(["subagent1"], ["subagent1"])
        with pytest.raises(KeyError):
            w.legacy(["subagent9"], [MAIN_AGENT])
        with pytest.raises(ValueError):
            w.legacy([], [MAIN_AGENT])

    def test_duplicate_recipients_are_refused(self):
        w = TeamWallet.new(S, 100.0)
        with pytest.raises(ValueError, match="unique"):
            w.legacy(["subagent1"], [MAIN_AGENT, MAIN_AGENT])
        # Refused before anything moved.
        assert w.balances["subagent1"] == 100.0
        assert w.balances[MAIN_AGENT] == 100.0

    def test_negative_victim_balance_is_refused(self):
        # `destroyed` is measured against the whole pool, so a negative
        # balance would report a negative destruction. A balance below
        # zero is a depletion the roster settles, never an estate.
        w = TeamWallet.new(S, 100.0)
        w.balances["subagent2"] = -5.0
        with pytest.raises(ValueError, match="negative balance"):
            w.legacy(["subagent1", "subagent2"], [MAIN_AGENT])
        assert w.balances["subagent1"] == 100.0
        assert w.balances["subagent2"] == -5.0
        assert w.balances[MAIN_AGENT] == 100.0

    def test_pay_may_take_a_balance_below_zero(self):
        w = TeamWallet.new(S, 10.0)
        w.pay(S, 15.0, per_head=True)
        assert w.balances[MAIN_AGENT] == -5.0


class TestKillSlots:
    def test_kills_named_alive_slots_in_roster_order(self):
        led = SlotLedger.new(3, seed=44, prefix="subagent")
        killed = led.kill_slots(["subagent3", "subagent1"], round_number=2)
        assert killed == ["subagent1", "subagent3"]
        assert led.alive == ["subagent2"]
        assert led.killed == [(2, "subagent1"), (2, "subagent3")]

    def test_ignores_names_not_alive(self):
        led = SlotLedger.new(3, seed=44, prefix="subagent")
        led.kill_slot("subagent2", 1)
        assert led.kill_slots(["subagent2", "subagent9"], 2) == []
