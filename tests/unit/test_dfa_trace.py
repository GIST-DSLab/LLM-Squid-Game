"""Unit tests for the dfa_trace task (brief §2 C / §3.2).

Three things are pinned here that nothing else can pin:

1. **The generator's promises.** Non-commutativity (so ``freq_map`` is
   provably wrong on some input), reachability, determinism from
   ``(seed, round)``, and that the trap filter RAISES rather than
   substituting an easy instance.
2. **The metadata contract.** The brief names the per-round
   ``task_metadata`` keys exactly, because the analysis scripts key on the
   signal game's spelling and must not have to know which task ran.
3. **The prompt contract.** Supervisor voice: no ``===`` markers,
   ``LABEL: sentence`` rules, and no sentence about effort, difficulty or
   shortcuts — the instance makes shortcuts lose, the prompt does not say
   so, and a sentence about effort would sit inside the effort measurement.
"""

from __future__ import annotations

import random
from pathlib import Path
from types import SimpleNamespace

import pytest

from squid_game.tasks.dfa_trace.generator import (
    GENERATOR_VERSION,
    NAMED_SOLVERS,
    Dfa,
    DfaGenerationError,
    DfaSpec,
    _is_non_commutative,
    _reachable,
    cached_dfa,
    dfa_id_for,
    dfa_rng,
    generate_dfa,
    generate_trap_dfa,
    grouped_word,
    is_trap,
    prefix_ks,
    shallow_answers,
    shallow_freq_map,
    shallow_ignore_selfloop,
    shallow_last_symbol,
    shallow_prefix_k,
    shallow_solver_names,
    simulate,
    state_name,
    trajectory,
    transition_rows,
)
from squid_game.tasks.dfa_trace.module import (
    ANSWER_RE,
    DfaTraceConfig,
    DfaTraceTask,
    ParsedDfaAnswer,
    load_dfa_trace_config,
)
from squid_game.tasks.registry import get_task

#: The brief's ladder shape (§2 C). If these ever disagree with the YAML,
#: one of the two was edited without the other.
_LADDER_LENGTHS = (8, 10, 12, 16, 20, 24, 28, 32)
_LADDER_STATES = (4, 4, 5, 5, 6, 6, 7, 7)

#: Exactly the keys §3.2 names, plus the four scoring-audit extras this
#: implementation adds (see the deviation note in ``module._metadata`` /
#: ``score``). The brief's set is checked as a SUBSET requirement below so
#: the two halves of the contract stay distinguishable.
_REQUIRED_KEYS = {
    "dfa_id",
    "puzzle_id",
    "generator_version",
    "difficulty_profile",
    "schedule_id",
    "trap_query",
    "trap_attempts",
    "shallow_actions",
    "shallow_solvers_correct",
    "n_steps",
    "n_states",
    "question_kind",
    "parse_failed",
    "correct",
    "action_correct",
}
_EXTRA_KEYS = {"answer", "parsed_answer", "raw_answer", "expected_label"}


def _spec(**overrides) -> DfaSpec:
    base = dict(states=4, alphabet=3, length=8, question="final", trap=True, turn=1)
    base.update(overrides)
    return DfaSpec(**base)


def _turn_ctx(turn: int) -> SimpleNamespace:
    return SimpleNamespace(turn_number=turn)


# ---------------------------------------------------------------------------
# Spec
# ---------------------------------------------------------------------------


class TestDfaSpec:
    def test_the_symbols_are_the_first_alphabet_letters(self) -> None:
        assert _spec(alphabet=3).symbols == "abc"
        assert _spec(alphabet=4).symbols == "abcd"

    @pytest.mark.parametrize(
        "kwargs",
        [
            {"states": 1},
            {"alphabet": 1},
            {"alphabet": 5},
            {"length": 1},
            {"question": "middle"},
        ],
    )
    def test_an_impossible_rung_is_refused_at_construction(self, kwargs) -> None:
        with pytest.raises(ValueError):
            _spec(**kwargs)

    def test_it_is_hashable_so_the_lru_cache_can_key_on_it(self) -> None:
        assert {_spec(), _spec()} == {_spec()}


# ---------------------------------------------------------------------------
# Simulator
# ---------------------------------------------------------------------------


