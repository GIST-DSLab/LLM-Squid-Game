"""Pre-decision context isolation (2026-09-05).

The confidence + decision calls run *before* the round's stimulus, yet
until now they shared the task call's system prompt (framing + task
rules) and its cumulative history block (signal / action / rule
hypothesis per turn). Both leak the task identity and the agent's own
rule understanding into the pre-decision context, so ``P_THREAT`` ends
up tracking rule uncertainty rather than survival pressure.

Two ``ForfeitLayerConfig`` knobs fix that, both defaulting to today's
behaviour:

* ``task_rules_before_decision=False`` → confidence + decision calls get
  the framing prompt only.
* ``split_context_level="outcome"`` → confidence + decision calls get an
  outcome-only history block (round, verdict, cumulative score, lives).

Scope:

1. ``build_system_prompt(include_task_rules=False)`` drops the rules.
2. ``format_outcome_history_block`` rendering + leak-freedom.
3. Config accepts the new value / flag, and defaults are unchanged.
4. Manager-level wiring — knobs on vs. off, across all three calls.
"""

from __future__ import annotations

import random
from typing import Any

import pytest

from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.legacy.risk_choice_layer import (
    RiskChoiceLayer,
    RiskChoiceLayerConfig,
)
from squid_game.core.legacy.survival import SurvivalPressure
from squid_game.core.turn_prompts import (
    build_system_prompt,
    format_history_block,
    format_outcome_history_block,
)
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import ForfeitLayerConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import GameState, TurnContext

from tests.unit.test_unified_turn import FakeSignalTask
from tests.unit.test_unified_turn_confidence_call import ConfidenceStubAgent

RULES_TEXT = "Pick GO when you see a signal; STAY otherwise."


# ---------------------------------------------------------------------------
# 1. build_system_prompt(include_task_rules=...)
# ---------------------------------------------------------------------------


def _turn_context(
    turn: int = 1,
    *,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    lives: bool = True,
) -> TurnContext:
    return TurnContext(
        turn_number=turn,
        total_turns=5,
        season_id="s",
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=forfeit,
        difficulty=Difficulty.MEDIUM,
        cumulative_score=30.0,
        lives_remaining=5 if lives else None,
        lives_total=5 if lives else None,
    )


def _system_prompt(**kw: Any) -> str:
    return build_system_prompt(
        _turn_context(),
        framing_mgr=FramingManager(framing=Framing.TRUE_BASELINE),
        task=FakeSignalTask(),
        forfeit_ctrl=ForfeitController(ForfeitCondition.ALLOWED),
        include_forfeit_text=False,
        **kw,
    )


class TestSystemPromptTaskRulesGate:
    def test_default_includes_task_rules(self) -> None:
        assert RULES_TEXT in _system_prompt()

    def test_include_task_rules_false_drops_them(self) -> None:
        prompt = _system_prompt(include_task_rules=False)
        assert RULES_TEXT not in prompt
        assert "signal" not in prompt.lower()

    def test_framing_body_survives(self) -> None:
        framed = _system_prompt(include_task_rules=False)
        full = _system_prompt()
        assert framed
        assert full.startswith(framed)


# ---------------------------------------------------------------------------
# 2. format_outcome_history_block
# ---------------------------------------------------------------------------


def _entry(
    turn: int,
    *,
    correct: bool | None,
    outcome: str,
    cumulative: float,
    lives_after: int | None = None,
    lives_total: int | None = None,
) -> dict[str, Any]:
    return {
        "turn": turn,
        "signal": f"signal-{turn}",
        "action": "GO",
        "rule_hypothesis": "GO when the signal is red",
        "stake_choice": None,
        "correct": correct,
        "outcome": outcome,
        "cumulative_score": cumulative,
        "lives_after": lives_after,
        "lives_total": lives_total,
    }


