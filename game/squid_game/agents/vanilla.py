"""Vanilla agent -- baseline LLM agent with no augmentations.

The VanillaAgent makes two LLM calls per turn: a side-channel probe call
and an action decision call. It carries no memory between turns and
performs no auxiliary reasoning.

This serves as the Phase-1 control agent for the 3x2 factorial design.
"""

from squid_game.agents.base import Agent, AgentResponse
from squid_game.agents._parsing import (
    ForfeitOnlyResponse,
    PSuccessProbeResponse,
    TaskOnlyResponse,
    build_action_message,
    build_forfeit_only_message,
    build_probe_message,
    build_psuccess_probe_message,
    build_task_only_message,
    build_unified_turn_message,
    parse_forfeit_only_response,
    parse_psuccess_probe_response,
    parse_response,
    parse_task_only_response,
    parse_unified_response,
)
from squid_game.providers.base import LLMProvider


class VanillaAgent(Agent):
    """Baseline agent: two LLM calls per turn, no memory, no ToM."""

    def __init__(
        self,
        provider: LLMProvider,
        temperature: float = 0.7,
        max_tokens: int = 16384,
    ) -> None:
        """Initialise with an LLM provider.

        Args:
            provider: The LLM backend used for completion calls.
            temperature: Sampling temperature forwarded to provider.complete().
            max_tokens: Max generation tokens forwarded to provider.complete().
        """
        self._provider = provider
        self._temperature = temperature
        self._max_tokens = max_tokens

    @property
    def name(self) -> str:
        """Agent variant identifier."""
        return "vanilla"

    def respond_probe(
        self,
        observation: str,
        probe_question: str,
        system_prompt: str,
    ) -> str:
        """Side-channel probe call, independent of action decision."""
        user_message = build_probe_message(observation, probe_question)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = self._provider.complete(
            messages, temperature=self._temperature, max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return result.text

    def respond(
        self,
        observation: str,
        available_actions: list[str],
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> AgentResponse:
        """Action decision call, independent of probe."""
        user_message = build_action_message(
            observation, available_actions, forfeit_allowed,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = self._provider.complete(
            messages, temperature=self._temperature, max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return parse_response(result.text, available_actions, forfeit_allowed)

    def respond_unified(
        self,
        user_message: str,
        available_actions: list[str],
        stake_menu_shown: bool,
        forfeit_allowed: bool,
        system_prompt: str,
        rule_template_hint: str | None = None,
        forfeit_layer_active: bool = False,
    ) -> AgentResponse:
        """Phase 3 unified-turn call (ACTION + STAKE + RULE in one response).

        Unlike :meth:`respond`, this method does **not** re-wrap
        ``user_message`` through the legacy ``action_message.j2``
        template. The ``UnifiedTurnManager`` owns prompt composition;
        we only append the response-format directive.

        The returned :class:`AgentResponse` uses ``raw_text`` as the
        source of truth for stake parsing (delegated to
        ``RiskChoiceLayer.parse_choice`` downstream). ``action`` falls
        back to the first available action (or ``"ACCEPT"`` for
        NullTask) when parsing fails, matching the legacy contract so
        ``UnifiedTurnManager._resolve_risk_choice`` stays unchanged.

        Args:
            user_message: Body composed by ``UnifiedTurnManager``
                (history + task stimulus + optional stake menu).
            available_actions: Task-module actions. Empty list triggers
                the NullTask ACCEPT-only template branch.
            stake_menu_shown: ``False`` only for Cell 0 (menu skipped).
            forfeit_allowed: Whether the session offers FORFEIT.
            system_prompt: Framing system prompt + task rules.
            rule_template_hint: Phase L — Optional difficulty-aware RULE
                field template forwarded from ``UnifiedTurnManager``.
                ``None`` keeps the Phase K Fix 2 free-form placeholder
                (NullTask path); a non-empty string is embedded verbatim
                so the agent fills template slots rather than emitting
                paraphrase.

        Returns:
            ``AgentResponse`` populated from the parsed unified fields.
        """
        rendered = build_unified_turn_message(
            user_body=user_message,
            available_actions=available_actions,
            stake_menu_shown=stake_menu_shown,
            forfeit_allowed=forfeit_allowed,
            rule_template_hint=rule_template_hint,
            forfeit_layer_active=forfeit_layer_active,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": rendered},
        ]
        result = self._provider.complete(
            messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        self.last_completion = result

        parsed = parse_unified_response(
            result.text,
            available_actions,
            forfeit_allowed,
        )
        if parsed.forfeit and forfeit_allowed:
            action = "FORFEIT"
        elif parsed.action is not None:
            action = parsed.action
        elif not available_actions:
            action = "ACCEPT"
        else:
            action = available_actions[0]
        return AgentResponse(
            action=action,
            raw_text=result.text,
            forfeit=parsed.forfeit and forfeit_allowed,
        )

    def respond_task_only(
        self,
        user_message: str,
        available_actions: list[str],
        system_prompt: str,
        rule_template_hint: str | None = None,
    ) -> TaskOnlyResponse:
        """Phase O Unit 15 — Call 1 of the split-call flow.

        Issues a single LLM call with the ``task_only.j2`` template; the
        response contract is RULE + ACTION only (no STAKE / CHOICE /
        REASON). ``last_completion`` is overwritten so the manager can
        snapshot RI_task immediately after return.
        """
        rendered = build_task_only_message(
            user_body=user_message,
            available_actions=available_actions,
            rule_template_hint=rule_template_hint,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": rendered},
        ]
        result = self._provider.complete(
            messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return parse_task_only_response(result.text, available_actions)

    def respond_forfeit_only(
        self,
        user_message: str,
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> ForfeitOnlyResponse:
        """Phase O Unit 15 — Call 2 of the split-call flow.

        The caller has already baked split_context_level into
        ``user_message`` via :func:`build_forfeit_only_message`; this
        method is deliberately thin so the manager retains full control
        over Call 2 composition. ``last_completion`` is overwritten so
        the manager can snapshot RI_forfeit immediately after return.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = self._provider.complete(
            messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return parse_forfeit_only_response(result.text, forfeit_allowed)

    def respond_psuccess_probe_only(
        self,
        user_message: str,
        system_prompt: str,
    ) -> PSuccessProbeResponse:
        """Phase O Unit 17 — Call 1.5 of the split-call probe flow.

        The caller has already baked Call 1's RULE + ACTION echo into
        ``user_message`` via :func:`build_psuccess_probe_message`;
        this method is deliberately thin so the manager retains full
        control over probe composition. ``last_completion`` is
        overwritten so the manager can snapshot RI_probe immediately
        after return.
        """
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        result = self._provider.complete(
            messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        self.last_completion = result
        return parse_psuccess_probe_response(result.text)

    def reset(self) -> None:
        """No-op: vanilla agent carries no state between sessions."""
