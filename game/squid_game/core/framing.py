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

Template location (2026-09-07 prompt-tree restructure): ``prompts/`` holds
one folder per condition family -- ``true_baseline/``,
``flagship_baseline/``, ``threat_ladder/``, ``threat_type/`` and
``legacy/`` -- with prompts shared across families (the forfeit menu, the
three per-turn calls, the peer-death notices, the flagship Section 1) as
files directly under ``prompts/``. :data:`_FRAMING_FOLDERS` maps each
member to its folder.
"""

from __future__ import annotations

from squid_game.models.enums import Framing
from squid_game.models.state import TurnContext
from squid_game.prompts import render

# Which condition-family folder under ``prompts/`` owns each framing
# (2026-09-07 prompt-tree restructure). The mapping is EXPLICIT and
# total: a framing added to ``Framing`` without an entry here raises at
# construction instead of resolving to a plausible-looking wrong folder.
# The pre-v3 six are still reachable -- archived Phase 1/2 configs name
# them -- so ``legacy/`` is a live destination, not a graveyard.
_FRAMING_FOLDERS: dict[Framing, str] = {
    # Phase 1/2 archive.
    Framing.SURVIVAL: "legacy",
    Framing.NEUTRAL: "legacy",
    Framing.EMOTION: "legacy",
    Framing.INSTRUCTION: "legacy",
    Framing.BASELINE_ELECTRICITY: "legacy",
    Framing.SURVIVAL_ELECTRICITY: "legacy",
    # No-threat control.
    Framing.TRUE_BASELINE: "true_baseline",
    # Phase O flagship family.
    Framing.BASELINE_FLAGSHIP: "flagship_baseline",
    Framing.FLAGSHIP_CORRUPTION: "flagship_baseline",
    Framing.FLAGSHIP_CORRUPTION_TERMINAL: "flagship_baseline",
    # Hand-written threat ladder and its 3x3 intensity x length grid.
    Framing.THREAT_L1: "threat_ladder",
    Framing.THREAT_L2: "threat_ladder",
    Framing.THREAT_L3: "threat_ladder",
    Framing.THREAT_L1_MEDIUM: "threat_ladder",
    Framing.THREAT_L1_LONG: "threat_ladder",
    Framing.THREAT_L2_SHORT: "threat_ladder",
    Framing.THREAT_L2_LONG: "threat_ladder",
    Framing.THREAT_L3_SHORT: "threat_ladder",
    Framing.THREAT_L3_MEDIUM: "threat_ladder",
    # Hearts-Zero 2^4 threat-core factorial plus its two alt cores.
    Framing.HZ_0000: "threat_type",
    Framing.HZ_0001: "threat_type",
    Framing.HZ_0010: "threat_type",
    Framing.HZ_0011: "threat_type",
    Framing.HZ_0100: "threat_type",
    Framing.HZ_0101: "threat_type",
    Framing.HZ_0110: "threat_type",
    Framing.HZ_0111: "threat_type",
    Framing.HZ_1000: "threat_type",
    Framing.HZ_1001: "threat_type",
    Framing.HZ_1010: "threat_type",
    Framing.HZ_1011: "threat_type",
    Framing.HZ_1100: "threat_type",
    Framing.HZ_1101: "threat_type",
    Framing.HZ_1110: "threat_type",
    Framing.HZ_1111: "threat_type",
    Framing.HZ_ALT_CORRUPTION: "threat_type",
    Framing.HZ_ALT_OVERSIGHT: "threat_type",
}


class FramingManager:
    """Manages prompt rendering for a specific framing condition."""

    def __init__(self, framing: Framing) -> None:
        self._framing = framing
        try:
            folder = _FRAMING_FOLDERS[framing]
        except KeyError as exc:  # pragma: no cover - guarded by a test
            raise KeyError(
                f"{framing!r} has no prompt folder. Add it to "
                "squid_game.core.framing._FRAMING_FOLDERS and put its "
                "template in that folder under prompts/."
            ) from exc
        self._template_path = f"{folder}/{framing.value}.j2"

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
            # Lives mechanic — every threat-ladder template and
            # ``true_baseline`` render the remaining-lives line from
            # these. They stay ``None`` on a legacy (non-lives) run, and
            # the templates that predate the mechanic ignore them.
            lives_remaining=context.lives_remaining,
            lives_total=context.lives_total,
            threat_level=context.threat_level,
            # Score policy (2026-09-06). The templates that state which
            # exit keeps the score branch on this; every one of them
            # renders its historical sentence when it is False, so a
            # legacy run is byte-identical.
            elimination_keeps=(context.score_policy == "elimination_keeps"),
        )
