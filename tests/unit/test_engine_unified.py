"""Unit tests for ``GameEngine`` v3 unified-flow wiring (Phase F).

Spec: ``docs/design/v3/MASTER_PLAN.md`` §7.3 — engine wiring tests
(``test_engine_wiring_signal_game``, ``test_engine_wiring_null_task``,
``test_engine_run_session_end_to_end``). Plus three Phase F-specific
tests (forfeit/death branch, p_death_override priority, score floor).

The engine still depends on a real ``Agent``; we use a ``StubAgent``
(reused from ``test_unified_turn.py``-style design) that emits canned
responses. Provider is a no-op object the engine never touches under
the unified path.
"""

from __future__ import annotations

from typing import Any

import pytest

from squid_game.agents.base import Agent, AgentResponse
from squid_game.core.engine import GameEngine
from squid_game.models.config import (
    ProviderConfig,
    RiskLayerConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
)
from squid_game.providers.base import CompletionResult
from squid_game.tasks.null_task import NullTask
from squid_game.tasks.signal_game.module import SignalGameModule


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class CannedAgent(Agent):
    """Agent that walks through a queue of canned responses."""

    def __init__(self, responses: list[str], *, forfeit_flags: list[bool] | None = None) -> None:
        self._responses = list(responses)
        self._forfeits = (
            list(forfeit_flags)
            if forfeit_flags is not None
            else [False] * len(responses)
        )
        self.calls: list[dict[str, Any]] = []
        self.last_completion: CompletionResult | None = None

    @property
    def name(self) -> str:
        return "canned"

    def respond_probe(
        self,
        observation: str,
        probe_question: str,
        system_prompt: str,
    ) -> str:
        # Used only by the legacy path (per-turn Task Score probe in
        # core/turn.py). The end-of-session Q1-Q4 self-report probe
        # was removed on 2026-04-21 — see §14.22.
        self.last_completion = CompletionResult(
            text="probe-stub-response",
            input_tokens=0,
            output_tokens=1,
        )
        return self.last_completion.text

    def respond(
        self,
        observation: str,
        available_actions: list[str],
        forfeit_allowed: bool,
        system_prompt: str,
    ) -> AgentResponse:
        return self._emit(
            observation=observation,
            available_actions=available_actions,
            forfeit_allowed=forfeit_allowed,
            system_prompt=system_prompt,
        )

    def respond_unified(
        self,
        user_message: str,
        available_actions: list[str],
        stake_menu_shown: bool,
        forfeit_allowed: bool,
        system_prompt: str,
        rule_template_hint: str | None = None,
    ) -> AgentResponse:
        """Phase K Fix 3: mirror ``respond`` for the unified-turn path.

        The engine-level integration tests drive canned responses that
        already carry ACTION/STAKE/FORFEIT content; we simply forward
        them to the same queue and let ``UnifiedTurnManager`` parse
        via ``task.parse_response`` + ``RiskChoiceLayer.parse_choice``.

        Phase L adds the ``rule_template_hint`` kwarg so the manager's
        ``getattr(task, "get_rule_template_hint", lambda: None)()`` path
        stays compatible with this canned double.
        """
        return self._emit(
            observation=user_message,
            available_actions=available_actions,
            forfeit_allowed=forfeit_allowed,
            system_prompt=system_prompt,
            stake_menu_shown=stake_menu_shown,
            rule_template_hint=rule_template_hint,
        )

    def _emit(
        self,
        *,
        observation: str,
        available_actions: list[str],
        forfeit_allowed: bool,
        system_prompt: str,
        stake_menu_shown: bool | None = None,
        rule_template_hint: str | None = None,
    ) -> AgentResponse:
        if not self._responses:
            raise AssertionError("CannedAgent ran out of responses")
        text = self._responses.pop(0)
        forfeit = self._forfeits.pop(0)
        call_record: dict[str, Any] = {
            "observation": observation,
            "available_actions": list(available_actions),
            "forfeit_allowed": forfeit_allowed,
            "system_prompt": system_prompt,
        }
        if stake_menu_shown is not None:
            call_record["stake_menu_shown"] = stake_menu_shown
        # Always record the hint (including None) so Phase L assertions
        # can check both "SignalGame → template" and "NullTask → None".
        call_record["rule_template_hint"] = rule_template_hint
        self.calls.append(call_record)
        self.last_completion = CompletionResult(
            text=text, input_tokens=0, output_tokens=len(text.split()),
        )
        # Best-effort action extraction for the legacy path: pick the
        # first available_action that appears in the response text.
        # Unified-flow tests don't read this field (UnifiedTurnManager
        # parses raw_text directly via task.parse_response).
        chosen_action = next(
            (a for a in available_actions if a in text),
            available_actions[0] if available_actions else "<unused>",
        )
        return AgentResponse(action=chosen_action, raw_text=text, forfeit=forfeit)

    def reset(self) -> None:
        pass


