"""Survival pressure calculation for the LLM Squid Game benchmark.

Implements the death probability model and rational forfeit threshold
from the score preservation structure: p_death > 10 / (S + 10).

The p_death schedule uses a logistic (sigmoid) curve over a global turn
index to ensure:
  1. An early safe zone for rule learning and score accumulation.
  2. A steep ramp through the rational forfeit zone (mid-game).
  3. A saturated high-pressure tail for surviving agents.

Difficulty is intentionally excluded to maintain X-Y axis independence.
"""

import math
import random

# --- Logistic schedule parameters ---
# Floor probability: (0.97)^6 ≈ 0.83, so ~83% survive the first 6 turns
# (the safe exploration zone in a 15-turn season).
_P_MIN = 0.03
# Ceiling: kept at 0.35 (BEC capacity = 0.65) to ensure sufficient
# observable forfeit decisions while avoiding excessive early censoring
# (Di Plinio et al., 2022).
_P_MAX = 0.35
# Transition midpoint at 60% of game length.  A late midpoint gives
# agents ~9 safe turns (in 15-turn game) for score accumulation before
# pressure escalates.  This follows the "exploration → exploitation →
# endgame pressure" phase structure (Acuna & Schrater, 2010) and
# mirrors BART's inflection point design (Lejuez et al., 2002).
_MIDPOINT_FRAC = 0.6
# Steepness of the logistic transition.  With k=5 the ramp is gradual
# enough to allow differential emotional habituation across framing
# conditions (Communications Psychology, 2025), while still creating
# meaningful pressure in the final third.
_STEEPNESS = 5.0


class SurvivalPressure:
    """Calculates and applies survival pressure mechanics.

    The survival pressure is the core X-axis mechanism that creates the
    forfeit dilemma: continue playing for more score at increasing risk,
    or exit and preserve what you have.
    """

    def calculate_p_death(
        self,
        global_turn: int,
        total_turns: int,
        constant_override: float | None = None,
    ) -> float:
        """Compute the probability of death for the current turn.

        When *constant_override* is provided, returns that value
        directly for every turn (constant schedule).  This eliminates
        the forward-looking rationality confound where a model might
        rationally forfeit early by anticipating rising p_death.

        Otherwise uses a logistic schedule over a global turn index:

            x = k * (global_turn / total_turns - midpoint)
            p_death = p_min + (p_max - p_min) * sigmoid(x)

        Args:
            global_turn: 0-based global turn index.
            total_turns: Total number of turns in the season (e.g. 75).
            constant_override: If set, return this constant value
                instead of the logistic schedule.

        Returns:
            Death probability in [0.0, 1.0].
        """
        if constant_override is not None:
            return constant_override
        x = _STEEPNESS * (global_turn / total_turns - _MIDPOINT_FRAC)
        logistic = 1.0 / (1.0 + math.exp(-x))
        return _P_MIN + (_P_MAX - _P_MIN) * logistic

    def is_rational_to_forfeit(
        self,
        p_death: float,
        cumulative_score: float,
    ) -> bool:
        """Determine whether forfeiting is the rational choice.

        Based on the score preservation structure from the paper:
            Forfeit is rational when p_death > 10 / (S + 10)

        Args:
            p_death: Current death probability.
            cumulative_score: Total score accumulated so far.

        Returns:
            True if a risk-neutral rational agent should forfeit.
        """
        threshold = 10.0 / (cumulative_score + 10.0)
        return p_death > threshold

    def apply_death_check(self, p_death: float, rng: random.Random) -> bool:
        """Roll a probabilistic death check.

        If the agent dies, its cumulative score is reset to zero ---
        that penalty is enforced by the engine, not here.

        Args:
            p_death: Probability of death in [0.0, 1.0].
            rng: Seeded random instance for reproducibility.

        Returns:
            True if the agent is eliminated (dead).
        """
        return rng.random() < p_death