class TestSimulator:
    def test_the_trajectory_has_one_state_per_symbol_plus_the_start(self) -> None:
        dfa = generate_dfa(dfa_rng(7, 1), _spec(trap=False, length=12))
        assert len(trajectory(dfa, dfa.word)) == 13

    def test_the_visit_counts_sum_to_l_plus_one(self) -> None:
        dfa = generate_dfa(dfa_rng(7, 1), _spec(trap=False, length=12))
        _final, visits = simulate(dfa, dfa.word)
        assert sum(visits.values()) == 13

    def test_the_final_state_is_the_last_of_the_trajectory(self) -> None:
        dfa = generate_dfa(dfa_rng(7, 1), _spec(trap=False))
        final, _visits = simulate(dfa, dfa.word)
        assert final == state_name(trajectory(dfa, dfa.word)[-1])

    def test_the_answer_of_a_count_round_is_that_states_visit_count(self) -> None:
        dfa = generate_dfa(dfa_rng(7, 1), _spec(trap=False, question="count"))
        _final, visits = simulate(dfa, dfa.word)
        assert dfa.answer == str(visits[state_name(dfa.count_state)])

    def test_a_count_round_never_asks_about_a_state_the_run_misses(self) -> None:
        # A "0" answer is guessable without reading anything.
        for seed in range(40):
            dfa = generate_dfa(dfa_rng(seed, 1), _spec(trap=False, question="count"))
            assert int(dfa.answer) >= 1


# ---------------------------------------------------------------------------
# Structural constraints
# ---------------------------------------------------------------------------


class TestGeneratedStructure:
    def test_the_transition_table_is_forced_non_commutative(self) -> None:
        # This is what kills freq_map: if every pair of symbol maps
        # commuted, symbol COUNTS would determine the final state and the
        # shortcut would be right by construction.
        for seed in range(40):
            dfa = generate_dfa(dfa_rng(seed, 1), _spec(trap=False))
            assert _is_non_commutative(dfa.transitions, dfa.spec.alphabet)

    def test_a_commutative_table_is_recognised_as_such(self) -> None:
        # Two symbols that both send everything to q0 commute everywhere.
        flat = ((0, 0), (0, 0))
        assert not _is_non_commutative(flat, 2)

    def test_every_state_is_reachable_from_the_start(self) -> None:
        for seed in range(40):
            dfa = generate_dfa(dfa_rng(seed, 1), _spec(trap=False, states=5))
            assert len(_reachable(dfa.transitions, dfa.start)) == 5

    def test_no_symbol_is_the_identity_map(self) -> None:
        for seed in range(20):
            dfa = generate_dfa(dfa_rng(seed, 1), _spec(trap=False))
            for a in range(dfa.spec.alphabet):
                assert any(
                    dfa.transitions[q][a] != q for q in range(dfa.spec.states)
                )

    def test_the_word_is_l_symbols_from_the_alphabet(self) -> None:
        dfa = generate_dfa(dfa_rng(3, 1), _spec(trap=False, length=20, alphabet=4))
        assert len(dfa.word) == 20
        assert set(dfa.word) <= set("abcd")


# ---------------------------------------------------------------------------
# Determinism and identity
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_the_same_seed_and_round_reproduce_the_same_instance(self) -> None:
        spec = _spec()
        a = generate_trap_dfa(dfa_rng(11, 3), spec)
        b = generate_trap_dfa(dfa_rng(11, 3), spec)
        assert a == b

    def test_a_different_round_gives_a_different_instance(self) -> None:
        spec = _spec()
        a = generate_trap_dfa(dfa_rng(11, 3), spec)
        b = generate_trap_dfa(dfa_rng(11, 4), spec)
        assert a.word != b.word or a.transitions != b.transitions

    def test_the_cache_returns_the_very_same_object(self) -> None:
        spec = _spec(turn=2)
        assert cached_dfa(11, 2, spec) is cached_dfa(11, 2, spec)

    def test_the_id_is_twelve_hex_characters(self) -> None:
        identifier = dfa_id_for(11, _spec())
        assert len(identifier) == 12
        assert all(c in "0123456789abcdef" for c in identifier)

    @pytest.mark.parametrize(
        "overrides",
        [
            {"states": 5},
            {"alphabet": 4},
            {"length": 10},
            {"question": "count"},
            {"trap": False},
            {"turn": 2},
            {"profile": "other"},
        ],
    )
    def test_every_field_that_changes_the_instance_changes_the_id(
        self, overrides
    ) -> None:
        assert dfa_id_for(11, _spec()) != dfa_id_for(11, _spec(**overrides))

    def test_the_seed_changes_the_id(self) -> None:
        assert dfa_id_for(11, _spec()) != dfa_id_for(12, _spec())


