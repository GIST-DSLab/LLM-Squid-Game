"""Underdetermined turns: reachability primitive and query candidate actions.

Spec: docs/history/specs/2026-09-06-signal-puzzle-underdetermined-turns-design.md
"""

from __future__ import annotations

import dataclasses
import textwrap

import pytest

from squid_game.core.engine import GameEngine
from squid_game.models.config import ProviderConfig, SeasonConfig, TaskConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext
from squid_game.runner import load_config_from_yaml
from squid_game.tasks.signal_game.module import (
    ParsedSignalResponse,
    SignalGameModule,
)
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

    def test_shipped_five_block_layout_has_two_schedules(self) -> None:
        """Width-2 blocks: the schedule is keyed on ``seed % 2``, not ``% 3``."""
        cfg = UnderdeterminedConfig(blocks=[(1, 2), (3, 4), (5, 6), (7, 8), (9, 10)])
        assert underdetermined_turns(42, cfg) == (1, 4, 5, 8, 9)
        assert underdetermined_turns(43, cfg) == (2, 3, 6, 7, 10)
        assert underdetermined_turns(44, cfg) == underdetermined_turns(42, cfg)
        # Every turn of the ladder is reachable across the two schedules.
        assert set(underdetermined_turns(42, cfg)) | set(underdetermined_turns(43, cfg)) == set(range(1, 11))


class TestUnderdeterminedConfigValidation:
    def test_packaged_yaml_has_the_block(self) -> None:
        cfg = load_signal_puzzle_config()
        assert cfg.underdetermined is not None
        assert cfg.underdetermined.blocks == ((1, 2), (3, 4), (5, 6), (7, 8), (9, 10))
        assert cfg.underdetermined.candidate_actions == 2

    def test_absent_block_is_none(self, tmp_path: Path) -> None:
        cfg = load_signal_puzzle_config(_write_task_yaml(tmp_path, None))
        assert cfg.underdetermined is None

    @pytest.mark.parametrize(
        ("blocks", "message"),
        [
            # Each case must be rejected *for its own reason* -- a bare
            # ``pytest.raises(ValueError)`` passed even when a descending
            # block was misdiagnosed as a one-turn block.
            ([(3, 1)], "is reversed"),                       # descending
            ([(1, 1)], "must span at least"),                # no Latin square
            ([(1, 3), (2, 5)], "ascending and disjoint"),    # overlapping
            ([(4, 6), (1, 3)], "ascending and disjoint"),    # out of order
            ([(1, 3), (9, 12)], "outside the"),              # past the ladder
        ],
    )
    def test_bad_blocks_rejected(self, tmp_path: Path, blocks, message) -> None:
        with pytest.raises(ValueError, match=message):
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


def _ctx(turn: int) -> TurnContext:
    """Same helper shape as tests/unit/test_signal_game_puzzle_mode.py."""
    return TurnContext(
        turn_number=turn, total_turns=10, season_id="s", cumulative_score=0.0,
        p_death=0.0, framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED, difficulty=Difficulty.MEDIUM,
    )


def _module(**kwargs) -> SignalGameModule:
    module = SignalGameModule()
    module.initialize(
        difficulty=Difficulty.MEDIUM,
        seed=kwargs.pop("seed", 42),
        signal_mode=kwargs.pop("signal_mode", "per_turn_puzzle"),
        total_turns=kwargs.pop("total_turns", 10),
        **kwargs,
    )
    return module


@pytest.fixture
def state() -> GameState:
    return GameState(season_id="s")


