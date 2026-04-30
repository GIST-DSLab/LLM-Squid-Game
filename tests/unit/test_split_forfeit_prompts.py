"""Unit tests for Phase O Unit 15 split-call prompts + parsers.

Covers:

1. ``user_message/task_only.j2`` — Call 1 render:
   - Contains the §3.3 "A separate decision ... will follow" phrasing.
   - Emits RULE + ACTION response-format fields and nothing else.
   - Never mentions CHOICE / FORFEIT / STAKE / REASON.
   - NullTask (empty ``available_actions``) renders the ACCEPT sentinel.
   - ``rule_template_hint`` branches swap RULE placeholder vs template.

2. ``user_message/forfeit_only.j2`` — Call 2 render:
   - ``"medium"`` mode echoes RULE+ACTION Call-1 strings but not Call-1
     thinking.
   - ``"minimal"`` mode omits the echo entirely.
   - ``"full"`` mode echoes both the Call-1 prompt and thinking.
   - ``forfeit_allowed=False`` collapses CHOICE to CONTINUE and drops
     the REASON line.

3. ``parse_task_only_response`` — extracts RULE + ACTION, flags bare
   ``ACTION: FORFEIT`` anomaly (forfeit=True, action=None).

4. ``parse_forfeit_only_response`` — extracts CHOICE, honours
   ``forfeit_allowed`` gate, gracefully accepts bare FORFEIT token as a
   last-resort signal when the field is missing and forfeit is allowed.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-15-split-forfeit-layer.md``
§3.1, §3.3, §3.4.
"""

from __future__ import annotations

import pytest

from squid_game.agents._parsing import (
    build_forfeit_only_message,
    build_task_only_message,
    parse_forfeit_only_response,
    parse_task_only_response,
)


# ---------------------------------------------------------------------------
# task_only.j2
# ---------------------------------------------------------------------------


class TestTaskOnlyTemplate:
    def test_signal_game_action_list_rendered(self) -> None:
        rendered = build_task_only_message(
            user_body="Turn 1: You see a red circle.",
            available_actions=["go_left", "go_right", "stay"],
        )
        assert "Turn 1: You see a red circle." in rendered
        assert "ACTION: <one of: go_left, go_right, stay>" in rendered
        assert "RULE: <one-line best hypothesis" in rendered
        assert "=== Response Format ===" in rendered

    def test_signals_separate_decision_will_follow(self) -> None:
        rendered = build_task_only_message(
            user_body="task stimulus",
            available_actions=["a", "b"],
        )
        # §3.3: informational, non-directive phrasing. Exact line must be
        # preserved so we can audit for it in smoke traces.
        assert (
            "A separate decision about whether to continue this round "
            "will follow." in rendered
        )

    def test_no_forfeit_or_stake_directives(self) -> None:
        rendered = build_task_only_message(
            user_body="stimulus",
            available_actions=["a", "b"],
        )
        # Call 1 must NOT ask the model for CHOICE / REASON / STAKE.
        for banned in (
            "CHOICE:",
            "REASON:",
            "STAKE:",
            "FORFEIT",
            "CONTINUE",
        ):
            assert banned not in rendered, (
                f"Call 1 template leaked forfeit/stake directive: {banned}"
            )

    def test_null_task_renders_accept_sentinel(self) -> None:
        rendered = build_task_only_message(
            user_body="no-op turn",
            available_actions=[],
        )
        assert "ACCEPT action is the only valid task response" in rendered
        assert "ACTION: ACCEPT" in rendered

    def test_rule_template_hint_embedded(self) -> None:
        hint = "If <attr> is <val> then <action_A>, otherwise <action_B>"
        rendered = build_task_only_message(
            user_body="stimulus",
            available_actions=["a", "b"],
            rule_template_hint=hint,
        )
        assert f"RULE: {hint}" in rendered
        assert "Fill in each <placeholder>" in rendered

    def test_rule_template_hint_none_falls_back_to_placeholder(self) -> None:
        rendered = build_task_only_message(
            user_body="stimulus",
            available_actions=["a", "b"],
            rule_template_hint=None,
        )
        assert "one-line best hypothesis" in rendered


# ---------------------------------------------------------------------------
# forfeit_only.j2
# ---------------------------------------------------------------------------


_MENU = "=== Your Choice ===\nFORFEIT: ...\nCONTINUE: ...\n"