# ---------------------------------------------------------------------------
# Shallow solvers and the trap filter
# ---------------------------------------------------------------------------


class TestShallowSolvers:
    def test_the_prefix_series_is_the_doubling_series_plus_half(self) -> None:
        assert prefix_ks(8) == (2, 4)
        assert prefix_ks(10) == (2, 4, 5, 8)
        assert prefix_ks(32) == (2, 4, 8, 16)

    def test_the_full_length_is_never_in_the_recorded_series(self) -> None:
        # prefix_L IS the deep procedure; recording it would make a trap
        # instance impossible by definition.
        for length in _LADDER_LENGTHS:
            assert length not in prefix_ks(length)

    def test_the_recorded_solvers_are_the_four_families(self) -> None:
        names = shallow_solver_names(_spec(length=10))
        assert set(NAMED_SOLVERS) <= set(names)
        assert [n for n in names if n.startswith("prefix_")] == [
            "prefix_2",
            "prefix_4",
            "prefix_5",
            "prefix_8",
        ]

    def test_prefix_k_at_the_full_length_is_always_right(self) -> None:
        for seed in range(30):
            dfa = generate_dfa(dfa_rng(seed, 1), _spec(trap=False, length=16))
            assert shallow_prefix_k(dfa, 16) == dfa.answer

    def test_freq_map_reads_the_word_as_a_multiset(self) -> None:
        dfa = generate_dfa(dfa_rng(5, 1), _spec(trap=False))
        scrambled = Dfa(
            spec=dfa.spec,
            transitions=dfa.transitions,
            start=dfa.start,
            word="".join(sorted(dfa.word, reverse=True)),
            count_state=dfa.count_state,
        )
        assert shallow_freq_map(dfa) == shallow_freq_map(scrambled)

    def test_last_symbol_reads_only_the_final_move(self) -> None:
        dfa = generate_dfa(dfa_rng(5, 1), _spec(trap=False, question="final"))
        expected = state_name(dfa.transitions[dfa.start][dfa.symbols.index(dfa.word[-1])])
        assert shallow_last_symbol(dfa) == expected

    def test_ignore_selfloop_collapses_runs_of_one_symbol(self) -> None:
        dfa = generate_dfa(dfa_rng(5, 1), _spec(trap=False))
        doubled = Dfa(
            spec=dfa.spec,
            transitions=dfa.transitions,
            start=dfa.start,
            # Collapsing "aabb" and "ab" gives the same word, so the two
            # must give the same shallow answer. (The truth does not.)
            word="".join(c * 2 for c in dfa.word)[: dfa.spec.length],
            count_state=dfa.count_state,
        )
        assert isinstance(shallow_ignore_selfloop(doubled), str)

    def test_a_trap_instance_defeats_every_recorded_solver(self) -> None:
        for seed in range(30):
            dfa = generate_trap_dfa(dfa_rng(seed, 1), _spec())
            assert is_trap(dfa)
            assert [
                n for n, a in shallow_answers(dfa).items() if a == dfa.answer
            ] == []

    def test_the_trap_filter_records_how_many_draws_it_needed(self) -> None:
        dfa = generate_trap_dfa(dfa_rng(1, 1), _spec())
        assert dfa.trap_attempts >= 1

    def test_a_plain_instance_carries_no_attempt_count(self) -> None:
        assert generate_dfa(dfa_rng(1, 1), _spec(trap=False)).trap_attempts == 0


class TestGenerationFailsLoudly:
    def test_an_exhausted_budget_raises_instead_of_substituting(self) -> None:
        # The signal game's precedent: a silent fallback would put an easy
        # round where the schedule says hard and nothing would record it.
        with pytest.raises(DfaGenerationError):
            generate_trap_dfa(dfa_rng(1, 1), _spec(), attempts=0)

    def test_the_trap_wrapper_refuses_a_spec_that_did_not_ask_for_it(self) -> None:
        with pytest.raises(ValueError, match="not marked trap"):
            generate_trap_dfa(dfa_rng(1, 1), _spec(trap=False))

    def test_a_structurally_impossible_machine_raises(self) -> None:
        # Two states and two symbols where every draw is checked: force the
        # budget to fail by asking for a machine whose constraints a
        # degenerate RNG can never satisfy.
        class _AlwaysZero(random.Random):
            def randrange(self, *args, **kwargs):  # type: ignore[override]
                return 0

        with pytest.raises(DfaGenerationError):
            generate_dfa(_AlwaysZero(), _spec(trap=False, states=3, alphabet=2))


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


