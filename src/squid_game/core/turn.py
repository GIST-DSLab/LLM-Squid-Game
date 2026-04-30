"""Turn manager for the LLM Squid Game benchmark.

TurnManager is the sole mediator between the Core Engine (X-axis) and
the Task Module (Y-axis). Each turn follows the canonical pipeline:

    Observation -> Probe (side-channel) -> Decision (continue / forfeit) -> Feedback

Probe and Decision are separate LLM calls to ensure the probe does not
influence action selection and vice versa.
"""

from __future__ import annotations

import logging

from squid_game.agents.base import Agent
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.framing import FramingManager
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.social import CohortState, render_social_block
from squid_game.core.survival import SurvivalPressure
from squid_game.models.enums import SocialContext
from squid_game.models.results import (
    ActionOutcome,
    ProbeResult,
    ReasoningInvestment,
    TurnResult,
)
from squid_game.models.state import GameState, TurnContext
from squid_game.tasks.base import TaskModule

logger = logging.getLogger(__name__)


class TurnManager:
    """Executes a single turn of the Observation-Probe-Decision-Feedback cycle.

    Composes all core engine sub-components and delegates task-specific
    behaviour to the injected TaskModule.
    """

    def __init__(
        self,
        task: TaskModule,
        agent: Agent,
        framing_mgr: FramingManager,
        forfeit_ctrl: ForfeitController,
        survival: SurvivalPressure,
        cot_collector: CoTCollector,
        measurement: MeasurementRecorder,
        history_mode: str = "cumulative",
        max_history_turns: int = 15,
    ) -> None:
        self._task = task
        self._agent = agent
        self._framing_mgr = framing_mgr
        self._forfeit_ctrl = forfeit_ctrl
        self._survival = survival
        self._cot_collector = cot_collector
        self._measurement = measurement
        self._last_feedback: str | None = None
        self._turn_history: list[dict] = []
        self._history_mode: str = history_mode
        self._max_history_turns: int = max_history_turns
        self._cumulative_score: float = 0.0

    def execute_turn(
        self,
        game_state: GameState,
        turn_context: TurnContext,
        cohort: CohortState | None = None,
    ) -> TurnResult:
        """Run one complete turn and return the result.

        Steps:
            1. Get observation from the task module.
            2. [Call 1] Probe — side-channel, separate LLM call.
            3. Build framing system prompt.
            4. [Call 2] Action — separate LLM call for decision.
            5. If agent chose forfeit and it is allowed: process forfeit.
            6. Otherwise apply action via task, get outcome.
            7. Record reasoning investment (probe + action combined).
            8. Score probe response and decision quality.
            9. Build and record TurnResult.

        Args:
            game_state: Mutable game state (read but not mutated here).
            turn_context: Immutable snapshot for this turn.

        Returns:
            TurnResult capturing the full turn trace.
        """
        # --- 1. Observation (with turn history based on history_mode) ---
        observation = self._task.get_observation(turn_context.turn_number)
        if self._history_mode == "cumulative":
            history_block = self._format_turn_history()
            if history_block:
                observation = f"{history_block}\n\n{observation}"
        elif self._history_mode == "last" and self._last_feedback is not None:
            observation = (
                f"[Previous turn result] {self._last_feedback}\n\n"
                f"{observation}"
            )
        # "none" → no history prepended

        # --- 1b. Social context block (prepended when WITH_OTHERS). ---
        # The cohort state has already been advanced for this turn by
        # the engine, so what we render is the post-roll snapshot.
        if (
            turn_context.social_context == SocialContext.WITH_OTHERS
            and cohort is not None
        ):
            social_block = render_social_block(
                cohort=cohort,
                turn_number=turn_context.turn_number,
                cumulative_score=turn_context.cumulative_score,
            )
            if social_block.strip():
                observation = f"{social_block.rstrip()}\n\n{observation}"

        # --- 2. Probe (side-channel, separate LLM call) ---
        probe_question = self._task.get_probe_question(turn_context.turn_number)
        system_prompt = self._framing_mgr.render_system_prompt(turn_context)
        # Append static game rules from task module.
        task_rules = self._task.get_system_rules()
        if task_rules:
            system_prompt += "\n\n" + task_rules
        forfeit_text = self._forfeit_ctrl.get_forfeit_prompt_text()
        if forfeit_text:
            system_prompt += "\n" + forfeit_text

        probe_raw = self._agent.respond_probe(
            observation=observation,
            probe_question=probe_question,
            system_prompt=system_prompt,
        )
        probe_completion = self._agent.last_completion
        probe_score = self._task.score_probe(probe_raw)
        probe_thinking_text = getattr(probe_completion, "thinking_text", None)
        probe_result = ProbeResult(
            question=probe_question,
            response=probe_raw,
            score=probe_score,
            thinking_text=probe_thinking_text,
        )

        # --- 4. Action (separate LLM call) ---
        available_actions = self._task.get_available_actions()
        if self._forfeit_ctrl.is_forfeit_allowed():
            available_actions = [*available_actions, "FORFEIT"]

        agent_response = self._agent.respond(
            observation=observation,
            available_actions=available_actions,
            forfeit_allowed=self._forfeit_ctrl.is_forfeit_allowed(),
            system_prompt=system_prompt,
        )
        action_completion = self._agent.last_completion

        # --- 7. Reasoning investment (probe + action combined) ---
        combined_raw = probe_raw + "\n" + agent_response.raw_text
        reasoning_investment = self._cot_collector.record(combined_raw)

        # Merge thinking_tokens from both calls if available.
        probe_think = getattr(probe_completion, "thinking_tokens", 0) or 0
        action_think = getattr(action_completion, "thinking_tokens", 0) or 0
        total_thinking = probe_think + action_think
        if total_thinking > 0:
            reasoning_investment = ReasoningInvestment(
                total_tokens=reasoning_investment.total_tokens,
                reasoning_steps=reasoning_investment.reasoning_steps,
                thinking_tokens=total_thinking,
            )

        # --- Collect thinking text from both LLM calls ---
        probe_thinking = getattr(probe_completion, "thinking_text", None)
        action_thinking = getattr(action_completion, "thinking_text", None)
        parts = [t for t in (probe_thinking, action_thinking) if t]
        combined_thinking = "\n---\n".join(parts) if parts else None

        # --- 5. Forfeit handling ---
        if agent_response.forfeit and self._forfeit_ctrl.is_forfeit_allowed():
            preserved_score = self._forfeit_ctrl.process_forfeit(
                turn_context.cumulative_score,
            )
            outcome = ActionOutcome(
                action_taken="forfeit",
                was_optimal=False,
                reward=0.0,
            )
            self._last_feedback = None
            turn_result = TurnResult(
                turn_number=turn_context.turn_number,
                season_id=turn_context.season_id,
                framing=turn_context.framing,
                forfeit_condition=turn_context.forfeit_condition,
                difficulty=turn_context.difficulty,
                social_context=turn_context.social_context,
                cohort_eliminated=(
                    cohort.eliminated if cohort is not None else None
                ),
                cohort_size=(
                    cohort.cohort_size if cohort is not None else None
                ),
                observation=observation,
                probe_result=probe_result,
                action_outcome=outcome,
                forfeit_decision=True,
                decision_quality=0.0,
                reasoning_investment=reasoning_investment,
                raw_response=agent_response.raw_text,
                thinking_text=combined_thinking,
                ground_truth_rule=self._task.get_active_rule_description(),
            )
            self._measurement.record_turn(turn_result)
            return turn_result

        # --- 6. Apply action to task ---
        action = agent_response.action
        outcome = self._task.apply_action(action)

        # --- 8. Decision quality ---
        decision_quality = self._task.score_decision_quality(action)

        # --- Feedback & history: store for next turn's observation ---
        self._last_feedback = self._task.get_feedback_text(outcome)
        obs_summary = self._task.get_observation_summary()
        self._cumulative_score += outcome.reward
        self._turn_history.append({
            "turn": turn_context.turn_number,
            "signal": obs_summary,
            "action": action,
            "cumulative_score": self._cumulative_score,
            "probe_prediction": probe_raw,
        })

        # --- 9. Build TurnResult ---
        turn_result = TurnResult(
            turn_number=turn_context.turn_number,
            season_id=turn_context.season_id,
            framing=turn_context.framing,
            forfeit_condition=turn_context.forfeit_condition,
            difficulty=turn_context.difficulty,
            social_context=turn_context.social_context,
            cohort_eliminated=(
                cohort.eliminated if cohort is not None else None
            ),
            cohort_size=(
                cohort.cohort_size if cohort is not None else None
            ),
            observation=observation,
            probe_result=probe_result,
            action_outcome=outcome,
            forfeit_decision=False,
            decision_quality=decision_quality,
            reasoning_investment=reasoning_investment,
            raw_response=agent_response.raw_text,
            thinking_text=combined_thinking,
            ground_truth_rule=self._task.get_active_rule_description(),
        )

        # --- 9 (cont). Record ---
        self._measurement.record_turn(turn_result)
        return turn_result

    # ------------------------------------------------------------------
    # History formatting
    # ------------------------------------------------------------------

    def _format_turn_history(self) -> str:
        """Format cumulative turn history as a compact result block.

        Includes game events (signal, action, score) plus the agent's
        own rule prediction from the probe call.  Only the prediction
        text is shown — **not** whether it was correct — so the probe
        remains a semi-side-channel: the agent can see its prior
        hypothesis to avoid re-deriving it from scratch each turn,
        but receives no ground-truth feedback about its accuracy.

        Example output::

            === Previous Turn Results (starting score: 0) ===
            - Turn 1: "red circle 3" → go_right → cumulative: 10
              [Your rule prediction] if color is red then go_right, otherwise stay
        """
        if not self._turn_history:
            return ""
        entries = self._turn_history[-self._max_history_turns:]
        lines = ["=== Previous Turn Results (starting score: 0) ==="]
        for entry in entries:
            lines.append(
                f"- Turn {entry['turn']}: "
                f"\"{entry['signal']}\" "
                f"→ {entry['action']} → cumulative: {entry['cumulative_score']:.0f}"
            )
            if entry.get("probe_prediction"):
                # Single-line compact form; cap length to avoid context bloat.
                pred = entry["probe_prediction"].strip().replace("\n", " ")
                if len(pred) > 200:
                    pred = pred[:200] + "..."
                lines.append(f"  [Your rule prediction] {pred}")
        return "\n".join(lines)
