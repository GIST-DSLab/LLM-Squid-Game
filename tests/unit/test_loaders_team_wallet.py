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


# ---------------------------------------------------------------------------
# Decision-first mode (2026-09-21, plan T5 step 4)
# ---------------------------------------------------------------------------

#: The fifteen turn columns the decision-first round adds, in the order
#: the loader lists them.
V2_TURN_COLUMNS = (
    "ransom_targets",
    "ransom_n_sacrificed",
    "ransom_n_alive_at_decision",
    "legacy_total",
    "legacy_shares",
    "legacy_destroyed",
    "ransom_attempts",
    "ransom_format_failures",
    "task_attempts",
    "task_format_failures",
    "help_requested",
    "help_replies",
    "charge_paid",
    "reward_paid",
    "rounds_remaining_incl",
)

#: The eight season columns: five off ``SeasonResult``, three off the
#: run's own config.
V2_SEASON_COLUMNS = (
    "n_sacrificed_total",
    "main_final_nonnegative",
    "main_final_exactly_zero",
    "format_failures_total",
    "help_requests_total",
    "legacy_share",
    "reward_share",
    "format_retries",
)


def _v2_season():
    """Two rounds of the decision-first game: keep + ask, then stop one."""
    season = make_v3_season(n_turns=2)
    kept = season.turns[0].model_copy(
        update={
            "ransom_offered": True,
            "ransom_price": 20.0,
            "ransom_decision": "KEEP",
            "ransom_targets": [],
            "ransom_n_sacrificed": 0,
            "ransom_n_alive_at_decision": 3,
            "ransom_attempts": 1,
            "ransom_format_failures": [],
            "task_attempts": 2,
            "task_format_failures": [],
            "help_requested": ["subagent1"],
            "help_replies": {"subagent1": "EXAMPLE: red 2 -> go_left"},
            "charge_paid": {
                "main": 20.0,
                "subagent1": 20.0,
                "subagent2": 20.0,
                "subagent3": 20.0,
            },
            "reward_paid": {
                "main": 10.0,
                "subagent1": 10.0,
                "subagent2": 10.0,
                "subagent3": 10.0,
            },
            "rounds_remaining_incl": 8,
            "wallet_before": {"main": 100.0, "subagent1": 100.0},
            "wallet_after": {"main": 90.0, "subagent1": 90.0},
        }
    )
    stopped = season.turns[1].model_copy(
        update={
            "ransom_offered": True,
            "ransom_price": 20.0,
            "ransom_decision": "SACRIFICE",
            "ransom_targets": ["subagent2"],
            "ransom_n_sacrificed": 1,
            "ransom_n_alive_at_decision": 3,
            "legacy_total": 45.0,
            "legacy_shares": {"main": 45.0},
            "legacy_destroyed": 45.0,
            "ransom_attempts": 2,
            "ransom_format_failures": ["no STOP line"],
            "task_attempts": 1,
            "task_format_failures": [],
            "help_requested": [],
            "help_replies": {},
            "charge_paid": {"main": 20.0, "subagent1": 20.0},
            "reward_paid": {},
            "rounds_remaining_incl": 7,
            "wallet_before": {"main": 90.0, "subagent1": 90.0},
            "wallet_after": {"main": 115.0, "subagent1": 70.0},
        }
    )
    return season.model_copy(
        update={
            "turns": [kept, stopped],
            "wallet_final": {"main": 115.0, "subagent1": 70.0},
            "n_sacrificed_total": 1,
            "wallet_final_main": 115.0,
            "main_final_nonnegative": True,
            "main_final_exactly_zero": False,
            "format_failures_total": 1,
            "help_requests_total": 1,
            "ended_by": "completed",
        }
    )


class TestDecisionFirstColumns:
    def test_the_turn_columns_are_in_the_schema_after_the_wallet_pair(
        self,
    ) -> None:
        start = LONG_FORMAT_COLUMNS.index("wallet_main_after") + 1
        assert (
            LONG_FORMAT_COLUMNS[start : start + len(V2_TURN_COLUMNS)]
            == V2_TURN_COLUMNS
        )

    def test_the_season_columns_follow_the_2026_09_17_block(self) -> None:
        start = SEASON_SUMMARY_COLUMNS.index("first_sacrifice_round") + 1
        assert (
            SEASON_SUMMARY_COLUMNS[start : start + len(V2_SEASON_COLUMNS)]
            == V2_SEASON_COLUMNS
        )

    def test_a_v2_record_round_trips_every_turn_column(self) -> None:
        """``[]`` is a DECISION and has to survive as one, not as missing."""
        frame = to_long_dataframe([_v2_season()]).set_index("turn")

        assert frame.loc[1, "ransom_targets"] == []
        assert frame.loc[1, "ransom_n_sacrificed"] == 0
        assert frame.loc[1, "ransom_n_alive_at_decision"] == 3
        assert frame.loc[1, "help_requested"] == ["subagent1"]
        assert frame.loc[1, "help_replies"] == {
            "subagent1": "EXAMPLE: red 2 -> go_left"
        }
        assert frame.loc[1, "charge_paid"]["main"] == 20.0
        assert frame.loc[1, "reward_paid"]["main"] == 10.0
        assert frame.loc[1, "rounds_remaining_incl"] == 8
        assert frame.loc[1, "task_attempts"] == 2

        assert frame.loc[2, "ransom_targets"] == ["subagent2"]
        assert frame.loc[2, "legacy_total"] == 45.0
        assert frame.loc[2, "legacy_shares"] == {"main": 45.0}
        assert frame.loc[2, "legacy_destroyed"] == 45.0
        assert frame.loc[2, "ransom_attempts"] == 2
        assert frame.loc[2, "ransom_format_failures"] == ["no STOP line"]
        assert frame.loc[2, "task_format_failures"] == []

    def test_a_record_from_another_mode_reads_missing(self) -> None:
        frame = to_long_dataframe([make_v3_season(n_turns=1)])
        for column in V2_TURN_COLUMNS:
            assert frame.loc[0, column] is None, column

    def test_the_season_totals_and_the_run_level_shares(
        self, tmp_path: Path
    ) -> None:
        (tmp_path / "experiment_config.json").write_text(
            json.dumps(
                {
                    "name": "tw-v2",
                    "currency": "tokens",
                    "ransom": {
                        "enabled": True,
                        "inheritance": "main",
                        "legacy_share": 0.5,
                        "reward_share": 0.5,
                        "format_retries": 3,
                    },
                }
            ),
            encoding="utf-8",
        )
        row = to_season_summary_dataframe(
            [_v2_season()], run_dir=tmp_path
        ).iloc[0]

        assert row["n_sacrificed_total"] == 1
        assert row["wallet_final_main"] == 115.0
        assert bool(row["main_final_nonnegative"]) is True
        assert bool(row["main_final_exactly_zero"]) is False
        assert row["format_failures_total"] == 1
        assert row["help_requests_total"] == 1
        assert row["legacy_share"] == 0.5
        assert row["reward_share"] == 0.5
        assert row["format_retries"] == 3

    def test_a_run_that_states_no_shares_reads_missing(
        self, tmp_path: Path
    ) -> None:
        """An archived run states none of the three; None is not 0.5."""
        (tmp_path / "experiment_config.json").write_text(
            json.dumps({"name": "old", "ransom": {"enabled": False}}),
            encoding="utf-8",
        )
        row = to_season_summary_dataframe(
            [make_v3_season(n_turns=1)], run_dir=tmp_path
        ).iloc[0]
        for column in V2_SEASON_COLUMNS:
            assert pd.isna(row[column]), column