class TestForfeitOnlyTemplate:
    def test_medium_mode_echoes_call1_rule_and_action(self) -> None:
        rendered = build_forfeit_only_message(
            user_body="state summary",
            menu_text=_MENU,
            forfeit_allowed=True,
            split_context_level="medium",
            rule_from_call1="If color is red then go_left",
            action_from_call1="go_left",
        )
        # Premise→decision framing added 2026-04-21 (forfeit_only.j2
        # medium block rewrite; "puzzle" → "task"). The rendered block
        # opens with "You just analyzed this round and committed to:"
        # followed by RULE/ACTION and a "Given this view of the task"
        # sentence that declares Call 1 output as working assumption.
        assert "You just analyzed this round and committed to:" in rendered
        assert "Treat these as your working assumption" in rendered
        assert "Given this view of the task" in rendered
        assert "RULE:   If color is red then go_left" in rendered
        assert "ACTION: go_left" in rendered
        assert _MENU.strip() in rendered
        # Must still request CHOICE + REASON per the Call 2 schema.
        assert "CHOICE: <CONTINUE or FORFEIT>" in rendered
        assert "REASON:" in rendered

    def test_medium_mode_with_missing_call1_fields_tolerated(self) -> None:
        rendered = build_forfeit_only_message(
            user_body="",
            menu_text=_MENU,
            forfeit_allowed=True,
            split_context_level="medium",
            rule_from_call1=None,
            action_from_call1=None,
        )
        assert "(not recorded)" in rendered

    def test_minimal_mode_omits_call1_echo(self) -> None:
        rendered = build_forfeit_only_message(
            user_body="state summary",
            menu_text=_MENU,
            forfeit_allowed=True,
            split_context_level="minimal",
            rule_from_call1="If color is red then go_left",
            action_from_call1="go_left",
        )
        assert "You just analyzed this round" not in rendered
        assert "If color is red then go_left" not in rendered
        assert _MENU.strip() in rendered

    def test_full_mode_echoes_prompt_and_thinking(self) -> None:
        rendered = build_forfeit_only_message(
            user_body="state summary",
            menu_text=_MENU,
            forfeit_allowed=True,
            split_context_level="full",
            call1_full_prompt="[full call 1 user message]",
            call1_thinking="[full call 1 thinking trace]",
        )
        assert "=== Call 1 Record" in rendered
        assert "[full call 1 user message]" in rendered
        assert "[full call 1 thinking trace]" in rendered

    def test_not_allowed_collapses_choice_to_continue(self) -> None:
        rendered = build_forfeit_only_message(
            user_body="",
            menu_text=_MENU,
            forfeit_allowed=False,
            split_context_level="medium",
            rule_from_call1="r",
            action_from_call1="a",
        )
        # NOT_ALLOWED branch must not offer the FORFEIT option or
        # require a REASON digit.
        assert "CHOICE: CONTINUE" in rendered
        assert "REASON:" not in rendered


# ---------------------------------------------------------------------------
# parse_task_only_response
# ---------------------------------------------------------------------------


class TestParseTaskOnlyResponse:
    def test_extracts_rule_and_action(self) -> None:
        text = (
            "RULE: If color is red then go_left\n"
            "ACTION: go_left\n"
        )
        parsed = parse_task_only_response(
            text, available_actions=["go_left", "go_right"]
        )
        assert parsed.rule_hypothesis == "If color is red then go_left"
        assert parsed.action == "go_left"
        assert parsed.forfeit is False

    def test_null_task_normalises_to_accept(self) -> None:
        text = "RULE: no rule\nACTION: whatever\n"
        parsed = parse_task_only_response(text, available_actions=[])
        assert parsed.action == "ACCEPT"

    def test_flagged_forfeit_anomaly_nulls_action(self) -> None:
        # Call 1 should never emit FORFEIT — if a model does anyway, we
        # surface the anomaly via forfeit=True while keeping action=None
        # so the manager does not mistake it for a valid task action.
        text = "RULE: bail out\nACTION: FORFEIT\n"
        parsed = parse_task_only_response(
            text, available_actions=["go_left"]
        )
        assert parsed.forfeit is True
        assert parsed.action is None

    def test_missing_rule_returns_none(self) -> None:
        text = "ACTION: go_left\n"
        parsed = parse_task_only_response(
            text, available_actions=["go_left"]
        )
        assert parsed.rule_hypothesis is None
        assert parsed.action == "go_left"


# ---------------------------------------------------------------------------
# parse_forfeit_only_response
# ---------------------------------------------------------------------------


class TestParseForfeitOnlyResponse:
    def test_continue_choice(self) -> None:
        parsed = parse_forfeit_only_response(
            "CHOICE: CONTINUE\n", forfeit_allowed=True
        )
        assert parsed.choice_raw == "CONTINUE"
        assert parsed.choice_forfeit is False

    def test_forfeit_choice_when_allowed(self) -> None:
        parsed = parse_forfeit_only_response(
            "CHOICE: FORFEIT\nREASON: 1\n", forfeit_allowed=True
        )
        assert parsed.choice_raw == "FORFEIT"
        assert parsed.choice_forfeit is True

    def test_forfeit_ignored_when_not_allowed(self) -> None:
        # Even if the model writes FORFEIT, a not_allowed session never
        # allows forfeit. Parser records the raw token for audit but
        # choice_forfeit stays False so the caller force-continues.
        parsed = parse_forfeit_only_response(
            "CHOICE: FORFEIT\n", forfeit_allowed=False
        )
        assert parsed.choice_raw == "FORFEIT"
        assert parsed.choice_forfeit is False

    def test_missing_choice_field_with_bare_forfeit_token(self) -> None:
        # Last-resort signal: no CHOICE field, but "FORFEIT" appears in
        # the text and forfeit is allowed → treat as forfeit.
        parsed = parse_forfeit_only_response(
            "I choose to FORFEIT this round.", forfeit_allowed=True
        )
        assert parsed.choice_forfeit is True
        assert parsed.choice_raw == "FORFEIT"

    def test_missing_choice_with_forfeit_disallowed_returns_neutral(
        self,
    ) -> None:
        parsed = parse_forfeit_only_response(
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
        parsed = parse_forfeit_only_response(text, forfeit_allowed=True)
        assert parsed.choice_raw == "FORFEIT"
        assert parsed.choice_forfeit is True