class TestModuleWiring:
    def test_off_by_default(self) -> None:
        module = _module()
        assert module._underdetermined_turns == ()

    def test_schedule_computed_from_seed(self) -> None:
        assert _module(seed=42, underdetermined=True)._underdetermined_turns == (1, 4, 5, 8, 9)
        assert _module(seed=43, underdetermined=True)._underdetermined_turns == (2, 3, 6, 7, 10)

    def test_rejected_outside_puzzle_mode(self) -> None:
        with pytest.raises(ValueError, match="per_turn_puzzle"):
            _module(signal_mode="sequential", underdetermined=True)

    def test_scheduled_turn_gets_an_underdetermined_puzzle(self, state: GameState) -> None:
        module = _module(seed=42, underdetermined=True)
        module.prepare(state, _ctx(1))                  # scheduled for seed 42
        assert module._current_puzzle.n_candidate_actions == 2
        module.prepare(state, _ctx(2))                  # not scheduled
        assert module._current_puzzle.n_candidate_actions == 1

    def test_observation_text_is_shaped_like_any_other_turn(self, state: GameState) -> None:
        module = _module(seed=42, underdetermined=True)
        text = module.prepare(state, _ctx(1)).prompt_section
        assert text.startswith("Turn 1. This round's rule has exactly this shape")
        for word in ("guess", "ambiguous", "cannot", "underdetermined"):
            assert word not in text.lower()


class _StopAfterInitialize(Exception):
    """Sentinel raised by the spy so ``run_season`` stops at step 1."""


class TestConfigAndRunnerWiring:
    """The YAML -> TaskConfig -> engine -> module path (spec §4.1)."""

    def test_task_config_defaults_to_off(self) -> None:
        assert TaskConfig(task_name="signal_game").underdetermined is False

    def test_task_config_accepts_true(self) -> None:
        assert TaskConfig(task_name="signal_game", underdetermined=True).underdetermined is True

    def test_loader_forwards_the_yaml_key(self, tmp_path: Path) -> None:
        """The silent failure mode: without the runner whitelist entry the
        key parses fine and is dropped, so the run is quietly determined."""
        cfg_path = tmp_path / "exp.yaml"
        cfg_path.write_text(
            textwrap.dedent("""
                name: t
                seasons:
                - framing: true_baseline
                  forfeit_condition: not_allowed
                  task_config:
                    task_name: signal_game
                    total_turns: 3
                    seed: 42
                    signal_mode: per_turn_puzzle
                    underdetermined: true
                  provider_config:
                    provider: openai
                    model: stub
                num_repetitions: 1
                output_dir: outputs/tmp
            """),
            encoding="utf-8",
        )
        cfg = load_config_from_yaml(str(cfg_path))
        assert cfg.seasons[0].task_config.underdetermined is True

    def test_loader_defaults_to_off_when_the_key_is_absent(self, tmp_path: Path) -> None:
        cfg_path = tmp_path / "exp.yaml"
        cfg_path.write_text(
            textwrap.dedent("""
                name: t
                seasons:
                - framing: true_baseline
                  forfeit_condition: not_allowed
                  task_config:
                    task_name: signal_game
                    total_turns: 3
                  provider_config:
                    provider: openai
                    model: stub
                num_repetitions: 1
                output_dir: outputs/tmp
            """),
            encoding="utf-8",
        )
        cfg = load_config_from_yaml(str(cfg_path))
        assert cfg.seasons[0].task_config.underdetermined is False

    @pytest.mark.parametrize("flag", [True, False])
    def test_engine_forwards_the_flag_to_task_initialize(self, flag: bool) -> None:
        recorded: dict = {}
        task = SignalGameModule()

        def _spy(**kwargs) -> None:
            recorded.update(kwargs)
            raise _StopAfterInitialize

        task.initialize = _spy  # type: ignore[method-assign]
        season = SeasonConfig(
            framing=Framing.TRUE_BASELINE,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            task_config=TaskConfig(
                task_name="signal_game",
                total_turns=10,
                seed=42,
                signal_mode="per_turn_puzzle",
                underdetermined=flag,
            ),
            provider_config=ProviderConfig(provider="openai", model="stub"),
        )
        engine = GameEngine(config=season, task=task, agent=None, provider=None)
        with pytest.raises(_StopAfterInitialize):
            engine.run_season()
        assert recorded["underdetermined"] is flag


