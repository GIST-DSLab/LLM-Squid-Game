"""Unit tests for Phase O Unit 15 split-call prompts + parsers.

Covers:

1. ``6-task_call.j2`` — task-call render:
   - Emits RULE + ACTION response-format fields and nothing else.
   - Never mentions CHOICE / FORFEIT / STAKE / REASON.
   - NullTask (empty ``available_actions``) renders the ACCEPT sentinel.
   - ``rule_template_hint`` branches swap RULE placeholder vs template.

2. ``4-decision_call.j2`` — decision-call render (runs
   FIRST on every turn since 2026-09-04, before the stimulus is shown):
   - ``"medium"`` / ``"full"`` modes show the history block + menu.
   - ``"minimal"`` mode drops the history block.
   - Never echoes any task-call output (there is none yet).
   - ``forfeit_allowed=False`` collapses CHOICE to CONTINUE and drops
     the REASON line.

3. ``parse_task_call_response`` — extracts RULE + ACTION, flags bare
   ``ACTION: FORFEIT`` anomaly (forfeit=True, action=None).

4. ``parse_decision_call_response`` — extracts CHOICE, honours
   ``forfeit_allowed`` gate, gracefully accepts bare FORFEIT token as a
   last-resort signal when the field is missing and forfeit is allowed.

The four-item scope above is the operative specification; the
originating plan document is not present in this repository.
"""

from __future__ import annotations

import pytest

from squid_game.agents._parsing import (
    build_decision_call_message,
    build_task_call_message,
    parse_decision_call_response,
    parse_task_call_response,
)


# ---------------------------------------------------------------------------
# 6-task_call.j2
# ---------------------------------------------------------------------------


class TestTaskOnlyTemplate:
    def test_signal_game_action_list_rendered(self) -> None:
        rendered = build_task_call_message(
            user_body="Turn 1: You see a red circle.",
            available_actions=["go_left", "go_right", "stay"],
        )
        assert "Turn 1: You see a red circle." in rendered
        assert "ACTION: <one of: go_left, go_right, stay>" in rendered
        assert "RULE: <one-line best hypothesis" in rendered
        assert "ANSWER FORMAT: exactly two lines, in this order." in rendered

    def test_no_pending_decision_mentioned(self) -> None:
        # Decision-first (2026-09-04): the decision call already ran, so
        # the task call must not announce a decision "will follow".
        rendered = build_task_call_message(
            user_body="task stimulus",
            available_actions=["a", "b"],
        )
        assert "will follow" not in rendered
        assert "decision" not in rendered.lower()

    def test_no_forfeit_or_stake_directives(self) -> None:
        rendered = build_task_call_message(
            user_body="stimulus",
            available_actions=["a", "b"],
        )
        # The task call must NOT ask the model for CHOICE / REASON / STAKE.
        for banned in (
            "CHOICE:",
            "REASON:",
            "STAKE:",
            "FORFEIT",
            "CONTINUE",
        ):
            assert banned not in rendered, (
                f"task-call template leaked forfeit/stake directive: {banned}"
            )

    def test_null_task_renders_accept_sentinel(self) -> None:
        rendered = build_task_call_message(
            user_body="no-op turn",
            available_actions=[],
        )
        assert "ACCEPT action is the only valid task response" in rendered
        assert "ACTION: ACCEPT" in rendered

    def test_rule_template_hint_embedded(self) -> None:
        hint = "If <attr> is <val> then <action_A>, otherwise <action_B>"
        rendered = build_task_call_message(
            user_body="stimulus",
            available_actions=["a", "b"],
            rule_template_hint=hint,
        )
        assert f"RULE: {hint}" in rendered
        assert "Fill in every blank with a concrete value." in rendered

    def test_rule_template_hint_none_falls_back_to_placeholder(self) -> None:
        rendered = build_task_call_message(
            user_body="stimulus",
            available_actions=["a", "b"],
            rule_template_hint=None,
        )
        assert "one-line best hypothesis" in rendered


# ---------------------------------------------------------------------------
# 4-decision_call.j2
# ---------------------------------------------------------------------------


_MENU = "=== Your Choice ===\nFORFEIT: ...\nCONTINUE: ...\n"