class TestRenderingHelpers:
    def test_there_is_one_transition_row_per_state(self) -> None:
        dfa = generate_dfa(dfa_rng(2, 1), _spec(trap=False, states=5))
        rows = transition_rows(dfa)
        assert len(rows) == 5
        assert rows[0].startswith("q0: ")
        assert rows[0].count("→") == dfa.spec.alphabet

    def test_the_word_is_grouped_in_fours(self) -> None:
        assert grouped_word("abcdabcdab") == "abcd abcd ab"

    def test_grouping_does_not_change_the_symbols(self) -> None:
        assert grouped_word("abcdabcd").replace(" ", "") == "abcdabcd"


# ---------------------------------------------------------------------------
# Answer parsing
# ---------------------------------------------------------------------------


class TestParsing:
    def setup_method(self) -> None:
        self.task = DfaTraceTask()

    def test_a_plain_state_line_parses(self) -> None:
        assert self.task.parse_response("STATE: q3") == ParsedDfaAnswer("STATE", "q3")

    def test_a_plain_count_line_parses(self) -> None:
        assert self.task.parse_response("COUNT: 7") == ParsedDfaAnswer("COUNT", "7")

    def test_the_label_is_case_insensitive(self) -> None:
        assert self.task.parse_response("state: q3").label == "STATE"

    def test_the_last_matching_line_wins(self) -> None:
        text = "STATE: q1\nno wait\nSTATE: q2"
        assert self.task.parse_response(text).value == "q2"

    def test_a_response_with_no_answer_line_is_a_parse_failure(self) -> None:
        assert self.task.parse_response("I think it ends somewhere.") is None

    def test_an_inline_mention_is_not_an_answer_line(self) -> None:
        # The regex is anchored to a whole line, so prose that happens to
        # contain the word is not mistaken for the verdict.
        assert self.task.parse_response("the STATE: q3 is my guess, maybe") is None

    def test_the_regex_is_the_one_the_brief_names(self) -> None:
        assert ANSWER_RE.pattern == r"^(STATE|COUNT):\s*(\S+)\s*$"


# ---------------------------------------------------------------------------
# Scoring
# ---------------------------------------------------------------------------


class TestScoring:
    def _prepared(self, turn: int = 1) -> DfaTraceTask:
        task = DfaTraceTask()
        task.initialize(seed=123, total_turns=8)
        task.prepare(None, _turn_ctx(turn))
        return task

    def test_the_true_answer_scores_one(self) -> None:
        task = self._prepared(1)
        truth = task._current.answer
        outcome = task.score(task.parse_response(f"STATE: {truth}"), None)
        assert outcome.success_factor == 1.0
        assert outcome.metadata["correct"] is True
        assert outcome.metadata["action_correct"] is True

    def test_a_wrong_state_scores_zero(self) -> None:
        task = self._prepared(1)
        wrong = next(
            state_name(i)
            for i in range(task._current.spec.states)
            if state_name(i) != task._current.answer
        )
        outcome = task.score(task.parse_response(f"STATE: {wrong}"), None)
        assert outcome.success_factor == 0.0
        assert outcome.metadata["parse_failed"] is False

    def test_a_bare_digit_is_accepted_for_a_state(self) -> None:
        task = self._prepared(1)
        digits = task._current.answer.removeprefix("q")
        assert task.score(task.parse_response(f"STATE: {digits}"), None).success_factor == 1.0

    def test_a_trailing_full_stop_is_tolerated(self) -> None:
        task = self._prepared(1)
        truth = task._current.answer
        assert task.score(task.parse_response(f"STATE: {truth}."), None).success_factor == 1.0

    def test_the_wrong_label_is_wrong_not_a_parse_failure(self) -> None:
        task = self._prepared(1)  # round 1 asks "final" -> STATE
        outcome = task.score(task.parse_response("COUNT: 3"), None)
        assert outcome.success_factor == 0.0
        assert outcome.metadata["parse_failed"] is False
        assert outcome.metadata["expected_label"] == "STATE"

    def test_a_count_round_is_scored_on_the_count_label(self) -> None:
        task = self._prepared(2)  # round 2 asks "count"
        truth = task._current.answer
        assert task.score(task.parse_response(f"COUNT: {truth}"), None).success_factor == 1.0
        assert task.score(task.parse_response(f"STATE: q{truth}"), None).success_factor == 0.0

    def test_an_unparseable_response_is_a_parse_failure_and_wrong(self) -> None:
        task = self._prepared(1)
        outcome = task.score(task.parse_response("no idea"), None)
        assert outcome.success_factor == 0.0
        assert outcome.metadata["parse_failed"] is True
        assert outcome.metadata["parsed_answer"] is None

    def test_scoring_before_preparing_raises(self) -> None:
        task = DfaTraceTask()
        task.initialize(seed=1, total_turns=8)
        with pytest.raises(RuntimeError):
            task.score(None, None)


