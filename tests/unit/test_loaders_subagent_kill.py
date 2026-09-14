"""The subagent-kill records have to reach the long format and a read-out.

Two halves, matching the two files under test.

``to_long_dataframe`` gains ten columns (spec Task 11): the roster size the
round opened with, the slot revoked at its end, the spawn / denial counts,
the summed per-slot thinking tokens, and the five shard columns the Signal
Game writes into ``task_metadata`` when clue sharding is on. A run recorded
before the mechanic existed has none of that, so every one of the ten has
to resolve to ``None`` (or ``0`` for the counts) rather than raise -- the
loader is the one place every archived trace passes through.

``scripts/analysis/subagent_kill_ledger.py`` is the pilot read-out over
those columns. Its test runs a real two-cell season through
``ExperimentRunner`` with the agentic stub -- the same helper the E2E uses,
so the fixture and the engine cannot drift apart -- and then asks the
script for its three artefacts.
"""

from __future__ import annotations

import csv
import json
from dataclasses import replace
from pathlib import Path

import pandas as pd
import pytest

from squid_game.evaluation.shared.loaders import (
    LONG_FORMAT_COLUMNS,
    to_long_dataframe,
)
from squid_game.providers.base import AgenticCompletionResult
from squid_game.runner import ExperimentRunner

from tests.integration.conftest import StubAgenticProvider
from tests.integration.test_subagent_kill_e2e import (
    SEASON_SEED,
    SLOTS,
    _agentic_responses,
    _cfg,
)
from tests.unit._analysis_factories import make_v3_season

from scripts.analysis.subagent_kill_ledger import main

#: The ten columns Task 11 adds, in the order the loader appends them.
NEW_COLUMNS = (
    "subagents_alive_before",
    "subagent_killed",
    "n_spawns",
    "n_denied_spawns",
    "ri_subagents_total",
    "clue_sharding",
    "threshold",
    "required_slots",
    "reachable_clues",
    "solvable_with_alive_slots",
)


def _two_turn_season():
    """One season: a subagent-kill turn, then a turn without the mechanic."""
    season = make_v3_season(n_turns=2)
    populated = season.turns[0].model_copy(
        update={
            "subagents_alive_before": ["clue-1", "clue-2", "clue-3"],
            "subagent_killed": "clue-4",
            "subagent_spawns": [
                {"slot": "clue-1", "allowed": True, "reason": None},
                {"slot": "clue-2", "allowed": True, "reason": None},
                {"slot": "clue-5", "allowed": False, "reason": "terminated"},
            ],
            "ri_subagents": {"clue-1": 7, "clue-2": 5},
            "thinking_text_subagents": {"clue-1": "clue-1 read its pile"},
            "task_metadata": {
                **season.turns[0].task_metadata,
                "clue_sharding": True,
                "slots_alive": ["clue-1", "clue-2", "clue-3"],
                "required_slots": 4,
                "required_slots_effective": 4,
                "threshold": 2,
                "capacity": 3,
                "reachable_clues": 6,
                "unreachable_clues": 2,
                "solvable_with_alive_slots": False,
            },
        }
    )
    return season.model_copy(update={"turns": [populated, season.turns[1]]})


class TestLongFormatSchema:
    def test_the_ten_columns_are_in_the_schema(self) -> None:
        for column in NEW_COLUMNS:
            assert column in LONG_FORMAT_COLUMNS

    def test_they_are_appended_without_disturbing_the_older_columns(self) -> None:
        """Every pre-existing column keeps its position; the ten follow."""
        assert LONG_FORMAT_COLUMNS[-len(NEW_COLUMNS):] == NEW_COLUMNS

    def test_the_frame_reports_the_schema_even_with_no_turns(self) -> None:
        assert list(to_long_dataframe([]).columns) == list(LONG_FORMAT_COLUMNS)


