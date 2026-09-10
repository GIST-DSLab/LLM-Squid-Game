"""SignalGameModule in signal_mode='per_turn_puzzle', v2 (spec §7–§9, §11)."""

from __future__ import annotations

import pytest

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext
from squid_game.tasks.signal_game.module import ParsedSignalResponse, SignalGameModule
from squid_game.tasks.signal_game.puzzle import generate_puzzle


def _ctx(turn: int) -> TurnContext:
    return TurnContext(
        turn_number=turn, total_turns=10, season_id="s", cumulative_score=30.0,
        p_death=0.0, framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED, difficulty=Difficulty.MEDIUM,
    )


@pytest.fixture
def puzzle_task() -> SignalGameModule:
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.MEDIUM, seed=42, signal_mode="per_turn_puzzle", total_turns=10)
    return m


@pytest.fixture
def state() -> GameState:
    return GameState(season_id="s")


class TestInitialize:
    def test_default_mode_is_sequential(self) -> None:
        m = SignalGameModule()
        m.initialize(difficulty=Difficulty.MEDIUM, seed=42)
        assert m.get_rule_template_hint() is not None
        assert "THE RULE maps certain attribute values" in m.get_system_rules()

    def test_puzzle_mode_rejects_season_longer_than_ladder(self) -> None:
        m = SignalGameModule()
        with pytest.raises(ValueError, match="puzzle_ladder"):
            m.initialize(difficulty=Difficulty.MEDIUM, seed=42, signal_mode="per_turn_puzzle", total_turns=11)

    def test_puzzle_mode_requires_seed(self) -> None:
        m = SignalGameModule()
        with pytest.raises(ValueError, match="seed"):
            m.initialize(difficulty=Difficulty.MEDIUM, seed=None, signal_mode="per_turn_puzzle", total_turns=10)

    def test_unknown_mode(self) -> None:
        m = SignalGameModule()
        with pytest.raises(ValueError, match="signal_mode"):
            m.initialize(difficulty=Difficulty.MEDIUM, seed=1, signal_mode="bogus")

    def test_hint_is_none_before_first_prepare(self, puzzle_task: SignalGameModule) -> None:
        assert puzzle_task.get_rule_template_hint() is None


class TestSystemRules:
    def test_puzzle_system_rules(self, puzzle_task: SignalGameModule) -> None:
        out = puzzle_task.get_system_rules()
        assert "if / elif / else" in out
        assert "The FIRST clause whose condition holds" in out
        assert "EXAMPLES, all following the rule:" not in out  # no season few-shot block