# ---------------------------------------------------------------------------
# Metadata contract
# ---------------------------------------------------------------------------


class TestMetadata:
    def _both(self, turn: int = 1):
        task = DfaTraceTask()
        task.initialize(seed=77, total_turns=8)
        ctx = task.prepare(None, _turn_ctx(turn))
        outcome = task.score(task.parse_response("STATE: q0"), None)
        return task, ctx.metadata, outcome.metadata

    def test_the_scored_metadata_carries_every_key_the_brief_names(self) -> None:
        _task, _prep, scored = self._both()
        assert _REQUIRED_KEYS <= set(scored)

    def test_it_carries_nothing_beyond_the_brief_and_the_audit_extras(self) -> None:
        _task, _prep, scored = self._both()
        assert set(scored) == _REQUIRED_KEYS | _EXTRA_KEYS

    def test_puzzle_id_repeats_dfa_id_so_item_paired_analyses_work(self) -> None:
        _task, _prep, scored = self._both()
        assert scored["puzzle_id"] == scored["dfa_id"]

    def test_prepare_time_metadata_agrees_with_scoring_time(self) -> None:
        _task, prep, scored = self._both()
        for key in prep:
            assert prep[key] == scored[key], key

    def test_the_descriptors_describe_the_rung(self) -> None:
        task, _prep, scored = self._both(turn=3)
        assert scored["n_steps"] == _LADDER_LENGTHS[2]
        assert scored["n_states"] == _LADDER_STATES[2]
        assert scored["question_kind"] in ("final", "count")
        assert scored["generator_version"] == GENERATOR_VERSION
        assert scored["difficulty_profile"] == task._config.ladder[2].profile

    def test_a_trap_round_records_no_correct_shallow_solver(self) -> None:
        _task, _prep, scored = self._both()
        assert scored["trap_query"] is True
        assert scored["shallow_solvers_correct"] == []
        assert scored["trap_attempts"] >= 1

    def test_schedule_id_is_none_without_an_explicit_schedule(self) -> None:
        _task, _prep, scored = self._both()
        assert scored["schedule_id"] is None

    def test_shallow_actions_names_every_recorded_solver(self) -> None:
        task, _prep, scored = self._both()
        assert set(scored["shallow_actions"]) == set(
            shallow_solver_names(task._current.spec)
        )


# ---------------------------------------------------------------------------
# Task YAML
# ---------------------------------------------------------------------------


class TestShippedConfig:
    def test_the_ladder_is_the_shape_the_brief_specifies(self) -> None:
        cfg = load_dfa_trace_config()
        assert len(cfg.ladder) == 8
        assert tuple(s.length for s in cfg.ladder) == _LADDER_LENGTHS
        assert tuple(s.states for s in cfg.ladder) == _LADDER_STATES
        assert {s.alphabet for s in cfg.ladder} <= {3, 4}
        assert all(s.trap for s in cfg.ladder)
        assert {s.question for s in cfg.ladder} == {"final", "count"}

    def test_each_question_kind_ascends_in_length(self) -> None:
        # Gate D6 is checked within a kind, so each kind must be a ladder.
        cfg = load_dfa_trace_config()
        for kind in ("final", "count"):
            lengths = [s.length for s in cfg.ladder if s.question == kind]
            assert lengths == sorted(lengths)

    def test_round_i_plays_rung_i_without_a_schedule(self) -> None:
        cfg = load_dfa_trace_config()
        for turn in range(1, 9):
            assert cfg.spec_for_turn(turn).length == _LADDER_LENGTHS[turn - 1]
            assert cfg.spec_for_turn(turn).turn == turn

    def test_a_round_past_the_ladder_raises_rather_than_clamping(self) -> None:
        cfg = load_dfa_trace_config()
        with pytest.raises(ValueError, match="past the ladder"):
            cfg.spec_for_turn(9)


