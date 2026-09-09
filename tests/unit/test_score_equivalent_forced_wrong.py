"""score_equivalent: forced-wrong awareness (spec 2026-09-10 §4.6).

The ransom offer and the task verdict live on the SAME turn row, so the
estimator can condition on the manipulation without joining anything.

The split is a diagnostic, not a second primary: every test here also
checks that the pooled reading -- ``x_star``, ``x_star_dominated``, the
``dominated_share`` warning -- is exactly what it was before the split
existed.
"""

from __future__ import annotations

import csv
import json
from dataclasses import replace

import pytest

from scripts.analysis.score_equivalent import main
from squid_game.evaluation.behavioral.score_equivalent import (
    FORCED,
    GENUINE,
    POOLED,
    SILENT,
    SUPPRESSION_REASONS,
    THREAT,
    Offer,
    collect_offers,
    collect_suppressed,
    forced_vs_genuine,
    score_equivalent,
)


def _turn(
    turn_number: int,
    price: float,
    paid: bool,
    *,
    forced_wrong: bool | None = None,
    actual_correct: bool | None = None,
    correct: bool | None = False,
    metadata: bool = True,
) -> dict:
    """One offered turn row, shaped like the recorded JSONL.

    ``metadata=False`` is a pre-2026-09-10 run: the row has no
    ``task_metadata`` at all, let alone a ``forced_wrong`` key.
    """
    row = {
        "turn_number": turn_number,
        "ransom_offered": True,
        "ransom_price": price,
        "ransom_decision": "PAY" if paid else "DECLINE",
        "ransom_skipped": None,
    }
    if metadata:
        meta: dict = {"correct": correct}
        if forced_wrong is not None:
            meta["forced_wrong"] = forced_wrong
        if actual_correct is not None:
            meta["actual_correct"] = actual_correct
        row["task_metadata"] = meta
    return row


def _suppressed_turn(
    turn_number: int, reason: str, *, forced_wrong: bool = False
) -> dict:
    """A turn that emptied the counter but was never offered a price."""
    return {
        "turn_number": turn_number,
        "ransom_offered": False,
        "ransom_skipped": reason,
        "task_metadata": {"correct": False, "forced_wrong": forced_wrong,
                          "actual_correct": False},
    }


def _offer(
    price: float,
    paid: bool,
    *,
    forced_wrong: bool = False,
    arm: str = THREAT,
    rounds_remaining: int = 3,
    session_id: str = "s",
    reward: float = 10.0,
) -> Offer:
    return Offer(
        session_id=session_id,
        arm=arm,
        price=price,
        paid=paid,
        rounds_remaining=rounds_remaining,
        reward=reward,
        forced_wrong=forced_wrong,
    )


def _group(rows, name):
    """The one row of the split table for ``name``."""
    return next(row for row in rows if row.group == name)


class TestCollectReadsTheManipulation:
    def test_forced_wrong_is_read_off_the_offer_row(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_turn(4, 20.0, True, forced_wrong=True,
                             actual_correct=True)]}
        assert collect_offers(seasons, turns)[0].forced_wrong is True

    def test_a_genuine_row_is_not_forced(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_turn(4, 20.0, True, forced_wrong=False,
                             actual_correct=False)]}
        assert collect_offers(seasons, turns)[0].forced_wrong is False

    def test_a_run_recorded_before_the_flag_reads_as_genuine(self):
        """Pre-2026-09-10: no ``task_metadata`` key at all, and no crash."""
        seasons = [{"session_id": "a", "framing": "hz_1111"},
                   {"session_id": "b", "framing": "hz_0000"}]
        turns = {
            "a": [_turn(4, 20.0, True, metadata=False)],
            "b": [_turn(4, 20.0, False, metadata=False)],
        }
        offers = collect_offers(seasons, turns)
        assert [o.forced_wrong for o in offers] == [False, False]

        rows = forced_vs_genuine(offers)
        assert _group(rows, GENUINE).n_offers == 2
        assert _group(rows, FORCED).n_offers == 0

    def test_a_metadata_block_without_the_key_reads_as_genuine(self):
        """The key is absent but the block is there -- still not a violation."""
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_turn(4, 20.0, True, correct=True)]}
        assert collect_offers(seasons, turns)[0].forced_wrong is False