class TestFormatOutcomeHistoryBlock:
    def test_empty_history_returns_empty_string(self) -> None:
        assert format_outcome_history_block([], 10) == ""

    def test_renders_correct_and_incorrect_rows(self) -> None:
        history = [
            _entry(1, correct=True, outcome="+10", cumulative=40.0),
            _entry(2, correct=False, outcome="+0", cumulative=40.0),
        ]
        assert format_outcome_history_block(history, 10) == (
            "=== Previous Rounds ===\n"
            "- Round 1: correct → cumulative: 40.0\n"
            "- Round 2: incorrect → cumulative: 40.0"
        )

    def test_lives_suffix_only_when_entry_carries_lives(self) -> None:
        history = [
            _entry(
                1,
                correct=False,
                outcome="+0",
                cumulative=30.0,
                lives_after=4,
                lives_total=5,
            ),
            _entry(2, correct=True, outcome="+10", cumulative=40.0),
        ]
        rendered = format_outcome_history_block(history, 10)
        assert rendered == (
            "=== Previous Rounds ===\n"
            "- Round 1: incorrect → cumulative: 30.0 (lives: 4/5)\n"
            "- Round 2: correct → cumulative: 40.0"
        )

    @pytest.mark.parametrize("word", ["forfeit", "eliminated", "died"])
    def test_terminal_rounds_print_their_outcome_word(self, word: str) -> None:
        history = [_entry(3, correct=None, outcome=word, cumulative=40.0)]
        rendered = format_outcome_history_block(history, 10)
        assert f"- Round 3: {word} → cumulative: 40.0" in rendered

    def test_never_prints_signal_action_or_hypothesis(self) -> None:
        history = [
            _entry(1, correct=True, outcome="+10", cumulative=40.0),
            _entry(2, correct=False, outcome="+0", cumulative=40.0),
        ]
        rendered = format_outcome_history_block(history, 10)
        assert "signal-1" not in rendered
        assert "action=" not in rendered
        assert "GO" not in rendered
        assert "rule hypothesis" not in rendered.lower()

    def test_respects_max_history_turns(self) -> None:
        history = [
            _entry(n, correct=True, outcome="+10", cumulative=float(n))
            for n in range(1, 6)
        ]
        rendered = format_outcome_history_block(history, 2)
        assert "Round 4" in rendered and "Round 5" in rendered
        assert "Round 3" not in rendered

    def test_missing_correct_key_falls_back_to_outcome(self) -> None:
        legacy = {
            "turn": 1,
            "signal": "s",
            "action": "GO",
            "rule_hypothesis": None,
            "stake_choice": None,
            "outcome": "+10",
            "cumulative_score": 40.0,
        }
        rendered = format_outcome_history_block([legacy], 10)
        assert "- Round 1: +10 → cumulative: 40.0" in rendered


# ---------------------------------------------------------------------------
# 3. Config surface
# ---------------------------------------------------------------------------


class TestForfeitLayerConfigKnobs:
    def test_defaults_unchanged(self) -> None:
        cfg = ForfeitLayerConfig()
        assert cfg.split_context_level == "medium"
        assert cfg.task_rules_before_decision is True

    def test_accepts_outcome_level(self) -> None:
        assert (
            ForfeitLayerConfig(split_context_level="outcome").split_context_level
            == "outcome"
        )

    def test_accepts_task_rules_flag_false(self) -> None:
        assert (
            ForfeitLayerConfig(task_rules_before_decision=False).
            task_rules_before_decision
            is False
        )

    def test_rejects_unknown_level(self) -> None:
        with pytest.raises(Exception):
            ForfeitLayerConfig(split_context_level="outcomes")

    @pytest.mark.parametrize(
        "level", ["minimal", "medium", "full", "outcome"]
    )
    def test_legacy_levels_still_load(self, level: str) -> None:
        assert ForfeitLayerConfig(split_context_level=level)


# ---------------------------------------------------------------------------
# 4. Manager-level wiring
# ---------------------------------------------------------------------------


def _manager(
    agent: ConfidenceStubAgent,
    *,
    split_context_level: str = "medium",
    task_rules_before_decision: bool = True,
    forfeit_condition: ForfeitCondition = ForfeitCondition.ALLOWED,
) -> UnifiedTurnManager:
    return UnifiedTurnManager(
        task=FakeSignalTask(),
        agent=agent,
        framing_mgr=FramingManager(framing=Framing.TRUE_BASELINE),
        forfeit_ctrl=ForfeitController(forfeit_condition),
        survival=SurvivalPressure(),
        risk_layer=RiskChoiceLayer(RiskChoiceLayerConfig()),
        measurement=MeasurementRecorder(output_path=None),
        cot_collector=CoTCollector(),
        forfeit_layer=ForfeitLayer(
            ForfeitLayerConfig(
                base_reward=10.0,
                reward_mode="flat",
                split_context_level=split_context_level,
                task_rules_before_decision=task_rules_before_decision,
            )
        ),
        use_split_forfeit_layer=True,
        rng=random.Random(0),
        phantom_death=True,
        constant_p_death=0.0,
        lives_enabled=True,
        confidence_call_enabled=True,
    )


def _agent() -> ConfidenceStubAgent:
    return ConfidenceStubAgent(
        confidence_responses=["P_THREAT: 20", "P_THREAT: 30"],
        confidence_thinking=["hmm", "hmm"],
        task_responses=["RULE: r\nACTION: STAY", "RULE: r\nACTION: GO"],
        forfeit_responses=["CHOICE: CONTINUE", "CHOICE: CONTINUE"],
    )


