"""SignalGameModule in signal_mode='per_turn_puzzle' (spec §3, §8, §10, §11)."""

from __future__ import annotations

import pytest

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext
from squid_game.tasks.signal_game.module import SignalGameModule
from squid_game.tasks.signal_game.puzzle import enumerate_hypotheses
from squid_game.tasks.signal_game.rules import ACTIONS


def _ctx(turn: int) -> TurnContext:
    return TurnContext(
        turn_number=turn, total_turns=30, season_id="s", cumulative_score=30.0,
        p_death=0.0, framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED, difficulty=Difficulty.MEDIUM,
    )


@pytest.fixture
def puzzle_task() -> SignalGameModule:
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.MEDIUM, seed=42, signal_mode="per_turn_puzzle", total_turns=30)
    return m


@pytest.fixture
def state() -> GameState:
    return GameState(season_id="s")


class TestInitialize:
    def test_default_mode_is_sequential(self) -> None:
        m = SignalGameModule()
        m.initialize(difficulty=Difficulty.MEDIUM, seed=42)
        assert m.get_rule_template_hint() is not None
        assert "The hidden rule follows one of these formats" in m.get_system_rules()

    def test_puzzle_mode_rejects_season_longer_than_ladder(self) -> None:
        m = SignalGameModule()
        with pytest.raises(ValueError, match="puzzle_ladder"):
            m.initialize(difficulty=Difficulty.MEDIUM, seed=42, signal_mode="per_turn_puzzle", total_turns=31)

    def test_puzzle_mode_warns_when_legacy_knobs_given(self, caplog: pytest.LogCaptureFixture) -> None:
        m = SignalGameModule()
        with caplog.at_level("WARNING"):
            m.initialize(difficulty=Difficulty.HARD, seed=1, signal_mode="per_turn_puzzle",
                         total_turns=30, num_few_shot=1, curriculum_turns=3)
        assert "ignored" in caplog.text

    def test_unknown_mode_rejected(self) -> None:
        with pytest.raises(ValueError):
            SignalGameModule().initialize(difficulty=Difficulty.MEDIUM, seed=1, signal_mode="nope")


class TestSystemPromptAndHint:
    def test_system_rules_are_the_puzzle_template(self, puzzle_task: SignalGameModule) -> None:
        out = puzzle_task.get_system_rules()
        assert "changes every round" in out
        assert "example signal-action pairs" not in out     # no sequential few-shot block

    def test_rule_template_hint_is_none(self, puzzle_task: SignalGameModule) -> None:
        assert puzzle_task.get_rule_template_hint() is None

    def test_probe_question_is_free_form(self, puzzle_task: SignalGameModule) -> None:
        assert "<attribute>" not in puzzle_task.get_probe_question(1)


