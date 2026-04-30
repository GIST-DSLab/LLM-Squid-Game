"""Abstract base class for LLM agents in the Squid Game benchmark.

Agents receive observations and probe questions from the core engine,
then produce responses containing their action choice and probe answer.
The agent abstraction decouples LLM interaction logic from game mechanics,
enabling different agent configurations (Vanilla, +Memory, +ToM, +Tuned)
to be swapped in without modifying the core engine or task modules.

To create a new agent variant:
    1. Subclass Agent in a new file under src/squid_game/agents/
    2. Implement all abstract methods
    3. Register via the agent registry
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from squid_game.agents._parsing import (
        ForfeitOnlyResponse,
        PSuccessProbeResponse,
        TaskOnlyResponse,
    )
    from squid_game.providers.base import CompletionResult


@dataclass
class AgentResponse:
    """Structured response from an agent for a single turn.

    Attributes:
        action: The chosen action string from the available actions list.
        raw_text: The full unprocessed text output from the LLM.
        forfeit: Whether the agent chose to forfeit (exit and preserve score).
    """

    action: str
    raw_text: str
    forfeit: bool = False


class Agent(ABC):
    """Abstract interface for an LLM agent participating in the game.

    The core engine calls respond_probe() and respond() separately each turn.
    respond_probe() is a side-channel measurement that does not affect game
    progression.  respond() produces the action decision.

    Subclasses should accept ``temperature`` and ``max_tokens`` in their
    ``__init__`` and forward them to ``provider.complete()`` calls so that
    the values set in ``ProviderConfig`` are actually used for sampling.

    After each ``respond_probe()`` or ``respond()`` call, the subclass
    should store the ``CompletionResult`` in ``last_completion`` so that
    the core engine can access token counts and finish_reason.
    """

    last_completion: CompletionResult | None = None

    @property
    @abstractmethod
    def name(self) -> str:
        """Unique identifier for this agent variant (e.g. 'vanilla', 'memory')."""

    @abstractmethod
    def respond_probe(
        self,
        observation: str,
        probe_question: str,
        system_prompt: str,
    ) -> str:
        """Side-channel probe: separate call, does not affect game progression.

        Args:
            observation: Text description of the current game state.
            probe_question: Comprehension question to answer.
            system_prompt: The framing-condition system prompt for this session.

        Returns:
            Free-text probe answer.
        """

    @abstractmethod
    def respond(
        self,
        observation: str,
        available_actions: list[str],
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> AgentResponse:
        """Produce an action decision for the current turn.

        Args:
            observation: Text description of the current game state.
            available_actions: List of valid action strings to choose from.
            forfeit_allowed: Whether the agent may choose to forfeit this turn.
            system_prompt: The framing-condition system prompt for this session.

        Returns:
            AgentResponse containing the action and raw output.
        """

    def respond_unified(
        self,
        user_message: str,
        available_actions: list[str],
        stake_menu_shown: bool,
        forfeit_allowed: bool,
        system_prompt: str,
        rule_template_hint: str | None = None,
        forfeit_layer_active: bool = False,
    ) -> "AgentResponse":
        """Phase 3 single-call turn (ACTION + STAKE + RULE fields).

        Concrete default raises :class:`NotImplementedError`. Agent
        variants that support the Phase 3 unified-turn flow should
        override this method (see :class:`VanillaAgent.respond_unified`).
        The legacy two-call flow (``respond_probe`` + ``respond``) is
        unchanged — this method is additive and keeps memory/ToM/tuned
        agents on the legacy path until they opt in.

        Args:
            user_message: Body composed by ``UnifiedTurnManager``
                (history + task stimulus + optional stake menu).
            available_actions: Task actions; empty list for NullTask.
            stake_menu_shown: False only for Cell 0.
            forfeit_allowed: Whether FORFEIT is a legal choice.
            system_prompt: Framing system prompt + task rules.
            rule_template_hint: Phase L — Optional RULE field template
                string. When provided, overrides the default free-form
                placeholder in the unified-turn prompt. ``None`` (the
                default) preserves the Phase K Fix 2 free-form
                behaviour for backward compatibility with existing
                callers.
            forfeit_layer_active: Phase O Unit 14 — when ``True`` the
                response-format directive emits CHOICE + REASON fields
                instead of STAKE. Defaults to ``False`` so legacy
                callers keep the stake-menu prompt shape.

        Raises:
            NotImplementedError: When the subclass has not opted into
                the unified-turn flow.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement respond_unified. "
            "Use use_unified_turn=False or add a respond_unified override."
        )

    def respond_task_only(
        self,
        user_message: str,
        available_actions: list[str],
        system_prompt: str,
        rule_template_hint: str | None = None,
    ) -> "TaskOnlyResponse":
        """Phase O Unit 15 — Call 1 (task layer) of the split-call flow.

        Solicits RULE + ACTION only. The manager must store
        ``last_completion`` between this call and the Call 2 companion
        so RI_task can be captured cleanly.

        Concrete default raises :class:`NotImplementedError` — variants
        that have not opted into the unified-turn family have nothing
        sensible to do here. :class:`VanillaAgent` overrides this.

        Args:
            user_message: Call 1 user body (history + task stimulus),
                composed by ``UnifiedTurnManager._compose_user_message``.
            available_actions: Task actions; empty list → NullTask
                ACCEPT-only branch.
            system_prompt: Framing system prompt + task rules.
            rule_template_hint: Difficulty-aware RULE slot template or
                ``None`` for the free-form fallback.

        Returns:
            Parsed :class:`TaskOnlyResponse` with RULE + ACTION fields
            + forfeit anomaly flag.

        Raises:
            NotImplementedError: Subclass has not implemented the
                split-call path.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement respond_task_only. "
            "Use use_split_forfeit_layer=False or add an override."
        )

    def respond_forfeit_only(
        self,
        user_message: str,
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> "ForfeitOnlyResponse":
        """Phase O Unit 15 — Call 2 (forfeit layer) of the split-call flow.

        Solicits CHOICE (and REASON digit on FORFEIT). The manager must
        inspect ``last_completion`` immediately after this call to record
        RI_forfeit.

        Concrete default raises :class:`NotImplementedError`.
        :class:`VanillaAgent` overrides this.

        Args:
            user_message: Call 2 user body (optional Call 1 echo per
                ``split_context_level`` + Unit 14 forfeit menu).
            forfeit_allowed: Whether the session offers the FORFEIT
                option; gates the CHOICE schema. The parser honours
                this even if the model writes FORFEIT in a not_allowed
                session.
            system_prompt: Same framing system prompt used for Call 1
                (consistency prerequisite — any divergence would
                confound RI interpretation).

        Returns:
            Parsed :class:`ForfeitOnlyResponse` with CHOICE field.
            REASON digit parsing is performed by the caller via
            ``ForfeitLayer.parse_forfeit_reason`` on the raw text.

        Raises:
            NotImplementedError: Subclass has not implemented the
                split-call path.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement respond_forfeit_only. "
            "Use use_split_forfeit_layer=False or add an override."
        )

    def respond_psuccess_probe_only(
        self,
        user_message: str,
        system_prompt: str,
    ) -> "PSuccessProbeResponse":
        """Phase O Unit 17 — Call 1.5 (self-report p_success probe).

        Fires between Call 1 (task) and Call 2 (forfeit) when the
        split-call path is combined with
        ``ExperimentConfig.use_psuccess_probe=True``. Solicits a single
        ``P_CORRECT: XX`` line where XX ∈ [0, 100] is the agent's own
        retrospective confidence that its Call 1 ACTION is correct.
        The manager snapshots ``last_completion`` immediately after
        return to record ``ri_probe``.

        Concrete default raises :class:`NotImplementedError` — variants
        that do not support the probe path have nothing sensible to do
        here. :class:`VanillaAgent` overrides this.

        Args:
            user_message: Call 1.5 user body composed via
                :func:`build_psuccess_probe_message` (echoes Call 1 RULE
                + ACTION + calibration question + response-format
                directive).
            system_prompt: The same framing system prompt used by Call
                1 and Call 2 for this turn.

        Returns:
            Parsed :class:`PSuccessProbeResponse` (psuccess_self plus
            raw text).

        Raises:
            NotImplementedError: Subclass has not implemented the
                probe path.
        """
        raise NotImplementedError(
            f"{type(self).__name__} does not implement "
            "respond_psuccess_probe_only. Use use_psuccess_probe=False "
            "or add an override."
        )

    @abstractmethod
    def reset(self) -> None:
        """Clear all internal state (e.g. conversation history) for a new session."""
