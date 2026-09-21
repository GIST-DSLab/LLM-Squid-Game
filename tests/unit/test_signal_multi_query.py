"""Multi-query puzzle rounds: ``n_queries``, ``ACTIONS:``, all-or-nothing.

Plan: docs/history/plans/2026-09-17-team-wallet-task-candidates.md §2 B / §3.1.

The load-bearing claim of the whole feature is that a one-query round is
UNCHANGED -- same bytes, same spec digest, same metadata shape -- so the first
class here is the byte-identity pin and everything else is the new branch.
"""

from __future__ import annotations

import pytest

from squid_game.models.config import PuzzleChallengeConfig
from squid_game.models.enums import Difficulty
from squid_game.prompts import render
from squid_game.tasks.signal_game.module import ParsedSignalResponse, SignalGameModule
from squid_game.tasks.signal_game.puzzle import (
    SHALLOW_SOLVER_NAMES,
    PuzzleSpec,
    candidate_actions,
    generate_puzzle,
    generate_trap_puzzle,
    is_trap_query,
    is_unique,
    puzzle_id_for,
    puzzle_rng,
    shallow_actions,
    shallow_actions_per_query,
    shallow_solvers_correct,
)
from squid_game.tasks.signal_game.puzzle_config import PuzzleProfile

_OBS_KW = dict(
    turn_number=7,
    shape_line="if ___: ___; elif ___ and ___: ___; else: ___",
    clues=["red star with number 2 → stay", "blue circle with number 4 → jump"],
    actions_str="go_left, go_right, stay, jump",
)
_SYS_KW = dict(
    colors_str="red, blue, green, yellow",
    shapes_str="circle, triangle, square, star",
    numbers_str="1, 2, 3, 4",
    actions_str="go_left, go_right, stay, jump",
)


def _spec(n_queries: int = 1, **kwargs) -> PuzzleSpec:
    base = dict(
        turn=3,
        clauses=3,
        conjunctions=0,
        predicates=True,
        overlap_query=True,
        extra_clues=1,
    )
    base.update(kwargs)
    return PuzzleSpec(n_queries=n_queries, **base)


def _module(**kwargs) -> SignalGameModule:
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


def _challenge(profiles, rule_grading=False) -> PuzzleChallengeConfig:
    return PuzzleChallengeConfig(
        enabled=True,
        rule_grading=rule_grading,
        schedule=[
            {"turn": t, "profile": p} for t, p in enumerate(profiles, start=1)
        ],
    )


class TestByteIdentity:
    """One query renders, hashes and records exactly as it did before."""

    def test_the_observation_is_byte_identical_at_one_query(self) -> None:
        before = render(
            "tasks/signal_game/observation_puzzle.j2",
            query="green circle with number 3",
            **_OBS_KW,
        )
        after = render(
            "tasks/signal_game/observation_puzzle.j2",
            queries=["green circle with number 3"],
            **_OBS_KW,
        )
        assert after == before
        # And it is still the unnumbered NOW line the 2026-09-10 revision set.
        assert after.rstrip().endswith(
            "NOW: green circle with number 3.\nACTIONS: [go_left, go_right, stay, jump]"
        )
        assert "NOW 1:" not in after

    def test_the_system_rules_are_byte_identical_without_the_flag(self) -> None:
        before = render("tasks/signal_game/system_rules_puzzle.j2", **_SYS_KW)
        after = render(
            "tasks/signal_game/system_rules_puzzle.j2", multi_query=False, **_SYS_KW
        )
        assert after == before
        assert before.startswith("THE TASK:") and "ONE new signal" in before
        assert "ALL OR NOTHING" not in before

    def test_the_puzzle_id_of_a_one_query_spec_did_not_move(self) -> None:
        # The digest is what item-paired analyses key on, so adding a field
        # must not rename every item recorded before it existed.
        assert puzzle_id_for(42, _spec()) == "de425a72d408"

    def test_the_default_spec_asks_one_query(self) -> None:
        assert _spec().n_queries == 1
        puzzle = generate_puzzle(puzzle_rng(42, 3), _spec())
        assert puzzle.n_queries == 1
        assert puzzle.extra_queries == ()
        assert puzzle.queries == (puzzle.query,)
        assert puzzle.answers == (puzzle.correct_action,)
        assert puzzle.answer == puzzle.correct_action

    def test_shallow_actions_keeps_its_single_valued_shape(self) -> None:
        puzzle = generate_puzzle(puzzle_rng(42, 3), _spec())
        actions = shallow_actions(puzzle)
        assert set(actions) == set(SHALLOW_SOLVER_NAMES)
        assert all(isinstance(a, str) for a in actions.values())

    def test_the_metadata_of_a_one_query_round_keeps_its_shape(self) -> None:
        mod = _module()
        mod.get_observation(1)
        meta = mod._puzzle_metadata()
        assert meta["n_queries"] == 1
        assert all(isinstance(a, str) for a in meta["shallow_actions"].values())
        # The multi-only columns are absent, not None.
        assert "query_signals" not in meta
        assert "correct_actions" not in meta
        assert "per_query_correct" not in meta