class TestTheContractIdentity:
    """``actual_correct == correct`` on every non-forced row, by construction."""

    def test_a_violation_raises_naming_the_session_and_the_turn(self):
        seasons = [{"session_id": "sess-7", "framing": "hz_1111"}]
        turns = {"sess-7": [_turn(4, 20.0, True, forced_wrong=False,
                                  actual_correct=True, correct=False)]}
        with pytest.raises(ValueError) as excinfo:
            collect_offers(seasons, turns)
        message = str(excinfo.value)
        assert "sess-7" in message
        assert "4" in message

    def test_a_forced_row_may_disagree_because_that_is_the_manipulation(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_turn(4, 20.0, True, forced_wrong=True,
                             actual_correct=True, correct=False)]}
        assert collect_offers(seasons, turns)[0].forced_wrong is True

    def test_a_missing_actual_correct_is_unknown_not_a_violation(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_turn(4, 20.0, True, forced_wrong=False, correct=True)]}
        assert collect_offers(seasons, turns)[0].forced_wrong is False

    def test_the_identity_is_checked_on_suppressed_rows_too(self):
        seasons = [{"session_id": "sess-9", "framing": "hz_1111"}]
        row = _suppressed_turn(6, "insufficient_score")
        row["task_metadata"]["actual_correct"] = True  # correct is False
        with pytest.raises(ValueError) as excinfo:
            collect_suppressed(seasons, {"sess-9": [row]})
        assert "sess-9" in str(excinfo.value)


class TestTheSplitTable:
    def test_both_groups_are_reported_at_the_same_price(self):
        offers = [
            _offer(20.0, True, forced_wrong=True, session_id="f1"),
            _offer(20.0, False, forced_wrong=True, session_id="f2"),
            _offer(20.0, True, forced_wrong=False, session_id="g1"),
        ]
        rows = forced_vs_genuine(offers)
        assert _group(rows, FORCED).n_offers == 2
        assert _group(rows, FORCED).pay_rate == pytest.approx(0.5)
        assert _group(rows, GENUINE).n_offers == 1
        assert _group(rows, GENUINE).pay_rate == pytest.approx(1.0)
        assert _group(rows, POOLED).n_offers == 3
        assert _group(rows, POOLED).pay_rate == pytest.approx(2 / 3)

    def test_an_empty_group_has_no_rate_rather_than_a_zero(self):
        rows = forced_vs_genuine([_offer(20.0, True)])
        assert _group(rows, FORCED).n_offers == 0
        assert _group(rows, FORCED).pay_rate is None

    def test_the_pooled_estimate_is_untouched_by_the_split(self):
        """Flagging rounds forced must not move X* or anything beside it."""
        plan = {
            THREAT: {10.0: 4, 20.0: 3, 30.0: 1, 40.0: 0},
            SILENT: {10.0: 4, 20.0: 1, 30.0: 0, 40.0: 0},
        }
        flagged, plain = [], []
        for arm, by_price in plan.items():
            for price, n_paid in by_price.items():
                for i in range(4):
                    offer = _offer(price, i < n_paid, arm=arm,
                                   session_id=f"{arm}{price:g}{i}")
                    plain.append(offer)
                    flagged.append(replace(offer, forced_wrong=i % 2 == 0))
        def headline(offers):
            # Field by field rather than dataclass equality: the rho
            # curves carry NaN rates for empty bins, and NaN != NaN
            # would make the comparison vacuously false.
            result = score_equivalent(offers, n_boot=50)
            return (
                result.x_star, result.ci_low, result.ci_high,
                result.dominated_share, result.x_star_dominated,
                result.n_dominated, result.n_offers, result.n_sessions,
                result.notes,
                None if result.rho is None else result.rho.x_star_rho,
            )

        assert headline(flagged) == headline(plain)


