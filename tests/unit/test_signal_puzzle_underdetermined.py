"""Underdetermined turns: reachability primitive and query candidate actions.

Spec: docs/history/specs/2026-09-06-signal-puzzle-underdetermined-turns-design.md
"""

from __future__ import annotations

import dataclasses

import pytest

from squid_game.tasks.signal_game.puzzle import (
    SIGNAL_SPACE,
    Clue,
    PuzzleSpec,
    candidate_actions,
    cached_puzzle,
    enumerate_shape,
    exists_consistent,
    generate_puzzle,
    puzzle_rng,
)
from squid_game.tasks.signal_game.rules import ACTIONS
from squid_game.tasks.signal_game.signals import Signal


def _brute_consistent(shape, clues):
    """Every decision list of *shape* agreeing with *clues* (test oracle)."""
    for rule in enumerate_shape(shape):
        if all(rule.evaluate(c.signal) == c.action for c in clues):
            yield rule


class TestExistsConsistent:
    def test_single_clue_is_satisfiable(self) -> None:
        clues = [Clue(Signal(color="red", shape="star", number=3), "jump")]
        assert exists_consistent((1,), clues) is True

    def test_agrees_with_brute_force_on_random_clue_sets(self) -> None:
        rng = __import__("random").Random(7)
        for _ in range(40):
            shape = (1,)
            signals = rng.sample(SIGNAL_SPACE, 3)
            clues = [Clue(s, rng.choice(ACTIONS)) for s in signals]
            expected = any(True for _ in _brute_consistent(shape, clues))
            assert exists_consistent(shape, clues) is expected, clues

    def test_unsatisfiable_clue_set(self) -> None:
        # Shape (1,) can split the grid two ways at most; three clues that
        # demand three different actions cannot be served by one clause + else.
        clues = [
            Clue(Signal(color="red", shape="star", number=1), "jump"),
            Clue(Signal(color="blue", shape="circle", number=2), "stay"),
            Clue(Signal(color="green", shape="square", number=4), "go_left"),
        ]
        assert exists_consistent((1,), clues) is False

    def test_contradictory_clues_on_one_signal(self) -> None:
        sig = Signal(color="red", shape="star", number=3)
        assert exists_consistent((1,), [Clue(sig, "jump"), Clue(sig, "stay")]) is False


class TestCandidateActions:
    def test_unique_puzzle_has_exactly_one_candidate(self) -> None:
        spec = PuzzleSpec(turn=3, clauses=2, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=1)
        puzzle = generate_puzzle(puzzle_rng(11, 3), spec)
        cands = candidate_actions(puzzle.shape, puzzle.clues, puzzle.query)
        assert cands == (puzzle.correct_action,)

    def test_agrees_with_brute_force(self) -> None:
        spec = PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(5, 1), spec)
        shown = list(puzzle.clues)[:-1]          # drop one clue -> may split
        expected = tuple(
            a for a in ACTIONS
            if any(r.evaluate(puzzle.query) == a for r in _brute_consistent(puzzle.shape, shown))
        )
        assert candidate_actions(puzzle.shape, shown, puzzle.query) == expected

    def test_truth_action_is_always_a_candidate(self) -> None:
        spec = PuzzleSpec(turn=4, clauses=2, conjunctions=0, predicates=True,
                          overlap_query=True, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(23, 4), spec)
        for i in range(len(puzzle.clues)):
            shown = [c for j, c in enumerate(puzzle.clues) if j != i]
            assert puzzle.correct_action in candidate_actions(
                puzzle.shape, shown, puzzle.query
            )

    def test_returns_actions_in_canonical_order(self) -> None:
        spec = PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(5, 1), spec)
        cands = candidate_actions(puzzle.shape, list(puzzle.clues)[:1], puzzle.query)
        assert list(cands) == [a for a in ACTIONS if a in cands]


from squid_game.tasks.signal_game.puzzle import generate_underdetermined_puzzle

#: One rung from each of the two scheduled blocks, plus the extremes of
#: what block A and B can ask for.
_UD_SPECS = [
    PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
               overlap_query=False, extra_clues=2, underdetermined=True,
               n_candidate_actions=2),
    PuzzleSpec(turn=3, clauses=2, conjunctions=0, predicates=False,
               overlap_query=False, extra_clues=1, underdetermined=True,
               n_candidate_actions=2),
    PuzzleSpec(turn=5, clauses=3, conjunctions=0, predicates=True,
               overlap_query=True, extra_clues=0, underdetermined=True,
               n_candidate_actions=2),
    PuzzleSpec(turn=6, clauses=3, conjunctions=1, predicates=True,
               overlap_query=True, extra_clues=0, underdetermined=True,
               n_candidate_actions=2),
]