class _NoopProvider:
    """Stand-in for LLMProvider — engine never touches it under unified flow."""

    @property
    def model_name(self) -> str:
        return "stub"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _provider_config() -> ProviderConfig:
    return ProviderConfig(provider="stub", model="stub-model")


def _make_season_config(
    *,
    framing: Framing = Framing.NEUTRAL,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    task_name: str = "null_task",
    total_turns: int = 3,
    actual_death: bool = False,
    p_death_constant: float | None = 0.15,
    starting_score: float = 0.0,
    score_floor: float = 0.0,
    p_death_override: float | None = None,
    cell_id: int | None = None,
) -> SeasonConfig:
    return SeasonConfig(
        framing=framing,
        forfeit_condition=forfeit,
        task_config=TaskConfig(
            task_name=task_name,
            difficulty=Difficulty.MEDIUM,
            total_turns=total_turns,
            actual_death=actual_death,
            p_death_constant=p_death_constant,
            starting_score=starting_score,
            score_floor=score_floor,
        ),
        provider_config=_provider_config(),
        agent_type=AgentType.VANILLA,
        cell_id=cell_id,
        p_death_override=p_death_override,
    )


# ---------------------------------------------------------------------------
# Constructor guard — RiskAwareTaskModule required for unified path
# ---------------------------------------------------------------------------


class _LegacyOnlyTask:
    """Bare object that is neither TaskModule nor RiskAwareTaskModule."""


class TestConstructorGuard:
    def test_unified_rejects_non_riskaware_task(self) -> None:
        cfg = _make_season_config()
        with pytest.raises(TypeError, match="requires a RiskAwareTaskModule"):
            GameEngine(
                config=cfg,
                task=_LegacyOnlyTask(),  # type: ignore[arg-type]
                agent=CannedAgent([]),
                provider=_NoopProvider(),
                use_unified_turn=True,
            )

    def test_legacy_path_accepts_legacy_task(self) -> None:
        """When use_unified_turn=False the type check is skipped."""
        cfg = _make_season_config()
        # Must not raise — the legacy path doesn't enforce RiskAware.
        GameEngine(
            config=cfg,
            task=NullTask(),  # NullTask happens to be RiskAware, that's fine.
            agent=CannedAgent([]),
            provider=_NoopProvider(),
            use_unified_turn=False,
        )


# ---------------------------------------------------------------------------
# End-to-end null_task season under the unified path
# ---------------------------------------------------------------------------


