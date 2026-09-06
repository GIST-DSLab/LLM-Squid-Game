"""puzzle_ladder v2 loading and validation (spec §6)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from squid_game.tasks.signal_game.puzzle import PuzzleSpec
from squid_game.tasks.signal_game.puzzle_config import (
    SignalPuzzleConfig,
    load_signal_puzzle_config,
)

_GOOD = [
    {"turn": 1, "clauses": 1, "conjunctions": 0, "predicates": False, "overlap_query": False, "extra_clues": 2},
    {"turn": 2, "clauses": 2, "conjunctions": 1, "predicates": True, "overlap_query": True, "extra_clues": 0},
]


def _write(tmp_path: Path, ladder) -> Path:
    (tmp_path / "signal_game.yaml").write_text(
        yaml.safe_dump({"name": "signal_game", "puzzle_ladder": ladder}), encoding="utf-8"
    )
    return tmp_path


class TestPackagedLadder:
    def test_ten_turns_monotone(self) -> None:
        cfg = load_signal_puzzle_config()
        assert cfg.total_turns == 10
        turns = [s.turn for s in cfg.puzzle_ladder]
        assert turns == list(range(1, 11))
        clauses = [s.clauses for s in cfg.puzzle_ladder]
        assert clauses == sorted(clauses)
        assert clauses[0] == 1 and clauses[-1] == 6
        conj = [s.conjunctions for s in cfg.puzzle_ladder]
        assert conj == sorted(conj) and conj[-1] == 3
        extra = [s.extra_clues for s in cfg.puzzle_ladder]
        assert extra == sorted(extra, reverse=True)

    def test_spec_for_turn_and_clamp(self) -> None:
        cfg = load_signal_puzzle_config()
        s = cfg.spec_for_turn(6)
        assert isinstance(s, PuzzleSpec)
        assert s == PuzzleSpec(6, 3, 1, True, True, 0)
        assert cfg.spec_for_turn(99) == cfg.spec_for_turn(10)


class TestValidation:
    def test_good(self, tmp_path: Path) -> None:
        cfg = load_signal_puzzle_config(_write(tmp_path, _GOOD))
        assert cfg.total_turns == 2
        assert cfg.spec_for_turn(2).conjunctions == 1

    def test_turns_must_be_consecutive_from_one(self, tmp_path: Path) -> None:
        bad = [dict(_GOOD[0], turn=1), dict(_GOOD[1], turn=3)]
        with pytest.raises(ValueError, match="consecutive"):
            load_signal_puzzle_config(_write(tmp_path, bad))

    def test_conjunctions_bounded(self, tmp_path: Path) -> None:
        bad = [dict(_GOOD[0], conjunctions=2)]
        with pytest.raises(ValueError):
            load_signal_puzzle_config(_write(tmp_path, bad))

    def test_overlap_needs_two_clauses(self, tmp_path: Path) -> None:
        bad = [dict(_GOOD[0], overlap_query=True)]
        with pytest.raises(ValueError):
            load_signal_puzzle_config(_write(tmp_path, bad))

    def test_missing_block(self, tmp_path: Path) -> None:
        (tmp_path / "signal_game.yaml").write_text("name: signal_game\n", encoding="utf-8")
        with pytest.raises(ValueError, match="puzzle_ladder"):
            load_signal_puzzle_config(tmp_path)

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_signal_puzzle_config(tmp_path / "nowhere")

    def test_top_level_typo_key_rejected(self) -> None:
        """``extra="forbid"``: a misspelled top-level key must not be silently dropped.

        ``load_signal_puzzle_config`` only ever passes ``{"puzzle_ladder": ...}``,
        so the YAML's other top-level keys (``name``, ``difficulties``, ...) stay
        ignored; this exercises ``model_validate`` directly.
        """
        with pytest.raises(ValueError, match="puzzle_ladders"):
            SignalPuzzleConfig.model_validate({"puzzle_ladder": _GOOD, "puzzle_ladders": _GOOD})

    def test_v1_keys_rejected(self, tmp_path: Path) -> None:
        old = [{"tier": 1, "turns": 6, "families": ["A"], "n_clues": 12, "h_lo": 5, "h_hi": 17}]
        with pytest.raises(ValueError):
            load_signal_puzzle_config(_write(tmp_path, old))