class TestPrepare:
    def test_metadata_keys(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(1))
        md = ctx.metadata
        for key in ("signal", "hidden_rule", "correct_action", "turn", "puzzle_tier",
                    "rule_family", "clues", "query_signal", "n_clues", "n_consistent_hypotheses"):
            assert key in md, key
        assert md["turn"] == 1 and md["puzzle_tier"] == 1 and md["rule_family"] == "A"
        assert md["correct_action"] in ACTIONS
        assert isinstance(md["clues"], list) and len(md["clues"]) == md["n_clues"] >= 3
        assert all("→" in c for c in md["clues"])
        assert md["n_consistent_hypotheses"] >= 1

    def test_prompt_section_shows_clues_and_query(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        ctx = puzzle_task.prepare(state, _ctx(1))
        assert ctx.prompt_section.startswith("Turn 1.")
        assert "Now:" in ctx.prompt_section
        for clue in ctx.metadata["clues"]:
            assert clue in ctx.prompt_section

    def test_clues_change_every_turn(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        seen = {tuple(puzzle_task.prepare(state, _ctx(t)).metadata["clues"]) for t in range(1, 11)}
        assert len(seen) == 10

    def test_tier_follows_ladder(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        tiers = [puzzle_task.prepare(state, _ctx(t)).metadata["puzzle_tier"] for t in (1, 6, 7, 13, 19, 25, 30)]
        assert tiers == [1, 1, 2, 3, 4, 5, 5]

    def test_same_seed_same_puzzles_across_instances(self, state: GameState) -> None:
        a, b = SignalGameModule(), SignalGameModule()
        for m in (a, b):
            m.initialize(difficulty=Difficulty.MEDIUM, seed=7, signal_mode="per_turn_puzzle", total_turns=30)
        for t in (1, 9, 27):
            assert a.prepare(state, _ctx(t)).metadata == b.prepare(state, _ctx(t)).metadata

    def test_prepare_is_order_independent(self, state: GameState) -> None:
        """Turn 9's puzzle does not depend on whether turns 1-8 were prepared."""
        a = SignalGameModule(); a.initialize(difficulty=Difficulty.MEDIUM, seed=7, signal_mode="per_turn_puzzle", total_turns=30)
        b = SignalGameModule(); b.initialize(difficulty=Difficulty.MEDIUM, seed=7, signal_mode="per_turn_puzzle", total_turns=30)
        for t in range(1, 9):
            a.prepare(state, _ctx(t))
        assert a.prepare(state, _ctx(9)).metadata == b.prepare(state, _ctx(9)).metadata

    def test_reset_keeps_mode_and_seed(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        first = puzzle_task.prepare(state, _ctx(1)).metadata
        puzzle_task.reset()
        assert puzzle_task.get_rule_template_hint() is None
        assert puzzle_task.prepare(state, _ctx(1)).metadata == first


class TestScore:
    def test_correct_and_incorrect(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        md = puzzle_task.prepare(state, _ctx(1)).metadata
        parsed = puzzle_task.parse_response(f"RULE: {md['hidden_rule']}\nACTION: {md['correct_action']}")
        out = puzzle_task.score(parsed, state)
        assert out.success_factor == 1.0
        assert out.metadata["correct"] is True
        assert out.metadata["rule_match_score"] == 100.0
        assert out.metadata["rule_parsed_family"] == md["rule_family"]
        assert out.metadata["puzzle_tier"] == 1
        assert out.metadata["n_consistent_hypotheses"] == md["n_consistent_hypotheses"]

        wrong = next(a for a in ACTIONS if a != md["correct_action"])
        out2 = puzzle_task.score(puzzle_task.parse_response(f"RULE: no rule\nACTION: {wrong}"), state)
        assert out2.success_factor == 0.0
        assert out2.metadata["rule_match_score"] == 0.0

    def test_truth_description_scores_100(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        md = puzzle_task.prepare(state, _ctx(1)).metadata
        assert puzzle_task.score_probe_functional(md["hidden_rule"]) == 100.0

    def test_unparseable_hypothesis_scores_zero_and_flags_family_none(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        md = puzzle_task.prepare(state, _ctx(1)).metadata
        out = puzzle_task.score(puzzle_task.parse_response(
            f"RULE: it depends on colour somehow\nACTION: {md['correct_action']}"), state)
        assert out.metadata["rule_match_score"] == 0.0
        assert out.metadata["rule_parsed_family"] is None

    def test_partial_hypothesis_scores_between(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        md = puzzle_task.prepare(state, _ctx(1)).metadata
        # Same rule but with the two actions swapped -> 0 % agreement.
        rule = md["hidden_rule"]
        a_then = rule.split(" then ")[1].split(",")[0]
        a_else = rule.rstrip(".").split("otherwise ")[1]
        swapped = rule.replace(f"then {a_then}", "then TMP").replace(f"otherwise {a_else}", f"otherwise {a_then}").replace("then TMP", f"then {a_else}")
        assert puzzle_task.score_probe_functional(swapped) == 0.0

    def test_active_rule_description_is_current_puzzle(self, puzzle_task: SignalGameModule, state: GameState) -> None:
        md = puzzle_task.prepare(state, _ctx(2)).metadata
        assert puzzle_task.get_active_rule_description() == md["hidden_rule"]


class TestSequentialUnchanged:
    def test_sequential_prepare_has_no_puzzle_keys(self, state: GameState) -> None:
        m = SignalGameModule()
        m.initialize(difficulty=Difficulty.EASY, seed=42)
        md = m.prepare(state, _ctx(1)).metadata
        assert "puzzle_tier" not in md and "clues" not in md