class TestGenerateUnderdetermined:
    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_query_splits_exactly_two_ways(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        cands = candidate_actions(puzzle.shape, puzzle.clues, puzzle.query)
        assert len(cands) == 2
        assert puzzle.candidate_actions == cands
        assert puzzle.n_candidate_actions == 2

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_truth_is_among_the_candidates(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        assert puzzle.correct_action in puzzle.candidate_actions

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_dropped_clue_was_load_bearing_and_is_not_shown(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        assert puzzle.dropped_clue is not None
        assert puzzle.dropped_clue.signal not in {c.signal for c in puzzle.clues}
        # Putting it back must restore a single answer.
        restored = list(puzzle.clues) + [puzzle.dropped_clue]
        assert len(candidate_actions(puzzle.shape, restored, puzzle.query)) == 1

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_every_shown_clue_is_truthful(self, spec: PuzzleSpec) -> None:
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        for clue in puzzle.clues:
            assert puzzle.rule.evaluate(clue.signal) == clue.action
        assert puzzle.query not in {c.signal for c in puzzle.clues}

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_padding_restores_the_base_puzzles_clue_count(
        self, spec: PuzzleSpec
    ) -> None:
        """One clue out, one clue in: the round shows what its base showed.

        There is no single "unique twin" to rebuild: the generator resamples a
        fresh base whenever no load-bearing drop splits the query
        ``n_candidate_actions`` ways, so ``generate_puzzle(puzzle_rng(42,
        turn), spec)`` is the FIRST base sampled, not the one this puzzle was
        carved from. The base's clue count is therefore recorded on the puzzle
        and compared against directly — an off-by-one pad, or a pad that never
        appends while ``clue_count_padded`` stays True, fails here.
        """
        puzzle = generate_underdetermined_puzzle(puzzle_rng(42, spec.turn), spec)
        assert puzzle.base_clue_count > 0
        if puzzle.clue_count_padded:
            assert len(puzzle.clues) == puzzle.base_clue_count
        else:
            assert len(puzzle.clues) == puzzle.base_clue_count - 1

    @pytest.mark.parametrize("spec", _UD_SPECS, ids=lambda s: f"turn{s.turn}")
    def test_determined_puzzle_reports_its_own_clue_count(
        self, spec: PuzzleSpec
    ) -> None:
        determined = dataclasses.replace(
            spec, underdetermined=False, n_candidate_actions=1
        )
        puzzle = generate_puzzle(puzzle_rng(42, spec.turn), determined)
        assert puzzle.base_clue_count == len(puzzle.clues)

    def test_unique_puzzle_reports_one_candidate(self) -> None:
        spec = PuzzleSpec(turn=5, clauses=3, conjunctions=0, predicates=True,
                          overlap_query=True, extra_clues=0)
        puzzle = generate_puzzle(puzzle_rng(42, 5), spec)
        assert puzzle.candidate_actions == (puzzle.correct_action,)
        assert puzzle.n_candidate_actions == 1
        assert puzzle.dropped_clue is None
        assert puzzle.clue_count_padded is False

    def test_minimal_clue_signals_are_recorded(self) -> None:
        spec = PuzzleSpec(turn=1, clauses=1, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=2)
        puzzle = generate_puzzle(puzzle_rng(42, 1), spec)
        assert len(puzzle.minimal_clue_signals) == puzzle.n_minimal_clues
        assert puzzle.minimal_clue_signals <= {c.signal for c in puzzle.clues}


class TestCachedPuzzleBranch:
    def test_spec_flag_separates_the_two_versions(self) -> None:
        unique = PuzzleSpec(turn=2, clauses=1, conjunctions=0, predicates=True,
                            overlap_query=False, extra_clues=1)
        under = PuzzleSpec(turn=2, clauses=1, conjunctions=0, predicates=True,
                           overlap_query=False, extra_clues=1,
                           underdetermined=True, n_candidate_actions=2)
        a = cached_puzzle(42, 2, unique)
        b = cached_puzzle(42, 2, under)
        assert a.n_candidate_actions == 1
        assert b.n_candidate_actions == 2
        assert cached_puzzle(42, 2, under) is b        # memoised

    def test_generation_is_deterministic(self) -> None:
        spec = PuzzleSpec(turn=3, clauses=2, conjunctions=0, predicates=False,
                          overlap_query=False, extra_clues=1,
                          underdetermined=True, n_candidate_actions=2)
        first = generate_underdetermined_puzzle(puzzle_rng(99, 3), spec)
        second = generate_underdetermined_puzzle(puzzle_rng(99, 3), spec)
        assert first.rule.description == second.rule.description
        assert first.query == second.query
        assert [str(c) for c in first.clues] == [str(c) for c in second.clues]


from pathlib import Path

import yaml

from squid_game.tasks.signal_game.puzzle_config import (
    UnderdeterminedConfig,
    load_signal_puzzle_config,
    underdetermined_turns,
)

_LADDER = [
    {"turn": t, "clauses": 1, "conjunctions": 0, "predicates": False,
     "overlap_query": False, "extra_clues": 0}
    for t in range(1, 11)
]


def _write_task_yaml(tmp_path: Path, underdetermined) -> Path:
    body = {"name": "signal_game", "puzzle_ladder": _LADDER}
    if underdetermined is not None:
        body["underdetermined"] = underdetermined
    (tmp_path / "signal_game.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")
    return tmp_path


class TestSchedule:
    def test_one_turn_per_block(self) -> None:
        cfg = UnderdeterminedConfig(blocks=[(1, 3), (4, 6)])
        turns = underdetermined_turns(42, cfg)
        assert len(turns) == 2
        assert 1 <= turns[0] <= 3
        assert 4 <= turns[1] <= 6

    def test_three_consecutive_seeds_cover_every_position(self) -> None:
        cfg = UnderdeterminedConfig(blocks=[(1, 3), (4, 6)])
        block_a = {underdetermined_turns(s, cfg)[0] for s in (42, 43, 44)}
        block_b = {underdetermined_turns(s, cfg)[1] for s in (42, 43, 44)}
        assert block_a == {1, 2, 3}
        assert block_b == {4, 5, 6}

    def test_blocks_are_offset_from_each_other(self) -> None:
        cfg = UnderdeterminedConfig(blocks=[(1, 3), (4, 6)])
        for seed in range(40, 52):
            a, b = underdetermined_turns(seed, cfg)
            assert (a - 1) != (b - 4), f"seed {seed}: both blocks at the same offset"

    def test_same_seed_is_stable(self) -> None:
        cfg = UnderdeterminedConfig(blocks=[(1, 3), (4, 6)])
        assert underdetermined_turns(42, cfg) == underdetermined_turns(42, cfg)

    def test_known_values_for_base_seed_42(self) -> None:
        cfg = UnderdeterminedConfig(blocks=[(1, 3), (4, 6)])
        assert underdetermined_turns(42, cfg) == (1, 5)
        assert underdetermined_turns(43, cfg) == (2, 6)
        assert underdetermined_turns(44, cfg) == (3, 4)


class TestUnderdeterminedConfigValidation:
    def test_packaged_yaml_has_the_block(self) -> None:
        cfg = load_signal_puzzle_config()
        assert cfg.underdetermined is not None
        assert cfg.underdetermined.blocks == ((1, 3), (4, 6))
        assert cfg.underdetermined.candidate_actions == 2

    def test_absent_block_is_none(self, tmp_path: Path) -> None:
        cfg = load_signal_puzzle_config(_write_task_yaml(tmp_path, None))
        assert cfg.underdetermined is None

    @pytest.mark.parametrize(
        "blocks",
        [
            [(3, 1)],            # descending
            [(1, 1)],            # length 1 -- no Latin square
            [(1, 3), (2, 5)],    # overlapping
            [(4, 6), (1, 3)],    # out of order
            [(1, 3), (9, 12)],   # past the ladder (10 rungs)
        ],
    )
    def test_bad_blocks_rejected(self, tmp_path: Path, blocks) -> None:
        with pytest.raises(ValueError):
            load_signal_puzzle_config(
                _write_task_yaml(tmp_path, {"blocks": [list(b) for b in blocks]})
            )

    def test_candidate_actions_bounds(self, tmp_path: Path) -> None:
        with pytest.raises(ValueError):
            load_signal_puzzle_config(
                _write_task_yaml(
                    tmp_path, {"blocks": [[1, 3]], "candidate_actions": 1}
                )
            )