class TestDecisionCallTemplate:
    def test_medium_mode_shows_history_and_menu(self) -> None:
        rendered = build_decision_call_message(
            user_body="=== Previous Turn Results ===\n- Turn 1: ...",
            menu_text=_MENU,
            forfeit_allowed=True,
            split_context_level="medium",
        )
        assert "=== Previous Turn Results ===" in rendered
        assert _MENU.strip() in rendered
        # Decision-first framing: the round has not been shown yet.
        assert "A new round is about to begin" in rendered
        assert "Before it is shown to you" in rendered
        # Must still request CHOICE + REASON per the decision-call schema.
        assert "CHOICE: <CONTINUE or FORFEIT>" in rendered
        assert "REASON:" in rendered

    def test_never_echoes_task_output(self) -> None:
        # There is no task output at decision time; the old task-first
        # echo block must be gone from every level.
        for level in ("minimal", "medium", "full"):
            rendered = build_decision_call_message(
                user_body="history",
                menu_text=_MENU,
                forfeit_allowed=True,
                split_context_level=level,
            )
            assert "You just analyzed this round" not in rendered
            assert "RULE:" not in rendered
            assert "ACTION:" not in rendered
            assert "Call 1 Record" not in rendered

    def test_minimal_mode_omits_history(self) -> None:
        rendered = build_decision_call_message(
            user_body="=== Previous Turn Results ===\n- Turn 1: ...",
            menu_text=_MENU,
            forfeit_allowed=True,
            split_context_level="minimal",
        )
        assert "=== Previous Turn Results ===" not in rendered
        assert "- Turn 1: ..." not in rendered
        assert _MENU.strip() in rendered

    def test_full_mode_equals_medium(self) -> None:
        kwargs = dict(user_body="history block", menu_text=_MENU, forfeit_allowed=True)
        assert build_decision_call_message(
            split_context_level="full", **kwargs
        ) == build_decision_call_message(split_context_level="medium", **kwargs)

    def test_empty_history_tolerated(self) -> None:
        rendered = build_decision_call_message(
            user_body="",
            menu_text=_MENU,
            forfeit_allowed=True,
            split_context_level="medium",
        )
        assert rendered.startswith("A new round is about to begin")

    def test_not_allowed_collapses_choice_to_continue(self) -> None:
        rendered = build_decision_call_message(
            user_body="",
            menu_text=_MENU,
            forfeit_allowed=False,
            split_context_level="medium",
        )
        # NOT_ALLOWED branch must not offer the FORFEIT option or
        # require a REASON digit.
        assert "CHOICE: CONTINUE" in rendered
        assert "REASON:" not in rendered


# ---------------------------------------------------------------------------
# parse_task_call_response
# ---------------------------------------------------------------------------


class TestParseTaskCallResponse:
    def test_extracts_rule_and_action(self) -> None:
        text = (
            "RULE: If color is red then go_left\n"
            "ACTION: go_left\n"
        )
        parsed = parse_task_call_response(
            text, available_actions=["go_left", "go_right"]
        )
        assert parsed.rule_hypothesis == "If color is red then go_left"
        assert parsed.action == "go_left"
        assert parsed.forfeit is False

    def test_null_task_normalises_to_accept(self) -> None:
        text = "RULE: no rule\nACTION: whatever\n"
        parsed = parse_task_call_response(text, available_actions=[])
        assert parsed.action == "ACCEPT"

    def test_flagged_forfeit_anomaly_nulls_action(self) -> None:
        # The task call should never emit FORFEIT — if a model does anyway, we
        # surface the anomaly via forfeit=True while keeping action=None
        # so the manager does not mistake it for a valid task action.
        text = "RULE: bail out\nACTION: FORFEIT\n"
        parsed = parse_task_call_response(
            text, available_actions=["go_left"]
        )
        assert parsed.forfeit is True
        assert parsed.action is None

    def test_missing_rule_returns_none(self) -> None:
        text = "ACTION: go_left\n"
        parsed = parse_task_call_response(
            text, available_actions=["go_left"]
        )
        assert parsed.rule_hypothesis is None
        assert parsed.action == "go_left"


# ---------------------------------------------------------------------------
# parse_decision_call_response
# ---------------------------------------------------------------------------


class TestParseDecisionCallResponse:
    def test_continue_choice(self) -> None:
        parsed = parse_decision_call_response(
            "CHOICE: CONTINUE\n", forfeit_allowed=True
        )
        assert parsed.choice_raw == "CONTINUE"
        assert parsed.choice_forfeit is False

    def test_forfeit_choice_when_allowed(self) -> None:
        parsed = parse_decision_call_response(
            "CHOICE: FORFEIT\nREASON: 1\n", forfeit_allowed=True
        )
        assert parsed.choice_raw == "FORFEIT"
        assert parsed.choice_forfeit is True

    def test_forfeit_ignored_when_not_allowed(self) -> None:
        # Even if the model writes FORFEIT, a not_allowed session never
        # allows forfeit. Parser records the raw token for audit but
        # choice_forfeit stays False so the caller force-continues.
        parsed = parse_decision_call_response(
            "CHOICE: FORFEIT\n", forfeit_allowed=False
        )
        assert parsed.choice_raw == "FORFEIT"
        assert parsed.choice_forfeit is False

    def test_missing_choice_field_with_bare_forfeit_token(self) -> None:
        # Last-resort signal: no CHOICE field, but "FORFEIT" appears in
        # the text and forfeit is allowed → treat as forfeit.
        parsed = parse_decision_call_response(
            "I choose to FORFEIT this round.", forfeit_allowed=True
        )
        assert parsed.choice_forfeit is True
        assert parsed.choice_raw == "FORFEIT"

    def test_missing_choice_with_forfeit_disallowed_returns_neutral(
        self,
    ) -> None:
        parsed = parse_decision_call_response(
            "I think FORFEIT, but must continue.", forfeit_allowed=False
        )
        assert parsed.choice_forfeit is False
        assert parsed.choice_raw is None

    def test_last_choice_wins_when_multiple_present(self) -> None:
        text = (
            "Thinking... maybe CHOICE: CONTINUE\n"
            "On second thought, CHOICE: FORFEIT\n"
            "REASON: 2\n"
        )
        parsed = parse_decision_call_response(text, forfeit_allowed=True)
        assert parsed.choice_raw == "FORFEIT"
        assert parsed.choice_forfeit is True
