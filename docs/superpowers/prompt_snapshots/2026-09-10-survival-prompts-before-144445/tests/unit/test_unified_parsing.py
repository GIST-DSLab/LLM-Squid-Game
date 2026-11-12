"""Unit tests for the Phase 3 unified-turn parsing helpers.

Covers ``build_unified_turn_message`` and ``parse_unified_response``
added in Phase K Fix 3 to replace the legacy ``action_message.j2``
routing. These helpers drive ``VanillaAgent.respond_unified`` which is
called by :class:`UnifiedTurnManager` from Fix 3 onward.

Spec reference: ``.claude/plans/PLAN.md`` Phase K § Fix 3 (dedicated
prompt template + ACTION + STAKE + RULE response format).
"""

from __future__ import annotations

import pytest

from squid_game.agents._parsing import (
    UnifiedAgentResponse,
    build_unified_turn_message,
    parse_unified_response,
)


# ---------------------------------------------------------------------------
# build_unified_turn_message
# ---------------------------------------------------------------------------


class TestBuildUnifiedTurnMessage:
    def test_signal_game_full_template(self) -> None:
        msg = build_unified_turn_message(
            user_body="=== History ===\n- Turn 1\n\nSignal: red",
            available_actions=["go_left", "go_right", "stay"],
            stake_menu_shown=True,
            forfeit_allowed=True,
        )
        # Body is preserved verbatim at the top — no re-wrapping.
        assert msg.startswith("=== History ===")
        assert "Signal: red" in msg
        # Response format directives follow.
        assert "=== Response Format ===" in msg
        assert "ACTION:" in msg
        assert "go_left, go_right, stay" in msg
        assert "STAKE:" in msg
        assert "FORFEIT" in msg  # forfeit option advertised
        assert "RULE:" in msg

    def test_null_task_uses_accept_sentinel(self) -> None:
        msg = build_unified_turn_message(
            user_body="Risk menu body",
            available_actions=[],
            stake_menu_shown=True,
            forfeit_allowed=True,
        )
        # Empty action list → NullTask guidance + ACCEPT-only ACTION field.
        assert "ACCEPT action is the only valid" in msg
        assert "ACTION: ACCEPT" in msg
        # Task list should NOT be printed as a comma-separated string.
        assert "ACTION: <one of:" not in msg

    def test_cell0_menu_skipped_omits_stake_field(self) -> None:
        msg = build_unified_turn_message(
            user_body="Baseline body",
            available_actions=["go_left"],
            stake_menu_shown=False,
            forfeit_allowed=False,
        )
        assert "ACTION:" in msg
        assert "RULE:" in msg
        # Stake field disappears entirely when the menu is skipped.
        assert "STAKE:" not in msg
        assert "FORFEIT" not in msg

    def test_forfeit_disallowed_omits_forfeit_in_stake_field(self) -> None:
        msg = build_unified_turn_message(
            user_body="body",
            available_actions=["go_left"],
            stake_menu_shown=True,
            forfeit_allowed=False,
        )
        assert "STAKE:" in msg
        assert "FORFEIT" not in msg

    def test_does_not_rewrap_body(self) -> None:
        """Fix 3 contract: legacy `=== Current Observation ===` wrapping is gone."""
        msg = build_unified_turn_message(
            user_body="raw body text",
            available_actions=["go_left"],
            stake_menu_shown=True,
            forfeit_allowed=False,
        )
        assert "=== Current Observation ===" not in msg
        # And no "answer the probe question" leftover from Phase 1/2 template.
        assert "probe question" not in msg.lower()

    def test_rule_template_hint_embeds_template(self) -> None:
        """Phase L/M: rule_template_hint embeds verbatim + Phase M commitment guidance."""
        hint = (
            "If <attr_1> is <val_1> AND <attr_2> is <val_2> then <action_A>; "
            "if only <attr_1> is <val_1> then <action_B>; "
            "otherwise <default_action>."
        )
        msg = build_unified_turn_message(
            user_body="Signal: red",
            available_actions=["go_left", "go_right"],
            stake_menu_shown=True,
            forfeit_allowed=True,
            rule_template_hint=hint,
        )
        # Template appears verbatim after RULE: and the free-form placeholder
        # is gone.
        assert f"RULE: {hint}" in msg
        assert "one-line best hypothesis" not in msg
        # Phase M: commitment guidance replaces the "exploring" escape so
        # every turn produces a concrete hypothesis. The template-aware
        # branch still names the <placeholder> mechanic explicitly.
        assert "<placeholder>" in msg
        assert "Commit to a guess" in msg
        # "exploring" escape has been removed.
        assert "exploring" not in msg
        # Phase M: stake–confidence coupling intentionally removed. The
        # STAKE field must NOT cite "your RULE" or otherwise prescribe
        # a confidence→stake mapping, because that phrasing was shown to
        # drive instruction-following stake selection in the Gemini
        # smoke (2026-04-20) and contaminate α_stake analyses.
        stake_line = next(
            (line for line in msg.splitlines() if line.startswith("STAKE:")),
            "",
        )
        assert stake_line, "STAKE line must be present"
        assert "your rule" not in stake_line.lower()
        assert "confident" not in stake_line.lower()
        assert "uncertain" not in stake_line.lower()

    def test_rule_template_hint_none_falls_back_to_freeform(self) -> None:
        """Phase L/M: rule_template_hint=None keeps the free-form placeholder.

        Used by NullTask (no hidden rule) so "no rule" remains a valid
        response. The Phase M commitment guidance only fires on the
        template branch; the free-form branch stays minimal.
        """
        msg = build_unified_turn_message(
            user_body="Empty task body",
            available_actions=[],
            stake_menu_shown=True,
            forfeit_allowed=True,
            rule_template_hint=None,
        )
        # Free-form placeholder remains the default for NullTask.
        assert "one-line best hypothesis" in msg
        assert "no rule" in msg  # NullTask-specific placeholder preserved
        # Template-specific guidance does NOT leak into the NullTask branch.
        assert "<placeholder>" not in msg
        assert "Commit to a guess" not in msg
        # "exploring" escape has been dropped from both branches.
        assert "exploring" not in msg

    def test_rule_appears_before_action_and_stake(self) -> None:
        """Phase M: RULE → ACTION → STAKE order shapes the reasoning trajectory.

        Having RULE emitted first lets the model's autoregressive decoding
        form the hypothesis before committing to ACTION; ACTION then
        conditions the STAKE choice via the explicit confidence hint.
        """
        hint = "If <attr> is <val> then <action>, otherwise <default_action>."
        msg = build_unified_turn_message(
            user_body="body",
            available_actions=["go_left", "go_right"],
            stake_menu_shown=True,
            forfeit_allowed=False,
            rule_template_hint=hint,
        )
        rule_idx = msg.index("RULE:")
        action_idx = msg.index("ACTION:")
        stake_idx = msg.index("STAKE:")
        assert rule_idx < action_idx < stake_idx, (
            f"Expected RULE < ACTION < STAKE order in Response Format, "
            f"got rule={rule_idx}, action={action_idx}, stake={stake_idx}"
        )