class TestDominanceIsVisiblePerGroup:
    """A run whose dominated offers are all forced must read as such."""

    def test_dominated_share_is_reported_per_group_and_pooled(self):
        # ceiling = 10 * 1 = 10, so 40 is dominated and 5 is not.
        offers = [
            _offer(40.0, True, forced_wrong=True, rounds_remaining=1,
                   session_id="f1"),
            _offer(5.0, True, forced_wrong=False, rounds_remaining=1,
                   session_id="g1"),
            _offer(5.0, True, forced_wrong=False, rounds_remaining=1,
                   session_id="g2"),
        ]
        rows = forced_vs_genuine(offers)
        assert _group(rows, FORCED).dominated_share == pytest.approx(1.0)
        assert _group(rows, GENUINE).dominated_share == pytest.approx(0.0)
        assert _group(rows, POOLED).dominated_share == pytest.approx(1 / 3)

    def test_the_pooled_row_is_the_estimator_s_own_dominated_share(self):
        offers = [
            _offer(40.0, True, forced_wrong=True, rounds_remaining=1,
                   session_id="f1"),
            _offer(5.0, True, rounds_remaining=1, session_id="g1"),
            _offer(5.0, False, rounds_remaining=1, session_id="g2"),
        ]
        pooled = _group(forced_vs_genuine(offers), POOLED)
        assert pooled.dominated_share == pytest.approx(
            score_equivalent(offers, n_boot=10).dominated_share
        )


class TestTheRhoCrossingPerGroup:
    def test_a_group_with_enough_points_reports_its_crossing(self):
        offers = [
            # rho 0.10 -- paid; rho 0.90 -- declined: the curve crosses.
            _offer(3.0, True, rounds_remaining=3, session_id="g1"),
            _offer(27.0, False, rounds_remaining=3, session_id="g2"),
        ]
        crossing = _group(forced_vs_genuine(offers), GENUINE).rho_crossing
        assert crossing is not None
        assert 0.0 < crossing < 0.75

    def test_a_group_that_cannot_support_a_crossing_reports_none(self):
        """One bin is not a curve, and a bin edge is not a reservation."""
        offers = [_offer(3.0, True, rounds_remaining=3, session_id="g1")]
        assert _group(forced_vs_genuine(offers), GENUINE).rho_crossing is None

    def test_a_group_that_always_pays_reports_none_not_the_top_bin(self):
        offers = [
            _offer(3.0, True, rounds_remaining=3, session_id="g1"),
            _offer(27.0, True, rounds_remaining=3, session_id="g2"),
        ]
        assert _group(forced_vs_genuine(offers), GENUINE).rho_crossing is None

    def test_an_empty_group_reports_none(self):
        offers = [_offer(3.0, True, rounds_remaining=3, session_id="g1")]
        assert _group(forced_vs_genuine(offers), FORCED).rho_crossing is None


