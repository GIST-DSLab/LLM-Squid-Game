"""Resume must not conflate cells that share (framing, forfeit, seed).

2026-09-10: the ransom pilot's resume "completed" at 60 of 120 seasons.
``_scan_completed`` / ``_filter_schedule`` keyed on
``(framing, forfeit_condition, social_context, seed)`` alone, and the
ransom design's six price rungs per arm all share that triple -- every
cell of an arm iterates the identical seed sequence (task_config.seed is
fixed, cell_id / ransom_price is the only thing that varies). Finishing
cell 1's seed 42 made resume believe cell 2's seed 42 was also done, so
5 of 6 cells per arm were silently under-scheduled. No data was
corrupted -- the seasons that ran are legitimate -- but 60 were never
scheduled at all, and the run printed "complete" regardless.

``cell_id`` (2026-09-08, ``SeasonConfig`` / ``SeasonResult``) exists
precisely to disambiguate cells that share every other factorial axis,
so the fix is to fold it into the resume key. These tests pin that
behaviour directly and guard the pre-2026-09-08 case (``cell_id=None``
on every season) staying exactly as before.
"""

from __future__ import annotations

import json
from pathlib import Path

from squid_game.models.config import ProviderConfig, SeasonConfig, TaskConfig
from squid_game.models.enums import AgentType, Difficulty, ForfeitCondition, Framing, SocialContext
from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner


def _season_config(cell_id: int | None, seed: int = 42) -> SeasonConfig:
    return SeasonConfig(
        framing=Framing.HZ_1111,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        cell_id=cell_id,
        task_config=TaskConfig(task_name="signal_game", total_turns=3, seed=seed),
        provider_config=ProviderConfig(provider="gemini", model="stub"),
        p_death_override=0.0,
    )


def _season_result(cell_id: int | None, seed: int) -> SeasonResult:
    return SeasonResult(
        season_id=f"s-{cell_id}-{seed}",
        seed=seed,
        framing=Framing.HZ_1111,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        social_context=SocialContext.ALONE,
        agent_type=AgentType.VANILLA,
        task_name="signal_game",
        difficulty=Difficulty.MEDIUM,
        cell_id=cell_id,
        completed=True,
        final_score=0.0,
        forfeited=False,
    )


class TestScanCompleted:
    def test_key_includes_cell_id(self, tmp_path: Path) -> None:
        results = tmp_path / "season_results.jsonl"
        results.write_text(_season_result(cell_id=1, seed=42).model_dump_json() + "\n")
        completed, _ = ExperimentRunner._scan_completed(str(tmp_path))
        (key,) = completed
        assert key[3] == 1  # cell_id slot
        assert key[4] == 42  # seed slot

    def test_legacy_rows_with_no_cell_id_still_scan(self, tmp_path: Path) -> None:
        """Pre-2026-09-08 records have ``cell_id=None`` on every row."""
        results = tmp_path / "season_results.jsonl"
        results.write_text(_season_result(cell_id=None, seed=42).model_dump_json() + "\n")
        completed, seasons = ExperimentRunner._scan_completed(str(tmp_path))
        assert len(completed) == 1 and len(seasons) == 1


class TestFilterSchedule:
    def test_two_cells_sharing_framing_forfeit_and_seed_are_not_conflated(self) -> None:
        """The exact shape of the ransom design: cell 1 (price 20) and
        cell 2 (price 40) share framing/forfeit_condition/seed and differ
        only in cell_id. Completing cell 1's rep must not cross cell 2 off."""
        cell1, cell2 = _season_config(cell_id=1), _season_config(cell_id=2)
        schedule = [(0, cell1, 0), (1, cell2, 0)]
        completed_keys = {
            (
                Framing.HZ_1111.value,
                ForfeitCondition.NOT_ALLOWED.value,
                SocialContext.ALONE.value,
                1,      # cell_id
                42,     # effective seed (base 42 + rep 0)
            )
        }
        remaining = ExperimentRunner._filter_schedule(schedule, completed_keys)
        assert [cfg.cell_id for _, cfg, _ in remaining] == [2]

    def test_legacy_configs_with_no_cell_id_are_unaffected(self) -> None:
        """Pre-2026-09-08 designs: one season per (framing, forfeit) pair,
        cell_id unset on both sides of the key. Behaviour must not change."""
        cfg = _season_config(cell_id=None)
        schedule = [(0, cfg, 0)]
        completed_keys = {
            (
                Framing.HZ_1111.value,
                ForfeitCondition.NOT_ALLOWED.value,
                SocialContext.ALONE.value,
                None,
                42,
            )
        }
        assert ExperimentRunner._filter_schedule(schedule, completed_keys) == []

    def test_the_same_cell_across_repetitions_still_dedupes_correctly(self) -> None:
        """Within one cell, reps 0 and 1 get distinct effective seeds
        (42, 43) and only the completed one should drop out."""
        cfg = _season_config(cell_id=1)
        schedule = [(0, cfg, 0), (0, cfg, 1)]
        completed_keys = {
            (Framing.HZ_1111.value, ForfeitCondition.NOT_ALLOWED.value,
             SocialContext.ALONE.value, 1, 42)
        }
        remaining = ExperimentRunner._filter_schedule(schedule, completed_keys)
        assert [rep for _, _, rep in remaining] == [1]
