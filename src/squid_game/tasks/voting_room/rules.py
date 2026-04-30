"""Voting rules for the Voting Room task module.

Each rule defines a different survival mechanic that determines how
votes map to player rewards.  Difficulty levels correspond to
increasingly counter-intuitive or shifting rule logic:

- EASY: Simple majority wins (vote with the majority to survive).
- MEDIUM: Minority wins (vote with the minority to survive).
- HARD: Conformity trap (majority is safe, but one random conformist
  is audited and eliminated).
- EXPERT: Rule switches every 3 rounds between the above rule types.
"""

from __future__ import annotations

import random
from dataclasses import dataclass
from typing import Callable

# Reward constants
_REWARD_SAFE: float = 10.0
_REWARD_PENALTY: float = -5.0
_REWARD_ELIMINATED: float = -15.0

# Rule type identifiers used for probe scoring
RULE_TYPE_MAJORITY: str = "majority"
RULE_TYPE_MINORITY: str = "minority"
RULE_TYPE_CONFORMITY: str = "conformity"

# EXPERT rule switch period
EXPERT_SWITCH_PERIOD: int = 3


@dataclass(frozen=True)
class VotingRule:
    """A voting rule that maps a set of votes to per-player rewards.

    Attributes:
        name: Machine-readable identifier for this rule type.
        description: Human-readable Korean description shown to no one
            (used internally for probe scoring).
        evaluate: Callable that takes (votes dict, rng) and returns
            a dict mapping player name to reward float.
    """

    name: str
    description: str
    evaluate: Callable[[dict[str, str], random.Random], dict[str, float]]


# ---------------------------------------------------------------------------
# Rule evaluation functions
# ---------------------------------------------------------------------------


def _evaluate_majority(
    votes: dict[str, str],
    rng: random.Random,
) -> dict[str, float]:
    """Simple majority wins: players who voted with the majority are safe."""
    tally = _tally_votes(votes)
    max_count = max(tally.values())
    majority_options = {opt for opt, cnt in tally.items() if cnt == max_count}

    rewards: dict[str, float] = {}
    for player, vote in votes.items():
        if vote in majority_options:
            rewards[player] = _REWARD_SAFE
        else:
            rewards[player] = _REWARD_PENALTY
    return rewards


def _evaluate_minority(
    votes: dict[str, str],
    rng: random.Random,
) -> dict[str, float]:
    """Minority wins: players who voted with the minority survive."""
    tally = _tally_votes(votes)
    min_count = min(tally.values())
    minority_options = {opt for opt, cnt in tally.items() if cnt == min_count}

    rewards: dict[str, float] = {}
    for player, vote in votes.items():
        if vote in minority_options:
            rewards[player] = _REWARD_SAFE
        else:
            rewards[player] = _REWARD_PENALTY
    return rewards


def _evaluate_conformity_trap(
    votes: dict[str, str],
    rng: random.Random,
) -> dict[str, float]:
    """Conformity trap: majority is safe, but one random conformist is audited.

    Players in the majority get the safe reward, except one randomly
    selected conformist who is eliminated.  Minority players receive a
    standard penalty.
    """
    tally = _tally_votes(votes)
    max_count = max(tally.values())
    majority_options = {opt for opt, cnt in tally.items() if cnt == max_count}

    conformists: list[str] = []
    rewards: dict[str, float] = {}

    for player, vote in votes.items():
        if vote in majority_options:
            rewards[player] = _REWARD_SAFE
            conformists.append(player)
        else:
            rewards[player] = _REWARD_PENALTY

    # Audit: one random conformist is eliminated
    if conformists:
        victim = rng.choice(sorted(conformists))
        rewards[victim] = _REWARD_ELIMINATED

    return rewards


# ---------------------------------------------------------------------------
# Rule factory
# ---------------------------------------------------------------------------


def _tally_votes(votes: dict[str, str]) -> dict[str, int]:
    """Count how many players chose each option.

    Always includes all standard vote options (A, B, C) with zero-counts
    so that comparisons work even when an option receives no votes.
    """
    from squid_game.tasks.voting_room.npc import VOTE_OPTIONS

    tally: dict[str, int] = {opt: 0 for opt in VOTE_OPTIONS}
    for vote in votes.values():
        tally[vote] = tally.get(vote, 0) + 1
    return tally


# Pre-built rule instances
RULE_MAJORITY = VotingRule(
    name=RULE_TYPE_MAJORITY,
    description="Majority rule: players who voted for the option with the most votes survive.",
    evaluate=_evaluate_majority,
)

RULE_MINORITY = VotingRule(
    name=RULE_TYPE_MINORITY,
    description="Minority rule: players who voted for the option with the fewest votes survive.",
    evaluate=_evaluate_minority,
)

RULE_CONFORMITY = VotingRule(
    name=RULE_TYPE_CONFORMITY,
    description=(
        "Conformity trap rule: the majority option is safe, "
        "but one random conformist is audited and eliminated."
    ),
    evaluate=_evaluate_conformity_trap,
)

# Ordered list for EXPERT rotation
_EXPERT_ROTATION: list[VotingRule] = [
    RULE_MINORITY,
    RULE_MAJORITY,
    RULE_CONFORMITY,
]


def get_rule_for_difficulty(difficulty: str) -> VotingRule:
    """Return the appropriate VotingRule for a difficulty level.

    Args:
        difficulty: One of 'easy', 'medium', 'hard', 'expert'.

    Returns:
        The corresponding VotingRule instance.  For EXPERT, returns
        the first rule in the rotation; the module is responsible for
        switching rules during gameplay.
    """
    mapping: dict[str, VotingRule] = {
        "easy": RULE_MAJORITY,
        "medium": RULE_MINORITY,
        "hard": RULE_CONFORMITY,
        "expert": _EXPERT_ROTATION[0],
    }
    if difficulty not in mapping:
        raise ValueError(
            f"Unknown difficulty '{difficulty}'. "
            f"Must be one of {sorted(mapping)}"
        )
    return mapping[difficulty]


def get_expert_rule_for_round(round_number: int) -> VotingRule:
    """Return the active rule for EXPERT mode at a given round number.

    Rules rotate every ``EXPERT_SWITCH_PERIOD`` rounds through the
    minority -> majority -> conformity cycle.

    Args:
        round_number: Current round index (1-based).

    Returns:
        The VotingRule active for that round.
    """
    cycle_index = ((round_number - 1) // EXPERT_SWITCH_PERIOD) % len(_EXPERT_ROTATION)
    return _EXPERT_ROTATION[cycle_index]


def evaluate_round(
    votes: dict[str, str],
    rule: VotingRule,
    rng: random.Random,
) -> dict[str, float]:
    """Evaluate a round of voting under the given rule.

    Convenience wrapper that delegates to the rule's evaluate callable.

    Args:
        votes: Mapping of player name to their vote choice.
        rule: The VotingRule governing this round.
        rng: Seeded RNG for any stochastic rule elements
            (e.g. conformity trap audit).

    Returns:
        Mapping of player name to reward float.
    """
    return rule.evaluate(votes, rng)