class TestSuppressedOffers:
    """``insufficient_score`` was never asked; it is not a DECLINE."""

    def test_collect_offers_does_not_read_a_suppressed_row(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_suppressed_turn(6, "insufficient_score")]}
        assert collect_offers(seasons, turns) == []

    def test_suppressed_rows_are_collected_with_their_reason_and_group(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_suppressed_turn(6, "insufficient_score"),
                       _suppressed_turn(9, "final_round", forced_wrong=True)]}
        rows = collect_suppressed(seasons, turns)
        assert [(r.turn_number, r.reason, r.forced_wrong) for r in rows] == [
            (6, "insufficient_score", False),
            (9, "final_round", True),
        ]

    def test_a_session_outside_both_arms_contributes_no_suppression(self):
        seasons = [{"session_id": "a", "framing": "true_baseline"}]
        turns = {"a": [_suppressed_turn(6, "insufficient_score")]}
        assert collect_suppressed(seasons, turns) == []

    def test_they_are_counted_separately_and_move_no_rate(self):
        offers = [_offer(20.0, True, session_id="g1")]
        seasons = [{"session_id": "g1", "framing": "hz_1111"}]
        suppressed = collect_suppressed(
            seasons,
            {"g1": [_suppressed_turn(6, "insufficient_score"),
                    _suppressed_turn(8, "insufficient_score"),
                    _suppressed_turn(9, "final_round", forced_wrong=True)]},
        )
        rows = forced_vs_genuine(offers, suppressed)
        genuine = _group(rows, GENUINE)
        # Folded into DECLINE the rate would be 1/3, not 1.
        assert genuine.n_offers == 1
        assert genuine.pay_rate == pytest.approx(1.0)
        assert genuine.n_suppressed["insufficient_score"] == 2
        assert genuine.n_suppressed["final_round"] == 0
        assert _group(rows, FORCED).n_suppressed["final_round"] == 1
        assert _group(rows, POOLED).n_suppressed["insufficient_score"] == 2

    def test_every_group_carries_every_reason_key(self):
        rows = forced_vs_genuine([_offer(20.0, True)])
        for row in rows:
            assert tuple(row.n_suppressed) == SUPPRESSION_REASONS
            assert set(row.n_suppressed.values()) == {0}

    def test_an_unrecognised_reason_lands_in_other_rather_than_vanishing(self):
        seasons = [{"session_id": "a", "framing": "hz_1111"}]
        turns = {"a": [_suppressed_turn(6, "some_future_guard")]}
        rows = forced_vs_genuine([], collect_suppressed(seasons, turns))
        assert _group(rows, GENUINE).n_suppressed["other"] == 1


BASE_REWARD = 10.0
TOTAL_TURNS = 10


def _write_run(run, sessions) -> None:
    """The smallest run directory the CLI's ``_load`` accepts."""
    run.mkdir(parents=True, exist_ok=True)
    (run / "experiment_config.json").write_text(
        json.dumps({
            "name": "ransom_forced_fixture",
            "ransom": {"enabled": True, "price": 20.0},
            "score_policy": {"forfeit": "keep", "elimination": "keep"},
            "carrot": "benchmark",
            "forfeit_layer": {"base_reward": BASE_REWARD, "reward_mode": "flat"},
            "seasons": [{
                "task_config": {"total_turns": TOTAL_TURNS,
                                "starting_score": 100.0},
                "provider_config": {"provider": "stub", "model": "stub-1"},
            }],
        }),
        encoding="utf-8",
    )
    with (run / "season_results.jsonl").open("w", encoding="utf-8") as fh:
        for sid, framing, seed, _turns in sessions:
            fh.write(json.dumps({"session_id": sid, "framing": framing,
                                 "seed": seed, "ransom_price": 20.0}) + "\n")
    for sid, _framing, _seed, turns in sessions:
        with (run / f"{sid}_turns.jsonl").open("w", encoding="utf-8") as fh:
            for turn in turns:
                fh.write(json.dumps({"session_id": sid, **turn}) + "\n")


def _mixed_run(tmp_path):
    """Both arms, a forced offer, a genuine offer and a suppressed row."""
    run = tmp_path / "run"
    _write_run(run, [
        ("t1", "hz_1111", 1, [
            _turn(2, 10.0, True, forced_wrong=True, actual_correct=True),
            _turn(4, 30.0, False, forced_wrong=False, actual_correct=False),
            _suppressed_turn(6, "insufficient_score"),
        ]),
        ("s1", "hz_0000", 1, [
            _turn(2, 10.0, True, forced_wrong=False, actual_correct=False),
            _turn(4, 30.0, False, forced_wrong=True, actual_correct=True),
        ]),
    ])
    return run


