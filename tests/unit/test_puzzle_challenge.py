"""puzzle_challenge: shallow solvers, trap queries, profiles, rule grading.

Spec: docs/history/specs/2026-09-10-signal-game-effort-sensitive-difficulty-design.md
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from squid_game.models.config import PuzzleChallengeConfig, TaskConfig
from squid_game.models.enums import Difficulty
from squid_game.prompts import render
from squid_game.tasks.signal_game.puzzle import (
    CONDITION_BY_LABEL,
    GENERATOR_VERSION,
    SHALLOW_SOLVER_NAMES,
    Clue,
    Puzzle,
    PuzzleGenerationError,
    PuzzleRule,
    PuzzleSpec,
    cached_puzzle,
    generate_puzzle,
    generate_trap_puzzle,
    is_trap_query,
    is_unique,
    puzzle_id_for,
    puzzle_rng,
    shallow_actions,
    shallow_last_match,
    shallow_majority,
    shallow_nearest_neighbour,
    shallow_single_attribute,
)
from squid_game.tasks.signal_game.puzzle_config import (
    PuzzleProfile,
    load_signal_puzzle_config,
)
from squid_game.tasks.signal_game.module import ParsedSignalResponse, SignalGameModule
from squid_game.tasks.signal_game.signals import Signal

_LADDER = [
    {
        "turn": t,
        "clauses": 1,
        "conjunctions": 0,
        "predicates": False,
        "overlap_query": False,
        "extra_clues": 0,
    }
    for t in range(1, 11)
]


def _write_task_yaml(tmp_path: Path, profiles=None) -> Path:
    body = {"name": "signal_game", "puzzle_ladder": _LADDER}
    if profiles is not None:
        body["puzzle_profiles"] = profiles
    (tmp_path / "signal_game.yaml").write_text(yaml.safe_dump(body), encoding="utf-8")
    return tmp_path


def _hand_puzzle(rule: PuzzleRule, clue_signals, query: Signal) -> Puzzle:
    """A Puzzle built by hand for solver unit tests (no generator involved)."""
    return Puzzle(
        rule=rule,
        spec=PuzzleSpec(
            turn=1,
            clauses=len(rule.clauses),
            conjunctions=0,
            predicates=False,
            overlap_query=False,
            extra_clues=0,
        ),
        clues=tuple(Clue(s, rule.evaluate(s)) for s in clue_signals),
        query=query,
        n_minimal_clues=len(clue_signals),
    )


class TestShallowSolvers:
    def test_nearest_neighbour_copies_the_closest_clue(self) -> None:
        # Rule: if color == "red": stay; else: jump
        rule = PuzzleRule(
            clauses=((CONDITION_BY_LABEL['color == "red"'], "stay"),),
            else_action="jump",
        )
        query = Signal(color="red", shape="star", number=1)
        # One clue differs from the query in one attribute (shape) -> distance 1
        # and is red, so it says "stay". Two blue clues are further away.
        clues = [
            Signal(color="red", shape="circle", number=1),
            Signal(color="blue", shape="square", number=4),
            Signal(color="blue", shape="triangle", number=3),
        ]
        assert shallow_nearest_neighbour(_hand_puzzle(rule, clues, query)) == "stay"

    def test_majority_ignores_the_query(self) -> None:
        rule = PuzzleRule(
            clauses=((CONDITION_BY_LABEL['color == "red"'], "stay"),),
            else_action="jump",
        )
        query = Signal(color="red", shape="star", number=1)
        clues = [
            Signal(color="blue", shape="square", number=4),  # jump
            Signal(color="blue", shape="triangle", number=3),  # jump
            Signal(color="red", shape="circle", number=1),  # stay
        ]
        assert shallow_majority(_hand_puzzle(rule, clues, query)) == "jump"

    def test_last_match_reverses_clause_priority(self) -> None:
        # if number % 2 == 0: stay; elif color == "red": jump; else: go_left
        # A red even signal fires BOTH clauses; first-match says "stay",
        # last-match says "jump".
        rule = PuzzleRule(
            clauses=(
                (CONDITION_BY_LABEL["number % 2 == 0"], "stay"),
                (CONDITION_BY_LABEL['color == "red"'], "jump"),
            ),
            else_action="go_left",
        )
        query = Signal(color="red", shape="star", number=2)
        p = _hand_puzzle(rule, [Signal(color="blue", shape="star", number=1)], query)
        assert p.correct_action == "stay"
        assert shallow_last_match(p) == "jump"

    def test_single_attribute_is_deterministic(self) -> None:
        rule = PuzzleRule(
            clauses=((CONDITION_BY_LABEL['color == "red"'], "stay"),),
            else_action="jump",
        )
        query = Signal(color="red", shape="star", number=1)
        clues = [
            Signal(color="red", shape="circle", number=2),
            Signal(color="blue", shape="square", number=4),
        ]
        p = _hand_puzzle(rule, clues, query)
        first = shallow_single_attribute(p)
        assert first == shallow_single_attribute(p)  # no RNG anywhere
        assert first in ("stay", "jump", "go_left", "go_right")

    def test_shallow_actions_names_every_solver(self) -> None:
        rule = PuzzleRule(
            clauses=((CONDITION_BY_LABEL['color == "red"'], "stay"),),
            else_action="jump",
        )
        p = _hand_puzzle(
            rule,
            [Signal(color="red", shape="circle", number=2)],
            Signal(color="blue", shape="star", number=1),
        )
        assert set(shallow_actions(p)) == set(SHALLOW_SOLVER_NAMES)


class TestTrapPredicate:
    def test_a_trap_means_every_shallow_solver_is_wrong(self) -> None:
        spec = PuzzleSpec(
            turn=7,
            clauses=4,
            conjunctions=1,
            predicates=True,
            overlap_query=True,
            extra_clues=1,
        )
        seen_trap = seen_non_trap = False
        for seed in range(1000, 1040):
            p = generate_puzzle(puzzle_rng(seed, 7), spec)
            trap = is_trap_query(p)
            hits = [n for n, a in shallow_actions(p).items() if a == p.correct_action]
            if trap:
                seen_trap = True
                assert hits == [], f"trap puzzle solved by {hits}"
            else:
                seen_non_trap = True
                assert hits, "non-trap puzzle should be solved by at least one solver"
        assert seen_trap and seen_non_trap, "sample should contain both kinds"


class TestSpecExtensions:
    def test_new_fields_default_to_the_old_behaviour(self) -> None:
        spec = PuzzleSpec(
            turn=1,
            clauses=1,
            conjunctions=0,
            predicates=False,
            overlap_query=False,
            extra_clues=0,
        )
        assert spec.trap_query is False
        assert spec.profile == ""
        assert spec.generator_version == GENERATOR_VERSION

    def test_trap_needs_at_least_three_clauses(self) -> None:
        # With one or two clauses there is no priority to get wrong, so no
        # trap exists and the generator would burn its whole budget.
        with pytest.raises(ValueError, match="trap_query needs clauses >= 3"):
            PuzzleSpec(
                turn=1,
                clauses=2,
                conjunctions=0,
                predicates=True,
                overlap_query=True,
                extra_clues=0,
                trap_query=True,
            )

    def test_trap_and_underdetermined_are_mutually_exclusive(self) -> None:
        with pytest.raises(ValueError, match="trap_query and underdetermined"):
            PuzzleSpec(
                turn=1,
                clauses=3,
                conjunctions=0,
                predicates=True,
                overlap_query=True,
                extra_clues=0,
                trap_query=True,
                underdetermined=True,
                n_candidate_actions=2,
            )


class TestTrapGeneration:
    def test_generated_trap_puzzles_are_traps_and_still_unique(self) -> None:
        spec = PuzzleSpec(
            turn=3,
            clauses=4,
            conjunctions=1,
            predicates=True,
            overlap_query=True,
            extra_clues=1,
            trap_query=True,
            profile="hard",
        )
        for seed in range(2000, 2006):
            p = generate_trap_puzzle(puzzle_rng(seed, 3), spec)
            assert is_trap_query(p)
            assert is_unique(p.shape, p.clues, p.rule)
            assert p.trap_attempts >= 1
            # Every shown clue is truthful.
            assert all(p.rule.evaluate(c.signal) == c.action for c in p.clues)
            # The query is never one of the clues.
            assert all(c.signal != p.query for c in p.clues)

    def test_generation_is_deterministic_in_seed_and_spec(self) -> None:
        spec = PuzzleSpec(
            turn=3,
            clauses=4,
            conjunctions=1,
            predicates=True,
            overlap_query=True,
            extra_clues=1,
            trap_query=True,
            profile="hard",
        )
        a = generate_trap_puzzle(puzzle_rng(2000, 3), spec)
        b = generate_trap_puzzle(puzzle_rng(2000, 3), spec)
        assert a.rule.description == b.rule.description
        assert a.query == b.query
        assert [str(c) for c in a.clues] == [str(c) for c in b.clues]

    def test_exhausting_the_budget_raises_rather_than_falling_back(self) -> None:
        # An easy shape has no traps at all; the generator must NOT quietly
        # return an ordinary puzzle (spec §5.1).
        spec = PuzzleSpec(
            turn=1,
            clauses=3,
            conjunctions=0,
            predicates=False,
            overlap_query=False,
            extra_clues=0,
            trap_query=True,
        )
        with pytest.raises(PuzzleGenerationError):
            generate_trap_puzzle(puzzle_rng(7, 1), spec, attempts=3)

    def test_refuses_a_spec_that_is_not_marked_trap(self) -> None:
        spec = PuzzleSpec(
            turn=1,
            clauses=3,
            conjunctions=0,
            predicates=True,
            overlap_query=True,
            extra_clues=0,
        )
        with pytest.raises(ValueError, match="not marked trap_query"):
            generate_trap_puzzle(puzzle_rng(1, 1), spec)


class TestPuzzleId:
    def test_id_is_stable_and_separates_profiles(self) -> None:
        base = dict(
            turn=2,
            clauses=3,
            conjunctions=0,
            predicates=True,
            overlap_query=True,
            extra_clues=1,
        )
        a = PuzzleSpec(profile="medium", **base)
        b = PuzzleSpec(profile="other", **base)
        assert puzzle_id_for(42, a) == puzzle_id_for(42, a)
        assert puzzle_id_for(42, a) != puzzle_id_for(42, b)
        assert puzzle_id_for(42, a) != puzzle_id_for(43, a)
        assert len(puzzle_id_for(42, a)) == 12


class TestCachedPuzzleDispatch:
    def test_cached_puzzle_returns_a_trap_when_the_spec_asks(self) -> None:
        spec = PuzzleSpec(
            turn=4,
            clauses=4,
            conjunctions=1,
            predicates=True,
            overlap_query=True,
            extra_clues=1,
            trap_query=True,
            profile="hard",
        )
        assert is_trap_query(cached_puzzle(2100, 4, spec))

    def test_a_plain_spec_is_untouched_by_this_change(self) -> None:
        spec = PuzzleSpec(
            turn=4,
            clauses=2,
            conjunctions=0,
            predicates=True,
            overlap_query=True,
            extra_clues=0,
        )
        a = cached_puzzle(55, 4, spec)
        b = generate_puzzle(puzzle_rng(55, 4), spec)
        assert a.rule.description == b.rule.description
        assert a.query == b.query
        assert [str(c) for c in a.clues] == [str(c) for c in b.clues]


class TestPuzzleProfiles:
    def test_absent_block_is_none(self, tmp_path: Path) -> None:
        assert load_signal_puzzle_config(_write_task_yaml(tmp_path)).puzzle_profiles is None

    def test_block_is_loaded(self, tmp_path: Path) -> None:
        cfg = load_signal_puzzle_config(
            _write_task_yaml(
                tmp_path,
                {
                    "easy": {
                        "clauses": 1,
                        "conjunctions": 0,
                        "predicates": False,
                        "overlap_query": False,
                        "extra_clues": 2,
                        "trap_query": False,
                    },
                    "hard": {
                        "clauses": 4,
                        "conjunctions": 1,
                        "predicates": True,
                        "overlap_query": True,
                        "extra_clues": 1,
                        "trap_query": True,
                    },
                },
            )
        )
        assert set(cfg.puzzle_profiles) == {"easy", "hard"}
        assert cfg.puzzle_profiles["hard"].trap_query is True

    def test_trap_query_defaults_to_false(self) -> None:
        p = PuzzleProfile(
            clauses=3,
            conjunctions=0,
            predicates=True,
            overlap_query=True,
            extra_clues=0,
        )
        assert p.trap_query is False

    @pytest.mark.parametrize(
        ("payload", "message"),
        [
            (
                {
                    "clauses": 1,
                    "conjunctions": 2,
                    "predicates": True,
                    "overlap_query": False,
                    "extra_clues": 0,
                },
                "conjunctions",
            ),
            (
                {
                    "clauses": 1,
                    "conjunctions": 0,
                    "predicates": True,
                    "overlap_query": True,
                    "extra_clues": 0,
                },
                "overlap_query needs",
            ),
            (
                {
                    "clauses": 2,
                    "conjunctions": 0,
                    "predicates": True,
                    "overlap_query": True,
                    "extra_clues": 0,
                    "trap_query": True,
                },
                "trap_query needs clauses >= 3",
            ),
        ],
    )
    def test_invalid_profiles_are_rejected(self, payload, message) -> None:
        with pytest.raises(ValueError, match=message):
            PuzzleProfile(**payload)

    def test_to_spec_carries_the_turn_and_the_name(self) -> None:
        spec = PuzzleProfile(
            clauses=4,
            conjunctions=1,
            predicates=True,
            overlap_query=True,
            extra_clues=1,
            trap_query=True,
        ).to_spec(turn=5, name="hard")
        assert (spec.turn, spec.profile, spec.trap_query) == (5, "hard", True)
        assert spec.underdetermined is False


class TestShippedProfiles:
    def test_the_task_yaml_ships_three_profiles(self) -> None:
        cfg = load_signal_puzzle_config()  # packaged configs/tasks
        assert cfg.puzzle_profiles is not None
        assert set(cfg.puzzle_profiles) == {"easy", "medium", "hard"}
        assert cfg.puzzle_profiles["hard"].trap_query is True
        assert cfg.puzzle_profiles["easy"].trap_query is False
        assert cfg.puzzle_profiles["medium"].trap_query is False

    def test_the_ladder_is_untouched(self) -> None:
        cfg = load_signal_puzzle_config()
        assert cfg.total_turns == 10
        assert cfg.puzzle_ladder[0].clauses == 1
        assert cfg.puzzle_ladder[9].clauses == 6


class TestPuzzleChallengeConfig:
    def test_defaults_are_off(self) -> None:
        cfg = PuzzleChallengeConfig()
        assert cfg.enabled is False and cfg.rule_grading is False and cfg.schedule == []

    def test_profile_for_turn(self) -> None:
        cfg = PuzzleChallengeConfig(
            enabled=True,
            schedule=[{"turn": 1, "profile": "easy"}, {"turn": 2, "profile": "hard"}],
        )
        assert cfg.profile_for_turn(1) == "easy"
        assert cfg.profile_for_turn(2) == "hard"
        assert cfg.profile_for_turn(3) is None

    def test_schedule_id_is_stable_and_order_sensitive(self) -> None:
        a = PuzzleChallengeConfig(
            schedule=[{"turn": 1, "profile": "easy"}, {"turn": 2, "profile": "hard"}]
        )
        b = PuzzleChallengeConfig(
            schedule=[{"turn": 1, "profile": "hard"}, {"turn": 2, "profile": "easy"}]
        )
        assert a.schedule_id == PuzzleChallengeConfig(schedule=list(a.schedule)).schedule_id
        assert a.schedule_id != b.schedule_id
        assert len(a.schedule_id) == 8

    def test_task_config_defaults_to_none(self) -> None:
        assert TaskConfig(task_name="signal_game").puzzle_challenge is None


class TestBothGates:
    """A new task key must pass runner._TASK_OPTIONAL_FIELDS AND the engine's
    explicit initialize() kwargs; missing either one is a silent no-op."""

    def test_runner_forwards_the_key(self, tmp_path: Path) -> None:
        from squid_game.runner import load_config_from_yaml

        body = {
            "name": "gate-test",
            "seasons": [
                {
                    "framing": "hz_0000",
                    "forfeit_condition": "not_allowed",
                    "task_config": {
                        "task_name": "signal_game",
                        "signal_mode": "per_turn_puzzle",
                        "total_turns": 2,
                        "seed": 42,
                        "puzzle_challenge": {
                            "enabled": True,
                            "rule_grading": True,
                            "schedule": [
                                {"turn": 1, "profile": "easy"},
                                {"turn": 2, "profile": "medium"},
                            ],
                        },
                    },
                    "provider_config": {"provider": "gemini", "model": "x"},
                }
            ],
            "num_repetitions": 1,
            "output_dir": str(tmp_path / "out"),
            "use_unified_turn": True,
            "use_forfeit_layer": True,
            "use_split_forfeit_layer": True,
            "use_psuccess_probe": False,
        }
        path = tmp_path / "gate.yaml"
        path.write_text(yaml.safe_dump(body), encoding="utf-8")
        cfg = load_config_from_yaml(str(path))
        pc = cfg.seasons[0].task_config.puzzle_challenge
        assert pc is not None and pc.enabled is True and pc.rule_grading is True
        assert [e.profile for e in pc.schedule] == ["easy", "medium"]

    def test_engine_passes_it_to_the_task_module(self) -> None:
        import inspect

        from squid_game.core import engine as engine_mod

        src = inspect.getsource(engine_mod.GameEngine.run_season)
        assert "puzzle_challenge=task_cfg.puzzle_challenge" in src, (
            "GameEngine.run_season must forward puzzle_challenge to "
            "self._task.initialize(...), or the YAML key is a silent no-op"
        )


def _module(**kwargs):
    """A puzzle-mode module initialised with sensible defaults."""
    mod = SignalGameModule()
    base = dict(
        difficulty=Difficulty.MEDIUM,
        seed=42,
        signal_mode="per_turn_puzzle",
        total_turns=3,
    )
    base.update(kwargs)
    mod.initialize(**base)
    return mod


def _challenge(turns, rule_grading=False, profiles=("easy", "medium", "hard")):
    return PuzzleChallengeConfig(
        enabled=True,
        rule_grading=rule_grading,
        schedule=[
            {"turn": t, "profile": p} for t, p in zip(turns, profiles, strict=True)
        ],
    )


class TestChallengeValidation:
    def test_requires_puzzle_mode(self) -> None:
        with pytest.raises(ValueError, match="requires signal_mode"):
            _module(signal_mode="sequential", puzzle_challenge=_challenge([1, 2, 3]))

    def test_rejects_compress_puzzle_ladder(self) -> None:
        with pytest.raises(ValueError, match="compress_puzzle_ladder"):
            _module(compress_puzzle_ladder=True, puzzle_challenge=_challenge([1, 2, 3]))

    def test_rejects_underdetermined(self) -> None:
        with pytest.raises(ValueError, match="underdetermined"):
            _module(underdetermined=True, puzzle_challenge=_challenge([1, 2, 3]))

    def test_rejects_forced_wrong(self) -> None:
        with pytest.raises(ValueError, match="forced_wrong"):
            _module(forced_wrong=True, puzzle_challenge=_challenge([1, 2, 3]))

    def test_rejects_unknown_total_turns(self) -> None:
        with pytest.raises(ValueError, match="needs a known total_turns"):
            _module(total_turns=None, puzzle_challenge=_challenge([1, 2, 3]))

    @pytest.mark.parametrize(
        ("turns", "profiles"),
        [
            ((1, 2), ("easy", "medium")),  # round 3 missing
            ((1, 1, 2), ("easy", "medium", "hard")),  # round 1 twice, 3 missing
            ((1, 2, 4), ("easy", "medium", "hard")),  # round 4 out of season
        ],
    )
    def test_schedule_must_cover_every_round_exactly_once(self, turns, profiles) -> None:
        with pytest.raises(ValueError, match="schedule"):
            _module(puzzle_challenge=_challenge(turns, profiles=profiles))

    def test_rejects_an_unknown_profile_name(self) -> None:
        with pytest.raises(ValueError, match="impossible"):
            _module(
                puzzle_challenge=_challenge(
                    [1, 2, 3], profiles=("easy", "medium", "impossible")
                )
            )

    def test_rejects_a_task_yaml_without_profiles(self, tmp_path: Path) -> None:
        _write_task_yaml(tmp_path)  # ladder only, no puzzle_profiles
        with pytest.raises(ValueError, match="puzzle_profiles"):
            _module(puzzle_config_dir=tmp_path, puzzle_challenge=_challenge([1, 2, 3]))


class TestChallengeGeneration:
    def test_each_round_uses_its_profile(self) -> None:
        mod = _module(puzzle_challenge=_challenge([1, 2, 3]))
        mod.get_observation(1)
        assert mod._current_puzzle.spec.profile == "easy"
        assert mod._current_puzzle.spec.clauses == 1
        assert mod._current_puzzle.spec.trap_query is False
        mod.get_observation(3)
        assert mod._current_puzzle.spec.profile == "hard"
        assert mod._current_puzzle.spec.trap_query is True
        assert is_trap_query(mod._current_puzzle)

    def test_the_ladder_is_not_consulted(self) -> None:
        # Ladder rung 3 is 2 clauses; the schedule says "easy" (1 clause).
        mod = _module(
            puzzle_challenge=_challenge([1, 2, 3], profiles=("hard", "medium", "easy"))
        )
        mod.get_observation(3)
        assert mod._current_puzzle.spec.clauses == 1

    def test_metadata_carries_the_challenge_descriptors(self) -> None:
        mod = _module(puzzle_challenge=_challenge([1, 2, 3]))
        mod.get_observation(3)
        meta = mod._puzzle_metadata()
        assert meta["difficulty_profile"] == "hard"
        assert meta["trap_query"] is True
        assert meta["trap_attempts"] >= 1
        assert meta["generator_version"] == GENERATOR_VERSION
        assert len(meta["puzzle_id"]) == 12
        assert set(meta["shallow_actions"]) == set(SHALLOW_SOLVER_NAMES)
        assert meta["shallow_solvers_correct"] == []  # it is a trap
        assert len(meta["schedule_id"]) == 8

    def test_a_plain_puzzle_run_still_reports_ids_and_shallow_actions(self) -> None:
        mod = _module()  # no puzzle_challenge at all
        mod.get_observation(1)
        meta = mod._puzzle_metadata()
        assert meta["difficulty_profile"] is None
        assert meta["schedule_id"] is None
        assert meta["trap_query"] is False
        assert meta["trap_attempts"] == 0
        assert len(meta["puzzle_id"]) == 12
        assert set(meta["shallow_actions"]) == set(SHALLOW_SOLVER_NAMES)


class TestRuleGradingPrompt:
    def test_off_renders_byte_identically(self) -> None:
        a = render(
            "tasks/signal_game/system_rules_puzzle.j2",
            actions_str="a",
            colors_str="c",
            shapes_str="s",
            numbers_str="1",
        )
        b = render(
            "tasks/signal_game/system_rules_puzzle.j2",
            actions_str="a",
            colors_str="c",
            shapes_str="s",
            numbers_str="1",
            rule_grading=False,
        )
        assert a == b
        # 2026-09-10 supervisor-voice revision: the "===" footer is gone; the
        # off-render ends on the GUARANTEE line (plan L3).
        assert a.endswith(
            "GUARANTEE: All examples in a round follow that round's rule, and the "
            "examples always determine the rule and the correct action for the new "
            "signal.\n"
        )
        assert "===" not in a

    def test_on_states_the_grading_rule(self) -> None:
        text = render(
            "tasks/signal_game/system_rules_puzzle.j2",
            actions_str="a",
            colors_str="c",
            shapes_str="s",
            numbers_str="1",
            rule_grading=True,
        )
        assert "A round counts as correct only if both are true" in text
        assert "every example shown this round" in text
        assert "RULE GRADING:" in text
        assert text.endswith("next to it.\n")
        assert "===" not in text

    def test_the_module_passes_the_flag(self) -> None:
        graded = _module(puzzle_challenge=_challenge([1, 2, 3], rule_grading=True))
        plain = _module(puzzle_challenge=_challenge([1, 2, 3], rule_grading=False))
        assert "A round counts as correct only if" in graded.get_system_rules()
        assert "A round counts as correct only if" not in plain.get_system_rules()
        # A run with no challenge block at all is byte-identical to before.
        assert _module().get_system_rules() == plain.get_system_rules()


class TestRuleGradingVerdict:
    @staticmethod
    def _play(mod, rule_text: str | None):
        mod.get_observation(1)
        puzzle = mod._current_puzzle
        response = ParsedSignalResponse(
            action=puzzle.correct_action, rule_hypothesis=rule_text
        )
        return mod.score(response, None), puzzle

    def test_right_action_plus_a_faithful_rule_is_correct(self) -> None:
        mod = _module(puzzle_challenge=_challenge([1, 2, 3], rule_grading=True))
        mod.get_observation(1)
        truth_text = mod._current_puzzle.rule.description
        out = mod.score(
            ParsedSignalResponse(
                action=mod._current_puzzle.correct_action, rule_hypothesis=truth_text
            ),
            None,
        )
        assert out.success_factor == 1.0
        assert out.metadata["correct"] is True
        assert out.metadata["action_correct"] is True
        assert out.metadata["rule_reproduces_clues"] is True
        assert out.metadata["rule_graded"] is True
        assert out.metadata["actual_correct"] == out.metadata["correct"]

    def test_right_action_with_no_rule_is_incorrect_when_graded(self) -> None:
        mod = _module(puzzle_challenge=_challenge([1, 2, 3], rule_grading=True))
        out, _ = self._play(mod, None)
        assert out.success_factor == 0.0
        assert out.metadata["correct"] is False
        assert out.metadata["action_correct"] is True
        assert out.metadata["rule_reproduces_clues"] is None
        assert out.metadata["actual_correct"] is False

    def test_right_action_with_an_unparseable_rule_is_incorrect_when_graded(self) -> None:
        mod = _module(puzzle_challenge=_challenge([1, 2, 3], rule_grading=True))
        out, _ = self._play(mod, "no idea, probably something about colour")
        assert out.metadata["correct"] is False
        assert out.metadata["rule_reproduces_clues"] is None

    def test_grading_is_shape_blind(self) -> None:
        # A one-clause hypothesis on a one-clause round that reproduces the
        # clues passes even if the parser reports a different shape is
        # impossible here -- the point is the predicate never reads .shape.
        import inspect

        src = inspect.getsource(SignalGameModule._reproduces_clues)
        assert ".shape" not in src, (
            "_reproduces_clues must be shape-blind; the shape-strict reading "
            "stays in _consistent_with_clues, whose meaning recorded runs use"
        )

    def test_ungraded_challenge_keeps_the_old_verdict(self) -> None:
        mod = _module(puzzle_challenge=_challenge([1, 2, 3], rule_grading=False))
        out, _ = self._play(mod, None)
        assert out.success_factor == 1.0
        assert out.metadata["correct"] is True
        assert out.metadata["rule_graded"] is False
        assert out.metadata["action_correct"] is True

    def test_a_plain_puzzle_run_is_unaffected(self) -> None:
        mod = _module()
        out, _ = self._play(mod, None)
        assert out.success_factor == 1.0
        assert out.metadata["rule_graded"] is False
        assert out.metadata["action_correct"] is True
        assert out.metadata["actual_correct"] is True


class TestValidationCli:
    def test_report_measures_a_profile(self) -> None:
        from scripts.dev.validate_puzzle_challenge import profile_report

        rep = profile_report(
            "hard",
            PuzzleProfile(
                clauses=4,
                conjunctions=1,
                predicates=True,
                overlap_query=True,
                extra_clues=1,
                trap_query=True,
            ),
            seeds=range(5000, 5012),
            turn=3,
        )
        assert rep["n"] == 12
        assert rep["shallow_accuracy"]["nn"] == 0.0  # every one is a trap
        assert rep["trap_yield"] > 0.0
        assert 0.0 < rep["max_answer_share"] <= 1.0
        assert rep["p95_seconds"] >= 0.0

    def test_gates_pass_on_the_shipped_hard_profile(self) -> None:
        from scripts.dev.validate_puzzle_challenge import check_gates, profile_report

        profiles = load_signal_puzzle_config().puzzle_profiles
        rep = profile_report("hard", profiles["hard"], seeds=range(6000, 6060), turn=3)
        assert check_gates(rep) == []

    def test_gates_pass_on_the_shipped_easy_profile(self) -> None:
        from scripts.dev.validate_puzzle_challenge import check_gates, profile_report

        profiles = load_signal_puzzle_config().puzzle_profiles
        rep = profile_report("easy", profiles["easy"], seeds=range(6000, 6060), turn=1)
        assert check_gates(rep) == []

    def test_a_failing_gate_is_named(self) -> None:
        from scripts.dev.validate_puzzle_challenge import check_gates

        fake = {
            "name": "hard",
            "n": 100,
            "trap_query": True,
            "trap_yield": 0.01,
            "max_answer_share": 0.9,
            "clue_count_median": 6.0,
            "clue_count_median_plain": 6.0,
            "p95_seconds": 99.0,
            "max_shape_share": 0.9,
            "shallow_accuracy": {"nn": 0.0},
            "clauses": 4,
        }
        failed = check_gates(fake)
        assert "G1_trap_yield" in failed
        assert "G2_answer_balance" in failed
        assert "G4_generation_time" in failed
        assert "G6_shape_diversity" in failed


_PILOTS = [
    "signal_effort_pilot_a_gptoss120b.yaml",
    "signal_effort_pilot_b_gptoss120b.yaml",
    "signal_effort_pilot_a_gemma4.yaml",
    "signal_effort_pilot_b_gemma4.yaml",
    "signal_effort_pilot_a_nograde_gptoss120b.yaml",
]

_REPO = Path(__file__).resolve().parents[2]


class TestPilotConfigs:
    @pytest.mark.parametrize("name", _PILOTS)
    def test_pilot_loads_and_is_shaped_right(self, name: str) -> None:
        from squid_game.runner import load_config_from_yaml

        cfg = load_config_from_yaml(str(_REPO / "configs" / "experiment" / name))
        assert len(cfg.seasons) == 3, "one cell per reasoning_effort level"
        efforts = [s.provider_config.reasoning_effort for s in cfg.seasons]
        assert efforts == ["low", "medium", "high"]
        assert cfg.num_repetitions == 20, "even, so seed%2 schedules balance"
        for s in cfg.seasons:
            tc = s.task_config
            assert tc.signal_mode == "per_turn_puzzle"
            assert tc.total_turns == 6
            assert tc.forced_wrong is False and tc.underdetermined is False
            assert tc.compress_puzzle_ladder is False
            assert tc.puzzle_challenge is not None and tc.puzzle_challenge.enabled
            assert len(tc.puzzle_challenge.schedule) == 6
            assert s.forfeit_condition.value == "not_allowed"
        # No truncation: every session must reach round 6.
        assert cfg.lives.initial > 6

    def test_the_two_schedules_are_mirrored(self) -> None:
        from squid_game.runner import load_config_from_yaml

        a = load_config_from_yaml(
            str(_REPO / "configs/experiment/signal_effort_pilot_a_gptoss120b.yaml")
        )
        b = load_config_from_yaml(
            str(_REPO / "configs/experiment/signal_effort_pilot_b_gptoss120b.yaml")
        )
        pa = [e.profile for e in a.seasons[0].task_config.puzzle_challenge.schedule]
        pb = [e.profile for e in b.seasons[0].task_config.puzzle_challenge.schedule]
        assert pa != pb, "B must place the profiles at different rounds than A"
        assert sorted(pa) == sorted(pb), "same profile mix, different positions"

    def test_the_nograde_twin_differs_only_in_rule_grading(self) -> None:
        a = yaml.safe_load(
            (
                _REPO / "configs/experiment/signal_effort_pilot_a_gptoss120b.yaml"
            ).read_text()
        )
        n = yaml.safe_load(
            (
                _REPO
                / "configs/experiment/signal_effort_pilot_a_nograde_gptoss120b.yaml"
            ).read_text()
        )
        for body in (a, n):
            body.pop("name"), body.pop("description"), body.pop("output_dir")
            for s in body["seasons"]:
                s["task_config"]["puzzle_challenge"].pop("rule_grading")
        assert a == n


class TestEffortDoseResponse:
    @staticmethod
    def _row(
        effort,
        puzzle_id,
        correct,
        profile="hard",
        ri=100,
        cot_words=100,
        shallow_hits=(),
    ):
        return {
            "effort": effort,
            "turn_number": 1,
            "ri_task": ri,
            "thinking_text_task": " ".join(["w"] * cot_words),
            "task_metadata": {
                "correct": correct,
                "action_correct": correct,
                "rule_graded": True,
                "puzzle_id": puzzle_id,
                "difficulty_profile": profile,
                "trap_query": profile == "hard",
                "shallow_solvers_correct": list(shallow_hits),
            },
        }

    def test_gates_pass_on_a_synthetic_good_run(self) -> None:
        from scripts.analysis.effort_dose_response import evaluate_gates

        rows = []
        for i in range(20):
            # low 20% -> high 70%: a clear dose response with no floor/ceiling
            rows.append(self._row("low", f"p{i}", i < 4, ri=100, cot_words=50))
            rows.append(
                self._row(
                    "medium",
                    f"p{i}",
                    i < 9,
                    ri=200,
                    cot_words=100 + (200 if i < 9 else 0),
                    profile="medium",
                )
            )
            rows.append(self._row("high", f"p{i}", i < 14, ri=300, cot_words=300))
        gates = evaluate_gates(rows)
        assert gates["effort_gain"]["passed"] is True
        assert gates["no_floor_or_ceiling"]["passed"] is True
        assert gates["shallow_solvers"]["passed"] is True
        assert gates["effort_moves_tokens"]["passed"] is True

    def test_a_flat_run_fails_the_first_gate(self) -> None:
        from scripts.analysis.effort_dose_response import evaluate_gates

        rows = []
        for i in range(20):
            for effort, ri in (("low", 100), ("medium", 100), ("high", 100)):
                rows.append(self._row(effort, f"p{i}", i < 10, ri=ri))
        gates = evaluate_gates(rows)
        assert gates["effort_gain"]["passed"] is False
        assert gates["effort_moves_tokens"]["passed"] is False

    def test_a_shallow_solvable_run_fails_gate_four(self) -> None:
        from scripts.analysis.effort_dose_response import evaluate_gates

        rows = []
        for i in range(20):
            for effort in ("low", "medium", "high"):
                rows.append(self._row(effort, f"p{i}", True, shallow_hits=("nn",)))
        assert evaluate_gates(rows)["shallow_solvers"]["passed"] is False

    def test_effort_is_joined_through_cell_id(self, tmp_path: Path) -> None:
        """season_results.jsonl records cell_id, never the provider config."""
        from scripts.analysis.effort_dose_response import load_turns

        run = tmp_path / "run"
        run.mkdir()
        (run / "experiment_config.json").write_text(
            json.dumps(
                {
                    "seasons": [
                        {
                            "cell_id": 0,
                            "provider_config": {"reasoning_effort": "low"},
                        },
                        {
                            "cell_id": 2,
                            "provider_config": {"reasoning_effort": "high"},
                        },
                    ]
                }
            ),
            encoding="utf-8",
        )
        (run / "season_results.jsonl").write_text(
            "\n".join(
                [
                    json.dumps({"season_id": "aaa", "cell_id": 0}),
                    json.dumps({"season_id": "bbb", "cell_id": 2}),
                ]
            ),
            encoding="utf-8",
        )
        (run / "aaa_turns.jsonl").write_text(
            json.dumps({"season_id": "aaa", "task_metadata": {"correct": True}}),
            encoding="utf-8",
        )
        (run / "bbb_turns.jsonl").write_text(
            json.dumps({"season_id": "bbb", "task_metadata": {"correct": False}}),
            encoding="utf-8",
        )
        rows = load_turns([run])
        assert sorted(r["effort"] for r in rows) == ["high", "low"]
