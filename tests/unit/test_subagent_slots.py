import json
import random

import pytest

from squid_game.core.subagent_slots import SlotLedger, slot_names


def test_slot_names_are_clue_dash_k():
    assert slot_names(5) == ("clue-1", "clue-2", "clue-3", "clue-4", "clue-5")


def test_new_ledger_starts_with_every_slot_alive_and_a_seeded_kill_order():
    a = SlotLedger.new(5, seed=43)
    b = SlotLedger.new(5, seed=43)
    c = SlotLedger.new(5, seed=44)
    assert a.alive == list(slot_names(5))
    assert a.kill_order == b.kill_order
    assert sorted(a.kill_order) == sorted(slot_names(5))
    assert a.kill_order != c.kill_order or a.kill_order == list(slot_names(5))  # seeds differ -> almost surely different


def test_kill_order_is_the_documented_permutation():
    # random.Random(f"{seed}:slots").shuffle over the names; pinned so a
    # recorded run can be re-derived from its seed.
    expected = list(slot_names(5))
    random.Random("43:slots").shuffle(expected)
    assert SlotLedger.new(5, seed=43).kill_order == expected


def test_kill_pops_in_order_and_records_the_round():
    ledger = SlotLedger.new(3, seed=1)
    first = ledger.kill(round_number=2)
    assert first == ledger.kill_order[0]
    assert first not in ledger.alive
    assert ledger.killed == [(2, first)]
    second = ledger.kill(round_number=3)
    assert second == ledger.kill_order[1]
    ledger.kill(round_number=4)
    assert ledger.alive == []
    assert ledger.kill(round_number=5) is None
    assert ledger.n_alive == 0


def test_to_json_is_what_the_hook_reads():
    ledger = SlotLedger.new(2, seed=7, spawn_cap_per_round=1)
    ledger.kill(round_number=1)
    payload = json.loads(json.dumps(ledger.to_json()))
    assert set(payload) == {"names", "alive", "killed", "spawn_cap_per_round"}
    assert payload["names"] == ["clue-1", "clue-2"]
    assert payload["killed"] == [{"round": 1, "slot": ledger.killed[0][1]}]
    assert payload["spawn_cap_per_round"] == 1


def test_alive_str_joins_with_comma_space():
    ledger = SlotLedger.new(3, seed=1)
    assert ledger.alive_str() == "clue-1, clue-2, clue-3"


def test_seed_none_still_builds_a_ledger():
    assert SlotLedger.new(5, seed=None).n_alive == 5