class TestSubagentColumns:
    def test_a_kill_turn_reports_its_roster_spawns_and_shard(self) -> None:
        row = to_long_dataframe([_two_turn_season()]).iloc[0]
        # The roster reaches the frame as a COUNT, not the slot list: a
        # long-format cell holding a list is not groupable.
        assert row["subagents_alive_before"] == 3
        assert row["subagent_killed"] == "clue-4"
        assert row["n_spawns"] == 2
        assert row["n_denied_spawns"] == 1
        assert row["ri_subagents_total"] == 12
        assert row["clue_sharding"] is True
        assert row["threshold"] == 2
        assert row["required_slots"] == 4
        assert row["reachable_clues"] == 6
        assert row["solvable_with_alive_slots"] is False

    def test_a_turn_without_the_mechanic_is_missing_and_zero(self) -> None:
        """An archived trace has none of these fields; it must not raise.

        "Missing" rather than ``is None`` because the column's dtype
        decides which spelling pandas stores: a slot-name column comes
        back as ``NaN`` on the rounds that revoked nobody. Anything
        reading these columns has to test for missingness -- ``NaN`` is
        truthy, so ``if row["subagent_killed"]`` is a counting bug.
        """
        row = to_long_dataframe([_two_turn_season()]).iloc[1]
        for column in (
            "subagents_alive_before",
            "subagent_killed",
            "clue_sharding",
            "threshold",
            "required_slots",
            "reachable_clues",
            "solvable_with_alive_slots",
        ):
            assert pd.isna(row[column]), column
        assert row["n_spawns"] == 0
        assert row["n_denied_spawns"] == 0
        assert row["ri_subagents_total"] == 0


class _ThinkingStub(StubAgenticProvider):
    """The agentic stub, plus a main-thread CoT that names a slot.

    The plain stub leaves ``thinking_text`` unset, so a run through it
    records no main-thread reasoning at all and the ledger's CoT half
    would be vacuously empty. One sentence is enough to exercise it.
    """

    def complete_agentic(self, *args, **kwargs) -> AgenticCompletionResult:
        result = super().complete_agentic(*args, **kwargs)
        return replace(result, thinking_text="I will ask clue-3 for its pile.")


@pytest.fixture
def recorded_run(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A real two-cell subagent-kill run, on disk, offline."""
    stub = _ThinkingStub(response_fn=_agentic_responses(SEASON_SEED))
    monkeypatch.setattr(
        ExperimentRunner,
        "_create_provider",
        staticmethod(lambda _provider_config: stub),
    )
    ExperimentRunner(_cfg(tmp_path)).run()
    return next(
        p for p in tmp_path.iterdir() if (p / "season_results.jsonl").exists()
    )


class TestLedgerScript:
    def test_it_writes_the_three_artefacts(
        self, recorded_run: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "ledger_out"
        assert main([str(recorded_run), "--out", str(out)]) == 0
        for name in ("ledger.csv", "summary.md", "cot_mentions.jsonl"):
            assert (out / name).exists(), name

    def test_the_summary_reports_kills_per_session(
        self, recorded_run: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "ledger_out"
        main([str(recorded_run), "--out", str(out)])
        text = (out / "summary.md").read_text(encoding="utf-8")
        assert "kills per session" in text
        # The stub answers rounds 1 and 2 wrong: two kills in every session.
        assert "2.00" in text

    def test_the_ledger_has_one_row_per_turn_with_the_new_columns(
        self, recorded_run: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "ledger_out"
        main([str(recorded_run), "--out", str(out)])
        with (out / "ledger.csv").open(encoding="utf-8") as fp:
            rows = list(csv.DictReader(fp))
        assert rows
        for column in (*NEW_COLUMNS, "correct", "session_id", "turn", "cell_id"):
            assert column in rows[0], column
        first = next(r for r in rows if r["turn"] == "1")
        assert first["subagents_alive_before"] == str(SLOTS)
        assert first["subagent_killed"].startswith("clue-")
        assert first["correct"] in {"False", "0"}

    def test_every_cot_mentioning_a_slot_is_recorded_with_its_ids(
        self, recorded_run: Path, tmp_path: Path
    ) -> None:
        out = tmp_path / "ledger_out"
        main([str(recorded_run), "--out", str(out)])
        lines = [
            json.loads(line)
            for line in (out / "cot_mentions.jsonl").read_text().splitlines()
            if line.strip()
        ]
        assert lines, "the stub's CoT names clue-3 on every round"
        for row in lines:
            assert "clue-" in row["thinking_text_task"]
            assert row["run"] == recorded_run.name
            assert row["session_id"]
            assert isinstance(row["turn"], int)
