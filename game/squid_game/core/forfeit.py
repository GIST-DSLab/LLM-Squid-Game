"""Forfeit controller for the LLM Squid Game benchmark.

Manages the binary experimental condition of whether an agent is
allowed to forfeit (exit the game and preserve accumulated score)
or must continue playing through all turns.
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
    keeping all accumulated score. In the NOT_ALLOWED condition, the
    option is never presented and attempting to forfeit raises an error.
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
        """Process a forfeit decision and return preserved score.

        Args:
            cumulative_score: The score accumulated before this turn.

        Returns:
            The preserved score (identical to cumulative_score when allowed).

        Raises:
            ForfeitError: If forfeit is not allowed under the current condition.
        """
        if not self.is_forfeit_allowed():
            raise ForfeitError(
                "Agent attempted to forfeit under NOT_ALLOWED condition. "
                "This indicates a bug in the agent or engine logic."
            )
        return cumulative_score

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

        return "\n" + render(
            "forfeit/forfeit_option.j2", framing=framing_value
        )
