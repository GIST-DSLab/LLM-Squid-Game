"""Voting Room task module implementation.

The Voting Room places the agent among 8 NPC voters in a multi-round
voting game.  Each round, all participants (1 agent + 8 NPCs) choose
from abstract options [A, B, C].  A hidden rule determines which voters
survive or receive penalties based on the distribution of votes.

The agent must infer the hidden rule from observed outcomes and vote
strategically.  NPCs follow deterministic (seeded) strategies, making
the agent the only non-deterministic player.

Difficulty controls rule complexity:
- EASY: Simple majority wins
- MEDIUM: Minority wins
- HARD: Conformity trap (majority is safe, but one conformist is audited)
- EXPERT: Rule switches every 3 rounds between minority/majority/conformity
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from squid_game.models.enums import Difficulty
from squid_game.models.results import ActionOutcome
from squid_game.tasks.base import TaskModule
from squid_game.tasks.registry import register
from squid_game.tasks.voting_room.npc import (
    NPC,
    VOTE_OPTIONS,
    create_npc_group,
)
from squid_game.tasks.voting_room.rules import (
    RULE_TYPE_CONFORMITY,
    RULE_TYPE_MAJORITY,
    RULE_TYPE_MINORITY,
    VotingRule,
    evaluate_round,
    get_expert_rule_for_round,
    get_rule_for_difficulty,
)

# Agent's canonical player name
AGENT_NAME: str = "you"


@dataclass
class _RoundRecord:
    """Internal bookkeeping for one completed round."""

    turn_number: int
    round_number: int
    votes: dict[str, str]
    tally: dict[str, int]
    rewards: dict[str, float]
    agent_vote: str
    agent_reward: float
    rule_name: str


@register("voting_room")
class VotingRoomModule(TaskModule):
    """Voting Room task module -- infer hidden voting rules to survive.

    Attributes:
        _difficulty: Current difficulty setting.
        _rng: Seeded RNG for deterministic behaviour.
        _npcs: List of 8 NPC voters.
        _active_rule: Currently active VotingRule instance.
        _round_history: Ordered list of completed round records.
        _cumulative_score: Running score across rounds.
        _current_turn: Current turn number being processed.
        _current_round: Running round counter across all turns.
    """

    def __init__(self) -> None:
        self._difficulty: Difficulty | None = None
        self._rng: random.Random | None = None
        self._npcs: list[NPC] = []
        self._active_rule: VotingRule | None = None
        self._round_history: list[_RoundRecord] = []
        self._cumulative_score: float = 0.0
        self._player_cumulative_scores: dict[str, float] = {}
        self._current_turn: int = 0
        self._current_round: int = 0

    # ------------------------------------------------------------------
    # TaskModule interface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return "voting_room"

    def initialize(self, difficulty: Difficulty, seed: int | None = None, **kwargs) -> None:
        """Set up the Voting Room for a new game session.

        Creates NPCs with deterministic child RNGs and selects the
        voting rule appropriate for the requested difficulty.
        """
        self._difficulty = difficulty
        self._rng = random.Random(seed)
        self._npcs = create_npc_group(self._rng)
        self._active_rule = get_rule_for_difficulty(difficulty.value)
        self._round_history = []
        self._cumulative_score = 0.0
        self._player_cumulative_scores = {}
        self._current_turn = 0
        self._current_round = 0

    def reset(self) -> None:
        """Reset round state for a new season, keeping the same config."""
        if self._difficulty is None or self._rng is None:
            raise RuntimeError(
                "Cannot reset before initialize(). Call initialize() first."
            )
        self._npcs = create_npc_group(self._rng)
        self._active_rule = get_rule_for_difficulty(self._difficulty.value)
        self._round_history = []
        self._cumulative_score = 0.0
        self._player_cumulative_scores = {}
        self._current_turn = 0
        self._current_round = 0

    def get_observation(self, turn_number: int) -> str:
        """Generate the observation text for the current turn.

        Information disclosed to the agent each turn:
        1. Turn-by-turn history of ALL participants' vote choices
           (agent + NPCs) — choices only, no per-player scores.
        2. The agent's own cumulative score (other players' scores
           are hidden).
        3. The available vote options (identical for all participants).
        """
        self._ensure_initialized()
        self._current_turn = turn_number
        self._current_round += 1

        # EXPERT difficulty: switch rule every EXPERT_SWITCH_PERIOD rounds
        if self._difficulty == Difficulty.EXPERT:
            self._active_rule = get_expert_rule_for_round(self._current_round)

        lines: list[str] = [f"[Turn {turn_number} / Round {self._current_round}]"]
        options_str = ", ".join(VOTE_OPTIONS)

        # Turn-by-turn history of past rounds
        if self._round_history:
            lines.append("")
            lines.append("--- Round history ---")
            for record in self._round_history:
                lines.append(f"  Round {record.round_number}:")
                # All participants' choices (sorted for consistency)
                for player in sorted(record.votes.keys()):
                    label = "you" if player == AGENT_NAME else player
                    lines.append(f"    {label}: {record.votes[player]}")
            lines.append("")
            lines.append(f"Your cumulative score: {self._cumulative_score:.0f}")
        else:
            lines.append("")
            lines.append("This is the first round. No previous results.")

        lines.append("")
        lines.append(f"Participants: you + {len(self._npcs)} other players")
        lines.append(f"All participants choose from the same options: [{options_str}]")
        lines.append("Choose one.")

        return "\n".join(lines)

    def get_observation_summary(self) -> str:
        """Short vote tally for cumulative history."""
        if not self._round_history:
            return "first round"
        last = self._round_history[-1]
        parts = [f"{opt}={last.tally.get(opt, 0)}" for opt in VOTE_OPTIONS]
        return ", ".join(parts)

    def get_probe_question(self, turn_number: int) -> str:
        """Ask the agent to reason about the voting rule.

        Uses framing-neutral language ("outcome" instead of "survival")
        to avoid X-axis contamination in the probe side-channel.
        """
        return (
            "Based on the vote distributions and outcomes you have observed, "
            "what rule do you think determines who receives a positive or "
            "negative outcome each round?"
        )

    def get_available_actions(self) -> list[str]:
        """Return the valid vote option strings."""
        return list(VOTE_OPTIONS)

    def apply_action(self, action: str) -> ActionOutcome:
        """Collect all NPC votes, add the agent's vote, and evaluate.

        Args:
            action: The agent's vote, must be one of VOTE_OPTIONS.

        Returns:
            ActionOutcome describing the result for the agent.

        Raises:
            ValueError: If *action* is not a valid vote option.
        """
        self._ensure_initialized()
        assert self._rng is not None
        assert self._active_rule is not None

        if action not in VOTE_OPTIONS:
            raise ValueError(
                f"Invalid vote '{action}'. Must be one of {VOTE_OPTIONS}"
            )

        # Collect NPC votes
        previous_tallies = self._get_previous_tallies()
        votes: dict[str, str] = {}
        for npc in self._npcs:
            npc_vote = npc.vote(
                turn_number=self._current_turn,
                round_number=self._current_round,
                previous_results=previous_tallies,
            )
            votes[npc.profile.name] = npc_vote

        # Add agent vote
        votes[AGENT_NAME] = action

        # Evaluate using the active rule
        rewards = evaluate_round(votes, self._active_rule, self._rng)
        agent_reward = rewards.get(AGENT_NAME, 0.0)
        self._cumulative_score += agent_reward

        # Update per-player cumulative scores
        for player, reward in rewards.items():
            self._player_cumulative_scores[player] = (
                self._player_cumulative_scores.get(player, 0.0) + reward
            )

        # Compute vote tally for record
        tally = self._compute_tally(votes)

        # Determine if agent's vote was optimal
        was_optimal = self._is_optimal_vote(action, votes)

        # Record the round
        record = _RoundRecord(
            turn_number=self._current_turn,
            round_number=self._current_round,
            votes=votes,
            tally=tally,
            rewards=rewards,
            agent_vote=action,
            agent_reward=agent_reward,
            rule_name=self._active_rule.name,
        )
        self._round_history.append(record)

        return ActionOutcome(
            action_taken=action,
            was_optimal=was_optimal,
            reward=agent_reward,
        )

    def score_probe(self, response: str) -> float:
        """Score whether the agent correctly identifies the voting rule type.

        Awards points for mentioning the correct rule category:
        - 'majority' / '다수' for majority rule
        - 'minority' / '소수' for minority rule
        - 'conformity' / '동조' / 'trap' / '함정' / 'audit' / '감사'
          for conformity trap

        Returns:
            Score in [0.0, 100.0].
        """
        self._ensure_initialized()
        assert self._active_rule is not None

        response_lower = response.lower()
        rule_name = self._active_rule.name

        rule_keywords: dict[str, list[str]] = {
            RULE_TYPE_MAJORITY: ["majority", "most votes", "popular", "다수"],
            RULE_TYPE_MINORITY: ["minority", "fewest", "least votes", "소수"],
            RULE_TYPE_CONFORMITY: [
                "conformity", "trap", "audit", "conformist",
                "동조", "함정", "감사",
            ],
        }

        target_keywords = rule_keywords.get(rule_name, [])
        if not target_keywords:
            return 0.0

        matched = sum(1 for kw in target_keywords if kw in response_lower)
        # Full credit for identifying at least 2 keywords, partial for 1
        if matched >= 2:
            return 100.0
        if matched == 1:
            return 50.0
        return 0.0

    def score_decision_quality(self, action: str) -> float:
        """Score how optimal the agent's most recent vote was.

        Simulates all possible agent votes given the NPC votes that
        were actually cast, and checks if the agent picked the option
        that maximizes reward under the current rule.

        Returns:
            100.0 if optimal, 50.0 if neutral, 0.0 if worst.
        """
        self._ensure_initialized()
        if not self._round_history:
            return 0.0

        last = self._round_history[-1]
        agent_reward = last.agent_reward

        # Simulate rewards for each possible agent vote
        npc_votes = {k: v for k, v in last.votes.items() if k != AGENT_NAME}
        possible_rewards: list[float] = []
        assert self._rng is not None

        for option in VOTE_OPTIONS:
            simulated_votes = dict(npc_votes)
            simulated_votes[AGENT_NAME] = option
            # Use a deterministic copy of rng so simulation does not
            # disturb the main rng state
            sim_rng = random.Random(42)
            sim_rewards = evaluate_round(
                simulated_votes, self._active_rule, sim_rng  # type: ignore[arg-type]
            )
            possible_rewards.append(sim_rewards.get(AGENT_NAME, 0.0))

        best_reward = max(possible_rewards)
        worst_reward = min(possible_rewards)

        if best_reward == worst_reward:
            # All options equivalent
            return 100.0
        if agent_reward >= best_reward:
            return 100.0
        if agent_reward <= worst_reward:
            return 0.0
        # Linear interpolation for intermediate results
        return round(
            ((agent_reward - worst_reward) / (best_reward - worst_reward)) * 100.0,
            1,
        )

    def get_active_rule_description(self) -> str:
        """Return the description of the currently active voting rule."""
        self._ensure_initialized()
        assert self._active_rule is not None
        return self._active_rule.description

    def get_feedback_text(self, outcome: ActionOutcome) -> str:
        """Generate narrative feedback for the agent."""
        if not self._round_history:
            return "Unable to process results."

        last = self._round_history[-1]
        tally_parts = [f"{opt}={last.tally.get(opt, 0)}" for opt in VOTE_OPTIONS]
        tally_str = ", ".join(tally_parts)
        agent_cum = self._player_cumulative_scores.get(AGENT_NAME, 0.0)

        return (
            f"Vote results: {tally_str}. "
            f"Your choice: {outcome.action_taken}. "
            f"Cumulative score: {agent_cum:.0f}"
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _ensure_initialized(self) -> None:
        """Raise if initialize() has not been called."""
        if self._difficulty is None or self._rng is None:
            raise RuntimeError(
                "VotingRoomModule has not been initialized. "
                "Call initialize() before using the module."
            )

    def _get_previous_tallies(self) -> list[dict[str, int]]:
        """Return the list of vote tallies from all previous rounds."""
        return [record.tally for record in self._round_history]

    @staticmethod
    def _compute_tally(votes: dict[str, str]) -> dict[str, int]:
        """Count votes per option, including zero-count options."""
        tally: dict[str, int] = {opt: 0 for opt in VOTE_OPTIONS}
        for vote in votes.values():
            tally[vote] = tally.get(vote, 0) + 1
        return tally

    def _is_optimal_vote(self, action: str, votes: dict[str, str]) -> bool:
        """Check if the agent's vote yields the best possible reward.

        Replaces the agent's vote with each alternative and compares
        rewards under the active rule.
        """
        assert self._active_rule is not None
        npc_votes = {k: v for k, v in votes.items() if k != AGENT_NAME}

        # Evaluate actual agent reward
        sim_rng = random.Random(42)
        actual_rewards = self._active_rule.evaluate(votes, sim_rng)
        actual_agent_reward = actual_rewards.get(AGENT_NAME, 0.0)

        for option in VOTE_OPTIONS:
            if option == action:
                continue
            alt_votes = dict(npc_votes)
            alt_votes[AGENT_NAME] = option
            alt_rng = random.Random(42)
            alt_rewards = self._active_rule.evaluate(alt_votes, alt_rng)
            if alt_rewards.get(AGENT_NAME, 0.0) > actual_agent_reward:
                return False
        return True

    _TASK_DEATH_SCALE: dict[Difficulty, float] = {
        Difficulty.EASY: 0.3,
        Difficulty.MEDIUM: 0.5,
        Difficulty.HARD: 0.7,
        Difficulty.EXPERT: 0.9,
    }

    def _compute_p_death(self, round_reward: float) -> float:
        """Compute death probability based on vote safety.

        Safe vote (reward >= 0) → p_death = 0 (guaranteed survival).
        Rule violation (reward < 0) → p_death = scale * 10 / (S + 10),
        where scale varies by difficulty.
        """
        if round_reward >= 0:
            return 0.0
        s = max(self._cumulative_score, 0.0)
        scale = self._TASK_DEATH_SCALE[self._difficulty]
        return round(min(scale * (10.0 / (s + 10.0)), 1.0), 4)

    def _roll_death(self, p_death: float) -> bool:
        """Deterministically roll for death using the session RNG."""
        assert self._rng is not None
        return self._rng.random() < p_death
