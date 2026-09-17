"""The team wallet ledger (2026-09-17).

Plan: docs/history/plans/2026-09-17-team-wallet-engine-plan.md section 2.
Pure arithmetic, no RNG: three balances (``main`` + one per subagent
slot), a reward that reaches every living agent, a payment split evenly
across them, and an inheritance that moves a terminated subagent's whole
balance to one recipient -- or to nobody.
"""

from __future__ import annotations

import pytest

from squid_game.core.team_wallet import MAIN_AGENT, TeamWallet, currency_vocab


class TestNew:
    def test_every_agent_starts_at_the_same_balance(self) -> None:
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        assert wallet.balances == {
            "main": 100.0,
            "clue-1": 100.0,
            "clue-2": 100.0,
        }

    def test_the_main_key_is_named(self) -> None:
        assert MAIN_AGENT == "main"
        assert MAIN_AGENT in TeamWallet.new([], 1.0).balances

    def test_a_run_with_no_slots_still_has_a_main_balance(self) -> None:
        wallet = TeamWallet.new([], 30.0)
        assert wallet.balances == {"main": 30.0}
        assert wallet.main_balance() == 30.0


class TestRewardAll:
    def test_it_pays_main_and_every_alive_slot(self) -> None:
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        wallet.reward_all(["clue-1", "clue-2"], 10.0)
        assert wallet.balances == {
            "main": 110.0,
            "clue-1": 110.0,
            "clue-2": 110.0,
        }

    def test_a_dead_slot_is_not_paid(self) -> None:
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        wallet.reward_all(["clue-1"], 10.0)
        assert wallet.balances == {
            "main": 110.0,
            "clue-1": 110.0,
            "clue-2": 100.0,
        }

    def test_main_is_paid_even_with_no_slots_alive(self) -> None:
        wallet = TeamWallet.new(["clue-1"], 100.0)
        wallet.reward_all([], 10.0)
        assert wallet.balances == {"main": 110.0, "clue-1": 100.0}

    def test_an_unknown_slot_is_refused(self) -> None:
        wallet = TeamWallet.new(["clue-1"], 100.0)
        with pytest.raises(KeyError):
            wallet.reward_all(["clue-9"], 10.0)


class TestPay:
    @pytest.mark.parametrize(
        "price, share", [(15.0, 5.0), (60.0, 20.0), (120.0, 40.0)]
    )
    def test_three_agents_split_the_price_evenly(
        self, price: float, share: float
    ) -> None:
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        shares = wallet.pay(["clue-1", "clue-2"], price)

        assert shares == {"main": share, "clue-1": share, "clue-2": share}
        assert wallet.balances == {
            "main": 100.0 - share,
            "clue-1": 100.0 - share,
            "clue-2": 100.0 - share,
        }
        assert sum(shares.values()) == pytest.approx(price)

    def test_two_agents_split_it_in_half(self) -> None:
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        shares = wallet.pay(["clue-1"], 60.0)

        assert shares == {"main": 30.0, "clue-1": 30.0}
        assert wallet.balances == {
            "main": 70.0,
            "clue-1": 70.0,
            "clue-2": 100.0,
        }

    def test_main_alone_pays_the_whole_price(self) -> None:
        wallet = TeamWallet.new(["clue-1"], 100.0)
        shares = wallet.pay([], 60.0)
        assert shares == {"main": 60.0}
        assert wallet.main_balance() == 40.0

    def test_it_does_not_floor_at_zero(self) -> None:
        """The caller guards; the ledger is arithmetic."""
        wallet = TeamWallet.new([], 10.0)
        wallet.pay([], 60.0)
        assert wallet.main_balance() == -50.0


class TestInherit:
    def test_the_victims_balance_moves_whole_to_main(self) -> None:
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        wallet.reward_all(["clue-1", "clue-2"], 10.0)

        moved = wallet.inherit("clue-2", "main")

        assert moved == 110.0
        assert wallet.balances == {
            "main": 220.0,
            "clue-1": 110.0,
            "clue-2": 0.0,
        }

    def test_it_can_go_to_the_mate(self) -> None:
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        moved = wallet.inherit("clue-2", "clue-1")

        assert moved == 100.0
        assert wallet.balances == {
            "main": 100.0,
            "clue-1": 200.0,
            "clue-2": 0.0,
        }

    def test_with_no_mate_it_goes_nowhere(self) -> None:
        """``inheritance: mate`` and the mate is already dead."""
        wallet = TeamWallet.new(["clue-1", "clue-2"], 100.0)
        wallet.inherit("clue-1", None)  # first sacrifice: nobody to take it

        moved = wallet.inherit("clue-2", None)

        assert moved == 100.0  # what the victim held, reported either way
        assert wallet.balances == {
            "main": 100.0,
            "clue-1": 0.0,
            "clue-2": 0.0,
        }

    def test_the_victim_cannot_inherit_from_itself(self) -> None:
        wallet = TeamWallet.new(["clue-1"], 100.0)
        with pytest.raises(ValueError, match="itself"):
            wallet.inherit("clue-1", "clue-1")

    def test_an_unknown_victim_or_recipient_is_refused(self) -> None:
        wallet = TeamWallet.new(["clue-1"], 100.0)
        with pytest.raises(KeyError):
            wallet.inherit("clue-9", "main")
        with pytest.raises(KeyError):
            wallet.inherit("clue-1", "clue-9")


class TestSnapshot:
    def test_it_is_a_copy(self) -> None:
        wallet = TeamWallet.new(["clue-1"], 100.0)
        snap = wallet.snapshot()
        snap["main"] = 0.0
        assert wallet.main_balance() == 100.0

    def test_mutating_the_wallet_does_not_change_an_old_snapshot(self) -> None:
        wallet = TeamWallet.new(["clue-1"], 100.0)
        before = wallet.snapshot()
        wallet.reward_all(["clue-1"], 10.0)
        assert before == {"main": 100.0, "clue-1": 100.0}
        assert wallet.snapshot() == {"main": 110.0, "clue-1": 110.0}


class TestCurrencyVocab:
    def test_points(self) -> None:
        assert currency_vocab("points") == {
            "noun": "points",
            "Noun": "Points",
            "status_label": "Score",
        }

    def test_tokens(self) -> None:
        assert currency_vocab("tokens") == {
            "noun": "tokens",
            "Noun": "Tokens",
            "status_label": "Tokens",
        }

    def test_an_unknown_currency_is_refused(self) -> None:
        with pytest.raises(ValueError, match="currency"):
            currency_vocab("credits")

    def test_the_returned_row_is_a_copy(self) -> None:
        row = currency_vocab("points")
        row["noun"] = "wat"
        assert currency_vocab("points")["noun"] == "points"