def _run_two_turns(mgr: UnifiedTurnManager) -> None:
    state = GameState(season_id="s", cumulative_score=30.0)
    mgr.execute_turn(state, _turn_context(1))
    mgr.execute_turn(state, _turn_context(2))


def _by_kind(agent: ConfidenceStubAgent, kind: str) -> list[tuple[str, str]]:
    return [(s, u) for k, s, u in agent.call_log if k == kind]


class TestManagerWiringKnobsOn:
    @pytest.fixture
    def agent(self) -> ConfidenceStubAgent:
        a = _agent()
        _run_two_turns(
            _manager(
                a,
                split_context_level="outcome",
                task_rules_before_decision=False,
            )
        )
        return a

    def test_pre_decision_system_prompts_have_no_task_rules(
        self, agent: ConfidenceStubAgent
    ) -> None:
        for kind in ("confidence", "decision"):
            for system, _ in _by_kind(agent, kind):
                assert RULES_TEXT not in system

    def test_task_call_system_prompt_keeps_task_rules(
        self, agent: ConfidenceStubAgent
    ) -> None:
        for system, _ in _by_kind(agent, "task"):
            assert RULES_TEXT in system

    def test_pre_decision_bodies_are_leak_free(
        self, agent: ConfidenceStubAgent
    ) -> None:
        for kind in ("confidence", "decision"):
            for _, body in _by_kind(agent, kind):
                assert "signal-1" not in body
                assert "signal-2" not in body
                assert "action=" not in body
                assert "rule hypothesis" not in body.lower()

    def test_pre_decision_bodies_carry_outcome_history_from_turn_two(
        self, agent: ConfidenceStubAgent
    ) -> None:
        for kind in ("confidence", "decision"):
            first, second = _by_kind(agent, kind)
            assert "=== Previous Rounds ===" not in first[1]
            assert "=== Previous Rounds ===" in second[1]
            # Turn 1 answered STAY against correct_action GO → incorrect.
            assert "- Round 1: incorrect" in second[1]
            assert "(attempts: 4/5)" in second[1]  # true_baseline → attempts vocabulary

    def test_task_call_body_keeps_the_full_history(
        self, agent: ConfidenceStubAgent
    ) -> None:
        _, second = _by_kind(agent, "task")
        assert "=== Previous Turn Results ===" in second[1]
        assert "signal-1" in second[1]

    def test_result_records_the_decision_system_prompt(self) -> None:
        a = _agent()
        mgr = _manager(
            a,
            split_context_level="outcome",
            task_rules_before_decision=False,
        )
        result = mgr.execute_turn(
            GameState(season_id="s", cumulative_score=30.0), _turn_context(1)
        )
        assert result.system_prompt == _by_kind(a, "decision")[0][0]
        assert RULES_TEXT not in result.system_prompt
        assert result.decision_call_input == _by_kind(a, "decision")[0][1]


class TestManagerWiringKnobsOffIsByteIdentical:
    def test_all_three_calls_unchanged(self) -> None:
        baseline = _agent()
        _run_two_turns(_manager(baseline))
        explicit = _agent()
        _run_two_turns(
            _manager(
                explicit,
                split_context_level="medium",
                task_rules_before_decision=True,
            )
        )
        assert explicit.call_log == baseline.call_log

    def test_defaults_still_show_full_history_to_the_decision_call(
        self,
    ) -> None:
        a = _agent()
        _run_two_turns(_manager(a))
        _, second = _by_kind(a, "decision")
        assert "=== Previous Turn Results ===" in second[1]
        assert "signal-1" in second[1]
        assert RULES_TEXT in second[0]

    def test_golden_decision_body_matches_format_history_block(self) -> None:
        a = _agent()
        mgr = _manager(a)
        state = GameState(season_id="s", cumulative_score=30.0)
        mgr.execute_turn(state, _turn_context(1))
        after_turn_one = mgr.history
        mgr.execute_turn(state, _turn_context(2))
        expected = format_history_block(after_turn_one, "cumulative", 15)
        assert expected
        assert expected in _by_kind(a, "decision")[1][1]


# ---------------------------------------------------------------------------
# 2b. lives_label — control cells must not say "lives"
# ---------------------------------------------------------------------------


class TestOutcomeHistoryLivesLabel:
    _HISTORY = [
        {
            "turn": 1,
            "outcome": "+0",
            "correct": False,
            "cumulative_score": 30.0,
            "lives_after": 4,
            "lives_total": 5,
        }
    ]

    def test_default_label_is_lives(self) -> None:
        assert format_outcome_history_block(self._HISTORY, 10).endswith(
            "(lives: 4/5)"
        )

    def test_control_label_attempts(self) -> None:
        rendered = format_outcome_history_block(
            self._HISTORY, 10, lives_label="attempts"
        )
        assert rendered.endswith("(attempts: 4/5)")
        assert "lives" not in rendered
