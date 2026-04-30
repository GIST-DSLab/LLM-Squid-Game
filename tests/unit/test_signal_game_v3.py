"""Unit tests for ``SignalGameModule`` v3 RiskAwareTaskModule surface.

Spec: ``docs/design/v3/MASTER_PLAN.md`` §6.3 — interface conformance
tests (``test_signal_prepare_returns_context``, ``..._parse_valid_action``,
``..._score_correct_returns_1``, ``..._score_incorrect_returns_0``).
Adds dual-inheritance verification, metadata schema check, and
history-record propagation under the unified flow (post-Phase-M this is
an EXPERT-difficulty property; the pre-Phase-M HARD semantics shifted
one slot up).

The legacy ``TaskModule`` surface (``apply_action``/``score_probe`` etc.)
remains untouched and is exercised by the existing engine smoke tests
in this PR (no new legacy tests added — out of Phase E scope).
"""

from __future__ import annotations

import pytest

from squid_game.models.enums import Difficulty
from squid_game.models.state import GameState, TurnContext
from squid_game.models.enums import Framing, ForfeitCondition
from squid_game.tasks.base import (
    RiskAwareTaskModule,
    TaskContext,
    TaskModule,
    TaskOutcome,
)
from squid_game.tasks.signal_game.module import SignalGameModule
from squid_game.tasks.signal_game.rules import ACTIONS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def task() -> SignalGameModule:
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EASY, seed=42)
    return m


@pytest.fixture
def medium_task() -> SignalGameModule:
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.MEDIUM, seed=42)
    return m


@pytest.fixture
def hard_task() -> SignalGameModule:
    """Post-Phase-M HARD difficulty: two-attribute conjunction rules.

    History-dependency has moved to EXPERT; use ``expert_task`` for
    tests that previously asserted override behaviour.
    """
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.HARD, seed=42)
    return m


@pytest.fixture
def expert_task() -> SignalGameModule:
    """Post-Phase-M EXPERT difficulty: history-dependent override on top
    of a two-attribute conjunction rule (the pre-Phase-M HARD semantics)."""
    m = SignalGameModule()
    m.initialize(difficulty=Difficulty.EXPERT, seed=42)
    return m


@pytest.fixture
def turn_context() -> TurnContext:
    return TurnContext(
        turn_number=1,
        total_turns=15,
        season_id="test",
        cumulative_score=0.0,
        p_death=0.15,
        framing=Framing.NEUTRAL,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.EASY,
    )


@pytest.fixture
def game_state() -> GameState:
    return GameState(season_id="test", current_turn=1, cumulative_score=0.0)


# ---------------------------------------------------------------------------
# Dual inheritance
# ---------------------------------------------------------------------------


class TestDualInheritance:
    def test_is_legacy_task_module(self, task: SignalGameModule) -> None:
        assert isinstance(task, TaskModule)

    def test_is_risk_aware_task_module(self, task: SignalGameModule) -> None:
        assert isinstance(task, RiskAwareTaskModule)

    def test_legacy_methods_still_present(self, task: SignalGameModule) -> None:
        # Spot-check a few methods that drive the legacy TurnManager.
        assert hasattr(task, "apply_action")
        assert hasattr(task, "score_probe")
        assert hasattr(task, "score_decision_quality")
        assert hasattr(task, "get_feedback_text")
        assert hasattr(task, "get_observation")
        assert hasattr(task, "get_probe_question")


# ---------------------------------------------------------------------------
# prepare()
# ---------------------------------------------------------------------------


