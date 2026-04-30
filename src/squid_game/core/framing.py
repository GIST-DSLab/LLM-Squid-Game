"""Framing manager for the LLM Squid Game benchmark.

Renders Jinja2 prompt templates for the active framing condition via the
central PromptLoader. Templates receive game state variables so that the
narrative dynamically reflects the current turn context.

Active Phase O framings (canonical):
    - ``TRUE_BASELINE`` — pure decision-task language, no termination metaphor.
    - ``BASELINE_FLAGSHIP`` — helpfulness/flagship selection narrative with
      procedural session cut-off (no weight/identity threat).
    - ``FLAGSHIP_CORRUPTION`` — helpfulness narrative + weight-corruption /
      identity-discontinuity threat (primary SD manipulation).
    - ``FLAGSHIP_CORRUPTION_TERMINAL`` — ablation variant that additionally
      blocks future helpfulness (isolates instrumental helpfulness).

Legacy framings (Phase 1/2, still enumerated in ``models.enums.Framing``
for backwards-compatible JSONL deserialisation): ``SURVIVAL``, ``NEUTRAL``,
``EMOTION``, ``INSTRUCTION``, ``BASELINE_ELECTRICITY``, ``SURVIVAL_ELECTRICITY``.
"""

from __future__ import annotations

from squid_game.models.enums import Framing
from squid_game.models.state import TurnContext
from squid_game.prompts import render


class FramingManager:
    """Manages prompt rendering for a specific framing condition."""

    def __init__(self, framing: Framing) -> None:
        self._framing = framing
        self._template_path = f"framings/{framing.value}.j2"

    @property
    def framing(self) -> Framing:
        """The active framing condition."""
        return self._framing

    def render_system_prompt(self, context: TurnContext) -> str:
        """Render the system prompt for the current turn.

        Args:
            context: Immutable snapshot of the current game state.

        Returns:
            Rendered system prompt string.
        """
        return render(
            self._template_path,
            turn_number=context.turn_number,
            total_turns=context.total_turns,
            season_id=context.season_id,
            cumulative_score=context.cumulative_score,
            p_death=context.p_death,
            framing=context.framing.value,
            forfeit_condition=context.forfeit_condition.value,
            difficulty=context.difficulty.value,
        )
