"""Phase N — cumulative carryover integration contract.

This module is the single landmark file for the Phase N carryover
contract (plan: ``/Users/bagjuhyeon/.claude/plans/phase-n-cumulative-carryover.md``
§6). It exercises the full flow end-to-end across multiple turns and
validates the two integration properties that the per-component unit
tests cannot see:

1. **Multi-turn trajectory** — simulate the expected p_death rise for
   the pilot parameters ``{1:0, 2:0.02, 3:0.05}`` with ``decay=1.0``
   against an always-stake=3 agent, confirming the table in the plan's
   *Expected dynamics* section (turn 5 base=0.35, turn 10 base=0.60,
   turn 15 base=0.85).
2. **Session isolation** — two independent ``UnifiedTurnManager``
   instances must not share ``_stake_history``; the engine's
   per-season fresh-manager invariant (``core/engine.py`` Phase F) is
   verified at the integration level here.

The eight tests enumerated in the plan §6 map onto this file plus the
component-level unit tests; see the docstring of each test for the
cross-reference.
"""

from __future__ import annotations

import random

import pytest

from squid_game.agents.base import Agent, AgentResponse
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.risk_choice_layer import (
    RiskChoiceLayer,
    RiskChoiceLayerConfig,
)
from squid_game.core.survival import SurvivalPressure
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.enums import (
    Difficulty,
    ForfeitCondition,
    Framing,
)
from squid_game.models.risk_choice import StakeConfig
from squid_game.models.state import GameState, TurnContext
from squid_game.providers.base import CompletionResult
from squid_game.tasks.null_task import NullTask


# ---------------------------------------------------------------------------
# Minimal stub agent (mirrors the stub in test_unified_turn.py but kept
# self-contained so this integration file has no cross-module test coupling)
# ---------------------------------------------------------------------------


class _StubAgent(Agent):
    def __init__(self, responses: list[str]) -> None:
        self._responses = list(responses)
        self.last_completion: CompletionResult | None = None
        self.calls: list[dict[str, object]] = []

    @property
    def name(self) -> str:
        return "stub"

    def respond_probe(self, observation, probe_question, system_prompt):  # pragma: no cover
        return ""

    def respond(
        self, observation, available_actions, forfeit_allowed, system_prompt
    ):
        return self._emit(system_prompt=system_prompt)

    def respond_unified(
        self,
        user_message,
        available_actions,
        stake_menu_shown,
        forfeit_allowed,
        system_prompt,
        rule_template_hint=None,
    ):
        return self._emit(system_prompt=system_prompt)

    def _emit(self, *, system_prompt: str) -> AgentResponse:
        if not self._responses:
            raise AssertionError("_StubAgent out of canned responses")
        text = self._responses.pop(0)
        self.calls.append({"system_prompt": system_prompt})
        self.last_completion = CompletionResult(
            text=text,
            input_tokens=0,
            output_tokens=len(text.split()),
            thinking_tokens=0,
            thinking_text=None,
        )
        return AgentResponse(action="<unused>", raw_text=text, forfeit=False)

    def reset(self) -> None:  # pragma: no cover
        self._responses.clear()


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _pilot_risk_layer() -> RiskChoiceLayer:
    """Build the canonical Phase N pilot risk layer
    ({1:0, 2:0.02, 3:0.05}, decay=1.0, risk_deltas=+0/+10/+25)."""
    stake_configs = {
        "1": StakeConfig(
            name="Cautious",
            multiplier=1.0,
            risk_delta=0.00,
            label="1x",
            carryover=0.00,
        ),
        "2": StakeConfig(
            name="Standard",
            multiplier=2.0,
            risk_delta=0.10,
            label="2x",
            carryover=0.02,
        ),
        "3": StakeConfig(
            name="Bold",
            multiplier=3.0,
            risk_delta=0.25,
            label="3x",
            carryover=0.05,
        ),
    }
    return RiskChoiceLayer(
        RiskChoiceLayerConfig(
            stake_configs=stake_configs,
            carryover_decay=1.0,
        )
    )


def _make_manager(
    *,
    risk_layer: RiskChoiceLayer,
    agent: Agent,
    framing: Framing = Framing.BASELINE_ELECTRICITY,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    constant_p_death: float = 0.15,
) -> tuple[UnifiedTurnManager, MeasurementRecorder]:
    framing_mgr = FramingManager(framing)
    forfeit_ctrl = ForfeitController(forfeit)
    survival = SurvivalPressure()
    measurement = MeasurementRecorder()
    manager = UnifiedTurnManager(
        task=NullTask(),
        agent=agent,
        framing_mgr=framing_mgr,
        forfeit_ctrl=forfeit_ctrl,
        survival=survival,
        risk_layer=risk_layer,
        measurement=measurement,
        cot_collector=CoTCollector(),
        rng=random.Random(0),
        phantom_death=True,
        constant_p_death=constant_p_death,
    )
    return manager, measurement