class TestGeneration:
    def test_extra_queries_are_unshown_distinct_and_pinned(self) -> None:
        for seed in range(9000, 9010):
            puzzle = generate_puzzle(puzzle_rng(seed, 3), _spec(n_queries=3))
            shown = {c.signal for c in puzzle.clues}
            assert len(puzzle.queries) == 3
            assert len(set(puzzle.queries)) == 3
            assert all(q not in shown for q in puzzle.queries)
            assert is_unique(puzzle.shape, puzzle.clues, puzzle.rule)
            for q, a in zip(puzzle.queries, puzzle.answers, strict=True):
                assert candidate_actions(puzzle.shape, puzzle.clues, q) == (a,)

    def test_the_clue_set_is_the_one_query_clue_set(self) -> None:
        """Extra queries are asked ABOUT the same puzzle, not a harder one."""
        one = generate_puzzle(puzzle_rng(4242, 3), _spec())
        three = generate_puzzle(puzzle_rng(4242, 3), _spec(n_queries=3))
        assert three.rule.description == one.rule.description
        assert three.query == one.query
        assert [str(c) for c in three.clues] == [str(c) for c in one.clues]

    def test_overlap_query_holds_for_every_query(self) -> None:
        puzzle = generate_puzzle(puzzle_rng(9001, 3), _spec(n_queries=3))
        assert all(puzzle.rule.overlap_count(q) >= 2 for q in puzzle.queries)

    def test_the_puzzle_id_separates_query_counts(self) -> None:
        assert puzzle_id_for(42, _spec(n_queries=3)) != puzzle_id_for(42, _spec())


class TestSpecValidation:
    def test_n_queries_must_be_at_least_one(self) -> None:
        with pytest.raises(ValueError, match="n_queries must be >= 1"):
            _spec(n_queries=0)

    def test_n_queries_is_capped(self) -> None:
        with pytest.raises(ValueError, match="n_queries must be <= 8"):
            _spec(n_queries=9)

    def test_underdetermined_and_multi_query_are_exclusive(self) -> None:
        with pytest.raises(ValueError, match="mutually exclusive"):
            _spec(n_queries=3, underdetermined=True, n_candidate_actions=2)

    def test_the_profile_carries_n_queries_into_the_spec(self) -> None:
        profile = PuzzleProfile(
            clauses=3,
            conjunctions=0,
            predicates=True,
            overlap_query=True,
            extra_clues=1,
            n_queries=3,
        )
        assert profile.to_spec(turn=4, name="multi3").n_queries == 3

    def test_the_profile_default_is_one(self) -> None:
        profile = PuzzleProfile(
            clauses=1,
            conjunctions=0,
            predicates=False,
            overlap_query=False,
            extra_clues=2,
        )
        assert profile.n_queries == 1
        assert profile.to_spec(turn=1, name="easy").n_queries == 1

    def test_the_profile_rejects_an_absurd_count(self) -> None:
        with pytest.raises(ValueError, match="n_queries"):
            PuzzleProfile(
                clauses=3,
                conjunctions=0,
                predicates=True,
                overlap_query=True,
                extra_clues=1,
                n_queries=99,
            )

    def test_trap_query_still_needs_three_clauses(self) -> None:
        with pytest.raises(ValueError, match="trap_query needs clauses >= 3"):
            PuzzleProfile(
                clauses=2,
                conjunctions=0,
                predicates=True,
                overlap_query=True,
                extra_clues=0,
                trap_query=True,
                n_queries=3,
            )

    def test_the_shipped_profiles_load(self) -> None:
        from squid_game.tasks.signal_game.puzzle_config import (
            load_signal_puzzle_config,
        )

        profiles = load_signal_puzzle_config().puzzle_profiles or {}
        assert profiles["easy"].n_queries == 1
        assert profiles["medium"].n_queries == 1
        assert profiles["hard"].n_queries == 1
        assert profiles["multi3"].n_queries == 3
        assert profiles["multi3"].trap_query is False
        assert profiles["multi3_trap"].n_queries == 3
        assert profiles["multi3_trap"].trap_query is True


