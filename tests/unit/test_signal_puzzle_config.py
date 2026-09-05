"""puzzle_ladder loading for the per-turn puzzle mode (spec §6)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from squid_game.tasks.signal_game.puzzle import TierSpec
from squid_game.tasks.signal_game.puzzle_config import (
    SignalPuzzleConfig,
    load_signal_puzzle_config,
)

LADDER = [
    {"tier": 1, "turns": 2, "families": ["A"], "n_clues": 3, "h_lo": 1, "h_hi": 50},
    {"tier": 2, "turns": 2, "families": ["A", "D"], "n_clues": 2, "h_lo": 5, "h_hi": 200},
    {"tier": 3, "turns": 1, "families": ["B"], "n_clues": 4, "h_lo": 5, "h_hi": 500},
]


def _write(tmp_path: Path, ladder) -> Path:
    (tmp_path / "signal_game.yaml").write_text(
        yaml.safe_dump({"name": "signal_game", "puzzle_ladder": ladder}), encoding="utf-8"
    )
    return tmp_path


class TestLoad:
    def test_loads_and_expands(self, tmp_path: Path) -> None:
        cfg = load_signal_puzzle_config(_write(tmp_path, LADDER))
        assert cfg.total_turns == 5
        assert cfg.spec_for_turn(1) == TierSpec(1, ("A",), 3, 1, 50)
        assert cfg.spec_for_turn(3) == TierSpec(2, ("A", "D"), 2, 5, 200)
        assert cfg.spec_for_turn(5).tier == 3
        # past the ladder -> clamps to the last tier
        assert cfg.spec_for_turn(99).tier == 3

    def test_turn_zero_rejected(self, tmp_path: Path) -> None:
        cfg = load_signal_puzzle_config(_write(tmp_path, LADDER))
        with pytest.raises(ValueError):
            cfg.spec_for_turn(0)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_signal_puzzle_config(tmp_path)

    def test_missing_key(self, tmp_path: Path) -> None:
        (tmp_path / "signal_game.yaml").write_text("name: signal_game\n", encoding="utf-8")
        with pytest.raises(ValueError, match="puzzle_ladder"):
            load_signal_puzzle_config(tmp_path)

    def test_env_override_dir(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        _write(tmp_path, LADDER)
        monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(tmp_path))
        assert load_signal_puzzle_config().total_turns == 5


class TestValidation:
    def test_h_lo_above_h_hi_rejected(self) -> None:
        bad = [dict(LADDER[0], h_lo=60, h_hi=50)]
        with pytest.raises(ValueError, match="h_lo"):
            SignalPuzzleConfig.model_validate({"puzzle_ladder": bad})

    def test_tiers_must_increase(self) -> None:
        bad = [LADDER[1], LADDER[0]]
        with pytest.raises(ValueError, match="increasing"):
            SignalPuzzleConfig.model_validate({"puzzle_ladder": bad})

    def test_unknown_family_rejected(self) -> None:
        bad = [dict(LADDER[0], families=["E"])]
        with pytest.raises(ValueError):
            SignalPuzzleConfig.model_validate({"puzzle_ladder": bad})

    def test_empty_ladder_rejected(self) -> None:
        with pytest.raises(ValueError):
            SignalPuzzleConfig.model_validate({"puzzle_ladder": []})


class TestRepoYaml:
    def test_repo_ladder_covers_thirty_turns_in_five_tiers(self) -> None:
        cfg = load_signal_puzzle_config()
        assert cfg.total_turns == 30
        assert [s.tier for s in cfg.puzzle_ladder] == [1, 2, 3, 4, 5]
        assert [s.families for s in cfg.puzzle_ladder] == [
            ["A"], ["A", "D"], ["B"], ["C"], ["A", "B", "C", "D"]
        ]
        # Clue counts descend so that |H| rises across the ladder; 3 is the
        # floor because two clues never pin the query answer over the
        # four-family union (measured in Task 2). Written by
        # scripts/dev/calibrate_signal_puzzle_ladder.py (Task 5).
        assert [s.n_clues for s in cfg.puzzle_ladder] == [12, 10, 8, 4, 3]
