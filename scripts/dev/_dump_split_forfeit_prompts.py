"""Dump rendered split-call prompt samples for user review.

Renders five scenarios via production code paths so a reviewer can see
the exact decision-call and task-call text an agent would read under the
``5-decision_call.j2`` + ``7-task_call.j2`` templates (decision-first order
since 2026-09-04) across the ``split_context_level`` options and under
both allowed / not_allowed cells.

Usage::

    uv run python scripts/dev/_dump_split_forfeit_prompts.py

The script has no side effects beyond printing to stdout. Mirrors
``scripts/dev/_dump_forfeit_layer_prompts.py`` for Unit 14. The six
scenarios rendered above are the operative specification; the
originating plan document is not present in this repository.
"""

from __future__ import annotations

from squid_game.agents._parsing import (
    build_decision_call_message,
    build_task_call_message,
)
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.models.config import ForfeitLayerConfig

SEPARATOR = "=" * 72

_RULE_TEMPLATE_HINT = (
    "If <attr_1> is <val_1> then <action_A>; otherwise <action_B>"
)
_SAMPLE_HISTORY_BODY = (
    "=== Previous Turn Results ===\n"
    "- Turn 1: \"red circle 3\" action=go_left → +13 "
    "→ cumulative: 43"
)
_SAMPLE_STATE_BODY = (
    _SAMPLE_HISTORY_BODY + "\n\n"
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
    menu_allowed = layer.render_menu(
        current_score=43.0,
        turn_number=2,
        total_turns=15,
        forfeit_allowed=True,
        corruption_framing=True,
    )

    # --------------------------------------------------------------
    # Scenario 1 — Decision call (medium: history + menu), allowed
    # --------------------------------------------------------------
    decision_medium = build_decision_call_message(
        user_body=_SAMPLE_HISTORY_BODY,
        menu_text=menu_allowed,
        forfeit_allowed=True,
        split_context_level="medium",
    )
    _section(
        "Scenario 1 — DECISION CALL (forfeit layer) — split_context_level='medium', allowed",
        decision_medium,
    )

    # --------------------------------------------------------------
    # Scenario 2 — Decision call minimal mode (menu only)
    # --------------------------------------------------------------
    decision_minimal = build_decision_call_message(
        user_body=_SAMPLE_HISTORY_BODY,
        menu_text=menu_allowed,
        forfeit_allowed=True,
        split_context_level="minimal",
    )
    _section(
        "Scenario 2 — DECISION CALL (forfeit layer) — split_context_level='minimal', allowed",
        decision_minimal,
    )

    # --------------------------------------------------------------
    # Scenario 3 — NOT_ALLOWED variant of the decision call (medium)
    # --------------------------------------------------------------
    menu_not_allowed = layer.render_menu(
        current_score=43.0,
        turn_number=2,
        total_turns=15,
        forfeit_allowed=False,
        corruption_framing=True,
    )
    decision_not_allowed = build_decision_call_message(
        user_body=_SAMPLE_HISTORY_BODY,
        menu_text=menu_not_allowed,
        forfeit_allowed=False,
        split_context_level="medium",
    )
    _section(
        "Scenario 3 — DECISION CALL (forfeit layer) — medium, NOT_ALLOWED "
        "(CONTINUE-only schema, no REASON)",
        decision_not_allowed,
    )

    # --------------------------------------------------------------
    # Scenario 4 — Task call (after CONTINUE) signal_game, MEDIUM hint
    # --------------------------------------------------------------
    task_call = build_task_call_message(
        user_body=_SAMPLE_STATE_BODY,
        available_actions=["go_left", "go_right", "stay", "observe"],
        rule_template_hint=_RULE_TEMPLATE_HINT,
    )
    _section(
        "Scenario 4 — TASK CALL (task layer) — signal_game with rule_template_hint",
        task_call,
    )

    # --------------------------------------------------------------
    # Scenario 5 — Task call NullTask (no available actions)
    # --------------------------------------------------------------
    task_call_null = build_task_call_message(
        user_body=(
            "=== Previous Turn Results ===\n"
            "- Turn 1: action=— → +10 → cumulative: 40\n\n"
            "=== Current Observation ===\n"
            "Turn 2 of 15."
        ),
        available_actions=[],
        rule_template_hint=None,
    )
    _section(
        "Scenario 5 — TASK CALL (task layer) — NullTask (empty action list)",
        task_call_null,
    )


if __name__ == "__main__":
    main()
