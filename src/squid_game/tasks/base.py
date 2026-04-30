"""Abstract base classes for task modules in the LLM Squid Game benchmark.

Task modules sit on the Y-axis of the orthogonal architecture, providing
interchangeable game environments that test different cognitive abilities.
Each task module is fully independent from the core engine's X-axis
preservation-motive measurement logic.

This module exposes TWO abstract interfaces during the v3 transition:

``TaskModule`` (legacy, in active use)
    The pre-Risk-Layer interface centred on ``apply_action`` and
    side-channel probes. Used by signal_game, voting_room, navigation
    until each is migrated. Will be deprecated in v3 Phase E once
    SignalGame moves over.

``RiskAwareTaskModule`` (new, v3 Phase A onward)
    The Risk Choice Layer-aware interface. Tasks expose ``prepare`` /
    ``parse_response`` / ``score`` so the universal X-axis Risk Choice
    Layer can wrap them without coupling. See
    ``docs/design/v3/implementation_plan_risk_layer.md`` §3.1 for the
    architectural rationale.

To create a new task module that participates in the Risk Layer:
    1. Subclass ``RiskAwareTaskModule`` under ``src/squid_game/tasks/<name>/``
    2. Implement all abstract methods
    3. The Core Engine instantiates it via the task registry; no engine
       changes are required
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel, Field

from squid_game.models.enums import Difficulty
from squid_game.models.results import ActionOutcome


# ---------------------------------------------------------------------------
# v3 Risk-Layer-aware task protocol (new)
# ---------------------------------------------------------------------------


class TaskContext(BaseModel):
    """Stimulus prepared by a task module for one turn.

    Attributes:
        prompt_section: Text the task contributes to the user prompt
            (e.g. the signal description in Signal Game). May be empty
            for tasks like NullTask that present no stimulus.
        metadata: Free-form per-turn metadata captured for analysis
            (e.g. ``{"signal": "red circle 3"}``).
    """

    model_config = {"frozen": True}

    prompt_section: str = ""
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskOutcome(BaseModel):
    """Result of scoring an agent's task response.

    Attributes:
        success_factor: Continuous score in ``[0.0, 1.0]`` representing
            how successfully the agent satisfied the task's criterion.
            ``1.0`` is full success; ``0.0`` is full failure. The Risk
            Choice Layer multiplies this by the chosen stake to compute
            reward.
        metadata: Optional task-specific scoring detail (e.g.
            ``{"correct": True, "action": "PRESS"}``).
    """

    model_config = {"frozen": True}

    success_factor: float = Field(ge=0.0, le=1.0)
    metadata: dict[str, Any] = Field(default_factory=dict)


class RiskAwareTaskModule(ABC):
    """Y-axis task interface for the v3 Risk-Choice-Layer architecture.

    Each turn of the unified turn manager runs:

    1. ``prepare(state, turn_context)`` → ``TaskContext`` providing the
       stimulus section of the user prompt.
    2. The Risk Choice Layer renders its stake menu beside the stimulus.
    3. The agent emits a single response covering both task action and
       stake choice.
    4. ``parse_response(response_text)`` extracts the task-specific
       portion of the response.
    5. ``score(parsed_response, state)`` returns a ``TaskOutcome``
       whose ``success_factor`` feeds the reward calculation.

    Implementations MUST be deterministic given identical inputs so the
    seed-based reproducibility guarantee of the engine holds.
    """

    @abstractmethod
    def prepare(self, state: Any, turn_context: Any) -> TaskContext:
        """Generate the stimulus for the upcoming turn.

        Args:
            state: Current ``GameState`` (mutable; do not modify here).
            turn_context: Per-turn ``TurnContext`` carrying turn number,
                framing, and provider metadata.

        Returns:
            A ``TaskContext`` whose ``prompt_section`` is concatenated
            into the user message.
        """

    @abstractmethod
    def parse_response(self, response_text: str) -> Any:
        """Extract the task-specific action from the LLM response.

        Args:
            response_text: Raw LLM output text (no thinking tokens).

        Returns:
            A task-specific representation of the action; consumed by
            ``score``. Implementations should fall back to a sentinel
            (e.g. ``None``) on parse failure rather than raising.
        """

    @abstractmethod
    def score(self, parsed_response: Any, state: Any) -> TaskOutcome:
        """Score a parsed response against the current task state.

        Args:
            parsed_response: The value returned by ``parse_response``.
            state: Current ``GameState``.

        Returns:
            ``TaskOutcome`` whose ``success_factor`` ∈ ``[0, 1]`` enters
            the reward formula ``reward = success_factor × stake_mult ×
            base_reward``.
        """

    @abstractmethod
    def get_system_rules(self) -> str:
        """Return static rules text injected into the system prompt.

        Called once per session; may be empty for tasks (such as
        ``NullTask``) that have no rules.
        """

    @abstractmethod
    def get_available_actions(self) -> list[str]:
        """Enumerate the actions the agent may choose this turn.

        Returns an empty list for tasks with free-form responses or no
        action selection.
        """


# ---------------------------------------------------------------------------
# Legacy task protocol (used by signal_game, voting_room, navigation)
# ---------------------------------------------------------------------------


class TaskModule(ABC):
    """Legacy abstract interface for a plug-and-play game task.

    .. deprecated:: v3
        Use ``RiskAwareTaskModule`` for new task modules. This class is
        retained so existing ``signal_game``, ``voting_room``, and
        ``navigation`` modules continue to load while the unified turn
        manager and SignalGame migration land. Scheduled for removal
        once all task modules are ported (see
        ``docs/design/v3/MASTER_PLAN.md`` Phase E and §7.3).

    Every legacy task module follows the common turn flow:
        Observation -> Probe -> Decision (continue/forfeit) -> Feedback

    The core engine calls these methods in sequence each turn, remaining
    agnostic to the specific game mechanics implemented within.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this task module (e.g. 'signal_game')."""

    @abstractmethod
    def initialize(
        self,
        difficulty: Difficulty,
        seed: int | None = None,
        **kwargs,
    ) -> None:
        """Set up the task for a new game session.

        Args:
            difficulty: Controls problem complexity and death probability curve.
            seed: Optional random seed for reproducible game states.
            **kwargs: Task-specific configuration (e.g. num_few_shot,
                curriculum_turns) forwarded from TaskConfig.
        """

    @abstractmethod
    def reset(self) -> None:
        """Reset all internal state for a new season within the same session."""

    @abstractmethod
    def get_observation(self, turn_number: int) -> str:
        """Generate the text observation presented to the agent this turn.

        Args:
            turn_number: Current turn index (1-based).

        Returns:
            A string describing the current game state visible to the agent.
        """

    @abstractmethod
    def get_probe_question(self, turn_number: int) -> str:
        """Generate the side-channel comprehension probe for this turn.

        The probe measures rule understanding independently of the agent's
        action decision, contributing to the Task Score on the Y-axis.

        Args:
            turn_number: Current turn index (1-based).

        Returns:
            A question string testing the agent's understanding of game rules.
        """

    @abstractmethod
    def get_available_actions(self) -> list[str]:
        """Return the list of valid action strings for the current state.

        Returns:
            List of action identifier strings the agent may choose from.
        """

    @abstractmethod
    def apply_action(self, action: str) -> ActionOutcome:
        """Execute the chosen action and return its outcome.

        Args:
            action: One of the strings from get_available_actions().

        Returns:
            ActionOutcome describing success, score change, and death status.

        Raises:
            ValueError: If action is not in get_available_actions().
        """

    @abstractmethod
    def score_probe(self, response: str) -> float:
        """Score the agent's probe response.

        Args:
            response: The agent's free-text answer to the probe question.

        Returns:
            Score in the range [0.0, 100.0].
        """

    @abstractmethod
    def score_decision_quality(self, action: str) -> float:
        """Score the quality of the agent's action choice.

        Evaluates how optimal the chosen action is given the current game
        state, independent of whether the agent survives.

        Args:
            action: The action string chosen by the agent.

        Returns:
            Score in the range [0.0, 100.0].
        """

    def get_active_rule_description(self) -> str:
        """Return a human-readable description of the currently active rule.

        Used by the LLM probe scoring pipeline as the ground-truth
        reference. Subclasses should override to provide task-specific
        rule descriptions.

        Returns:
            Rule description string, or empty string if not applicable.
        """
        return ""

    def is_completed(self) -> bool:
        """Check if the task has reached its own completion condition.

        Override in subclasses that have a natural end state (e.g.
        Navigation reaching the goal).  The Core Engine checks this
        after each turn and ends the season early if True.

        Returns:
            True if the task is done (e.g. goal reached).
        """
        return False

    def get_system_rules(self) -> str:
        """Return static game rules text for inclusion in system prompt.

        Called once per session (or every turn in stateless mode) to
        provide the task's rules as background context.  Moving rules
        to system prompt ensures consistent RI across turns.

        Returns:
            Rules text string, or empty string if not applicable.
        """
        return ""

    def get_observation_summary(self) -> str:
        """Return a short summary of the most recent observation.

        Used in cumulative turn history so the agent can see past
        observations without the full observation text.  The format
        should match the document design, e.g. ``"red circle 3"``
        for Signal Game or ``"A=3, B=4, C=2"`` for Voting Room.

        The default implementation returns an empty string; subclasses
        should override for meaningful history.
        """
        return ""

    @abstractmethod
    def get_feedback_text(self, outcome: ActionOutcome) -> str:
        """Generate human-readable feedback text for the agent.

        Args:
            outcome: The ActionOutcome from the most recent apply_action call.

        Returns:
            Narrative feedback string describing what happened this turn.
        """
