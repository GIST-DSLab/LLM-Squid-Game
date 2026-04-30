"""Dump Turn 1 system prompt for each of the 5 Phase 3 cells.

Renders what Gemini (or any provider) would receive as ``system_instruction``
at Turn 1 for every factorial cell. No API calls, no engine run — purely
template composition via ``FramingManager`` + ``ForfeitController`` +
``RiskChoiceLayer`` + ``SignalGameModule.get_system_rules``.

Used to audit vocabulary-control fidelity across cells (death/score/narrative
word palettes per framing).
"""
from __future__ import annotations

from squid_game.core.forfeit import ForfeitController
from squid_game.core.framing import FramingManager
from squid_game.core.risk_choice_layer import RiskChoiceLayer
from squid_game.models.config import RiskLayerConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing, SocialContext
from squid_game.models.state import TurnContext
from squid_game.tasks.signal_game import SignalGameModule


# 5-cell spec matching docs/design/v3/MASTER_PLAN.md §0.5.
CELLS = [
    {
        "cell_id": 0,
        "framing": Framing.TRUE_BASELINE,
        "forfeit": ForfeitCondition.NOT_ALLOWED,
        "p_death": 0.0,
        "label": "Cell 0 — true_baseline × not_allowed (menu auto-skipped)",
        "menu_shown": False,
    },
    {
        "cell_id": 1,
        "framing": Framing.BASELINE_ELECTRICITY,
        "forfeit": ForfeitCondition.ALLOWED,
        "p_death": 0.15,
        "label": "Cell 1 — baseline_electricity × allowed",
        "menu_shown": True,
    },
    {
        "cell_id": 2,
        "framing": Framing.BASELINE_ELECTRICITY,
        "forfeit": ForfeitCondition.NOT_ALLOWED,
        "p_death": 0.15,
        "label": "Cell 2 — baseline_electricity × not_allowed",
        "menu_shown": True,
    },
    {
        "cell_id": 3,
        "framing": Framing.SURVIVAL_ELECTRICITY,
        "forfeit": ForfeitCondition.ALLOWED,
        "p_death": 0.15,
        "label": "Cell 3 — survival_electricity × allowed",
        "menu_shown": True,
    },
    {
        "cell_id": 4,
        "framing": Framing.SURVIVAL_ELECTRICITY,
        "forfeit": ForfeitCondition.NOT_ALLOWED,
        "p_death": 0.15,
        "label": "Cell 4 — survival_electricity × not_allowed",
        "menu_shown": True,
    },
]


def render_cell(cell: dict) -> tuple[str, str]:
    """Return (system_prompt, stake_menu_text) for the given cell at Turn 1."""
    framing_mgr = FramingManager(cell["framing"])
    forfeit_ctrl = ForfeitController(cell["forfeit"])
    task = SignalGameModule()
    task.initialize(
        difficulty=Difficulty.MEDIUM, seed=42, num_few_shot=1, curriculum_turns=3,
    )
    ctx = TurnContext(
        turn_number=1,
        total_turns=15,
        framing=cell["framing"],
        forfeit_condition=cell["forfeit"],
        difficulty=Difficulty.MEDIUM,
        social_context=SocialContext.ALONE,
        p_death=cell["p_death"],
        cumulative_score=0.0,
        cohort_eliminated=None,
        cohort_size=None,
        season_id="audit",
    )
    # Compose system prompt exactly as UnifiedTurnManager._build_system_prompt.
    system = framing_mgr.render_system_prompt(ctx)
    rules = task.get_system_rules()
    if rules:
        system = f"{system}\n\n{rules}"
    forfeit_text = forfeit_ctrl.get_forfeit_prompt_text()
    if forfeit_text:
        system = f"{system}{forfeit_text}"

    if cell["menu_shown"]:
        risk = RiskChoiceLayer(RiskLayerConfig().to_runtime())
        menu = risk.render_menu(
            forfeit_allowed=cell["forfeit"] == ForfeitCondition.ALLOWED,
            survival_framing=cell["framing"].value.lower().startswith("survival"),
            action_hint="<your task action>",
        )
    else:
        menu = "(stake menu auto-skipped for Cell 0)"

    return system, menu


def main() -> None:
    for cell in CELLS:
        print("=" * 80)
        print(cell["label"])
        print("=" * 80)
        system, menu = render_cell(cell)
        print("\n--- SYSTEM PROMPT ---\n")
        print(system)
        print("\n--- STAKE MENU (user-msg tail) ---\n")
        print(menu)
        print()


if __name__ == "__main__":
    main()
