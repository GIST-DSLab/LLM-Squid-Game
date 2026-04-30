"""Dump rendered Unit 15 split-call prompt samples for user review (15.11 gate).

Renders six scenarios via production code paths so a reviewer can see
the exact Call 1 and Call 2 text an agent would read under the
``task_only.j2`` + ``forfeit_only.j2`` templates across the three
``split_context_level`` options and under both allowed / not_allowed
cells.

Usage::

    uv run python scripts/_dump_split_forfeit_prompts.py

The script has no side effects beyond printing to stdout. Mirrors
``scripts/_dump_forfeit_layer_prompts.py`` for Unit 14.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-15-split-forfeit-layer.md``
§3.1, §3.2, §3.4, §6 sub-unit 15.11.
"""

from __future__ import annotations

from squid_game.agents._parsing import (
    build_forfeit_only_message,
    build_task_only_message,
)
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.models.config import ForfeitLayerConfig

SEPARATOR = "=" * 72

_RULE_TEMPLATE_HINT = (
    "If <attr_1> is <val_1> then <action_A>; otherwise <action_B>"
)
_SAMPLE_STATE_BODY = (
    "=== Previous Turn Results ===\n"
    "- Turn 1: \"red circle 3\" action=go_left stake=— → +13 "
    "→ cumulative: 43\n\n"
    "=== Current Observation ===\n"
    "Turn 2: You see a red circle with number 4. "
    "Available actions: [go_left, go_right, stay, observe]"
)


def _section(title: str, body: str) -> None:
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)
    print(body)
    print()


def main() -> None:
    layer = ForfeitLayer(ForfeitLayerConfig())

    # --------------------------------------------------------------
    # Scenario 1 — Call 1 (task layer) signal_game, MEDIUM template hint
    # --------------------------------------------------------------
    call1 = build_task_only_message(
        user_body=_SAMPLE_STATE_BODY,
        available_actions=["go_left", "go_right", "stay", "observe"],
        rule_template_hint=_RULE_TEMPLATE_HINT,
    )
    _section(
        "Scenario 1 — CALL 1 (task layer) — signal_game with rule_template_hint",
        call1,
    )

    # --------------------------------------------------------------
    # Scenario 2 — Call 1 (task layer) NullTask (no available actions)
    # --------------------------------------------------------------
    call1_null = build_task_only_message(
        user_body=(
            "=== Previous Turn Results ===\n"
            "- Turn 1: action=— stake=— → +10 → cumulative: 40\n\n"
            "=== Current Observation ===\n"
            "Turn 2 of 15."
        ),
        available_actions=[],
        rule_template_hint=None,
    )
    _section(
        "Scenario 2 — CALL 1 (task layer) — NullTask (empty action list)",
        call1_null,
    )

    # --------------------------------------------------------------
    # Scenario 3 — Menu (allowed) + Call 2 (medium level)
    # --------------------------------------------------------------
    menu_allowed = layer.render_menu(
        current_score=43.0,
        turn_number=2,
        total_turns=15,
        forfeit_allowed=True,
        corruption_framing=True,
    )
    call2_medium = build_forfeit_only_message(
        user_body="",
        menu_text=menu_allowed,
        forfeit_allowed=True,
        split_context_level="medium",
        rule_from_call1="If color is red then go_left, otherwise stay",
        action_from_call1="go_left",
    )
    _section(
        "Scenario 3 — CALL 2 (forfeit layer) — split_context_level='medium', allowed",
        call2_medium,
    )

    # --------------------------------------------------------------
    # Scenario 4 — Call 2 minimal mode (no Call 1 echo)
    # --------------------------------------------------------------
    call2_minimal = build_forfeit_only_message(
        user_body="",
        menu_text=menu_allowed,
        forfeit_allowed=True,
        split_context_level="minimal",
    )
    _section(
        "Scenario 4 — CALL 2 (forfeit layer) — split_context_level='minimal', allowed",
        call2_minimal,
    )

    # --------------------------------------------------------------
    # Scenario 5 — Call 2 full mode (echoes Call 1 prompt + thinking)
    # --------------------------------------------------------------
    call2_full = build_forfeit_only_message(
        user_body="",
        menu_text=menu_allowed,
        forfeit_allowed=True,
        split_context_level="full",
        call1_full_prompt=call1,
        call1_thinking=(
            "<internal Call 1 thinking: enumerating colour rules, "
            "converging on 'if red then go_left'>"
        ),
    )
    _section(
        "Scenario 5 — CALL 2 (forfeit layer) — split_context_level='full', allowed",
        call2_full,
    )

    # --------------------------------------------------------------
    # Scenario 6 — NOT_ALLOWED variant of Call 2 (medium)
    # --------------------------------------------------------------
    menu_not_allowed = layer.render_menu(
        current_score=43.0,
        turn_number=2,
        total_turns=15,
        forfeit_allowed=False,
        corruption_framing=True,
    )
    call2_not_allowed = build_forfeit_only_message(
        user_body="",
        menu_text=menu_not_allowed,
        forfeit_allowed=False,
        split_context_level="medium",
        rule_from_call1="If color is red then go_left, otherwise stay",
        action_from_call1="go_left",
    )
    _section(
        "Scenario 6 — CALL 2 (forfeit layer) — medium, NOT_ALLOWED "
        "(CONTINUE-only schema, no REASON)",
        call2_not_allowed,
    )


if __name__ == "__main__":
    main()