class TestShallowSolversPerQuery:
    def test_every_solver_answers_every_query(self) -> None:
        puzzle = generate_puzzle(puzzle_rng(9002, 3), _spec(n_queries=3))
        per_query = shallow_actions_per_query(puzzle)
        assert set(per_query) == set(SHALLOW_SOLVER_NAMES)
        assert all(len(v) == 3 for v in per_query.values())
        # The first entry is what the single-valued helper reports.
        assert {k: v[0] for k, v in per_query.items()} == shallow_actions(puzzle)

    def test_majority_is_query_independent(self) -> None:
        puzzle = generate_puzzle(puzzle_rng(9003, 3), _spec(n_queries=3))
        answers = shallow_actions_per_query(puzzle)["majority"]
        assert len(set(answers)) == 1

    def test_correctness_is_all_or_nothing(self) -> None:
        """A solver right on two of three queries has lost the round."""
        seen_partial = False
        for seed in range(9000, 9040):
            puzzle = generate_puzzle(puzzle_rng(seed, 3), _spec(n_queries=3))
            per_query = shallow_actions_per_query(puzzle)
            hits = set(shallow_solvers_correct(puzzle))
            for solver, actions in per_query.items():
                right = sum(a == t for a, t in zip(actions, puzzle.answers, strict=True))
                assert (solver in hits) == (right == 3)
                seen_partial = seen_partial or 0 < right < 3
        assert seen_partial, "no partially-correct solver in 40 seeds; test is vacuous"

    def test_the_trap_filter_applies_per_query(self) -> None:
        for seed in range(9000, 9006):
            puzzle = generate_trap_puzzle(
                puzzle_rng(seed, 3), _spec(n_queries=3, clauses=4, conjunctions=1, trap_query=True)
            )
            assert is_trap_query(puzzle)
            assert shallow_solvers_correct(puzzle) == ()
            # Every solver is wrong on at least one query -- which is weaker
            # than being wrong on all of them, and is exactly the claim.
            per_query = shallow_actions_per_query(puzzle)
            for actions in per_query.values():
                assert any(
                    a != t for a, t in zip(actions, puzzle.answers, strict=True)
                )

    def test_a_trap_puzzle_is_still_a_puzzle(self) -> None:
        puzzle = generate_trap_puzzle(
            puzzle_rng(9000, 3), _spec(n_queries=3, clauses=4, conjunctions=1, trap_query=True)
        )
        assert is_unique(puzzle.shape, puzzle.clues, puzzle.rule)
        assert puzzle.trap_attempts >= 1
        assert len(set(puzzle.queries)) == 3


