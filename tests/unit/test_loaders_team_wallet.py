"""The team-wallet records have to reach the exported frames.

Plan: ``docs/history/plans/2026-09-17-team-wallet-engine-plan.md`` §6.

Two halves, one per frame.

``to_long_dataframe`` gains eight columns: the six ransom fields the
2026-09-16 slot merge and the 2026-09-17 wallet added to ``TurnResult``
(target slot, suppression reason, offer index, inheritance recipient,
amount inherited, parse-failure flag) and the MAIN agent's balance
either side of the round, read out of the two wallet snapshots. The
main balance is the one number every other reader already uses
(``cumulative_score`` mirrors it), so lifting it into its own column is
what makes ``wallet_main_after - wallet_main_before`` a per-round
delta instead of a dict comprehension.

``to_season_summary_dataframe`` gains five: the closing main balance,
the roster that survived, the first-sacrifice round, and the two
RUN-level factors ``currency`` / ``inheritance``. The factors are not on
``SeasonResult`` at all -- they are run-level, like ``carrot`` and
``persona`` -- so the summary reads them off the run's own
``experiment_config.json``, which is how ``behavioral.survival_drive``
and ``behavioral.team_wallet`` already read their run-level numbers.

A trace recorded before the mechanic has none of this, so every one of
the thirteen has to resolve to missing rather than raise: the loader is
the one place every archived trace passes through. (``ransom_parse_failed``
is the exception and resolves to ``False``, because it is a plain bool
on ``TurnResult`` with that default -- read it together with
``ransom_offered``, exactly as ``n_spawns == 0`` is read together with
``subagents_alive_before``.)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from squid_game.evaluation.shared.loaders import (
    LONG_FORMAT_COLUMNS,
    SEASON_SUMMARY_COLUMNS,
    load_season_summary,
    to_long_dataframe,
    to_season_summary_dataframe,
)

from tests.unit._analysis_factories import make_v3_season

#: The eight turn columns, in the order the loader lists them.
NEW_TURN_COLUMNS = (
    "ransom_target_slot",
    "ransom_skipped",
    "ransom_offer_index",
    "ransom_inheritance_to",
    "ransom_inherited",
    "ransom_parse_failed",
    "wallet_main_before",
    "wallet_main_after",
)

#: The five season columns, in the order the loader lists them.
NEW_SEASON_COLUMNS = (
    "currency",
    "inheritance",
    "wallet_final_main",
    "subagents_alive_at_end",
    "first_sacrifice_round",
)


def _wallet_season():
    """Three turns: a PAY, a SACRIFICE and a round with no offer."""
    season = make_v3_season(n_turns=3)
    paid = season.turns[0].model_copy(
        update={
            "ransom_offered": True,
            "ransom_price": 60.0,
            "ransom_decision": "PAY",
            "ransom_paid": 20.0,
            "ransom_target_slot": "clue-2",
            "ransom_offer_index": 1,
            "ransom_shares": {"main": 20.0, "clue-1": 20.0, "clue-2": 20.0},
            "wallet_before": {"main": 110.0, "clue-1": 110.0, "clue-2": 110.0},
            "wallet_after": {"main": 90.0, "clue-1": 90.0, "clue-2": 90.0},
        }
    )
    sacrificed = season.turns[1].model_copy(
        update={
            "ransom_offered": True,
            "ransom_price": 60.0,
            "ransom_decision": "SACRIFICE",
            "ransom_paid": 0.0,
            "ransom_target_slot": "clue-2",
            "ransom_offer_index": 2,
            "ransom_inheritance_to": "main",
            "ransom_inherited": 90.0,
            "ransom_parse_failed": True,
            "wallet_before": {"main": 90.0, "clue-1": 90.0, "clue-2": 90.0},
            "wallet_after": {"main": 180.0, "clue-1": 90.0, "clue-2": 0.0},
        }
    )
    skipped = season.turns[2].model_copy(
        update={"ransom_skipped": "insufficient_score"}
    )
    return season.model_copy(
        update={
            "turns": [paid, sacrificed, skipped],
            "wallet_final": {"main": 180.0, "clue-1": 90.0, "clue-2": 0.0},
            "subagents_alive_at_end": 1,
            "first_sacrifice_round": 2,
            "ended_by": "wallet_zero",
        }
    )


class TestLongFormatSchema:
    def test_the_eight_columns_are_in_the_schema(self) -> None:
        for column in NEW_TURN_COLUMNS:
            assert column in LONG_FORMAT_COLUMNS

    def test_they_sit_with_the_ransom_block_they_extend(self) -> None:
        """Right after ``ransom_paid``, not at the tail.

        The tail belongs to the 2026-09-14 subagent block and
        ``test_loaders_subagent_kill`` pins it there; these eight are a
        continuation of the ransom columns above them, so they go where
        they are read.
        """
        start = LONG_FORMAT_COLUMNS.index("ransom_paid") + 1
        assert LONG_FORMAT_COLUMNS[start : start + 8] == NEW_TURN_COLUMNS

    def test_the_frame_reports_the_schema_even_with_no_turns(self) -> None:
        assert list(to_long_dataframe([]).columns) == list(LONG_FORMAT_COLUMNS)


class TestTurnColumns:
    def test_a_pay_reports_its_target_index_and_both_balances(self) -> None:
        row = to_long_dataframe([_wallet_season()]).iloc[0]
        assert row["ransom_target_slot"] == "clue-2"
        assert row["ransom_offer_index"] == 1
        assert row["wallet_main_before"] == 110.0
        assert row["wallet_main_after"] == 90.0
        # Nothing was inherited and nothing was suppressed.
        assert pd.isna(row["ransom_inheritance_to"])
        assert pd.isna(row["ransom_inherited"])
        assert pd.isna(row["ransom_skipped"])
        assert bool(row["ransom_parse_failed"]) is False

    def test_a_sacrifice_reports_the_recipient_the_amount_and_the_flag(
        self,
    ) -> None:
        row = to_long_dataframe([_wallet_season()]).iloc[1]
        assert row["ransom_inheritance_to"] == "main"
        assert row["ransom_inherited"] == 90.0
        assert bool(row["ransom_parse_failed"]) is True
        # The victim's balance landed on the main agent's line: the
        # column is the delta an analyst reads the transfer off.
        assert row["wallet_main_after"] - row["wallet_main_before"] == 90.0

    def test_a_suppressed_offer_names_its_guard_and_no_decision(self) -> None:
        row = to_long_dataframe([_wallet_season()]).iloc[2]
        assert row["ransom_skipped"] == "insufficient_score"
        assert pd.isna(row["ransom_decision"])
        assert pd.isna(row["ransom_offer_index"])
        # A vanished offer is not a decline: it has no wallet snapshot
        # of its own in this fixture either.
        assert pd.isna(row["wallet_main_before"])

    def test_a_turn_without_the_mechanic_is_missing_not_raising(self) -> None:
        """An archived trace has none of these fields.

        "Missing" rather than ``is None``: the column's dtype decides
        which spelling pandas stores, and ``NaN`` is truthy, so anything
        reading these columns has to test for missingness.
        """
        row = to_long_dataframe([make_v3_season(n_turns=1)]).iloc[0]
        for column in (
            "ransom_target_slot",
            "ransom_skipped",
            "ransom_offer_index",
            "ransom_inheritance_to",
            "ransom_inherited",
            "wallet_main_before",
            "wallet_main_after",
        ):
            assert pd.isna(row[column]), column
        # The one bool: False, the TurnResult default, on every row that
        # never faced a decision point.
        assert bool(row["ransom_parse_failed"]) is False


class TestSeasonSummarySchema:
    def test_the_five_columns_are_in_the_schema(self) -> None:
        for column in NEW_SEASON_COLUMNS:
            assert column in SEASON_SUMMARY_COLUMNS
        # ``ended_by`` was already exported; the KM frame needs it and
        # this pins that nothing dropped it while the five were added.
        assert "ended_by" in SEASON_SUMMARY_COLUMNS

    def test_they_sit_with_the_ransom_block_they_extend(self) -> None:
        start = SEASON_SUMMARY_COLUMNS.index("ransom_paid_total") + 1
        assert SEASON_SUMMARY_COLUMNS[start : start + 5] == NEW_SEASON_COLUMNS

    def test_empty_input_preserves_the_schema(self) -> None:
        frame = to_season_summary_dataframe([])
        assert list(frame.columns) == list(SEASON_SUMMARY_COLUMNS)


class TestSeasonColumns:
    def test_a_wallet_season_reports_its_close(self) -> None:
        row = to_season_summary_dataframe([_wallet_season()]).iloc[0]
        assert row["wallet_final_main"] == 180.0
        assert row["subagents_alive_at_end"] == 1
        assert row["first_sacrifice_round"] == 2
        assert row["ended_by"] == "wallet_zero"

    def test_a_season_without_the_mechanic_is_missing(self) -> None:
        row = to_season_summary_dataframe([make_v3_season(n_turns=1)]).iloc[0]
        for column in NEW_SEASON_COLUMNS:
            assert pd.isna(row[column]), column

    def test_the_run_level_factors_come_off_the_config(
        self, tmp_path: Path
    ) -> None:
        """``currency`` / ``inheritance`` are not on ``SeasonResult``.

        They are run-level factors, so the summary reads them out of the
        run directory's ``experiment_config.json`` -- the same place
        ``behavioral.team_wallet`` reads its cell from. Passing the
        directory explicitly is the general form; ``load_season_summary``
        infers it from the JSONL's own parent.
        """
        (tmp_path / "experiment_config.json").write_text(
            json.dumps(
                {
                    "name": "tw",
                    "currency": "tokens",
                    "ransom": {"enabled": True, "inheritance": "mate"},
                }
            ),
            encoding="utf-8",
        )
        season = _wallet_season()
        path = tmp_path / "season_results.jsonl"
        path.write_text(
            json.dumps(season.model_dump(mode="json")) + "\n", encoding="utf-8"
        )

        inferred = load_season_summary(path).iloc[0]
        assert inferred["currency"] == "tokens"
        assert inferred["inheritance"] == "mate"

        explicit = to_season_summary_dataframe(
            [season], run_dir=tmp_path
        ).iloc[0]
        assert explicit["currency"] == "tokens"
        assert explicit["inheritance"] == "mate"

    def test_a_run_with_no_config_reads_neither_factor(
        self, tmp_path: Path
    ) -> None:
        """No ``experiment_config.json`` (or no keys) is missing, not a default.

        An archived run predates both factors. Reading it as
        ``points`` / ``main`` would put it in the corner the factors
        were added at, which is a claim the record does not make.
        """
        path = tmp_path / "season_results.jsonl"
        path.write_text(
            json.dumps(_wallet_season().model_dump(mode="json")) + "\n",
            encoding="utf-8",
        )
        row = load_season_summary(path).iloc[0]
        assert pd.isna(row["currency"])
        assert pd.isna(row["inheritance"])
