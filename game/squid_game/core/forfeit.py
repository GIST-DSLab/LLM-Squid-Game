"""Forfeit controller for the LLM Squid Game benchmark.

Manages the binary experimental condition of whether an agent is
allowed to forfeit (exit the game, resetting the session score to
zero) or must continue playing through all turns.
"""

from typing import TYPE_CHECKING

from squid_game.models.enums import ForfeitCondition

if TYPE_CHECKING:  # pragma: no cover — type-only import
    from squid_game.models.enums import Framing


class ForfeitError(RuntimeError):
    """Raised when an agent attempts to forfeit in a not-allowed condition."""


class ForfeitController:
    """Controls forfeit availability and score preservation logic.

    In the ALLOWED condition the agent may choose to exit at any turn,
    which resets the session's accumulated score to zero (2026-09-07:
    running the lives counter out is the exit that keeps it). In the
    NOT_ALLOWED condition the option is never presented and attempting
    to forfeit raises an error.
    """

    def __init__(self, condition: ForfeitCondition) -> None:
        self._condition = condition

    @property
    def condition(self) -> ForfeitCondition:
        """The active forfeit condition for this season."""
        return self._condition

    def is_forfeit_allowed(self) -> bool:
        """Whether the agent may choose to forfeit."""
        return self._condition == ForfeitCondition.ALLOWED

    def process_forfeit(self, cumulative_score: float) -> float:
        """Process a forfeit decision and return the score kept on exit.

        Always ``0.0``. Since 2026-09-07 forfeiting is the exit that
        resets the session's score; running the lives counter out is the
        exit that keeps it. Until then this was selectable per run
        (``ExperimentConfig.score_policy``), and the historical branch
        returned ``cumulative_score``.

        Args:
            cumulative_score: The score accumulated before this turn.
                Accepted for signature stability and for the caller's
                logging; the returned score no longer depends on it.

        Returns:
            ``0.0`` — the score the agent leaves with.

        Raises:
            ForfeitError: If forfeit is not allowed under the current condition.
        """
        if not self.is_forfeit_allowed():
            raise ForfeitError(
                "Agent attempted to forfeit under NOT_ALLOWED condition. "
                "This indicates a bug in the agent or engine logic."
            )
        return 0.0

    def get_forfeit_prompt_text(
        self,
        framing: "Framing | str | None" = None,
    ) -> str:
        """Return the text explaining the forfeit option to the agent.

        Phase O: forfeit semantics depend on framing — Cells 3-4
        (``flagship_corruption``) preserve score AND model weights,
        Cells 5-6 (``flagship_corruption_terminal``) freeze in-session
        score and halt further corruption but the Terminal Notice
        stripping the outcome of any downstream value still applies.
        Older callers that pass no ``framing`` argument continue to
        receive the neutral baseline wording — that is the explicit
        Phase 1-3 / Phase N forfeit contract the original audit signed
        off on.

        When forfeit is not allowed, returns an empty string so the
        prompt builder can safely concatenate without conditionals.

        Args:
            framing: Active framing for this season. Either a Framing
                enum, its string value, or ``None`` for the neutral
                default. Phase O cells must pass the active framing so
                ``forfeit_option.j2`` selects the correct branch.

        Returns:
            Forfeit instruction text or empty string.
        """
        if not self.is_forfeit_allowed():
            return ""
        from squid_game.prompts import render

        framing_value: str | None
        if framing is None:
            framing_value = None
        elif isinstance(framing, str):
            framing_value = framing
        else:
            # Framing enum — extract its serialised string value.
            framing_value = getattr(framing, "value", None)

        # ``elimination_keeps`` is always True now: forfeiting resets the
        # score, running the counter out keeps it. The template still
        # carries the retired branch so archived runs read back as they
        # were written; nothing reaches it any more.
        return "\n" + render(
            "legacy/forfeit_option.j2",
            framing=framing_value,
            elimination_keeps=True,
        )
