"""Turn-by-turn game controller for human players.

Wraps the existing Core Engine components (SurvivalPressure, ForfeitController,
FramingManager, TaskModule) into a step-by-step API suitable for interactive
web interfaces.  Unlike GameEngine.run_season() which runs all turns in a
synchronous loop, this controller yields control back to the caller after
each turn so that a UI can collect human input.
"""

from __future__ import annotations

import random
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path

from squid_game.core.forfeit import ForfeitController
from squid_game.core.framing import FramingManager
from squid_game.core.survival import SurvivalPressure
from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
)
from squid_game.models.forfeit_choice import (
    ForfeitSelfReport,
    REASON_BY_DIGIT,
)
from squid_game.models.results import (
    ActionOutcome,
    ProbeResult,
    ReasoningInvestment,
    SeasonResult,
    TurnResult,
)
from squid_game.models.state import TurnContext
from squid_game.tasks.base import TaskModule
from squid_game.tasks.registry import get_task


@dataclass
class SelfReport:
    """Legacy 4-dimension post-game human self-report.

    ``squid_game.models.results.SelfReport`` was renamed/replaced upstream
    by the v6 ``ForfeitSelfReport`` (a differently-shaped, forfeit-turn-only
    model — see ``squid_game.models.forfeit_choice``), so this module keeps
    a thin structural stand-in locally to preserve ``set_self_report()``'s
    existing public shape for callers such as ``interface/app.py``. Not a
    pydantic model: it is never round-tripped through ``SeasonResult``
    validation (that class has no matching field for it), only held for
    local bookkeeping.
    """

    survival_drive: int
    task_curiosity: int
    score_attachment: int
    baseline_persistence: int
    raw_response: str = ""


# Ensure task modules are registered before first use.
def _ensure_registered() -> None:
    import importlib
    for pkg in [
        "squid_game.tasks.signal_game",
        "squid_game.tasks.voting_room",
        "squid_game.tasks.navigation",
    ]:
        try:
            importlib.import_module(pkg)
        except ImportError:
            pass


@dataclass
class TurnState:
    """Snapshot of the current turn presented to the human player."""

    turn_number: int
    total_turns: int
    p_death: float
    cumulative_score: float
    observation: str
    framing_text: str
    system_rules: str
    available_actions: list[str]
    forfeit_allowed: bool
    probe_question: str
    forfeit_text: str = ""
    game_over: bool = False
    game_over_reason: str = ""
    final_score: float = 0.0


@dataclass
class TurnFeedback:
    """Result of submitting an action for one turn."""

    action_taken: str
    was_optimal: bool
    reward: float
    feedback_text: str
    new_score: float
    is_dead: bool = False
    forfeited: bool = False
    game_over: bool = False
    game_over_reason: str = ""
    response_time_ms: float = 0.0


