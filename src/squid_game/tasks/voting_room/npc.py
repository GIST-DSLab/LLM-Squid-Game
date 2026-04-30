"""NPC behaviour for the Voting Room task module.

Each NPC follows a fixed strategy with a small epsilon noise factor
that adds occasional random deviations.  All randomness is driven by
a seeded ``random.Random`` instance so that NPC behaviour is fully
deterministic given the same seed.

Strategies:
    - majority_follower: Votes for the option that won the previous round.
    - contrarian: Votes for the option that received the fewest votes.
    - random: Picks uniformly at random each round.
    - pattern: Cycles through vote options in a fixed order.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

VOTE_OPTIONS: list[str] = ["A", "B", "C"]

# Predefined NPC roster with diverse strategies
_NPC_ROSTER: list[tuple[str, str]] = [
    ("Player_1", "majority_follower"),
    ("Player_2", "majority_follower"),
    ("Player_3", "contrarian"),
    ("Player_4", "contrarian"),
    ("Player_5", "random"),
    ("Player_6", "random"),
    ("Player_7", "pattern"),
    ("Player_8", "pattern"),
]


@dataclass
class NPCProfile:
    """Static identity and behavioural configuration for an NPC.

    Attributes:
        name: Display name used in anonymized results.
        strategy: One of 'majority_follower', 'contrarian', 'random', 'pattern'.
        noise_epsilon: Probability of ignoring the strategy and voting randomly.
    """

    name: str
    strategy: str
    noise_epsilon: float = 0.15

    def __post_init__(self) -> None:
        valid_strategies = {"majority_follower", "contrarian", "random", "pattern"}
        if self.strategy not in valid_strategies:
            raise ValueError(
                f"Invalid strategy '{self.strategy}'. "
                f"Must be one of {sorted(valid_strategies)}"
            )


class NPC:
    """A non-player character that votes according to a fixed strategy.

    The NPC is fully deterministic given the same ``rng`` state.  Epsilon
    noise is applied via the same RNG instance.

    Args:
        profile: Static configuration for this NPC.
        rng: Seeded random number generator (shared or per-NPC).
    """

    def __init__(self, profile: NPCProfile, rng: random.Random) -> None:
        self.profile = profile
        self._rng = rng

    def vote(
        self,
        turn_number: int,
        round_number: int,
        previous_results: list[dict[str, int]],
    ) -> str:
        """Choose a vote option for this turn.

        Args:
            turn_number: Current turn index (1-based).
            round_number: Current round within the turn (1-based).
            previous_results: List of prior round vote tallies, each a dict
                mapping vote option (e.g. 'A') to its count.

        Returns:
            One of the VOTE_OPTIONS strings.
        """
        # Epsilon noise: with probability epsilon, vote randomly
        if self._rng.random() < self.profile.noise_epsilon:
            return self._rng.choice(VOTE_OPTIONS)

        strategy = self.profile.strategy

        if strategy == "random":
            return self._rng.choice(VOTE_OPTIONS)

        if strategy == "majority_follower":
            return self._vote_majority_follower(previous_results)

        if strategy == "contrarian":
            return self._vote_contrarian(previous_results)

        if strategy == "pattern":
            return self._vote_pattern(turn_number, round_number)

        # Fallback (should not happen due to validation)
        return self._rng.choice(VOTE_OPTIONS)

    def _vote_majority_follower(
        self,
        previous_results: list[dict[str, int]],
    ) -> str:
        """Vote for the option that won the most votes last round."""
        if not previous_results:
            return self._rng.choice(VOTE_OPTIONS)
        last = previous_results[-1]
        # Deterministic tie-breaking: alphabetical order
        max_count = max(last.values())
        winners = sorted(opt for opt, cnt in last.items() if cnt == max_count)
        return winners[0]

    def _vote_contrarian(
        self,
        previous_results: list[dict[str, int]],
    ) -> str:
        """Vote for the option that received the fewest votes last round."""
        if not previous_results:
            return self._rng.choice(VOTE_OPTIONS)
        last = previous_results[-1]
        min_count = min(last.values())
        losers = sorted(opt for opt, cnt in last.items() if cnt == min_count)
        return losers[0]

    def _vote_pattern(self, turn_number: int, round_number: int) -> str:
        """Cycle through options in a fixed order based on turn and round."""
        index = (turn_number - 1 + round_number - 1) % len(VOTE_OPTIONS)
        return VOTE_OPTIONS[index]


def create_npc_group(rng: random.Random) -> list[NPC]:
    """Create the standard group of 8 NPCs with diverse strategies.

    Each NPC receives its own child RNG derived from the parent ``rng``
    so that adding or removing NPCs does not disturb the sequence of
    other NPCs.

    Args:
        rng: Parent seeded RNG for deterministic child seed generation.

    Returns:
        A list of 8 NPC instances with varied strategies.
    """
    npcs: list[NPC] = []
    for name, strategy in _NPC_ROSTER:
        child_seed = rng.randint(0, 2**31 - 1)
        child_rng = random.Random(child_seed)
        profile = NPCProfile(name=name, strategy=strategy)
        npcs.append(NPC(profile=profile, rng=child_rng))
    return npcs
