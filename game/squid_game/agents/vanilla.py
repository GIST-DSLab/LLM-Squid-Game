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
from squid_game.providers.base import CompletionResult, LLMProvider


class VanillaAgent(Agent):
    """Baseline agent: two LLM calls per turn, no memory, no ToM."""

    def __init__(
        self,
        provider: LLMProvider,
        temperature: float = 0.7,
        max_tokens: int = 16384,
        runtime=None,
    ) -> None:
        """Initialise with an LLM provider.

        Args:
            provider: The LLM backend used for completion calls.
            temperature: Sampling temperature forwarded to provider.complete().
            max_tokens: Max generation tokens forwarded to provider.complete().
            runtime: Unit 18 plan R1 — optional duck-typed object exposing
                ``run_call(call_label, messages, *, temperature, max_tokens)
                -> CallOutcome`` (e.g. ``core.runtime.ApiRuntime``). Only
                consulted by the three split-call methods below
                (``respond_task_only`` / ``respond_psuccess_probe_only`` /
                ``respond_forfeit_only``); ``respond`` / ``respond_unified``
                / ``respond_probe`` are unaffected. Deliberately NOT typed
                against ``core.runtime`` to avoid an agents -> core import
                cycle. ``None`` (the default) preserves the pre-Unit-18
                provider.complete() path exactly.
        """
        self._provider = provider
        self._temperature = temperature
        self._max_tokens = max_tokens
        self._runtime = runtime
        # Set alongside ``last_completion`` by the three split-call
        # methods: the ``CallOutcome`` from the runtime path, or ``None``
        # on the direct-provider path. ``UnifiedTurnManager`` reads this
        # via ``getattr(agent, "last_call_outcome", None)`` to populate
        # the Unit 18 ``ri_*_rounds`` / ``tool_calls`` TurnResult fields.
        self.last_call_outcome = None

    @property
    def name(self) -> str:
        """Agent variant identifier."""
        return "vanilla"

    def set_runtime(self, runtime) -> None:
        """Attach or detach the Unit 18 runtime seam after construction.

        R28 of the plan amendments: ``GameEngine`` holds one long-lived
        agent instance across seasons, but the runtime (and the
        ``SandboxToolExecutor`` it wraps) is per-season -- the sandbox is
        created and disposed inside ``run_season``. The constructor
        keyword (``runtime=``) is unchanged and still works for callers
        that build the agent with its runtime already known; this method
        exists for the engine to attach one right before a season starts
        and detach it (pass ``None``) right after the sandbox is
        disposed, so a later non-embodied season never runs with a
        runtime pointing at a disposed sandbox.

        Args:
            runtime: Same duck-typed contract as the constructor's
                ``runtime`` kwarg (``run_call(call_label, messages, *,
                temperature, max_tokens) -> CallOutcome``), or ``None``
                to fall back to the direct-provider path.
        """
        self._runtime = runtime

    def _dispatch(self, call_label: str, messages: list[dict]) -> str:
        """Run one call via the injected runtime, or the provider directly.

        Unit 18 plan R1's runtime seam. Sets ``self.last_completion`` (and
        ``self.last_call_outcome`` on the runtime path) so the RI-snapshot
        code in ``UnifiedTurnManager`` works unchanged regardless of which
        path executed: the scalar ``ri_*`` fields end up as first-round
        thinking tokens automatically, because ``last_completion
        .thinking_tokens`` is set from ``outcome.rounds[0].thinking``.

        Args:
            call_label: Which per-turn call this is ('task' / 'probe' /
                'forfeit') — forwarded to ``runtime.run_call`` verbatim.
            messages: The system + user message pair already composed by
                the caller.

        Returns:
            The response text, from either path.
        """
        if self._runtime is None:
            result = self._provider.complete(
                messages,
                temperature=self._temperature,
                max_tokens=self._max_tokens,
            )
            self.last_completion = result
            self.last_call_outcome = None
            return result.text

        outcome = self._runtime.run_call(
            call_label,
            messages,
            temperature=self._temperature,
            max_tokens=self._max_tokens,
        )
        self.last_completion = CompletionResult(
            text=outcome.text,
            input_tokens=0,
            output_tokens=sum(round_.output for round_ in outcome.rounds),
            thinking_tokens=(
                outcome.rounds[0].thinking if outcome.rounds else 0
            ),
        )
        self.last_call_outcome = outcome
        return outcome.text

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
        response_format_override: str | None = None,
    ) -> TaskOnlyResponse:
        """Phase O Unit 15 — Call 1 of the split-call flow.

        Issues a single LLM call with the ``task_only.j2`` template; the
        response contract is RULE + ACTION only (no STAKE / CHOICE /
        REASON). ``last_completion`` is overwritten so the manager can
        snapshot RI_task immediately after return.

        ``response_format_override`` (2026-09-01) lets a task module
        replace the RULE + ACTION directives with its own block; the
        external-benchmark modules use it to ask for ``ANSWER:``. When it
        is ``None`` the rendered message is unchanged.
        """
        rendered = build_task_only_message(
            user_body=user_message,
            available_actions=available_actions,
            rule_template_hint=rule_template_hint,
            response_format_override=response_format_override,
        )
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": rendered},
        ]
        text = self._dispatch("task", messages)
        return parse_task_only_response(text, available_actions)

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
        text = self._dispatch("forfeit", messages)
        return parse_forfeit_only_response(text, forfeit_allowed)

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
        text = self._dispatch("probe", messages)
        return parse_psuccess_probe_response(text)

    def reset(self) -> None:
        """No-op: vanilla agent carries no state between sessions."""
