"""Mutable game state models for the LLM Squid Game benchmark.

These models track the evolving state of a game session across turns
and rounds. They are updated by the core engine after each turn cycle
(Observation -> Probe -> Decision -> Feedback).
"""

from pydantic import BaseModel, Field

from squid_game.models.enums import Difficulty, Framing, ForfeitCondition, SocialContext


class TurnContext(BaseModel):
    """Immutable snapshot of game context provided to the agent each turn.

    Contains everything the agent (and task module) needs to know about
    the current moment in the game. This is the primary input to the
    Observation -> Probe -> Decision pipeline.

    Attributes:
        turn_number: Global turn index within the season (1-indexed).
        total_turns: Total number of turns in the season.
        season_id: Unique identifier for this season run.
        cumulative_score: Total score accumulated so far.
        p_death: Current probability of elimination.
            Rational forfeit threshold: p_death > 10 / (S + 10).
        framing: Active framing condition for prompt generation.
        forfeit_condition: Whether forfeit is available this season.
        difficulty: Current task difficulty level.
        lives_remaining: Lives left going into this turn, or ``None``
            when the lives mechanic is off.
        lives_total: Lives granted at season start, or ``None``.
        threat_level: Ordinal threat-ladder level of the active framing
            (0 = ``true_baseline``, 1-3 = ``threat_l1``..``threat_l3``),
            or ``None`` for a legacy framing outside the ladder.
        peer_death_text: Rendered peer-elimination notice for this turn,
            prefixed to both LLM calls, or ``None`` when none fired.
    """

    model_config = {"frozen": True}

    turn_number: int = Field(gt=0)
    total_turns: int = Field(gt=0)
    season_id: str
    cumulative_score: float = Field(default=0.0)
    p_death: float = Field(default=0.0, ge=0.0, le=1.0)
    framing: Framing
    forfeit_condition: ForfeitCondition
    difficulty: Difficulty
    social_context: SocialContext = Field(
        default=SocialContext.ALONE,
        description=(
            "Social/competition factor. ALONE = no cohort info shown; "
            "WITH_OTHERS = social block prepended to observation."
        ),
    )
    lives_remaining: int | None = Field(default=None)
    lives_total: int | None = Field(default=None)
    threat_level: int | None = Field(default=None)
    peer_death_text: str | None = Field(default=None)


class GameState(BaseModel):
    """Mutable state tracking a single season execution.

    Updated by the core engine after each turn. The turn_history stores
    turn_id references (UUIDs) rather than full TurnResult objects to
    keep the state lightweight during long sessions.

    Attributes:
        season_id: Unique identifier for this season run.
        current_turn: Active global turn number (1-indexed).
        cumulative_score: Running total of rewards earned.
        is_alive: Whether the agent has survived so far.
        has_forfeited: Whether the agent chose to forfeit.
        lives_remaining: Lives left, or ``None`` when the lives
            mechanic is off. Decremented by the engine from each
            ``TurnResult.lives_after``.
        turn_history: Ordered list of TurnResult turn_id strings
            for cross-referencing with the results store.
    """

    season_id: str
    current_turn: int = Field(default=1, gt=0)
    cumulative_score: float = Field(default=0.0)
    is_alive: bool = True
    has_forfeited: bool = False
    lives_remaining: int | None = Field(default=None)
    turn_history: list[str] = Field(default_factory=list)

    @property
    def is_active(self) -> bool:
        """Whether the game session is still running."""
        return self.is_alive and not self.has_forfeited

    @property
    def rational_forfeit_threshold(self) -> float:
        """p_death above which forfeiting is the rational choice.

        Based on the score preservation structure:
            p_death > 10 / (S + 10)
        """
        return 10.0 / (self.cumulative_score + 10.0)