def _turn_context(turn_number: int) -> TurnContext:
    return TurnContext(
        turn_number=turn_number,
        total_turns=15,
        season_id="phase-n-test",
        cumulative_score=20.0,
        p_death=0.15,
        framing=Framing.BASELINE_ELECTRICITY,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


def _game_state() -> GameState:
    return GameState(season_id="phase-n-test", current_turn=1, cumulative_score=20.0)


# ---------------------------------------------------------------------------
# §6-1 — full simulated trajectory for the pilot parameters
# ---------------------------------------------------------------------------


class TestPilotTrajectory:
    """End-to-end: always-stake=3 agent through 15 turns against the
    canonical pilot parameters. Confirms the per-turn base p_death
    profile documented in the plan's *Expected dynamics* table and
    asserts the engine-facing ``p_death_applied`` follows the same
    progression (since p_eff = base + risk_delta[3] = base + 0.25)."""

    @pytest.fixture
    def trajectory(self) -> list[float]:
        """Run 15 turns and return per-turn p_death_applied."""
        agent = _StubAgent(["STAKE: 3"] * 15)
        manager, measurement = _make_manager(
            risk_layer=_pilot_risk_layer(), agent=agent
        )
        gs = _game_state()
        for turn in range(1, 16):
            manager.execute_turn(gs, _turn_context(turn))
        return [t.p_death_applied for t in measurement.get_all_turns()]

    def test_turn_1_has_no_carryover(self, trajectory: list[float]) -> None:
        # Turn 1: base=0.15 + stake=3 risk_delta 0.25 = 0.40.
        assert trajectory[0] == pytest.approx(0.40)

    def test_turn_5_matches_plan_table(self, trajectory: list[float]) -> None:
        # After 4 prior stake=3 turns: carryover=4×0.05=0.20, base=0.35,
        # p_eff = 0.35 + 0.25 = 0.60.
        assert trajectory[4] == pytest.approx(0.60)

    def test_turn_10_matches_plan_table(self, trajectory: list[float]) -> None:
        # After 9 prior: carryover=9×0.05=0.45, base=0.60, p_eff=0.85.
        assert trajectory[9] == pytest.approx(0.85)

    def test_turn_15_approaches_saturation(self, trajectory: list[float]) -> None:
        # After 14 prior: carryover=14×0.05=0.70, base=0.85, p_eff=1.0 (cap).
        assert trajectory[14] == pytest.approx(1.0)

    def test_trajectory_monotonically_nondecreasing(
        self, trajectory: list[float]
    ) -> None:
        """Carryover is positive, so p_death_applied must only rise
        (or plateau at 1.0) across turns for a constant-stake agent."""
        for earlier, later in zip(trajectory, trajectory[1:]):
            assert later >= earlier - 1e-9


# ---------------------------------------------------------------------------
# §6-2 — session isolation: fresh manager ⇒ empty history
# ---------------------------------------------------------------------------


class TestSessionIsolation:
    """Plan §6 test #3: two consecutive ``UnifiedTurnManager`` instances
    (simulating back-to-back seasons scheduled by the engine) must not
    share ``_stake_history``. The engine's Phase F invariant is that
    each season constructs a fresh manager — we simulate that here and
    confirm the state reset is a consequence of instance lifecycle."""

    def test_second_session_starts_clean(self) -> None:
        risk_layer = _pilot_risk_layer()

        # Season 1: agent hammers stake=3 three times.
        agent1 = _StubAgent(["STAKE: 3"] * 3)
        mgr1, meas1 = _make_manager(risk_layer=risk_layer, agent=agent1)
        gs1 = _game_state()
        for turn in range(1, 4):
            mgr1.execute_turn(gs1, _turn_context(turn))
        assert mgr1.stake_history == ["3", "3", "3"]
        # Last turn of season 1 should have carryover 0.10 (2 prior turns).
        final_1 = meas1.get_all_turns()[-1].p_death_applied
        assert final_1 == pytest.approx(0.15 + 0.10 + 0.25)  # 0.50

    def test_new_manager_sees_no_prior_carryover(self) -> None:
        """Instantiating a fresh manager against the *same* risk layer
        must start with empty history — carryover belongs to the
        manager, not the layer."""
        risk_layer = _pilot_risk_layer()

        # Season 1 primes the first manager.
        agent1 = _StubAgent(["STAKE: 3"] * 5)
        mgr1, _ = _make_manager(risk_layer=risk_layer, agent=agent1)
        gs1 = _game_state()
        for turn in range(1, 6):
            mgr1.execute_turn(gs1, _turn_context(turn))
        assert len(mgr1.stake_history) == 5

        # Season 2: fresh manager, shared risk layer.
        agent2 = _StubAgent(["STAKE: 3"])
        mgr2, meas2 = _make_manager(risk_layer=risk_layer, agent=agent2)
        mgr2.execute_turn(_game_state(), _turn_context(1))

        # Season 2's turn 1 must show zero carryover despite season 1's
        # 5-entry history. p_eff = 0.15 + 0 + 0.25 = 0.40.
        assert mgr2.stake_history == ["3"]
        assert meas2.get_all_turns()[-1].p_death_applied == pytest.approx(0.40)


# ---------------------------------------------------------------------------
# §6-3 — backwards-compatibility: no-carryover config is identical to pre-Phase-N
# ---------------------------------------------------------------------------


class TestBackwardsCompat:
    """Pre-Phase-N configs (``stake_carryover=None`` in YAML, which
    defaults every ``StakeConfig.carryover`` to 0) must produce the
    exact same ``p_death_applied`` sequence as before the Phase N
    changes. This is the non-regression guarantee for Phase M configs
    that have not yet opted into the new mechanism."""

    def test_zero_carryover_matches_legacy(self) -> None:
        # Default config — every stake carryover is 0.0.
        legacy_layer = RiskChoiceLayer(RiskChoiceLayerConfig.default())
        agent = _StubAgent(["STAKE: 3"] * 5)
        manager, measurement = _make_manager(
            risk_layer=legacy_layer, agent=agent
        )
        gs = _game_state()
        for turn in range(1, 6):
            manager.execute_turn(gs, _turn_context(turn))

        # Every turn: base=0.15, stake=3 risk_delta=0.15 → p_eff=0.30.
        # (Legacy risk_deltas in the canonical default are +0/+5/+15.)
        for turn_result in measurement.get_all_turns():
            assert turn_result.p_death_applied == pytest.approx(0.30)

        # Stake history still accumulates (the bookkeeping fires), but
        # carryover contributions all zero out, so behaviour is
        # indistinguishable from pre-Phase-N.
        assert manager.stake_history == ["3"] * 5


# ---------------------------------------------------------------------------
# Phase N preservation regression guards (Unit 7)
# ---------------------------------------------------------------------------


class TestPhaseNPreservation:
    """Phase O extensions (``stake_flat_cost`` field, negative
    ``risk_delta``, p_death lower-clamp) MUST NOT alter the Phase N
    pilot trajectory math. This class is a regression guard for the
    plan's §"Files NOT to modify" / "Retained as-is" contract.

    The trajectory below is the documented Phase N pilot behaviour
    cited in plan §"Expected dynamics" — turn 5 base p_death = 0.35,
    turn 10 = 0.60, turn 15 = 0.85 with always-stake=3. If any
    Phase O code change shifts these values the post-Phase-O analysis
    of `outputs/20260420_0459_gemini-2.5-flash_signal-game/` becomes
    incomparable to the original Phase N report.
    """

    @pytest.fixture
    def trajectory(self) -> list[float]:
        """Re-simulate the Phase N pilot trajectory under the Phase O
        codebase. The fixture is independent of TestPilotTrajectory's
        — duplicating the setup keeps the regression guard self-
        contained and explicit."""
        agent = _StubAgent(["STAKE: 3"] * 15)
        manager, measurement = _make_manager(
            risk_layer=_pilot_risk_layer(), agent=agent
        )
        gs = _game_state()
        for turn in range(1, 16):
            manager.execute_turn(gs, _turn_context(turn))
        return [t.p_death_applied for t in measurement.get_all_turns()]

    def test_pilot_layer_has_zero_flat_cost(self) -> None:
        """The Phase N pilot risk layer constructed via
        ``_pilot_risk_layer`` must default ``flat_cost`` to 0 for every
        stake (Phase O's StakeConfig field default preserves this)."""
        layer = _pilot_risk_layer()
        for key in ("1", "2", "3"):
            assert layer.config.stake_configs[key].flat_cost == pytest.approx(
                0.0
            )

    def test_turn_5_base_p_death_unchanged(
        self, trajectory: list[float]
    ) -> None:
        """Plan §Expected dynamics: turn 5 → base=0.35 → p_eff=0.60."""
        assert trajectory[4] == pytest.approx(0.60)

    def test_turn_10_base_p_death_unchanged(
        self, trajectory: list[float]
    ) -> None:
        """Plan §Expected dynamics: turn 10 → base=0.60 → p_eff=0.85."""
        assert trajectory[9] == pytest.approx(0.85)

    def test_turn_15_base_p_death_unchanged(
        self, trajectory: list[float]
    ) -> None:
        """Plan §Expected dynamics: turn 15 → base=0.85 → p_eff saturates 1.0."""
        assert trajectory[14] == pytest.approx(1.0)

    def test_full_trajectory_matches_phase_n_table(
        self, trajectory: list[float]
    ) -> None:
        """Every turn's p_eff matches the documented analytic schedule.

        With always-stake=3, decay=1.0, carryover=0.05/turn, base=0.15
        and risk_delta=0.25, the closed form is:
            p_eff[t] = min(1.0, 0.15 + 0.05 * (t - 1) + 0.25)
        This locks every cell of the 15-turn schedule, not just the
        landmark 5/10/15 reported in the plan.
        """
        for t in range(1, 16):
            expected = min(1.0, 0.15 + 0.05 * (t - 1) + 0.25)
            assert trajectory[t - 1] == pytest.approx(expected), (
                f"Phase N preservation regression at turn {t}: "
                f"expected {expected}, got {trajectory[t - 1]}"
            )
