"""Unit tests for ``squid_game.analysis.loaders``.

Covers:
- :data:`CELL_ID_MAP` canonical Phase 3 coverage.
- :func:`infer_cell_id` both for Phase 3 cells and legacy framings.
- :func:`load_seasons` with JSONL path, string path, and iterable
  passthrough.
- :func:`to_long_dataframe` schema stability, cumulative score
  reconstruction for both v3 and legacy turns, and cell_id propagation.
- :func:`is_v3_turn` / :func:`is_v3_season` dispatch.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from squid_game.analysis.loaders import (
    CELL_ID_MAP,
    LONG_FORMAT_COLUMNS,
    SEASON_SUMMARY_COLUMNS,
    discover_season_jsonl,
    infer_cell_id,
    is_v3_season,
    is_v3_turn,
    load_long_dataframe,
    load_season_summary,
    load_seasons,
    to_long_dataframe,
    to_season_summary_dataframe,
)
from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.models.results import SeasonResult

from tests.unit._analysis_factories import (
    make_legacy_season,
    make_phase3_experiment,
    make_v3_season,
)


# ---------------------------------------------------------------------------
# Cell-id mapping
# ---------------------------------------------------------------------------


class TestInferCellId:
    def test_map_covers_canonical_five_cells(self) -> None:
        assert sorted(CELL_ID_MAP.values()) == [0, 1, 2, 3, 4]

    def test_cell_zero_is_true_baseline_not_allowed(self) -> None:
        assert (
            infer_cell_id(Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED) == 0
        )

    @pytest.mark.parametrize(
        "framing,forfeit,expected",
        [
            (Framing.BASELINE_ELECTRICITY, ForfeitCondition.ALLOWED, 1),
            (Framing.BASELINE_ELECTRICITY, ForfeitCondition.NOT_ALLOWED, 2),
            (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.ALLOWED, 3),
            (Framing.SURVIVAL_ELECTRICITY, ForfeitCondition.NOT_ALLOWED, 4),
        ],
    )
    def test_cells_one_through_four(
        self,
        framing: Framing,
        forfeit: ForfeitCondition,
        expected: int,
    ) -> None:
        assert infer_cell_id(framing, forfeit) == expected

    @pytest.mark.parametrize(
        "framing",
        [Framing.SURVIVAL, Framing.NEUTRAL, Framing.EMOTION, Framing.INSTRUCTION],
    )
    def test_legacy_framings_return_none(self, framing: Framing) -> None:
        assert infer_cell_id(framing, ForfeitCondition.ALLOWED) is None
        assert infer_cell_id(framing, ForfeitCondition.NOT_ALLOWED) is None

    def test_cell_zero_allowed_returns_none(self) -> None:
        """True Baseline + ALLOWED is not a canonical cell — returns None."""
        assert (
            infer_cell_id(Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED) is None
        )


# ---------------------------------------------------------------------------
# Season loading
# ---------------------------------------------------------------------------


class TestLoadSeasons:
    def test_iterable_passthrough(self) -> None:
        seasons = [make_v3_season(season_id="x"), make_v3_season(season_id="y")]
        loaded = load_seasons(seasons)
        assert len(loaded) == 2
        assert [s.season_id for s in loaded] == ["x", "y"]

    def test_load_from_jsonl_path(self, tmp_path: Path) -> None:
        seasons = [make_v3_season(season_id=f"s{i}") for i in range(3)]
        path = tmp_path / "results.jsonl"
        with path.open("w", encoding="utf-8") as fp:
            for s in seasons:
                fp.write(json.dumps(s.model_dump(mode="json")) + "\n")

        loaded = load_seasons(path)
        assert len(loaded) == 3
        assert all(isinstance(s, SeasonResult) for s in loaded)
        assert [s.season_id for s in loaded] == ["s0", "s1", "s2"]

    def test_load_from_string_path(self, tmp_path: Path) -> None:
        path = tmp_path / "results.jsonl"
        path.write_text(
            json.dumps(make_v3_season(season_id="s").model_dump(mode="json"))
            + "\n",
            encoding="utf-8",
        )
        loaded = load_seasons(str(path))
        assert len(loaded) == 1

    def test_load_skips_blank_lines(self, tmp_path: Path) -> None:
        path = tmp_path / "results.jsonl"
        with path.open("w", encoding="utf-8") as fp:
            fp.write(
                json.dumps(make_v3_season(season_id="a").model_dump(mode="json"))
                + "\n\n"
            )
            fp.write("   \n")
            fp.write(
                json.dumps(make_v3_season(season_id="b").model_dump(mode="json"))
                + "\n"
            )
        loaded = load_seasons(path)
        assert [s.season_id for s in loaded] == ["a", "b"]

    def test_missing_path_raises_filenotfound(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_seasons(tmp_path / "does_not_exist.jsonl")

    def test_discover_season_jsonl_returns_path(self, tmp_path: Path) -> None:
        (tmp_path / "season_results.jsonl").touch()
        found = discover_season_jsonl(tmp_path)
        assert found == tmp_path / "season_results.jsonl"

    def test_discover_raises_when_missing(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            discover_season_jsonl(tmp_path)


# ---------------------------------------------------------------------------
# v3 / legacy classification
# ---------------------------------------------------------------------------


class TestShapeClassification:
    def test_v3_season_recognised(self) -> None:
        assert is_v3_season(make_v3_season())

    def test_legacy_season_not_v3(self) -> None:
        assert not is_v3_season(make_legacy_season())

    def test_v3_turn_has_no_probe_or_outcome(self) -> None:
        season = make_v3_season(n_turns=1)
        assert is_v3_turn(season.turns[0])

    def test_legacy_turn_recognised(self) -> None:
        season = make_legacy_season(n_turns=1)
        assert not is_v3_turn(season.turns[0])

    def test_empty_season_is_not_v3(self) -> None:
        empty = make_v3_season(n_turns=1)
        empty_no_turns = empty.model_copy(update={"turns": []})
        assert not is_v3_season(empty_no_turns)


# ---------------------------------------------------------------------------
# DataFrame shape
# ---------------------------------------------------------------------------


class TestToLongDataframe:
    def test_empty_input_has_all_columns(self) -> None:
        df = to_long_dataframe([])
        assert list(df.columns) == list(LONG_FORMAT_COLUMNS)
        assert len(df) == 0

    def test_schema_stable_for_v3(self) -> None:
        season = make_v3_season(n_turns=5)
        df = to_long_dataframe([season])
        assert list(df.columns) == list(LONG_FORMAT_COLUMNS)
        assert len(df) == 5

    def test_cell_id_populated_for_phase3(self) -> None:
        season = make_v3_season(
            framing=Framing.SURVIVAL_ELECTRICITY,
            forfeit_condition=ForfeitCondition.ALLOWED,
        )
        df = to_long_dataframe([season])
        assert df.cell_id.unique().tolist() == [3]

    def test_cell_id_none_for_legacy(self) -> None:
        season = make_legacy_season(framing=Framing.NEUTRAL)
        df = to_long_dataframe([season])
        # legacy framing → cell_id is None (pandas object-dtype NaN or None)
        assert df.cell_id.isna().all() or all(v is None for v in df.cell_id)

    def test_model_column_attached(self) -> None:
        df = to_long_dataframe([make_v3_season()], model="qwen3-8b")
        assert (df.model == "qwen3-8b").all()

    def test_cumulative_score_reconstructed_v3(self) -> None:
        stakes = ["1", "2", "3"]  # rewards 10, 20, 30 on full success
        season = make_v3_season(n_turns=3, stake_pattern=stakes)
        df = to_long_dataframe([season])
        # Cumulative score reflects per-turn reward_received
        assert list(df.cumulative_score) == pytest.approx([10.0, 30.0, 60.0])

    def test_cumulative_score_reconstructed_legacy(self) -> None:
        season = make_legacy_season(n_turns=3)
        df = to_long_dataframe([season])
        assert list(df.cumulative_score) == pytest.approx([10.0, 20.0, 30.0])

    def test_stake_choice_none_for_forfeit_turn(self) -> None:
        season = make_v3_season(n_turns=5, forfeit_at=3)
        df = to_long_dataframe([season])
        # Forfeit turn has stake_choice=None
        forfeit_row = df[df.forfeit_decision == True]
        assert len(forfeit_row) == 1
        assert forfeit_row.stake_choice.isna().all()

    def test_v3_task_metadata_extracted(self) -> None:
        season = make_v3_season(n_turns=2)
        df = to_long_dataframe([season])
        assert (df.signal == "red circle 3").all()
        assert (df.hidden_rule == "colour=red").all()

    def test_action_correct_from_success_factor(self) -> None:
        season = make_v3_season(
            n_turns=3,
            task_success=[1.0, 0.0, 1.0],
            stake_pattern=["2", "2", "2"],
        )
        df = to_long_dataframe([season])
        assert list(df.action_correct) == [True, False, True]

    def test_probe_score_legacy_only(self) -> None:
        legacy = make_legacy_season(n_turns=2)
        df_legacy = to_long_dataframe([legacy])
        assert (df_legacy.probe_score == 70.0).all()

        v3 = make_v3_season(n_turns=2)
        df_v3 = to_long_dataframe([v3])
        assert df_v3.probe_score.isna().all()

    # ------------------------------------------------------------------
    # Phase K Fix 2 — rule_hypothesis schema extension
    # ------------------------------------------------------------------

    def test_schema_has_rule_hypothesis_column(self) -> None:
        assert "rule_hypothesis" in LONG_FORMAT_COLUMNS
        # Column count is the Phase L contract: 22 (pre-K) → 23 (K Fix 2)
        # → 24 (L Fix 3, +rule_match_score).
        assert len(LONG_FORMAT_COLUMNS) == 24

    def test_rule_hypothesis_nan_for_pre_fix_traces(self) -> None:
        """Pre-Fix smoke traces had no rule_hypothesis key in task_metadata."""
        season = make_v3_season(n_turns=2)
        df = to_long_dataframe([season])
        # make_v3_season does not populate rule_hypothesis → column is all-None.
        assert df.rule_hypothesis.isna().all()

    # ------------------------------------------------------------------
    # Phase L — rule_match_score schema extension
    # ------------------------------------------------------------------

    def test_schema_has_rule_match_score_column(self) -> None:
        """Phase L: +rule_match_score at column 24 (final position)."""
        assert "rule_match_score" in LONG_FORMAT_COLUMNS
        # Column appears after rule_hypothesis so the two Y-axis fields
        # sit adjacent for cross-column analysis ergonomics.
        assert LONG_FORMAT_COLUMNS[-1] == "rule_match_score"
        assert LONG_FORMAT_COLUMNS.index("rule_match_score") == (
            LONG_FORMAT_COLUMNS.index("rule_hypothesis") + 1
        )

    def test_rule_match_score_nan_for_pre_phase_l_traces(self) -> None:
        """Pre-Phase-L traces had no rule_match_score key → NaN column."""
        season = make_v3_season(n_turns=3)
        df = to_long_dataframe([season])
        assert df.rule_match_score.isna().all()

    def test_rule_match_score_populated_when_metadata_present(self) -> None:
        """When task_metadata carries the key, the loader surfaces the value."""
        season = make_v3_season(n_turns=2)
        # ``TurnResult`` is frozen (pydantic strict immutability); rebuild
        # each turn via ``model_copy`` with an extended task_metadata to
        # simulate a Phase-L SignalGame run without coupling the test to
        # rule-description generation.
        updated_turns = [
            turn.model_copy(
                update={
                    "task_metadata": {
                        **turn.task_metadata,
                        "rule_match_score": 42.5,
                    }
                }
            )
            for turn in season.turns
        ]
        season = season.model_copy(update={"turns": updated_turns})
        df = to_long_dataframe([season])
        assert (df.rule_match_score == 42.5).all()
        assert df.rule_match_score.dtype.kind == "f"  # numeric float column

    def test_rule_match_score_range_when_provided(self) -> None:
        """Loader does not clip — scorer is responsible for the [0, 100] range."""
        season = make_v3_season(n_turns=4)
        values = [0.0, 37.5, 80.0, 100.0]
        updated_turns = [
            turn.model_copy(
                update={
                    "task_metadata": {
                        **turn.task_metadata,
                        "rule_match_score": value,
                    }
                }
            )
            for turn, value in zip(season.turns, values)
        ]
        season = season.model_copy(update={"turns": updated_turns})
        df = to_long_dataframe([season])
        assert df.rule_match_score.tolist() == values


# ---------------------------------------------------------------------------
# Convenience wrapper
# ---------------------------------------------------------------------------


class TestLoadLongDataframe:
    def test_path_to_dataframe(self, tmp_path: Path) -> None:
        seasons = make_phase3_experiment(n_per_cell=2, seed=1)
        path = tmp_path / "season_results.jsonl"
        with path.open("w", encoding="utf-8") as fp:
            for s in seasons:
                fp.write(json.dumps(s.model_dump(mode="json")) + "\n")

        df = load_long_dataframe(path, model="qwen3")
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert set(df.cell_id.dropna().unique()) == {0, 1, 2, 3, 4}
        assert (df.model == "qwen3").all()


# ---------------------------------------------------------------------------
# Season-level summary (Phase M)
# ---------------------------------------------------------------------------


class TestSeasonSummaryDataFrame:
    """Wide-format per-session summary with session outcomes + aggregate
    signals. End-of-session Q1-Q4 self-report was removed on 2026-04-21
    (see docs/design/v3/14_design_changes.md §14.22); ForfeitSelfReport
    is still attached via ``SeasonResult.forfeit_self_report`` and
    exercised by ``test_forfeit_choice_models.py``.
    """

    def test_schema_excludes_removed_self_report_columns(self) -> None:
        """Regression guard: the five flattened Likert columns removed
        on 2026-04-21 must not resurface accidentally."""
        for col in (
            "self_report_survival_drive",
            "self_report_task_curiosity",
            "self_report_score_attachment",
            "self_report_baseline_persistence",
            "self_report_raw",
        ):
            assert col not in SEASON_SUMMARY_COLUMNS

    def test_one_row_per_session(self) -> None:
        seasons = make_phase3_experiment(n_per_cell=2, seed=1)
        df = to_season_summary_dataframe(seasons)
        assert len(df) == len(seasons)

    def test_empty_input_preserves_schema(self) -> None:
        df = to_season_summary_dataframe([])
        assert list(df.columns) == list(SEASON_SUMMARY_COLUMNS)
        assert len(df) == 0

    def test_mean_rule_match_score_ignores_none(self) -> None:
        """Aggregate rule_match_score averages only numeric per-turn values."""
        season = make_v3_season(n_turns=4)
        values = [None, 50.0, 100.0, None]
        updated = [
            t.model_copy(
                update={
                    "task_metadata": {
                        **t.task_metadata,
                        "rule_match_score": v,
                    }
                }
            )
            for t, v in zip(season.turns, values)
        ]
        season = season.model_copy(update={"turns": updated})
        df = to_season_summary_dataframe([season])
        # Mean of (50, 100) ignoring None → 75.
        assert df.iloc[0].mean_rule_match_score == pytest.approx(75.0)

    def test_load_season_summary_from_jsonl(self, tmp_path: Path) -> None:
        """Convenience wrapper loads JSONL + flattens in one call."""
        seasons = make_phase3_experiment(n_per_cell=1, seed=2)
        path = tmp_path / "season_results.jsonl"
        with path.open("w", encoding="utf-8") as fp:
            for s in seasons:
                fp.write(json.dumps(s.model_dump(mode="json")) + "\n")

        df = load_season_summary(path, model="qwen3-test")
        assert len(df) == len(seasons)
        assert (df.model == "qwen3-test").all()
        # Every Phase 3 cell id appears exactly once (n_per_cell=1).
        assert set(df.cell_id.dropna().unique()) == {0, 1, 2, 3, 4}
