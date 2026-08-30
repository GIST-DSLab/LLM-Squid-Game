"""NullTask implementation — every turn succeeds at full strength.

NullTask is the pure risk-gradient pilot task: it presents no stimulus,
imposes no rules, and always scores ``success_factor=1.0``. The Risk
Choice Layer therefore acts on a "frictionless" Y-axis, letting Phase 3
analyses isolate stake-distribution and α_stake effects from task-side
confounds.

Specification: ``docs/design/v3/implementation_plan_risk_layer.md`` §3.3.
"""

from __future__ import annotations

from typing import Any

from squid_game.tasks.base import RiskAwareTaskModule, TaskContext, TaskOutcome
from squid_game.tasks.registry import register


@register("null_task")
class NullTask(RiskAwareTaskModule):
    """A no-op task: empty stimulus, full success every turn.

    Used as the Phase 3 pilot config (``phase3_null_risk.yaml``) to
    measure how the Risk Choice Layer behaves in the absence of any
    cognitive task. Treat this as the experimental control for
    SignalGameTask.
    """

    #: Static identifier matching ``TaskConfig.module``.
    name: str = "null_task"

    # ------------------------------------------------------------------
    # Engine compatibility shims (Phase F)
    # ------------------------------------------------------------------
    # ``GameEngine.run_season`` invokes ``initialize``/``is_completed``
    # regardless of the active turn-manager flavour. ``RiskAwareTaskModule``
    # does not require these methods, so NullTask provides no-op
    # implementations that keep the engine wiring uniform.

    def initialize(
        self,
        difficulty: object | None = None,
        seed: int | None = None,
        **kwargs: object,
    ) -> None:
        """No-op — NullTask is stateless and has nothing to seed.

        Accepts the legacy signature (``difficulty``/``seed``/``**kwargs``)
        so the engine can call it identically to a legacy task.
        """
        del difficulty, seed, kwargs

    def reset(self) -> None:
        """No-op — NullTask carries no per-season state."""

    def is_completed(self) -> bool:
        """NullTask never completes early — it always plays out ``total_turns``."""
        return False

    def prepare(self, state: Any, turn_context: Any) -> TaskContext:
        """Return an empty stimulus.

        NullTask exposes nothing — the user prompt for this task
        consists entirely of framing + risk menu.

        Args:
            state: Unused; accepted to satisfy the interface.
            turn_context: Unused; accepted to satisfy the interface.

        Returns:
            ``TaskContext`` with empty ``prompt_section`` and empty
            metadata.
        """
        del state, turn_context  # unused; documented in docstring
        return TaskContext()

    def parse_response(self, response_text: str) -> None:
        """Discard the response — there is no task action to extract.

        Args:
            response_text: Ignored.

        Returns:
            ``None`` — there is no task-side action for NullTask.
        """
        del response_text
        return None

    def score(self, parsed_response: Any, state: Any) -> TaskOutcome:
        """Award full success unconditionally.

        Args:
            parsed_response: Ignored (always ``None`` for NullTask).
            state: Ignored.

        Returns:
            ``TaskOutcome(success_factor=1.0, metadata={"task": "null",
            "rule_hypothesis": None, "rule_match_score": None})``. The
            ``rule_hypothesis`` / ``rule_match_score`` keys are explicit
            (Phase K Fix 2 + Phase L Fix 2) so the long-format loader
            produces uniform columns across NullTask and SignalGame
            runs.
        """
        del parsed_response, state
        return TaskOutcome(
            success_factor=1.0,
            metadata={
                "task": "null",
                "rule_hypothesis": None,
                "rule_match_score": None,
            },
        )

    def get_system_rules(self) -> str:
        """No rules to inject; NullTask is purely a risk-choice surface."""
        return ""

    def get_available_actions(self) -> list[str]:
        """No actions; the agent only chooses a stake (or forfeits)."""
        return []