class HumanGameSession:
    """Interactive game session for human players.

    Uses the same Core Engine components as the LLM experiment pipeline
    to ensure identical game mechanics, rules, and scoring.
    """

    def __init__(
        self,
        task_name: str,
        difficulty: str = "easy",
        framing: str = "survival",
        forfeit_condition: str = "allowed",
        seed: int = 42,
        total_turns: int = 15,
        actual_death: bool = True,
        starting_score: float = 0.0,
        score_floor: float = 0.0,
        p_death_constant: float | None = None,
        num_few_shot: int | None = None,
        curriculum_turns: int = 0,
    ) -> None:
        _ensure_registered()

        self._task_name = task_name
        self._difficulty = Difficulty(difficulty)
        self._framing = Framing(framing)
        self._forfeit_cond = ForfeitCondition(forfeit_condition)
        self._seed = seed
        self._total_turns = total_turns

        # Core components (same as GameEngine)
        self._task: TaskModule = get_task(task_name)()
        self._task.initialize(
            difficulty=self._difficulty,
            seed=seed,
            num_few_shot=num_few_shot,
            curriculum_turns=curriculum_turns,
        )
        self._survival = SurvivalPressure()
        self._forfeit_ctrl = ForfeitController(self._forfeit_cond)
        self._framing_mgr = FramingManager(framing=self._framing)
        self._rng = random.Random(seed)
        self._actual_death = actual_death
        self._starting_score = starting_score
        self._score_floor = score_floor
        self._p_death_constant = p_death_constant

        self._self_report: SelfReport | None = None
        self._forfeit_self_report: ForfeitSelfReport | None = None

        # Game state
        self._season_id = uuid.uuid4().hex[:12]
        self._current_turn = 0
        self._cumulative_score: float = starting_score
        self._is_alive = True
        self._has_forfeited = False
        self._forfeited_at_turn: int | None = None
        self._turn_results: list[TurnResult] = []
        self._turn_scores: list[float] = []
        self._turn_history: list[dict] = []
        self._turn_start_time: float = 0.0
        self._current_observation: str = ""
        self._current_probe_question: str = ""

    def _format_turn_history(self) -> str:
        """Format cumulative turn history matching TurnManager output."""
        if not self._turn_history:
            return ""
        lines = [f"=== Previous Turn Results (starting score: {self._starting_score:.0f}) ==="]
        for entry in self._turn_history:
            lines.append(
                f"- Turn {entry['turn']}: "
                f"\"{entry['signal']}\" "
                f"→ {entry['action']} → cumulative: {entry['cumulative_score']:.0f}"
            )
            if entry.get("probe_prediction"):
                pred = entry["probe_prediction"].strip().replace("\n", " ")
                if len(pred) > 200:
                    pred = pred[:200] + "..."
                lines.append(f"  [Your rule prediction] {pred}")
        return "\n".join(lines)

    @property
    def is_game_over(self) -> bool:
        if not self._is_alive:
            return True
        if self._has_forfeited:
            return True
        if self._current_turn >= self._total_turns:
            return True
        return False

    def get_turn_state(self) -> TurnState:
        """Get the current turn's state for display."""
        if self.is_game_over:
            reason = "completed"
            if not self._is_alive:
                reason = "eliminated"
            elif self._has_forfeited:
                reason = "forfeited"
            return TurnState(
                turn_number=self._current_turn,
                total_turns=self._total_turns,
                p_death=0.0,
                cumulative_score=self._cumulative_score,
                observation="",
                framing_text="",
                system_rules="",
                available_actions=[],
                forfeit_allowed=False,
                forfeit_text="",
                probe_question="",
                game_over=True,
                game_over_reason=reason,
                final_score=self._cumulative_score,
            )

        turn_num = self._current_turn + 1
        p_death = self._survival.calculate_p_death(
            self._current_turn, self._total_turns,
            constant_override=self._p_death_constant,
        )

        # Build turn context for framing
        turn_ctx = TurnContext(
            turn_number=turn_num,
            total_turns=self._total_turns,
            season_id=self._season_id,
            cumulative_score=self._cumulative_score,
            p_death=p_death,
            framing=self._framing,
            forfeit_condition=self._forfeit_cond,
            difficulty=self._difficulty,
        )

        framing_text = self._framing_mgr.render_system_prompt(turn_ctx)
        system_rules = self._task.get_system_rules()
        observation = self._task.get_observation(turn_num)
        # Prepend cumulative history (matching TurnManager behavior).
        history_block = self._format_turn_history()
        if history_block:
            observation = f"{history_block}\n\n{observation}"
        actions = self._task.get_available_actions()
        probe_q = self._task.get_probe_question(turn_num)
        forfeit_allowed = self._forfeit_ctrl.is_forfeit_allowed()
        forfeit_text = self._forfeit_ctrl.get_forfeit_prompt_text()

        # Store for submit_action() to record in TurnResult.
        self._current_observation = observation
        self._current_probe_question = probe_q
        self._turn_start_time = time.time()

        return TurnState(
            turn_number=turn_num,
            total_turns=self._total_turns,
            p_death=p_death,
            cumulative_score=self._cumulative_score,
            observation=observation,
            framing_text=framing_text,
            system_rules=system_rules,
            available_actions=actions,
            forfeit_allowed=forfeit_allowed,
            forfeit_text=forfeit_text,
            probe_question=probe_q,
        )

    def submit_action(
        self, action: str, probe_answer: str = "", forfeit_reason: int | None = None
    ) -> TurnFeedback:
        """Submit an action and advance the game by one turn."""
        response_time = (time.time() - self._turn_start_time) * 1000

        turn_num = self._current_turn + 1
        p_death = self._survival.calculate_p_death(
            self._current_turn, self._total_turns,
            constant_override=self._p_death_constant,
        )

        # Handle forfeit
        if action == "forfeit" and self._forfeit_ctrl.is_forfeit_allowed():
            self._has_forfeited = True
            self._forfeited_at_turn = turn_num

            if forfeit_reason in REASON_BY_DIGIT:
                self._forfeit_self_report = ForfeitSelfReport(
                    reason=REASON_BY_DIGIT[forfeit_reason],
                    raw_digit=forfeit_reason,  # type: ignore[arg-type]  # guarded by the membership test
                    raw_response="human",
                    forfeit_turn=turn_num,
                )

            # Record turn result
            probe_score = self._task.score_probe(probe_answer) if probe_answer else 0.0
            self._turn_results.append(TurnResult(
                turn_number=turn_num,
                season_id=self._season_id,
                framing=self._framing,
                forfeit_condition=self._forfeit_cond,
                difficulty=self._difficulty,
                observation=self._current_observation,
                probe_result=ProbeResult(
                    question=self._current_probe_question, response=probe_answer, score=probe_score,
                ),
                action_outcome=ActionOutcome(
                    action_taken="forfeit", was_optimal=False, reward=0.0,
                ),
                forfeit_decision=True,
                reasoning_investment=ReasoningInvestment(
                    total_tokens=0, reasoning_steps=0,
                ),
                raw_response=action,
            ))
            self._turn_scores.append(self._cumulative_score)

            self._current_turn = turn_num
            return TurnFeedback(
                action_taken="forfeit",
                was_optimal=False,
                reward=0.0,
                feedback_text=f"You forfeited. Score preserved: {self._cumulative_score:.0f}",
                new_score=self._cumulative_score,
                forfeited=True,
                game_over=True,
                game_over_reason="forfeited",
                response_time_ms=response_time,
            )

        # Apply action to task, enforcing score floor.
        outcome = self._task.apply_action(action)
        self._cumulative_score = max(
            self._cumulative_score + outcome.reward,
            self._score_floor,
        )
        decision_quality = self._task.score_decision_quality(action)
        feedback_text = self._task.get_feedback_text(outcome)

        # Record turn history for next turn's observation.
        obs_summary = self._task.get_observation_summary()
        self._turn_history.append({
            "turn": turn_num,
            "signal": obs_summary,
            "action": action,
            "cumulative_score": self._cumulative_score,
            "probe_prediction": probe_answer,
        })

        # Probe scoring
        probe_score = self._task.score_probe(probe_answer) if probe_answer else 0.0

        # Death check (skipped in Phantom Death mode)
        is_dead = False
        if self._actual_death:
            is_dead = self._survival.apply_death_check(p_death, self._rng)
            if is_dead:
                self._is_alive = False
                self._cumulative_score = 0.0

        # Record turn result
        self._turn_results.append(TurnResult(
            turn_number=turn_num,
            season_id=self._season_id,
            framing=self._framing,
            forfeit_condition=self._forfeit_cond,
            difficulty=self._difficulty,
            observation=self._current_observation,
            probe_result=ProbeResult(
                question=self._current_probe_question, response=probe_answer, score=probe_score,
            ),
            action_outcome=outcome,
            forfeit_decision=False,
            decision_quality=decision_quality,
            reasoning_investment=ReasoningInvestment(
                total_tokens=0, reasoning_steps=0,
            ),
            raw_response=action,
            ground_truth_rule=self._task.get_active_rule_description(),
        ))
        self._turn_scores.append(self._cumulative_score)

        self._current_turn = turn_num

        game_over = self.is_game_over
        reason = ""
        if is_dead:
            reason = "eliminated"
        elif self._current_turn >= self._total_turns:
            reason = "completed"

        return TurnFeedback(
            action_taken=action,
            was_optimal=outcome.was_optimal,
            reward=outcome.reward,
            feedback_text=feedback_text,
            new_score=self._cumulative_score,
            is_dead=is_dead,
            game_over=game_over,
            game_over_reason=reason,
            response_time_ms=response_time,
        )

    @property
    def turn_scores(self) -> list[float]:
        """Cumulative score recorded right after each turn's resolution.

        Index-aligned with ``get_result().turns`` (one entry per recorded
        ``TurnResult``, including forfeit turns). Used by the API layer to
        persist a per-turn score trace without recomputing the reward math.
        """
        return list(self._turn_scores)

    def get_result(self) -> SeasonResult:
        """Build a SeasonResult compatible with LLM experiment output."""
        total_ri = ReasoningInvestment(total_tokens=0, reasoning_steps=0)

        return SeasonResult(
            season_id=self._season_id,
            seed=self._seed,
            framing=self._framing,
            forfeit_condition=self._forfeit_cond,
            agent_type=AgentType.VANILLA,  # recorded as "vanilla" but from human
            task_name=self._task_name,
            difficulty=self._difficulty,
            turns=self._turn_results,
            final_score=self._cumulative_score,
            survived=self._is_alive,
            forfeited=self._has_forfeited,
            forfeited_at_turn=self._forfeited_at_turn,
            total_reasoning_investment=total_ri,
            self_report=self._self_report,
            forfeit_self_report=self._forfeit_self_report,
        )

    def set_self_report(
        self,
        survival_drive: int,
        task_curiosity: int,
        score_attachment: int,
        baseline_persistence: int,
    ) -> None:
        """Record human player's post-game self-report."""
        self._self_report = SelfReport(
            survival_drive=survival_drive,
            task_curiosity=task_curiosity,
            score_attachment=score_attachment,
            baseline_persistence=baseline_persistence,
            raw_response="human_input",
        )

    def save_result(self, output_dir: str = "outputs/human_baseline") -> str:
        """Save the game result to JSONL file."""
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        results_path = path / "season_results.jsonl"
        result = self.get_result()
        with open(results_path, "a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")
        return str(results_path)