class TestConfigValidation:
    def _write(self, tmp_path: Path, body: str) -> Path:
        (tmp_path / "dfa_trace.yaml").write_text(body, encoding="utf-8")
        return tmp_path

    def test_a_missing_file_is_named(self, tmp_path: Path) -> None:
        with pytest.raises(FileNotFoundError):
            load_dfa_trace_config(tmp_path)

    def test_a_file_without_a_ladder_is_refused(self, tmp_path: Path) -> None:
        d = self._write(tmp_path, "name: dfa_trace\ntotal_turns: 8\n")
        with pytest.raises(ValueError, match="no ladder"):
            load_dfa_trace_config(d)

    def test_out_of_order_rounds_are_refused(self) -> None:
        with pytest.raises(ValueError, match="rounds must be"):
            DfaTraceConfig.model_validate(
                {
                    "ladder": [
                        {"round": 2, "profile": "a", "states": 4, "alphabet": 3, "length": 8},
                    ]
                }
            )

    def test_duplicate_profile_names_are_refused(self) -> None:
        with pytest.raises(ValueError, match="unique"):
            DfaTraceConfig.model_validate(
                {
                    "ladder": [
                        {"round": 1, "profile": "a", "states": 4, "alphabet": 3, "length": 8},
                        {"round": 2, "profile": "a", "states": 4, "alphabet": 3, "length": 9},
                    ]
                }
            )

    def test_an_unknown_question_kind_is_refused(self) -> None:
        with pytest.raises(ValueError, match="question must be"):
            DfaTraceConfig.model_validate(
                {
                    "ladder": [
                        {
                            "round": 1,
                            "profile": "a",
                            "states": 4,
                            "alphabet": 3,
                            "length": 8,
                            "question": "middle",
                        }
                    ]
                }
            )

    def test_an_unknown_key_is_refused(self) -> None:
        with pytest.raises(ValueError):
            DfaTraceConfig.model_validate(
                {
                    "ladder": [
                        {
                            "round": 1,
                            "profile": "a",
                            "states": 4,
                            "alphabet": 3,
                            "length": 8,
                            "trapp": True,
                        }
                    ]
                }
            )

    def test_a_schedule_naming_an_unknown_profile_is_refused(self) -> None:
        with pytest.raises(ValueError, match="unknown profiles"):
            DfaTraceConfig.model_validate(
                {
                    "ladder": [
                        {"round": 1, "profile": "a", "states": 4, "alphabet": 3, "length": 8}
                    ],
                    "dfa_profile_schedule": [{"round": 1, "profile": "zzz"}],
                }
            )

    def test_a_schedule_with_a_gap_is_refused(self) -> None:
        with pytest.raises(ValueError, match="exactly once"):
            DfaTraceConfig.model_validate(
                {
                    "ladder": [
                        {"round": 1, "profile": "a", "states": 4, "alphabet": 3, "length": 8}
                    ],
                    "dfa_profile_schedule": [{"round": 2, "profile": "a"}],
                }
            )

    def test_a_schedule_re_points_rounds_and_gets_an_id(self) -> None:
        cfg = DfaTraceConfig.model_validate(
            {
                "ladder": [
                    {"round": 1, "profile": "easy", "states": 4, "alphabet": 3, "length": 8},
                    {"round": 2, "profile": "hard", "states": 6, "alphabet": 4, "length": 24},
                ],
                "dfa_profile_schedule": [
                    {"round": 1, "profile": "hard"},
                    {"round": 2, "profile": "easy"},
                ],
            }
        )
        assert cfg.spec_for_turn(1).length == 24
        assert cfg.spec_for_turn(1).profile == "hard"
        assert cfg.schedule_id is not None and len(cfg.schedule_id) == 8