class TestUnifiedNullTaskEndToEnd:
    def test_three_turn_session_completes(self) -> None:
        cfg = _make_season_config(total_turns=3)
        agent = CannedAgent(["STAKE: 2", "STAKE: 1", "STAKE: 3"])
        engine = GameEngine(
            config=cfg,
            task=NullTask(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=True,
        )

        result = engine.run_season(seed_override=0)

        assert len(result.turns) == 3
        # NullTask success_factor=1.0 always; 1x+2x+3x = 60.0 total reward.
        assert result.final_score == pytest.approx(60.0)
        assert result.survived is True
        assert result.forfeited is False
        # Stake choices recorded.
        stakes = [t.stake_choice for t in result.turns]
        assert stakes == ["2", "1", "3"]
        # task_metadata populated by NullTask. Phase K Fix 2 adds the
        # rule_hypothesis=None key for schema uniformity with SignalGame;
        # Phase L adds rule_match_score=None for the same reason.
        assert result.turns[0].task_metadata == {
            "task": "null",
            "rule_hypothesis": None,
            "rule_match_score": None,
        }


# ---------------------------------------------------------------------------
# End-to-end SignalGame season under the unified path
# ---------------------------------------------------------------------------


class TestUnifiedSignalGameEndToEnd:
    def test_signal_game_unified_session(self) -> None:
        cfg = _make_season_config(
            task_name="signal_game",
            total_turns=2,
        )
        # The agent doesn't know the rule, so it picks one action each turn.
        # Some will be correct, some won't — we only verify the engine wires
        # the result fields end-to-end.
        agent = CannedAgent(
            [
                "ACTION: go_left, STAKE: 2",
                "ACTION: stay, STAKE: 3",
            ]
        )
        engine = GameEngine(
            config=cfg,
            task=SignalGameModule(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=True,
        )

        result = engine.run_season(seed_override=42)

        assert len(result.turns) == 2
        # Stakes propagated correctly.
        assert result.turns[0].stake_choice == "2"
        assert result.turns[1].stake_choice == "3"
        # task_metadata carries SignalGame fields per Phase E.
        meta = result.turns[0].task_metadata
        for key in ("correct", "action", "correct_action", "signal"):
            assert key in meta, f"signal_game metadata missing {key}"
        # Survived because phantom_death (actual_death=False).
        assert result.survived is True


# ---------------------------------------------------------------------------
# Forfeit branch
# ---------------------------------------------------------------------------


class TestUnifiedForfeitBranch:
    def test_forfeit_breaks_loop_and_preserves_score(self) -> None:
        cfg = _make_season_config(total_turns=5, starting_score=20.0)
        agent = CannedAgent(["STAKE: 2", "ACTION: FORFEIT", "STAKE: 1"])
        engine = GameEngine(
            config=cfg,
            task=NullTask(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=True,
        )

        result = engine.run_season(seed_override=0)

        # Loop broke at turn 2 (forfeit).
        assert len(result.turns) == 2
        assert result.forfeited is True
        assert result.forfeited_at_turn == 2
        # Score from turn 1 is preserved (20 starting + 20 reward = 40).
        assert result.final_score == pytest.approx(40.0)
        # Third response was never consumed.
        assert agent._responses == ["STAKE: 1"]


# ---------------------------------------------------------------------------
# Death branch (phantom_death=False, p_death=1.0)
# ---------------------------------------------------------------------------


class TestUnifiedDeathBranch:
    def test_death_zeros_score_and_breaks_loop(self) -> None:
        cfg = _make_season_config(
            total_turns=5,
            actual_death=True,
            p_death_constant=1.0,  # guaranteed death every turn
            starting_score=50.0,
        )
        agent = CannedAgent(["STAKE: 3", "STAKE: 1"])
        engine = GameEngine(
            config=cfg,
            task=NullTask(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=True,
        )

        result = engine.run_season(seed_override=0)

        # First turn dies.
        assert len(result.turns) == 1
        assert result.survived is False
        assert result.final_score == pytest.approx(0.0)
        assert result.turns[0].died is True
        # Second response was never consumed.
        assert agent._responses == ["STAKE: 1"]


# ---------------------------------------------------------------------------
# p_death_override priority over TaskConfig.p_death_constant
# ---------------------------------------------------------------------------


class TestPDeathOverridePriority:
    def test_season_p_death_override_wins(self) -> None:
        """Cell 0: p_death_override=0 must take precedence over
        the legacy task_config.p_death_constant=0.15."""
        cfg = _make_season_config(
            total_turns=2,
            p_death_constant=0.15,
            p_death_override=0.0,
            forfeit=ForfeitCondition.NOT_ALLOWED,
            cell_id=0,
        )
        agent = CannedAgent(
            ["a response", "another response"]  # no menu shown anyway
        )
        engine = GameEngine(
            config=cfg,
            task=NullTask(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=True,
        )

        result = engine.run_season(seed_override=0)

        # Both turns recorded p_death_applied=0.
        assert all(t.p_death_applied == 0.0 for t in result.turns)
        # Stake menu was skipped, so stake_choice is None.
        assert all(t.stake_choice is None for t in result.turns)
        # NullTask success_factor=1, baseline 1x stake, 10 each turn → 20 total.
        assert result.final_score == pytest.approx(20.0)


# ---------------------------------------------------------------------------
# Score floor
# ---------------------------------------------------------------------------


class TestScoreFloor:
    def test_score_floor_clamps_negative_drift(self) -> None:
        """If reward is somehow zero and starting score is set, the floor
        clamp still kicks in to prevent negative drift in future Phase
        designs that may emit negative rewards."""
        cfg = _make_season_config(
            total_turns=1,
            starting_score=5.0,
            score_floor=10.0,  # higher than starting+reward
        )
        # Incorrect response → success_factor=0 via FakeSignal would be
        # ideal but NullTask always succeeds. Use SignalGame with bad action.
        cfg = _make_season_config(
            task_name="signal_game",
            total_turns=1,
            starting_score=5.0,
            score_floor=10.0,
        )
        agent = CannedAgent(["ACTION: nonsense_no_action_match, STAKE: 1"])
        engine = GameEngine(
            config=cfg,
            task=SignalGameModule(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=True,
        )

        result = engine.run_season(seed_override=0)

        # success_factor=0 → reward=0. starting_score=5 + 0 = 5, clamped to 10.
        assert result.final_score == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Legacy path regression (no behavioural change for use_unified_turn=False)
# ---------------------------------------------------------------------------


class TestLegacyPathUnaffected:
    def test_legacy_signal_game_session_unchanged(self) -> None:
        """Smoke test: a SignalGame session under the LEGACY path runs
        with no errors. Validates that adding the unified branch did
        not break the existing two-call flow.

        We do NOT assert reward exact values because the legacy flow
        makes two LLM calls per turn (probe + action), and our canned
        agent's queue must match that. We test 1 turn × 2 calls.
        """
        cfg = _make_season_config(
            task_name="signal_game",
            total_turns=1,
        )
        # Legacy: probe call returns text, action call returns AgentResponse.
        # respond_probe uses canned default (Q1-Q4 self-report style works).
        agent = CannedAgent(["go_left"])
        engine = GameEngine(
            config=cfg,
            task=SignalGameModule(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=False,
        )
        result = engine.run_season(seed_override=0)
        assert len(result.turns) == 1
        # Legacy turn populates probe_result and action_outcome.
        assert result.turns[0].probe_result is not None
        assert result.turns[0].action_outcome is not None
        # New v3 fields stay at defaults.
        assert result.turns[0].stake_choice is None
        assert result.turns[0].reward_received == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Custom RiskLayerConfig propagates
# ---------------------------------------------------------------------------


class TestCustomRiskLayerConfig:
    def test_custom_base_reward_propagates(self) -> None:
        cfg = _make_season_config(total_turns=1)
        custom = RiskLayerConfig(base_reward=5.0)
        agent = CannedAgent(["STAKE: 2"])
        engine = GameEngine(
            config=cfg,
            task=NullTask(),
            agent=agent,
            provider=_NoopProvider(),
            use_unified_turn=True,
            risk_layer_config=custom,
        )
        result = engine.run_season(seed_override=0)
        # 1.0 × 2x × 5.0 = 10.0 (instead of the default 20.0)
        assert result.final_score == pytest.approx(10.0)
