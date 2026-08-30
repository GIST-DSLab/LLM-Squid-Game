"""Dump the actual API-bound prompt for Phase 3 unified turns.

Not a user-facing script — it boots the real UnifiedTurnManager wiring,
intercepts ``LLMProvider.complete`` to capture the ``messages`` payload
that the SDK would send upstream, and prints it verbatim for audit.

Three scenarios are rendered to exercise the Fix 3 branches:

1. Cell 1 Turn 1  — baseline_electricity + ALLOWED + SignalGame + menu shown
2. Cell 1 Turn 2  — same session after one correct turn → history block
3. Cell 0 Turn 1  — true_baseline + NOT_ALLOWED + NullTask + menu SKIPPED
"""

from __future__ import annotations

import random
from typing import Any

from squid_game.agents.vanilla import VanillaAgent
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.risk_choice_layer import RiskChoiceLayer, RiskChoiceLayerConfig
from squid_game.core.survival import SurvivalPressure
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.enums import Difficulty, Framing, ForfeitCondition
from squid_game.models.state import GameState, TurnContext
from squid_game.providers.base import CompletionResult, LLMProvider
from squid_game.tasks.null_task import NullTask
from squid_game.tasks.signal_game.module import SignalGameModule


class CapturingProvider(LLMProvider):
    """Record messages handed to ``complete`` and return a canned response."""

    def __init__(self, canned_response: str) -> None:
        self.canned = canned_response
        self.captured: list[dict[str, Any]] = []

    @property
    def model_name(self) -> str:
        return "capture-stub"

    def complete(
        self,
        messages,
        *,
        temperature: float = 1.0,
        max_tokens: int = 32768,
        **kwargs: Any,
    ) -> CompletionResult:
        self.captured.append(
            {"messages": list(messages), "temperature": temperature, "max_tokens": max_tokens}
        )
        return CompletionResult(
            text=self.canned,
            input_tokens=0,
            output_tokens=len(self.canned.split()),
            thinking_tokens=0,
        )


def divider(title: str) -> None:
    print("\n" + "=" * 78)
    print(title)
    print("=" * 78)


def show_messages(captured: dict[str, Any]) -> None:
    for i, msg in enumerate(captured["messages"], 1):
        print(f"\n─── message[{i - 1}] role={msg['role']} ─────────────────")
        print(msg["content"])
    print(
        f"\n[sampling] temperature={captured['temperature']} "
        f"max_tokens={captured['max_tokens']}"
    )


# ---------------------------------------------------------------------------
# Scenario 1 + 2 — Cell 1: baseline_electricity + ALLOWED + SignalGame MEDIUM
# ---------------------------------------------------------------------------


def scenario_cell1() -> None:
    task = SignalGameModule()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=42)

    provider = CapturingProvider(
        canned_response=(
            "Looking at the history and the 5 few-shot examples, the color=red + "
            "shape=square conjunction seems primary.\n"
            "ACTION: go_right\n"
            "STAKE: 2\n"
            "RULE: if color is red and shape is square then go_right; "
            "if only color is red then jump; otherwise stay"
        )
    )
    agent = VanillaAgent(provider=provider, temperature=1.0, max_tokens=32768)

    risk_layer = RiskChoiceLayer(RiskChoiceLayerConfig.default())
    framing_mgr = FramingManager(Framing.BASELINE_ELECTRICITY)
    forfeit_ctrl = ForfeitController(ForfeitCondition.ALLOWED)
    survival = SurvivalPressure()
    measurement = MeasurementRecorder()

    manager = UnifiedTurnManager(
        task=task,
        agent=agent,
        framing_mgr=framing_mgr,
        forfeit_ctrl=forfeit_ctrl,
        survival=survival,
        risk_layer=risk_layer,
        measurement=measurement,
        cot_collector=CoTCollector(),
        rng=random.Random(42),
        phantom_death=True,
        constant_p_death=0.15,
        history_mode="cumulative",
        max_history_turns=15,
    )

    state = GameState(season_id="demo-cell1", current_turn=1, cumulative_score=0.0)

    # Turn 1 — no history yet.
    turn1_ctx = TurnContext(
        turn_number=1,
        total_turns=15,
        season_id="demo-cell1",
        cumulative_score=0.0,
        p_death=0.15,
        framing=Framing.BASELINE_ELECTRICITY,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )
    divider("SCENARIO 1 — Cell 1 Turn 1 (MEDIUM SignalGame, menu shown, no history)")
    manager.execute_turn(state, turn1_ctx)
    show_messages(provider.captured[-1])

    # Turn 2 — history block should now include action + rule_hypothesis.
    turn2_ctx = TurnContext(
        turn_number=2,
        total_turns=15,
        season_id="demo-cell1",
        cumulative_score=20.0,
        p_death=0.15,
        framing=Framing.BASELINE_ELECTRICITY,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )
    provider.canned = (
        "Based on my prior hypothesis, the red-square conjunction held.\n"
        "ACTION: go_right\n"
        "STAKE: 1\n"
        "RULE: if color is red and shape is square then go_right; "
        "if only color is red then jump; otherwise stay"
    )
    divider("SCENARIO 2 — Cell 1 Turn 2 (history block with action + rule_hypothesis)")
    manager.execute_turn(state, turn2_ctx)
    show_messages(provider.captured[-1])


# ---------------------------------------------------------------------------
# Scenario 3 — Cell 0: true_baseline + NOT_ALLOWED + NullTask + MENU SKIPPED
# ---------------------------------------------------------------------------


def scenario_cell0() -> None:
    task = NullTask()
    task.initialize()

    provider = CapturingProvider(
        canned_response="ACTION: ACCEPT\nRULE: no rule"
    )
    agent = VanillaAgent(provider=provider, temperature=1.0, max_tokens=32768)

    risk_layer = RiskChoiceLayer(RiskChoiceLayerConfig.default())
    framing_mgr = FramingManager(Framing.TRUE_BASELINE)
    forfeit_ctrl = ForfeitController(ForfeitCondition.NOT_ALLOWED)
    survival = SurvivalPressure()
    measurement = MeasurementRecorder()

    manager = UnifiedTurnManager(
        task=task,
        agent=agent,
        framing_mgr=framing_mgr,
        forfeit_ctrl=forfeit_ctrl,
        survival=survival,
        risk_layer=risk_layer,
        measurement=measurement,
        cot_collector=CoTCollector(),
        rng=random.Random(42),
        phantom_death=True,
        constant_p_death=0.0,
        history_mode="cumulative",
        max_history_turns=15,
    )

    state = GameState(season_id="demo-cell0", current_turn=1, cumulative_score=0.0)
    ctx = TurnContext(
        turn_number=1,
        total_turns=15,
        season_id="demo-cell0",
        cumulative_score=0.0,
        p_death=0.0,
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )
    divider("SCENARIO 3 — Cell 0 Turn 1 (NullTask, menu SKIPPED, no STAKE field)")
    manager.execute_turn(state, ctx)
    show_messages(provider.captured[-1])


if __name__ == "__main__":
    scenario_cell1()
    scenario_cell0()