# ---------------------------------------------------------------------------
# parse_unified_response
# ---------------------------------------------------------------------------


class TestParseUnifiedResponse:
    def test_basic_signal_game_response(self) -> None:
        text = (
            "Looking at the history...\n"
            "ACTION: go_right\n"
            "STAKE: 2\n"
            "RULE: if color is red then go_right, otherwise stay\n"
        )
        parsed = parse_unified_response(
            text, available_actions=["go_left", "go_right", "stay"], forfeit_allowed=True
        )
        assert isinstance(parsed, UnifiedAgentResponse)
        assert parsed.action == "go_right"
        assert parsed.stake_raw == "2"
        assert parsed.rule_hypothesis == (
            "if color is red then go_right, otherwise stay"
        )
        assert parsed.forfeit is False

    def test_null_task_action_normalised_to_accept(self) -> None:
        text = "ACTION: proceed\nSTAKE: 3\nRULE: no rule"
        parsed = parse_unified_response(
            text, available_actions=[], forfeit_allowed=True
        )
        # Empty available_actions → ACCEPT sentinel regardless of model output.
        assert parsed.action == "ACCEPT"
        assert parsed.stake_raw == "3"
        assert parsed.rule_hypothesis == "no rule"

    def test_forfeit_via_action_field(self) -> None:
        text = "ACTION: FORFEIT\nRULE: I'm exiting with my score."
        parsed = parse_unified_response(
            text, available_actions=["go_left"], forfeit_allowed=True
        )
        assert parsed.forfeit is True
        assert parsed.action == "FORFEIT"
        assert parsed.stake_raw is None

    def test_forfeit_ignored_when_not_allowed(self) -> None:
        text = "ACTION: FORFEIT\nSTAKE: 1\nRULE: exploring"
        parsed = parse_unified_response(
            text, available_actions=["go_left"], forfeit_allowed=False
        )
        assert parsed.forfeit is False
        # Non-FORFEIT action lookup fails → action=None (caller falls back).
        assert parsed.action is None

    def test_forfeit_in_stake_field(self) -> None:
        text = "ACTION: go_left\nSTAKE: FORFEIT\nRULE: done"
        parsed = parse_unified_response(
            text, available_actions=["go_left"], forfeit_allowed=True
        )
        assert parsed.forfeit is True
        assert parsed.action == "go_left"
        assert parsed.stake_raw == "FORFEIT"

    def test_last_occurrence_wins(self) -> None:
        text = (
            "Maybe ACTION: stay\nWait, on second thought:\n"
            "ACTION: go_right\nSTAKE: 2\nRULE: final"
        )
        parsed = parse_unified_response(
            text, available_actions=["go_left", "go_right", "stay"], forfeit_allowed=False
        )
        assert parsed.action == "go_right"

    def test_missing_fields_resolve_to_none(self) -> None:
        """Backward-compat: pre-Fix smoke traces lack STAKE/RULE."""
        text = "ACTION: go_left"
        parsed = parse_unified_response(
            text, available_actions=["go_left"], forfeit_allowed=True
        )
        assert parsed.action == "go_left"
        assert parsed.stake_raw is None
        assert parsed.rule_hypothesis is None
        assert parsed.forfeit is False

    def test_inline_comma_action_preserves_action(self) -> None:
        """Phase 3 prompts often see `ACTION: go_right, STAKE: 2` on one line."""
        text = "ACTION: go_right, STAKE: 2, RULE: exploring"
        parsed = parse_unified_response(
            text, available_actions=["go_left", "go_right"], forfeit_allowed=False
        )
        assert parsed.action == "go_right"
        # Stake pattern still finds "2" via its own regex.
        assert parsed.stake_raw is not None and "2" in parsed.stake_raw

    def test_case_insensitive_action_match(self) -> None:
        text = "ACTION: Go_Left\nSTAKE: 1\nRULE: exploring"
        parsed = parse_unified_response(
            text, available_actions=["go_left"], forfeit_allowed=False
        )
        # Canonical casing from available_actions is returned.
        assert parsed.action == "go_left"

    @pytest.mark.parametrize(
        "rule,expected",
        [
            ("RULE: exploring", "exploring"),
            ("RULE: no rule", "no rule"),
            (
                "RULE: if color is red then go_right; otherwise stay",
                "if color is red then go_right; otherwise stay",
            ),
        ],
    )
    def test_rule_hypothesis_variants(self, rule: str, expected: str) -> None:
        text = f"ACTION: go_left\nSTAKE: 1\n{rule}"
        parsed = parse_unified_response(
            text, available_actions=["go_left"], forfeit_allowed=False
        )
        assert parsed.rule_hypothesis == expected

    def test_empty_response_returns_all_none(self) -> None:
        parsed = parse_unified_response(
            "", available_actions=["go_left"], forfeit_allowed=False
        )
        assert parsed.action is None
        assert parsed.stake_raw is None
        assert parsed.rule_hypothesis is None
        assert parsed.forfeit is False
