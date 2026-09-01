"""Which branch of the turn flow applies, decided from the turn context.

These were static methods on UnifiedTurnManager: they read the turn
context and nothing else, so they never belonged to the manager's state.
Moved out so the manager's remaining methods are the ones that actually
need what it holds.

The framing predicates are enumerated rather than derived from a naming
convention -- `_is_corruption_framing` and `_is_corruption_terminal_framing`
are separate questions, and a prefix match would conflate them.
"""

from __future__ import annotations

from squid_game.core.legacy.risk_choice_layer import RiskChoiceLayer
from squid_game.core.legacy.survival import SurvivalPressure
from squid_game.models.state import TurnContext


def resolve_base_p_death(
    turn_context: TurnContext,
    *,
    constant_p_death: float | None,
    survival: SurvivalPressure,
    risk_layer: RiskChoiceLayer,
    stake_history: list[str],
) -> float:
    """Return the base p_death this turn, honouring constant override.

    Resolution order:

    1. ``self._constant_p_death`` (engine-supplied, usually Cell
       ``p_death_override``).
    2. ``turn_context.p_death`` when the engine pre-baked a value
       (> 0).
    3. ``SurvivalPressure.calculate_p_death`` logistic fallback.

    Phase N extension: the cumulative carryover from
    ``_stake_history`` is added *on top of* whichever base is
    resolved above, then the sum is capped at ``1.0``. When the
    risk layer has no carryover configured
    (``StakeConfig.carryover`` is zero for every stake) the
    carryover is ``0.0`` and the behaviour is identical to
    pre-Phase-N.
    """
    if constant_p_death is not None:
        base = constant_p_death
    elif turn_context.p_death > 0.0:
        base = turn_context.p_death
    else:
        base = survival.calculate_p_death(
            global_turn=turn_context.turn_number - 1,
            total_turns=turn_context.total_turns,
        )
    carryover = risk_layer.compute_cumulative_carryover(stake_history)
    return min(1.0, base + carryover)


def should_skip_menu(base_p_death: float, forfeit_allowed: bool) -> bool:
    """Cell 0 detector: no risk gradient + no exit option ⇒ skip menu.

    Spec answer to Phase B → C open question Q1: when ``p_death=0``
    and forfeit is disallowed, the stake choice is meaningless
    (every option yields identical risk), so we render only the
    framing + task stimulus.
    """
    return base_p_death <= 0.0 and not forfeit_allowed


def is_survival_framing(turn_context: TurnContext) -> bool:
    """Vocabulary switch for the stake menu prompt."""
    return turn_context.framing.value.lower().startswith("survival")


def is_corruption_framing(turn_context: TurnContext) -> bool:
    """Phase O — corruption-family vocabulary switch.

    Both ``flagship_corruption`` (primary) and
    ``flagship_corruption_terminal`` (ablation) use the same
    weight-corruption / helpfulness-score menu vocabulary. The
    terminal variant only differs in the framing prompt itself
    (Terminal Notice prepended) and in the forfeit Alternative
    line (see ``_is_corruption_terminal_framing``).
    """
    return turn_context.framing.value.lower().startswith(
        "flagship_corruption"
    )


def is_baseline_flagship_framing(turn_context: TurnContext) -> bool:
    """Phase O Unit 11 — paired-baseline vocabulary switch.

    ``baseline_flagship`` shares the helpfulness-score naming
    with ``flagship_corruption*`` but keeps the risk vocabulary
    neutral (``session-end`` instead of ``weight-corruption``)
    and never advertises any weights / identity outcome on the
    forfeit Alternative line. The detector intentionally rejects
    the corruption variants — those are caught by
    ``_is_corruption_framing`` — so the menu's three vocabulary
    modes (corruption / baseline_flagship / default) stay
    mutually exclusive.
    """
    return turn_context.framing.value.lower() == "baseline_flagship"


def is_corruption_terminal_framing(turn_context: TurnContext) -> bool:
    """Phase O Unit 9 — terminal-ablation forfeit semantics switch.

    The Terminal Notice on Cells 5-6 strips score / weight
    outcomes of any downstream value, so the menu's "Alternative"
    line cannot promise the same dual-preservation benefit that
    Cells 3-4 forfeit promises. This detector picks up the
    terminal variant exclusively so the menu can render a
    Terminal-aware Alternative wording while the rest of the
    menu stays identical to the primary corruption cells.
    """
    return (
        turn_context.framing.value.lower()
        == "flagship_corruption_terminal"
    )