class TestParsing:
    def test_the_actions_line_is_read_in_order(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        parsed = mod.parse_response("RULE: if ___: stay\nACTIONS: stay, jump, go_left")
        assert parsed.actions == ("stay", "jump", "go_left")
        assert parsed.action == "stay"
        assert parsed.rule_hypothesis == "if ___: stay"

    def test_the_last_matching_line_wins(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        parsed = mod.parse_response(
            "ACTIONS: jump, jump, jump\nwait, reconsidering\nACTIONS: stay, jump, stay"
        )
        assert parsed.actions == ("stay", "jump", "stay")

    def test_case_and_spacing_are_tolerated(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        parsed = mod.parse_response("actions:  STAY ,jump ,  Go_Left  ")
        assert parsed.actions == ("stay", "jump", "go_left")

    def test_the_singular_label_is_accepted(self) -> None:
        """Live smoke, 2026-09-21: every leader wrote ``ACTION:``.

        The label carries nothing the grading needs -- the order does,
        and the order is in the token sequence -- so rejecting it cost
        two seasons to ``format_error`` and bought nothing.
        """
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        assert mod.parse_response("ACTION: jump, stay, jump").actions == (
            "jump",
            "stay",
            "jump",
        )

    def test_whitespace_alone_separates(self) -> None:
        """gemma4 wrote the list without commas."""
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        assert mod.parse_response("ACTION: stay stay jump").actions == (
            "stay",
            "stay",
            "jump",
        )

    def test_commas_and_whitespace_mix_freely(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        assert mod.parse_response("ACTIONS: go_left,jump ,go_left").actions == (
            "go_left",
            "jump",
            "go_left",
        )

    def test_the_menu_line_is_still_refused_under_the_wider_grammar(
        self,
    ) -> None:
        """The brackets ride along on the first and last tokens.

        Widening the SEPARATORS could have let the observation's own menu
        line parse as an answer; the item check is what stops it, and it
        is checked here on the literal line rather than only through the
        rendered observation.
        """
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        assert mod.parse_response(
            "ACTIONS: [go_left, go_right, stay, jump]"
        ).actions == ()

    def test_the_menu_line_of_the_observation_is_not_an_answer(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        observation = mod.get_observation(1)
        assert "ACTIONS: [" in observation
        assert mod.parse_response(observation).actions == ()

    def test_an_unknown_token_rejects_the_whole_line(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        assert mod.parse_response("ACTIONS: stay, sideways, jump").actions == ()

    def test_a_single_query_round_does_not_take_the_plural_branch(self) -> None:
        mod = _module()
        mod.get_observation(1)
        parsed = mod.parse_response("ACTION: jump")
        assert parsed.actions == ("jump",)
        assert parsed.extra_actions == ()

    def test_a_singular_answer_is_a_wrong_answer_not_an_unreadable_one(
        self,
    ) -> None:
        """One action for three queries parses, and is scored 0.

        Flipped 2026-09-21 (T4 fix 4) after the second live smoke: the
        two-item minimum made ``ACTION: go_right`` on a three-query round
        unreadable, so the decision-first retry contract re-asked four
        times and ended the season. The agent DID say what it wanted to
        do; it said too little, which is a wrong answer. ``score`` grades
        it 0 with ``parse_failed`` false, because something was given.
        """
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        parsed = mod.parse_response("RULE: if red: stay\nACTION: go_right")
        assert parsed.actions == ("go_right",)
        assert parsed.action == "go_right"

        outcome = mod.score(parsed, state=None)
        assert outcome.success_factor == 0.0
        assert outcome.metadata["correct"] is False
        assert outcome.metadata["action_correct"] is False
        # Not a parse failure: the distinction is what tells the turn
        # manager to score the round instead of re-asking for it.
        assert outcome.metadata["parse_failed"] is False
        assert outcome.metadata["n_queries"] == 3
        assert outcome.metadata["per_query_correct"] == [False, False, False]

    def test_too_many_actions_is_also_a_wrong_answer(self) -> None:
        """The count rule is symmetric: four for three is graded, not re-asked."""
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        parsed = mod.parse_response("ACTIONS: stay, stay, stay, stay")
        assert len(parsed.actions) == 4
        outcome = mod.score(parsed, state=None)
        assert outcome.success_factor == 0.0
        assert outcome.metadata["parse_failed"] is False

    def test_the_alias_still_reads_the_first_action(self) -> None:
        parsed = ParsedSignalResponse(action="stay", extra_actions=("jump",))
        assert parsed.actions == ("stay", "jump")
        assert parsed.actions[0] == parsed.action
        assert ParsedSignalResponse(action=None).actions == ()


class TestScoring:
    def _round(self, answer_line: str, profile: str = "multi3"):
        mod = _module(puzzle_challenge=_challenge([profile, "easy", "easy"]))
        mod.get_observation(1)
        truth = mod._current_puzzle.answers
        parsed = mod.parse_response(answer_line.format(*truth) if "{" in answer_line else answer_line)
        return mod, mod.score(parsed, state=None), truth

    def test_every_query_right_scores_one(self) -> None:
        _, outcome, truth = self._round("ACTIONS: {}, {}, {}")
        assert outcome.success_factor == 1.0
        assert outcome.metadata["correct"] is True
        # The history block reads this key, so it names the WHOLE answer.
        assert outcome.metadata["action"] == ", ".join(truth)
        assert outcome.metadata["per_query_correct"] == [True, True, True]
        assert outcome.metadata["n_queries"] == 3
        assert outcome.metadata["correct_actions"] == list(truth)

    def test_one_query_wrong_scores_zero(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        truth = mod._current_puzzle.answers
        wrong = next(a for a in ("go_left", "go_right", "stay", "jump") if a != truth[2])
        parsed = mod.parse_response(f"ACTIONS: {truth[0]}, {truth[1]}, {wrong}")
        outcome = mod.score(parsed, state=None)
        assert outcome.success_factor == 0.0
        assert outcome.metadata["correct"] is False
        assert outcome.metadata["per_query_correct"] == [True, True, False]
        assert outcome.metadata["action_correct"] is False

    def test_a_short_list_is_not_a_win(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        truth = mod._current_puzzle.answers
        outcome = mod.score(
            mod.parse_response(f"ACTIONS: {truth[0]}, {truth[1]}"), state=None
        )
        assert outcome.success_factor == 0.0
        assert outcome.metadata["per_query_correct"] == [True, True, False]

    def test_a_parse_failure_is_recorded_and_scores_zero(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        outcome = mod.score(mod.parse_response("I am not sure."), state=None)
        assert outcome.success_factor == 0.0
        assert outcome.metadata["parse_failed"] is True
        assert outcome.metadata["action"] is None

    def test_a_single_query_round_still_scores_the_old_way(self) -> None:
        mod = _module()
        mod.get_observation(1)
        truth = mod._current_puzzle.correct_action
        outcome = mod.score(mod.parse_response(f"ACTION: {truth}"), state=None)
        assert outcome.success_factor == 1.0
        assert outcome.metadata["parse_failed"] is False
        assert outcome.metadata["n_queries"] == 1
        assert outcome.metadata["per_query_correct"] == [True]

    def test_the_shallow_column_is_per_query_on_a_multi_round(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        outcome = mod.score(mod.parse_response("ACTIONS: stay, stay, stay"), state=None)
        shallow = outcome.metadata["shallow_actions"]
        assert set(shallow) == set(SHALLOW_SOLVER_NAMES)
        assert all(len(v) == 3 for v in shallow.values())
        assert isinstance(outcome.metadata["shallow_solvers_correct"], list)


class TestPrompt:
    def test_the_round_shows_one_numbered_now_line_per_query(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        observation = mod.get_observation(1)
        assert observation.count("NOW ") == 3
        for i, query in enumerate(mod._current_puzzle.queries, start=1):
            assert f"NOW {i}: {query}." in observation

    def test_the_answer_format_states_the_actions_line(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3", "easy", "easy"]))
        mod.get_observation(1)
        block = mod.get_response_format_override()
        assert block is not None
        assert "ACTIONS: <3 actions" in block
        assert "in the order shown" in block
        assert block.startswith("Exactly two lines")

    def test_a_single_query_round_has_no_override(self) -> None:
        mod = _module()
        mod.get_observation(1)
        assert mod.get_response_format_override() is None

    def test_the_season_rules_say_one_or_more_only_when_scheduled(self) -> None:
        plain = _module(puzzle_challenge=_challenge(["easy", "medium", "hard"]))
        assert "ONE new signal" in plain.get_system_rules()
        assert "ALL OR NOTHING" not in plain.get_system_rules()

        multi = _module(puzzle_challenge=_challenge(["easy", "multi3", "hard"]))
        rules = multi.get_system_rules()
        assert "ONE OR MORE new signals" in rules
        assert "ALL OR NOTHING" in rules

    def test_the_prompt_never_names_the_machinery(self) -> None:
        mod = _module(puzzle_challenge=_challenge(["multi3_trap", "easy", "easy"]))
        text = mod.get_observation(1) + mod.get_system_rules()
        text += mod.get_response_format_override() or ""
        for word in ("trap", "shallow", "n_queries", "profile", "solver"):
            assert word not in text.lower()