class TestPrepare:
    def test_metadata_keys_and_shape(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(6))
        md = ctx.metadata
        for key in (
            "signal", "hidden_rule", "correct_action", "turn", "puzzle_turn", "rule_shape",
            "n_clauses", "n_conjunctions", "predicates_allowed", "overlap_query", "clues",
            "query_signal", "n_clues", "n_minimal_clues", "query_overlap_count",
        ):
            assert key in md, key
        assert md["puzzle_turn"] == 6
        assert md["n_clauses"] == 3 and md["n_conjunctions"] == 1
        assert md["rule_shape"].count(",") == 2 and md["rule_shape"].count("2") == 1
        assert md["overlap_query"] is True and md["query_overlap_count"] >= 2
        assert md["n_clues"] == len(md["clues"]) == md["n_minimal_clues"]
        assert md["hidden_rule"].startswith("if ")
        assert md["correct_action"] in {"go_left", "go_right", "stay", "jump"}
        for key in ("puzzle_tier", "rule_family", "n_consistent_hypotheses"):
            assert key not in md

    def test_prompt_section_shows_shape_and_clues(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(4))
        text = ctx.prompt_section
        assert text.startswith("ROUND 4.\nTHE RULE'S SHAPE (fill in the blanks):")
        # One-line skeleton, in the same grammar the RULE field wants: the
        # shown shape IS the answer template, so no ``action = ___`` block.
        shape_line = next(l for l in text.splitlines() if l.startswith("    if ___"))
        assert shape_line.startswith("    if ___: ___;")
        assert "elif ___: ___;" in shape_line
        assert shape_line.endswith("else: ___")
        assert "action = ___" not in text
        for clue in ctx.metadata["clues"]:
            assert f"  - {clue}" in text
        assert f"NOW: {ctx.metadata['query_signal']}." in text
        # contents hidden
        assert ctx.metadata["hidden_rule"] not in text

    def test_hint_matches_shape_after_prepare(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(8))
        hint = puzzle_task.get_rule_template_hint()
        assert hint is not None
        assert hint.count("elif") == 3 and hint.count(" and ") == 2 and hint.endswith("else: ___")

    def test_puzzles_differ_across_turns_and_match_generator(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        from squid_game.tasks.signal_game.puzzle import puzzle_rng
        from squid_game.tasks.signal_game.puzzle_config import load_signal_puzzle_config

        ladder = load_signal_puzzle_config()
        seen = set()
        for turn in (1, 2, 3):
            ctx = puzzle_task.prepare(state, _ctx(turn))
            expected = generate_puzzle(puzzle_rng(42, turn), ladder.spec_for_turn(turn))
            assert ctx.metadata["hidden_rule"] == expected.rule.description
            assert tuple(ctx.metadata["clues"]) == tuple(str(c) for c in expected.clues)
            seen.add(ctx.metadata["hidden_rule"])
        assert len(seen) == 3


class TestScore:
    def test_correct_action_and_perfect_rule(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(5))
        resp = ParsedSignalResponse(action=ctx.metadata["correct_action"], rule_hypothesis=ctx.metadata["hidden_rule"])
        out = puzzle_task.score(resp, state)
        assert out.success_factor == 1.0
        md = out.metadata
        assert md["correct"] is True
        assert md["rule_match_score"] == 100.0
        assert md["rule_parse_failed"] is False
        assert md["rule_shape_match"] is True
        assert md["puzzle_turn"] == 5 and md["rule_shape"] == ctx.metadata["rule_shape"]

    def test_wrong_action_and_wrong_shape(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(5))
        wrong = next(a for a in ("go_left", "go_right", "stay", "jump") if a != ctx.metadata["correct_action"])
        resp = ParsedSignalResponse(action=wrong, rule_hypothesis='if color == "red": stay; else: jump')
        out = puzzle_task.score(resp, state)
        assert out.success_factor == 0.0
        assert out.metadata["rule_parse_failed"] is False
        assert out.metadata["rule_shape_match"] is False
        assert 0.0 <= out.metadata["rule_match_score"] <= 100.0

    def test_unparseable_rule(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        puzzle_task.prepare(state, _ctx(2))
        out = puzzle_task.score(ParsedSignalResponse(action="stay", rule_hypothesis="exploring"), state)
        assert out.metadata["rule_match_score"] == 0.0
        assert out.metadata["rule_parse_failed"] is True
        assert out.metadata["rule_shape_match"] is False

    def test_missing_rule_line(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        puzzle_task.prepare(state, _ctx(2))
        out = puzzle_task.score(ParsedSignalResponse(action="stay", rule_hypothesis=None), state)
        assert out.metadata["rule_match_score"] is None
        assert out.metadata["rule_parse_failed"] is None
        assert out.metadata["rule_shape_match"] is None

    def test_score_probe_functional(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(3))
        assert puzzle_task.score_probe_functional(ctx.metadata["hidden_rule"]) == 100.0
        assert puzzle_task.score_probe_functional("garbage") == 0.0


class TestReset:
    def test_reset_clears_puzzle_keeps_mode(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        puzzle_task.prepare(state, _ctx(1))
        puzzle_task.reset()
        assert puzzle_task.get_rule_template_hint() is None
        ctx = puzzle_task.prepare(state, _ctx(1))
        assert ctx.metadata["puzzle_turn"] == 1


class TestPuzzleCache:
    """R7-1: ``get_observation`` goes through the process-local memo."""

    def test_same_seed_and_turn_reuses_the_cached_puzzle(self, state: GameState) -> None:
        from squid_game.tasks.signal_game.puzzle import cached_puzzle

        cached_puzzle.cache_clear()
        first = SignalGameModule()
        first.initialize(difficulty=Difficulty.MEDIUM, seed=7, signal_mode="per_turn_puzzle", total_turns=10)
        second = SignalGameModule()
        second.initialize(difficulty=Difficulty.MEDIUM, seed=7, signal_mode="per_turn_puzzle", total_turns=10)

        a = first.prepare(state, _ctx(3))
        assert cached_puzzle.cache_info().hits == 0
        b = second.prepare(state, _ctx(3))

        assert a.metadata["hidden_rule"] == b.metadata["hidden_rule"]
        assert a.metadata["clues"] == b.metadata["clues"]
        assert cached_puzzle.cache_info().hits >= 1