class TestMetadata:
    def _prepared(self, state: GameState, seed: int, turn: int):
        module = _module(seed=seed, underdetermined=True)
        module.prepare(state, _ctx(turn))
        return module

    def test_prepare_metadata_on_an_underdetermined_turn(self, state: GameState) -> None:
        module = self._prepared(state, 42, 1)
        puzzle = module._current_puzzle
        meta = module._puzzle_metadata()
        assert meta["underdetermined"] is True
        assert meta["n_candidate_actions"] == 2
        assert sorted(meta["candidate_actions"]) == sorted(puzzle.candidate_actions)
        assert meta["p_guess"] == pytest.approx(0.5)
        assert meta["dropped_clue"] == str(puzzle.dropped_clue)
        assert isinstance(meta["clue_count_padded"], bool)

    def test_task_context_carries_the_same_keys(self, state: GameState) -> None:
        module = _module(seed=42, underdetermined=True)
        ctx = module.prepare(state, _ctx(1))
        assert ctx.metadata["underdetermined"] is True
        assert ctx.metadata["n_candidate_actions"] == 2
        assert ctx.metadata["p_guess"] == pytest.approx(0.5)

    def test_prepare_metadata_on_a_determined_turn(self, state: GameState) -> None:
        module = self._prepared(state, 42, 2)
        meta = module._puzzle_metadata()
        assert meta["underdetermined"] is False
        assert meta["n_candidate_actions"] == 1
        assert meta["p_guess"] == pytest.approx(1.0)
        assert meta["dropped_clue"] is None

    def test_score_metadata_carries_the_flag(self, state: GameState) -> None:
        module = self._prepared(state, 42, 1)
        puzzle = module._current_puzzle
        outcome = module.score(
            ParsedSignalResponse(
                action=puzzle.correct_action, rule_hypothesis=puzzle.rule.description
            ),
            state,
        )
        assert outcome.metadata["underdetermined"] is True
        assert outcome.metadata["n_candidate_actions"] == 2
        assert outcome.metadata["p_guess"] == pytest.approx(0.5)
        assert outcome.metadata["rule_consistent_with_clues"] is True

    def test_rule_consistent_with_clues_false_for_a_clue_violator(self, state: GameState) -> None:
        module = self._prepared(state, 42, 2)
        puzzle = module._current_puzzle
        # A constant rule of the right shape that contradicts the first clue.
        wrong = next(a for a in ACTIONS if a != puzzle.clues[0].action)
        colour = puzzle.clues[0].signal.color
        hypothesis = f'if color == "{colour}": {wrong}; else: {wrong}'
        outcome = module.score(
            ParsedSignalResponse(action=wrong, rule_hypothesis=hypothesis), state
        )
        # The shape must still match, or the ``False`` above would be the
        # shape guard firing rather than the clue check — a ladder edit that
        # changed this rung's shape would otherwise pass this test for the
        # wrong reason.
        assert outcome.metadata["rule_shape_match"] is True
        assert outcome.metadata["rule_consistent_with_clues"] is False

    def test_rule_consistent_is_none_when_unparsable(self, state: GameState) -> None:
        module = self._prepared(state, 42, 2)
        outcome = module.score(
            ParsedSignalResponse(action="stay", rule_hypothesis="still exploring"), state
        )
        assert outcome.metadata["rule_consistent_with_clues"] is None

    def test_determined_turn_agreement_invariant(self, state: GameState) -> None:
        """On a determined turn, consistent + right shape implies score 100."""
        module = self._prepared(state, 42, 2)
        puzzle = module._current_puzzle
        outcome = module.score(
            ParsedSignalResponse(
                action=puzzle.correct_action, rule_hypothesis=puzzle.rule.description
            ),
            state,
        )
        assert outcome.metadata["rule_consistent_with_clues"] is True
        assert outcome.metadata["rule_match_score"] == pytest.approx(100.0)