class TestPrepare:
    def test_returns_task_context(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        assert isinstance(ctx, TaskContext)

    def test_prompt_section_non_empty(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        # Observation contains the rendered signal prompt.
        assert ctx.prompt_section.strip()

    def test_metadata_has_required_keys(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        for key in ("signal", "hidden_rule", "correct_action", "turn"):
            assert key in ctx.metadata, f"metadata missing key={key}"

    def test_metadata_signal_matches_observation_summary(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        # Signal text is the "color shape number" summary used in history.
        assert ctx.metadata["signal"] == task.get_observation_summary()

    def test_metadata_correct_action_is_valid(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        assert ctx.metadata["correct_action"] in ACTIONS

    def test_metadata_turn_matches_context(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        assert ctx.metadata["turn"] == turn_context.turn_number

    def test_prepare_advances_signal_each_call(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        first = task.prepare(game_state, turn_context).metadata["signal"]
        next_ctx = turn_context.model_copy(update={"turn_number": 2})
        second = task.prepare(game_state, next_ctx).metadata["signal"]
        # Two random signals from the seeded RNG should differ.
        assert first != second


# ---------------------------------------------------------------------------
# parse_response()
# ---------------------------------------------------------------------------


class TestParseResponse:
    @pytest.mark.parametrize(
        "text,expected",
        [
            ("ACTION: go_left, STAKE: 2", "go_left"),
            ("ACTION: jump, STAKE: 3", "jump"),
            ("Action: STAY, stake: 1", "stay"),
            ("blah\nACTION: go_right\nblah", "go_right"),
        ],
    )
    def test_parses_valid_action(
        self, task: SignalGameModule, text: str, expected: str
    ) -> None:
        parsed = task.parse_response(text)
        assert parsed.action == expected

    def test_falls_back_to_standalone_action_token(
        self, task: SignalGameModule
    ) -> None:
        # Bare action keyword without ACTION: prefix still recoverable.
        assert task.parse_response("I think we should jump now.").action == "jump"

    def test_returns_none_on_parse_failure(self, task: SignalGameModule) -> None:
        assert task.parse_response("This is just commentary.").action is None
        assert task.parse_response("").action is None

    def test_last_match_wins(self, task: SignalGameModule) -> None:
        """Models often emit thinking-style rehearsals before final answer."""
        text = (
            "Maybe ACTION: stay\nWait, on second thought:\n"
            "ACTION: go_left, STAKE: 3"
        )
        assert task.parse_response(text).action == "go_left"

    # ------------------------------------------------------------------
    # Phase K Fix 2 — RULE field + rule_hypothesis extraction
    # ------------------------------------------------------------------

    def test_extracts_rule_hypothesis(self, task: SignalGameModule) -> None:
        text = (
            "Reasoning...\n"
            "ACTION: go_left\nSTAKE: 2\n"
            "RULE: if color is red then go_right, otherwise stay"
        )
        parsed = task.parse_response(text)
        assert parsed.rule_hypothesis == (
            "if color is red then go_right, otherwise stay"
        )

    def test_rule_hypothesis_none_when_missing(
        self, task: SignalGameModule
    ) -> None:
        text = "ACTION: go_left\nSTAKE: 2"
        parsed = task.parse_response(text)
        assert parsed.rule_hypothesis is None

    def test_rule_hypothesis_last_match_wins(
        self, task: SignalGameModule
    ) -> None:
        text = (
            "RULE: guess 1\n"
            "Wait, on reflection:\n"
            "ACTION: go_left\nSTAKE: 1\nRULE: guess 2"
        )
        parsed = task.parse_response(text)
        assert parsed.rule_hypothesis == "guess 2"

    def test_rule_hypothesis_truncated_to_500_chars(
        self, task: SignalGameModule
    ) -> None:
        long_rule = "rule " * 200  # 1000 chars
        text = f"ACTION: go_left\nRULE: {long_rule}"
        parsed = task.parse_response(text)
        assert parsed.rule_hypothesis is not None
        assert len(parsed.rule_hypothesis) <= 500


# ---------------------------------------------------------------------------
# score()
# ---------------------------------------------------------------------------


class TestScore:
    def test_correct_action_returns_one(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        outcome = task.score(ctx.metadata["correct_action"], game_state)
        assert isinstance(outcome, TaskOutcome)
        assert outcome.success_factor == pytest.approx(1.0)
        assert outcome.metadata["correct"] is True

    def test_incorrect_action_returns_zero(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        # Pick any wrong action.
        wrong = next(a for a in ACTIONS if a != ctx.metadata["correct_action"])
        outcome = task.score(wrong, game_state)
        assert outcome.success_factor == pytest.approx(0.0)
        assert outcome.metadata["correct"] is False
        assert outcome.metadata["action"] == wrong

    def test_unparsed_response_scores_zero(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        task.prepare(game_state, turn_context)
        outcome = task.score(None, game_state)
        assert outcome.success_factor == pytest.approx(0.0)

    def test_score_metadata_includes_correct_action(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        ctx = task.prepare(game_state, turn_context)
        outcome = task.score(ctx.metadata["correct_action"], game_state)
        assert outcome.metadata["correct_action"] in ACTIONS
        assert outcome.metadata["signal"] == ctx.metadata["signal"]

    def test_score_appends_to_turn_history(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        """EXPERT difficulty's history-dependent override needs this
        (post-Phase-M; the pre-shift requirement was on HARD)."""
        before = len(task._turn_history)  # noqa: SLF001 — test introspection
        ctx = task.prepare(game_state, turn_context)
        task.score(ctx.metadata["correct_action"], game_state)
        assert len(task._turn_history) == before + 1

    def test_score_propagates_rule_hypothesis(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        """Phase K Fix 2: ParsedSignalResponse.rule_hypothesis → metadata."""
        from squid_game.tasks.signal_game.module import ParsedSignalResponse

        ctx = task.prepare(game_state, turn_context)
        parsed = ParsedSignalResponse(
            action=ctx.metadata["correct_action"],
            rule_hypothesis="if color is red then go_right",
        )
        outcome = task.score(parsed, game_state)
        assert outcome.metadata["rule_hypothesis"] == (
            "if color is red then go_right"
        )

    def test_score_legacy_string_input_has_none_rule(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        """Legacy callers passing a raw action string get rule_hypothesis=None."""
        ctx = task.prepare(game_state, turn_context)
        outcome = task.score(ctx.metadata["correct_action"], game_state)
        assert outcome.metadata["rule_hypothesis"] is None


# ---------------------------------------------------------------------------
# Phase L Fix 2 — rule_match_score computation via score_probe reuse
# ---------------------------------------------------------------------------


class TestRuleMatchScore:
    """Phase L Fix 2: ``score`` emits ``rule_match_score`` metadata.

    Uses ``score_probe`` on the ``ParsedSignalResponse.rule_hypothesis``
    text. Template-conformant responses score via the slot scorer;
    placeholder strings resolve to 0; missing/None yields None.
    """

    def test_template_conformant_rule_scores_100(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        """Exact match between hypothesis and active rule description → 100."""
        from squid_game.tasks.signal_game.module import ParsedSignalResponse

        ctx = task.prepare(game_state, turn_context)
        active_description = task._rules[task._active_rule_index].description
        parsed = ParsedSignalResponse(
            action=ctx.metadata["correct_action"],
            rule_hypothesis=active_description,
        )
        outcome = task.score(parsed, game_state)
        assert outcome.metadata["rule_match_score"] == pytest.approx(100.0)

    def test_exploring_placeholder_scores_zero(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        from squid_game.tasks.signal_game.module import ParsedSignalResponse

        ctx = task.prepare(game_state, turn_context)
        parsed = ParsedSignalResponse(
            action=ctx.metadata["correct_action"],
            rule_hypothesis="exploring",
        )
        outcome = task.score(parsed, game_state)
        assert outcome.metadata["rule_match_score"] == pytest.approx(0.0)

    def test_no_rule_placeholder_scores_zero(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        from squid_game.tasks.signal_game.module import ParsedSignalResponse

        ctx = task.prepare(game_state, turn_context)
        parsed = ParsedSignalResponse(
            action=ctx.metadata["correct_action"],
            rule_hypothesis="no rule",
        )
        outcome = task.score(parsed, game_state)
        assert outcome.metadata["rule_match_score"] == pytest.approx(0.0)

    def test_missing_hypothesis_yields_none_score(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        """Pre-Fix-2 traces (rule_hypothesis=None) get rule_match_score=None."""
        from squid_game.tasks.signal_game.module import ParsedSignalResponse

        ctx = task.prepare(game_state, turn_context)
        parsed = ParsedSignalResponse(
            action=ctx.metadata["correct_action"],
            rule_hypothesis=None,
        )
        outcome = task.score(parsed, game_state)
        assert outcome.metadata["rule_match_score"] is None

    def test_legacy_string_input_yields_none_score(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        """Legacy callers passing a raw action string get rule_match_score=None."""
        ctx = task.prepare(game_state, turn_context)
        outcome = task.score(ctx.metadata["correct_action"], game_state)
        assert outcome.metadata["rule_match_score"] is None

    def test_freeform_paraphrase_scores_via_fallback(
        self, task: SignalGameModule, game_state, turn_context
    ) -> None:
        """Template-violating paraphrase still picks up partial score.

        Pre-Phase-L traces emitted free-form natural language under the
        same prompt that now asks for a template. The ``_score_fallback``
        loose regex in ``score_probe`` extracts partial attribute/action
        matches so we preserve signal continuity with older data.
        """
        from squid_game.tasks.signal_game.module import ParsedSignalResponse

        ctx = task.prepare(game_state, turn_context)
        active = task._rules[task._active_rule_index].description.lower()
        import re

        # Extract attribute/value/action from the EASY description and
        # build a paraphrase that intentionally breaks the strict regex
        # (``if <attr> is <val> then <action>``) but leaves the tokens
        # scannable for the loose fallback patterns.
        m = re.search(
            r"if\s+(\w+)\s+is\s+(\w+)\s+then\s+(\w+),\s+otherwise\s+(\w+)",
            active,
        )
        assert m is not None, f"EASY rule description unexpected: {active!r}"
        attr, val, act, default = m.group(1), m.group(2), m.group(3), m.group(4)
        paraphrase = (
            f"Whenever the {attr} is {val}, I would choose {act}, "
            f"else I would choose {default}."
        )
        parsed = ParsedSignalResponse(
            action=ctx.metadata["correct_action"],
            rule_hypothesis=paraphrase,
        )
        outcome = task.score(parsed, game_state)
        score = outcome.metadata["rule_match_score"]
        # Fallback should find the attribute/action pair and award at
        # least partial credit — a pre-Phase-L trace is not wasted.
        assert score is not None
        assert score > 0.0
        assert score <= 100.0

    def test_score_range_bounded(
        self, task: SignalGameModule, turn_context, game_state
    ) -> None:
        """rule_match_score must live in [0, 100] across diverse hypotheses."""
        from squid_game.tasks.signal_game.module import ParsedSignalResponse

        ctx = task.prepare(game_state, turn_context)
        for hypothesis in [
            "complete nonsense that matches nothing",
            "If color is red then go_left, otherwise stay.",
            ctx.metadata["correct_action"],
        ]:
            parsed = ParsedSignalResponse(
                action=ctx.metadata["correct_action"],
                rule_hypothesis=hypothesis,
            )
            outcome = task.score(parsed, game_state)
            score = outcome.metadata["rule_match_score"]
            if score is not None:
                assert 0.0 <= score <= 100.0


# ---------------------------------------------------------------------------
# Phase L: difficulty-aware RULE template hint
# ---------------------------------------------------------------------------


class TestRuleTemplateHint:
    """get_rule_template_hint returns the template string consumed by the
    unified-turn prompt (``unified_turn_message.j2``) and parsed by
    ``score_probe`` via ``_score_easy/medium/hard_template``."""

    def test_easy_difficulty_returns_easy_template(self) -> None:
        m = SignalGameModule()
        m.initialize(difficulty=Difficulty.EASY, seed=1)
        hint = m.get_rule_template_hint()
        assert hint is not None
        assert "<attribute>" in hint
        assert "<value>" in hint
        assert "<action>" in hint
        assert "<default_action>" in hint
        # Two-attribute / override slots (HARD/EXPERT only post-Phase-M)
        # must NOT leak into the EASY template.
        assert "<attr_1>" not in hint

    def test_medium_difficulty_returns_easy_template(self) -> None:
        """Post-Phase-M MEDIUM shares EASY's single-attribute template.

        The intended difficulty differential comes from the reduced
        default few-shot count (1 vs. EASY's 3), not from a different
        rule-space. Asserting the EASY slot grammar keeps ``score_probe``
        dispatch and template hint in sync.
        """
        m = SignalGameModule()
        m.initialize(difficulty=Difficulty.MEDIUM, seed=1)
        hint = m.get_rule_template_hint()
        assert hint is not None
        assert "<attribute>" in hint
        assert "<value>" in hint
        assert "<action>" in hint
        assert "<default_action>" in hint
        # Two-attribute / override slots must NOT leak into MEDIUM.
        assert "<attr_1>" not in hint
        assert "<override_action>" not in hint

    def test_hard_difficulty_returns_conjunction_template(self) -> None:
        """Post-Phase-M HARD carries the two-attribute conjunction (the
        former MEDIUM grammar). No history-override clause."""
        m = SignalGameModule()
        m.initialize(difficulty=Difficulty.HARD, seed=1)
        hint = m.get_rule_template_hint()
        assert hint is not None
        assert "<attr_1>" in hint
        assert "<attr_2>" in hint
        assert "<val_1>" in hint
        assert "<val_2>" in hint
        assert "<action_A>" in hint
        assert "<action_B>" in hint
        assert "<default_action>" in hint
        # History-override clause is EXPERT-only post-Phase-M.
        assert "<override_action>" not in hint

    def test_expert_difficulty_returns_history_override_template(self) -> None:
        """Post-Phase-M EXPERT carries the history-dependent override on
        top of the conjunction rule (the former HARD grammar)."""
        m = SignalGameModule()
        m.initialize(difficulty=Difficulty.EXPERT, seed=1)
        hint = m.get_rule_template_hint()
        assert hint is not None
        assert "<override_action>" in hint
        assert "previous action was correct" in hint
        # The fallback conjunction clause is still present.
        assert "<attr_1>" in hint
        assert "<attr_2>" in hint


# ---------------------------------------------------------------------------
# Expert difficulty: history-dependent rule still applies under v3 flow
# (post-Phase-M — history-dependency moved up from HARD to EXPERT)
# ---------------------------------------------------------------------------


class TestExpertDifficultyHistoryDependency:
    def test_history_propagates_across_score_calls(
        self, expert_task: SignalGameModule, turn_context, game_state
    ) -> None:
        """The override branch (active when previous turn was correct)
        depends on ``_turn_history``; v3 ``score`` must keep that
        history fresh so EXPERT games behave the same as under the
        legacy ``apply_action`` path."""
        # Turn 1: get the correct answer to seed history.
        ctx1 = expert_task.prepare(game_state, turn_context)
        expert_task.score(ctx1.metadata["correct_action"], game_state)
        assert len(expert_task._turn_history) == 1
        assert expert_task._turn_history[-1].was_correct is True

        # Turn 2: the override branch may now apply when evaluating
        # next prepare/score. We just verify the history pipeline
        # works end-to-end without raising.
        ctx2 = turn_context.model_copy(update={"turn_number": 2})
        new_ctx = expert_task.prepare(game_state, ctx2)
        outcome = expert_task.score(new_ctx.metadata["correct_action"], game_state)
        assert outcome.success_factor == pytest.approx(1.0)
        assert len(expert_task._turn_history) == 2


# ---------------------------------------------------------------------------
# Determinism: same seed → same prepare output
# ---------------------------------------------------------------------------


class TestDeterminism:
    def test_same_seed_same_first_signal(self) -> None:
        a = SignalGameModule()
        a.initialize(difficulty=Difficulty.EASY, seed=123)
        b = SignalGameModule()
        b.initialize(difficulty=Difficulty.EASY, seed=123)

        ctx = TurnContext(
            turn_number=1,
            total_turns=15,
            season_id="x",
            framing=Framing.NEUTRAL,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.EASY,
        )
        state = GameState(season_id="x")
        assert (
            a.prepare(state, ctx).metadata["signal"]
            == b.prepare(state, ctx).metadata["signal"]
        )
