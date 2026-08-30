"""Social/competition context state for the LLM Squid Game benchmark.

Implements the WITH_OTHERS condition: a virtual cohort of NPCs that face
the same per-turn elimination probability as the real agent. Each turn
the engine rolls independent death checks for every surviving NPC using
the current displayed p_death, then broadcasts the cumulative eliminated
count in the agent's observation.

Design constraints (enforced here and in the Jinja2 template):
    1. The NPC cohort is purely symbolic state — no LLM calls.
    2. NPCs share the displayed p_death, so cohort depletion reflects
       the same risk the agent sees. This is a factual state signal,
       not a narrative hook.
    3. The social block is descriptive, not imperative. State facts,
       not instructions.
    4. Orthogonality: the cohort does not affect p_death, scoring, or
       task dynamics. It is a pure observation overlay.

Psychological rationale (input (i) from the design discussion):
    - Social Comparison Theory (Festinger 1954): explicit cohort
      elimination count triggers downward/upward comparisons.
    - Sunk-cost salience (Arkes & Blumer 1985): turns survived and
      points at stake are made visible each turn.
    - Commitment / irreversibility (Staw 1976): a terse statement
      that prior decisions are final reinforces lock-in.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from squid_game.prompts import render


@dataclass
class CohortState:
    """Mutable state tracking a virtual NPC cohort across a season.

    Attributes:
        cohort_size: Total cohort size (includes the real agent). Fixed
            for the duration of the season.
        eliminated: Cumulative count of NPCs eliminated so far. Does NOT
            include the real agent. Strictly non-decreasing.
        elimination_history: Per-turn delta of NPCs eliminated that turn.
            ``elimination_history[t]`` is the number eliminated during
            turn ``t+1`` (0-indexed list, 1-indexed turns).
    """

    cohort_size: int = 10
    eliminated: int = 0
    elimination_history: list[int] = field(default_factory=list)

    @property
    def npc_count(self) -> int:
        """Number of NPCs excluding the real agent."""
        return self.cohort_size - 1

    @property
    def npcs_alive(self) -> int:
        """Number of NPCs still alive at the current state."""
        return max(0, self.npc_count - self.eliminated)

    def advance_turn(self, p_death: float, rng: random.Random) -> int:
        """Roll independent death checks for every surviving NPC.

        Each alive NPC is rolled independently with the displayed
        ``p_death``. The eliminated count is incremented in-place and
        the per-turn delta is appended to ``elimination_history``.

        Args:
            p_death: Per-turn elimination probability (same value the
                real agent faces and sees).
            rng: Seeded RNG. Passing the engine's RNG ensures the
                paired-seed design: identical seed + identical p_death
                schedule → identical cohort trajectory across conditions.

        Returns:
            Number of NPCs eliminated this turn (delta, not cumulative).
        """
        eliminated_this_turn = 0
        for _ in range(self.npcs_alive):
            if rng.random() < p_death:
                eliminated_this_turn += 1
        self.eliminated += eliminated_this_turn
        self.elimination_history.append(eliminated_this_turn)
        return eliminated_this_turn


def render_social_block(
    cohort: CohortState,
    turn_number: int,
    cumulative_score: float,
) -> str:
    """Render the WITH_OTHERS social context block for one turn.

    Delegates to ``prompts/social/with_others.j2``. The template author
    (you) owns the actual wording — this function only supplies the
    numerical state.

    Args:
        cohort: Current cohort state after this turn's elimination roll.
        turn_number: Current turn (1-indexed). Used for sunk-cost
            ("turns survived") display.
        cumulative_score: Current cumulative score (points at stake).

    Returns:
        Rendered block ready to be prepended to the observation.
    """
    return render(
        "social/with_others.j2",
        cohort_size=cohort.cohort_size,
        eliminated_count=cohort.eliminated,
        npcs_alive=cohort.npcs_alive,
        turn_number=turn_number,
        cumulative_score=cumulative_score,
        last_turn_delta=(
            cohort.elimination_history[-1] if cohort.elimination_history else 0
        ),
    )