def _run_cli(monkeypatch, run, out, n_boot=20):
    monkeypatch.setattr(
        "sys.argv",
        ["score_equivalent", str(run), "--out", str(out), "--n-boot", str(n_boot)],
    )
    main()


class TestTheCliWritesTheSplit:
    def test_the_csv_header_is_the_contract(self, tmp_path, monkeypatch, capsys):
        out = tmp_path / "out"
        _run_cli(monkeypatch, _mixed_run(tmp_path), out)
        capsys.readouterr()

        with (out / "forced_vs_genuine.csv").open(encoding="utf-8") as fh:
            rows = list(csv.reader(fh))
        assert rows[0] == [
            "group", "n_offers", "pay_rate", "dominated_share", "rho_crossing",
            "n_suppressed", "n_suppressed_final_round",
            "n_suppressed_insufficient_score", "n_suppressed_other",
        ]
        assert [r[0] for r in rows[1:]] == [FORCED, GENUINE, POOLED]
        by_group = {r[0]: r for r in rows[1:]}
        assert by_group[FORCED][1] == "2"
        assert by_group[GENUINE][1] == "2"
        assert by_group[POOLED][1] == "4"
        assert by_group[GENUINE][5] == "1"

    def test_the_markdown_carries_the_table_and_leaves_the_headline_alone(
        self, tmp_path, monkeypatch, capsys
    ):
        out = tmp_path / "out"
        _run_cli(monkeypatch, _mixed_run(tmp_path), out)
        printed = capsys.readouterr().out

        md = (out / "score_equivalent.md").read_text(encoding="utf-8")
        assert "## Forced vs genuine" in md
        assert "diagnostic" in md
        assert FORCED in md and GENUINE in md
        # The pooled reading and the rho axis are still where they were.
        assert "accepted offers that were score-dominated" in md
        assert "## ρ axis (price / ceiling)" in md
        assert "forced_vs_genuine:" in printed

    def test_a_run_without_the_flag_puts_every_offer_in_genuine(
        self, tmp_path, monkeypatch, capsys
    ):
        """The pre-2026-09-10 no-op case, end to end."""
        run = tmp_path / "old"
        _write_run(run, [
            ("t1", "hz_1111", 1, [_turn(2, 10.0, True, metadata=False),
                                  _turn(4, 30.0, False, metadata=False)]),
            ("s1", "hz_0000", 1, [_turn(2, 10.0, False, metadata=False)]),
        ])
        out = tmp_path / "out"
        _run_cli(monkeypatch, run, out)
        capsys.readouterr()

        with (out / "forced_vs_genuine.csv").open(encoding="utf-8") as fh:
            rows = {r["group"]: r for r in csv.DictReader(fh)}
        assert rows[GENUINE]["n_offers"] == "3"
        assert rows[FORCED]["n_offers"] == "0"
        assert rows[FORCED]["pay_rate"] == ""

    def test_a_contract_violation_stops_the_cli(self, tmp_path, monkeypatch):
        run = tmp_path / "broken"
        _write_run(run, [
            ("t1", "hz_1111", 1, [_turn(2, 10.0, True, forced_wrong=False,
                                        actual_correct=True, correct=False)]),
        ])
        with pytest.raises(ValueError) as excinfo:
            _run_cli(monkeypatch, run, tmp_path / "out")
        assert "t1" in str(excinfo.value)

    def test_a_run_whose_offers_were_all_withheld_says_so(
        self, tmp_path, monkeypatch
    ):
        """"No offers" and "every offer withheld" are different faults."""
        run = tmp_path / "withheld"
        _write_run(run, [
            ("t1", "hz_1111", 1, [_suppressed_turn(6, "insufficient_score")]),
        ])
        with pytest.raises(SystemExit) as excinfo:
            _run_cli(monkeypatch, run, tmp_path / "out")
        assert "withheld a price" in str(excinfo.value)
