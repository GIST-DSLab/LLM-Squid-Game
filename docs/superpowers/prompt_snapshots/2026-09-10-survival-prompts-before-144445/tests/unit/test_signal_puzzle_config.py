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


class TestLadderCompression:
    """rung(i) = 1 + ceil((i-1) * (L-1) / (N-1)) -- spec 2026-09-10 §4.9.1.

    The reference ladder is never edited; a short season reads it at a
    coarser stride, anchored at BOTH ends so round 1 is still the
    ladder's warm-up rung and round N is still the hardest.
    """

    def test_identity_when_the_season_is_the_ladder_length(self) -> None:
        """N = L must reproduce today's ladder EXACTLY -- the whole
        back-compatibility argument rests on this one assertion."""
        cfg = load_signal_puzzle_config()
        for turn in range(1, cfg.total_turns + 1):
            assert cfg.compressed_rung(turn, cfg.total_turns) == turn
            assert cfg.compressed_spec_for_turn(turn, cfg.total_turns) == cfg.spec_for_turn(turn)

    @pytest.mark.parametrize(
        ("total_turns", "rungs"),
        [
            (6, [1, 3, 5, 7, 9, 10]),              # spec §4.9.2
            (8, [1, 3, 4, 5, 7, 8, 9, 10]),
            (10, list(range(1, 11))),
        ],
    )
    def test_mapping_table(self, total_turns, rungs) -> None:
        cfg = load_signal_puzzle_config()
        assert [cfg.compressed_rung(i, total_turns) for i in range(1, total_turns + 1)] == rungs

    def test_both_ends_are_anchored(self) -> None:
        """rung(1) = 1 and rung(N) = L, at every N.

        The second is why compression exists. The FIRST is why the
        formula is two-ended: with one life a genuine error on round 1
        opens a below-ceiling ransom whose DECLINE ends the session
        before its dominated round (spec §8 q6), so round 1 must stay
        the easiest rung there is.
        """
        cfg = load_signal_puzzle_config()
        for n in range(2, cfg.total_turns + 1):
            assert cfg.compressed_rung(1, n) == 1
            assert cfg.compressed_rung(n, n) == cfg.total_turns

    def test_round_one_keeps_the_warm_up_rung(self) -> None:
        """Explicitly: two spare clues and no predicates, at every N."""
        cfg = load_signal_puzzle_config()
        for n in (6, 8, 10):
            spec = cfg.compressed_spec_for_turn(1, n)
            assert (spec.clauses, spec.predicates, spec.extra_clues) == (1, False, 2)

    def test_strictly_increasing_so_no_rung_repeats(self) -> None:
        cfg = load_signal_puzzle_config()
        for n in range(2, cfg.total_turns + 1):
            seq = [cfg.compressed_rung(i, n) for i in range(1, n + 1)]
            assert seq == sorted(seq) and len(set(seq)) == len(seq)

    def test_emitted_turn_is_the_round_not_the_reference_rung(self) -> None:
        """``PuzzleSpec.turn`` keys ``cached_puzzle``; it must be the round
        the agent is playing, or two lengths would collide in the cache."""
        cfg = load_signal_puzzle_config()
        spec = cfg.compressed_spec_for_turn(3, 6)
        assert spec.turn == 3
        assert (spec.clauses, spec.conjunctions) == (3, 0)      # reference rung 5

    def test_six_round_ladder_in_full(self) -> None:
        """Spec §4.9.2's N = 6 table, verbatim."""
        cfg = load_signal_puzzle_config()
        got = [
            (s.clauses, s.conjunctions, s.predicates, s.overlap_query, s.extra_clues)
            for s in (cfg.compressed_spec_for_turn(i, 6) for i in range(1, 7))
        ]
        assert got == [
            (1, 0, False, False, 2),
            (2, 0, False, False, 1),
            (3, 0, True, True, 0),
            (4, 1, True, True, 0),
            (5, 2, True, True, 0),
            (6, 3, True, True, 0),
        ]

    def test_eight_round_ladder_in_full(self) -> None:
        """Spec §4.9.2's N = 8 table, verbatim -- the length an
        experimenter is most likely to reach for next."""
        cfg = load_signal_puzzle_config()
        got = [cfg.compressed_spec_for_turn(i, 8).clauses for i in range(1, 9)]
        assert got == [1, 2, 2, 3, 4, 4, 5, 6]

    def test_season_longer_than_the_ladder_is_refused(self) -> None:
        cfg = load_signal_puzzle_config()
        with pytest.raises(ValueError, match="longer than"):
            cfg.compressed_spec_for_turn(1, cfg.total_turns + 1)

    def test_one_round_season_is_refused(self) -> None:
        """The formula divides by N - 1 and its two anchors contradict
        each other at N = 1 (spec §4.9.1)."""
        cfg = load_signal_puzzle_config()
        with pytest.raises(ValueError, match="at least 2"):
            cfg.compressed_spec_for_turn(1, 1)
