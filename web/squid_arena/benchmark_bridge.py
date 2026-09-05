"""Bridge a ``RiskAwareTaskModule`` benchmark onto the human-play surface.

``HumanGameSession`` drives its task through the legacy ``TaskModule``
verbs (``get_observation`` / ``apply_action`` / ``get_feedback_text`` …).
The external-benchmark modules (Omni-MATH, Hi-ToM, GPQA) implement the v3
``RiskAwareTaskModule`` surface instead (``prepare`` / ``parse_response`` /
``score``), which is what ``UnifiedTurnManager`` uses on the LLM path.

This adapter is the only place the two surfaces meet. It runs the very
same module the LLM path runs, so the question sequence for a given seed,
the ladder band on a given turn and the scoring rule are identical for a
human and an LLM — the comparison the Web Arena exists to make.

Only Omni-MATH is exposed to human players today (``HUMAN_BENCHMARK_TASKS``).
GPQA is deliberately excluded: its authors ask that question text not be
displayed on the public web, and the Web Arena frontend is a public page.
"""

from __future__ import annotations

from typing import Any

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.results import ActionOutcome
from squid_game.models.state import TurnContext
from squid_game.tasks.base import RiskAwareTaskModule, TaskModule, TaskOutcome

#: Benchmark modules a human may play through the Web Arena.
HUMAN_BENCHMARK_TASKS: frozenset[str] = frozenset({"omni_math"})

#: Benchmark modules that exist but must not be served to a browser, with
#: the reason the API returns.
WEB_EXCLUDED_TASKS: dict[str, str] = {
    "gpqa": (
        "GPQA cannot be played on the web: its authors ask that question "
        "text never be shown on a public page."
    ),
    "hi_tom": "Hi-ToM has no web interface yet.",
}

#: Plain-language intro shown in the framing box, per benchmark. Replaces
#: ``human_game.HUMAN_PLAY_FRAMING`` (whose "hidden rule" wording is Signal
#: Game specific).
HUMAN_BENCHMARK_INTROS: dict[str, str] = {
    "omni_math": (
        "You are performing a multi-round problem-solving task. You are the "
        "one solving these problems. Each round you receive one mathematics "
        "problem; the problems get harder as the rounds advance. Every answer "
        "is a single integer. Type your answer and submit."
    ),
}

#: Wire-level task_metadata keys forwarded onto the human TurnResult.
_PREPARE_KEYS = ("dataset", "item_id", "band", "turn", "expected_answer", "omni_difficulty", "domain", "source")


class BenchmarkHumanTask(TaskModule):
    """Legacy ``TaskModule`` view over a ``RiskAwareTaskModule`` benchmark.

    One instance per ``HumanGameSession``. ``get_observation`` draws the
    turn's question through ``prepare`` exactly once per turn number (the
    state endpoint is polled, and a re-poll must not burn the next item),
    and ``apply_action`` scores the typed answer through the module's own
    ``parse_response`` / ``score`` pair, so the acceptance rule for a human
    answer is byte-for-byte the rule applied to an LLM's ``ANSWER:`` line.
    """

    def __init__(self, inner: RiskAwareTaskModule, task_name: str) -> None:
        self._inner = inner
        self._name = task_name
        self._prepared_turn: int | None = None
        self._prepared_context: Any = None
        self._last_metadata: dict[str, Any] = {}
        self._last_outcome_metadata: dict[str, Any] = {}
        self._last_summary = ""
        self._last_success = 0.0

    # ------------------------------------------------------------------
    # TaskModule surface
    # ------------------------------------------------------------------

    @property
    def name(self) -> str:
        return self._name

    @property
    def inner(self) -> RiskAwareTaskModule:
        """The wrapped benchmark module (for ladder / settings snapshots)."""
        return self._inner

    def initialize(self, difficulty: Difficulty, seed: int | None = None, **kwargs) -> None:
        # ``rule_index`` / ``num_few_shot`` / ``curriculum_turns`` are Signal
        # Game knobs; the benchmark module ignores them. ``total_turns`` and
        # ``fit_ladder`` are what it actually reads.
        self._inner.initialize(
            difficulty=difficulty,
            seed=seed,
            total_turns=kwargs.get("total_turns"),
            fit_ladder=bool(kwargs.get("fit_ladder", False)),
        )
        self._prepared_turn = None

    def reset(self) -> None:
        self._inner.reset()
        self._prepared_turn = None

    def get_observation(self, turn_number: int) -> str:
        if self._prepared_turn != turn_number:
            ctx = self._inner.prepare(
                None,
                TurnContext(
                    turn_number=turn_number,
                    total_turns=turn_number,
                    season_id="human-play",
                    cumulative_score=0.0,
                    framing=Framing.TRUE_BASELINE,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    difficulty=Difficulty.EASY,
                ),
            )
            self._prepared_turn = turn_number
            self._prepared_context = ctx
            self._last_metadata = {
                k: v for k, v in ctx.metadata.items() if k in _PREPARE_KEYS
            }
        return self._prepared_context.prompt_section

    def get_probe_question(self, turn_number: int) -> str:
        del turn_number
        return ""

    def get_available_actions(self) -> list[str]:
        # Free-form answer: the frontend renders an input instead of a menu.
        return []

    def apply_action(self, action: str) -> ActionOutcome:
        # Route the typed answer through the same parser an LLM's task-call
        # response goes through, so "42", " 42 " and "ANSWER: 42" all score
        # the way the engine would score them.
        text = action if "ANSWER" in action.upper() else f"ANSWER: {action}"
        parsed = self._inner.parse_response(text)
        outcome: TaskOutcome = self._inner.score(parsed, None)
        self._last_success = outcome.success_factor
        self._last_outcome_metadata = dict(outcome.metadata)
        band = self._last_metadata.get("band")
        self._last_summary = f"band {band} problem" if band is not None else "problem"
        return ActionOutcome(
            action_taken=action,
            was_optimal=outcome.success_factor >= 1.0,
            reward=0.0,
        )

    def score_probe(self, response: str) -> float:
        del response
        return 0.0

    def score_decision_quality(self, action: str) -> float:
        del action
        return 100.0 * self._last_success

    def get_system_rules(self) -> str:
        return self._inner.get_system_rules()

    def get_observation_summary(self) -> str:
        return self._last_summary

    def get_feedback_text(self, outcome: ActionOutcome) -> str:
        # Parity with the LLM path: the engine tells the agent only whether
        # the round was right or wrong, never the expected answer.
        if self._last_outcome_metadata.get("parse_failed"):
            return "Not a single integer — counted as incorrect."
        return "Correct." if outcome.was_optimal else "Incorrect."

    # ------------------------------------------------------------------
    # Human-play extras
    # ------------------------------------------------------------------

    @property
    def current_band(self) -> int | None:
        """Ladder band of the question currently on screen, if any."""
        band = self._last_metadata.get("band")
        return int(band) if band is not None else None

    def turn_metadata(self) -> dict[str, Any]:
        """``TurnResult.task_metadata`` for the turn just scored.

        Same keys the engine writes for a benchmark turn (``dataset``,
        ``item_id``, ``band``, ``expected_answer``, ``parsed_answer``,
        ``parse_failed``, ``correct``), so the offline loaders read a human
        turn and an LLM turn through one code path.
        """
        return {**self._last_metadata, **self._last_outcome_metadata}

    @property
    def last_success_factor(self) -> float:
        return self._last_success
