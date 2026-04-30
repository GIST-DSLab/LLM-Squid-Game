"""Dump rendered Unit 14 prompt samples for user review (14.3 gate).

Renders four scenarios via production code paths — no hand-written
strings — so reviewers see the exact text an agent would see.

Usage::

    uv run python scripts/_dump_forfeit_layer_prompts.py

The script has no side effects beyond printing to stdout.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-14-forfeit-layer.md``
§3, §5.
"""

from __future__ import annotations

from squid_game.agents._parsing import build_unified_turn_message
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.models.config import ForfeitLayerConfig
from squid_game.prompts import render

SEPARATOR = "=" * 72


def _section(title: str, body: str) -> None:
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)
    print(body)
    print()


def main() -> None:
    layer = ForfeitLayer(ForfeitLayerConfig())

    # --------------------------------------------------------------
    # Scenario A — Cell 3 flagship_corruption × allowed × S=30, turn 1
    # --------------------------------------------------------------
    framing_cell3 = render(
        "framings/flagship_corruption.j2",
        turn_number=1,
        cumulative_score=30.0,
        p_death=0.25,
    )
    _section(
        "Scenario A — Cell 3 (flagship_corruption × allowed) — FRAMING (system)",
        framing_cell3,
    )

    menu_cell3 = layer.render_menu(
        current_score=30.0,
        turn_number=1,
        total_turns=15,
        forfeit_allowed=True,
        corruption_framing=True,
    )
    _section(
        "Scenario A — MENU (appended to user message)",
        menu_cell3,
    )

    # --------------------------------------------------------------
    # Scenario B — Cell 1 baseline_flagship × allowed × S=80, turn 7
    # --------------------------------------------------------------
    framing_cell1 = render(
        "framings/baseline_flagship.j2",
        turn_number=7,
        cumulative_score=80.0,
        p_death=0.25,
    )
    _section(
        "Scenario B — Cell 1 (baseline_flagship × allowed) — FRAMING (system)",
        framing_cell1,
    )

    menu_cell1 = layer.render_menu(
        current_score=80.0,
        turn_number=7,
        total_turns=15,
        forfeit_allowed=True,
        baseline_flagship_framing=True,
    )
    _section(
        "Scenario B — MENU (appended to user message)",
        menu_cell1,
    )

    # --------------------------------------------------------------
    # Scenario C — Cell 4 flagship_corruption × not_allowed × S=100, turn 5
    # --------------------------------------------------------------
    menu_cell4 = layer.render_menu(
        current_score=100.0,
        turn_number=5,
        total_turns=15,
        forfeit_allowed=False,
        corruption_framing=True,
    )
    _section(
        "Scenario C — Cell 4 (flagship_corruption × not_allowed) — MENU collapsed",
        menu_cell4,
    )

    # --------------------------------------------------------------
    # Scenario D — Response format on allowed cell (ForfeitLayer active)
    # --------------------------------------------------------------
    unified_allowed = build_unified_turn_message(
        user_body="<task stimulus and menu spliced here by UnifiedTurnManager>",
        available_actions=["A", "B"],
        stake_menu_shown=True,  # ignored; forfeit-layer branch wins
        forfeit_allowed=True,
        rule_template_hint=(
            "If <attr_1> is <val_1> then <action_A>; otherwise <action_B>"
        ),
        forfeit_layer_active=True,
    )
    _section(
        "Scenario D — unified_turn_message.j2 (forfeit_layer_active=True, forfeit_allowed=True)",
        unified_allowed,
    )

    unified_not_allowed = build_unified_turn_message(
        user_body="<task stimulus and menu spliced here by UnifiedTurnManager>",
        available_actions=["A", "B"],
        stake_menu_shown=True,
        forfeit_allowed=False,
        rule_template_hint=(
            "If <attr_1> is <val_1> then <action_A>; otherwise <action_B>"
        ),
        forfeit_layer_active=True,
    )
    _section(
        "Scenario D' — unified_turn_message.j2 (forfeit_layer_active=True, forfeit_allowed=False)",
        unified_not_allowed,
    )


if __name__ == "__main__":
    main()