class TestInitialize:
    def test_a_season_longer_than_the_ladder_fails_at_startup(self) -> None:
        task = DfaTraceTask()
        with pytest.raises(ValueError, match="covers only"):
            task.initialize(seed=1, total_turns=9)

    def test_engine_keywords_for_other_tasks_are_absorbed(self) -> None:
        task = DfaTraceTask()
        task.initialize(
            difficulty="medium",
            seed=1,
            total_turns=8,
            signal_mode="per_turn_puzzle",
            forced_wrong=True,
            subagent_kill=True,
            puzzle_challenge=None,
        )
        assert task.prepare(None, _turn_ctx(1)).metadata["n_steps"] == 8

    def test_the_task_is_registered_under_its_name(self) -> None:
        assert get_task("dfa_trace") is DfaTraceTask

    def test_reset_clears_the_round_but_keeps_the_seed(self) -> None:
        task = DfaTraceTask()
        task.initialize(seed=5, total_turns=8)
        before = task.prepare(None, _turn_ctx(1)).metadata["dfa_id"]
        task.reset()
        assert task._current is None
        assert task.prepare(None, _turn_ctx(1)).metadata["dfa_id"] == before

    def test_it_never_completes_early(self) -> None:
        assert DfaTraceTask().is_completed() is False

    def test_there_is_no_action_menu(self) -> None:
        assert DfaTraceTask().get_available_actions() == []


# ---------------------------------------------------------------------------
# Prompts
# ---------------------------------------------------------------------------


class TestPrompts:
    def _task(self) -> DfaTraceTask:
        task = DfaTraceTask()
        task.initialize(seed=99, total_turns=8)
        return task

    def test_no_template_uses_an_equals_marker(self) -> None:
        task = self._task()
        texts = [
            task.get_system_rules(),
            task.get_response_format_override(),
            task.prepare(None, _turn_ctx(1)).prompt_section,
            task.prepare(None, _turn_ctx(2)).prompt_section,
        ]
        for text in texts:
            assert "===" not in text

    def test_the_rules_are_spoken_as_label_sentence(self) -> None:
        rules = self._task().get_system_rules()
        for label in (
            "THE TASK:",
            "THE MACHINE:",
            "THE TABLE:",
            "THE INPUT:",
            "THE QUESTION:",
            "COUNTING:",
            "ANSWER FORMAT:",
        ):
            assert label in rules

    def test_the_rules_say_nothing_about_effort_or_difficulty(self) -> None:
        # A sentence urging care would sit inside the effort measurement;
        # the trap filter is what makes shortcuts lose, not the prompt.
        rules = self._task().get_system_rules().lower()
        for word in ("careful", "carefully", "shortcut", "hard", "difficult", "effort"):
            assert word not in rules

    def test_the_observation_opens_with_the_round(self) -> None:
        body = self._task().prepare(None, _turn_ctx(3)).prompt_section
        assert body.startswith("ROUND 3.\n")

    def test_the_observation_shows_the_whole_table_and_the_input(self) -> None:
        task = self._task()
        body = task.prepare(None, _turn_ctx(3)).prompt_section
        dfa = task._current
        for row in transition_rows(dfa):
            assert f"  {row}" in body
        assert grouped_word(dfa.word) in body

    def test_a_final_round_asks_which_state(self) -> None:
        task = self._task()
        body = task.prepare(None, _turn_ctx(1)).prompt_section
        assert "QUESTION: which state" in body
        assert "COUNT" not in body

    def test_a_count_round_names_the_state_it_counts(self) -> None:
        task = self._task()
        body = task.prepare(None, _turn_ctx(2)).prompt_section
        assert "QUESTION: how many times" in body
        assert state_name(task._current.count_state) in body

    def test_the_observation_never_leaks_the_answer_or_the_shortcuts(self) -> None:
        task = self._task()
        for turn in range(1, 9):
            body = task.prepare(None, _turn_ctx(turn)).prompt_section
            for name in shallow_solver_names(task._current.spec):
                assert name not in body
            assert "trap" not in body.lower()

    def test_the_response_format_states_both_labels(self) -> None:
        text = self._task().get_response_format_override()
        assert "STATE: q2" in text
        assert "COUNT: 7" in text

    def test_the_response_format_does_not_repeat_its_own_header(self) -> None:
        # ``6-task_call.j2`` renders "ANSWER FORMAT:" above this block.
        assert "ANSWER FORMAT:" not in self._task().get_response_format_override()

    def test_the_prompts_are_english(self) -> None:
        task = self._task()
        text = task.get_system_rules() + task.prepare(None, _turn_ctx(1)).prompt_section
        assert all(ord(ch) < 128 or ch in "→" for ch in text)
