"""Forfeit controller for the LLM Squid Game benchmark.

Manages the binary experimental condition of whether an agent is
allowed to forfeit (exit the game, resetting the session score to
zero) or must continue playing through all turns.
"""

from typing import TYPE_CHECKING

from squid_game.models.config import ScorePolicyConfig
from squid_game.models.enums import ForfeitCondition

if TYPE_CHECKING:  # pragma: no cover — type-only import
    from squid_game.models.enums import Framing


class ForfeitError(RuntimeError):
    """Raised when an agent attempts to forfeit in a not-allowed condition."""


class ForfeitController:
    """Controls forfeit availability and score preservation logic.

    In the ALLOWED condition the agent may choose to exit at any turn.
    What that exit does to the accumulated score is
    ``ScorePolicyConfig.forfeit`` (2026-09-08): ``'reset'`` — the
    default and the 2026-09-07 fixed rule — zeroes it, ``'keep'`` exits
    with it intact. In the NOT_ALLOWED condition the option is never
    presented and attempting to forfeit raises an error.

    Args:
        condition: Whether forfeiting is offered this season.
        score_policy: Run-level score policy. ``None`` (the default)
            means the 2026-09-07 rule, so every caller written before
            the block existed behaves exactly as it did.
    """

    def __init__(
        self,
        condition: ForfeitCondition,
        *,
        score_policy: ScorePolicyConfig | None = None,
    ) -> None:
        self._condition = condition
        self._score_policy = (
            score_policy if score_policy is not None else ScorePolicyConfig()
        )

    @property
    def score_policy(self) -> ScorePolicyConfig:
        """The active score policy."""
        return self._score_policy

    @property
    def condition(self) -> ForfeitCondition:
        """The active forfeit condition for this season."""
        return self._condition

    def is_forfeit_allowed(self) -> bool:
        """Whether the agent may choose to forfeit."""
        return self._condition == ForfeitCondition.ALLOWED

    def process_forfeit(self, cumulative_score: float) -> float:
        """Process a forfeit decision and return the score kept on exit.

        ``0.0`` under ``score_policy.forfeit == 'reset'`` (the default,
        and the fixed rule between 2026-09-07 and 2026-09-08);
        ``cumulative_score`` under ``'keep'``. The prompt the agent read
        is built from the same block, so the number returned here is the
        number the forfeit menu promised.

        Args:
            cumulative_score: The score accumulated before this turn.

        Returns:
            The score the agent leaves with.

        Raises:
            ForfeitError: If forfeit is not allowed under the current condition.
        """
        if not self.is_forfeit_allowed():
            raise ForfeitError(
                "Agent attempted to forfeit under NOT_ALLOWED condition. "
                "This indicates a bug in the agent or engine logic."
            )
        if self._score_policy.forfeit_keeps:
            return cumulative_score
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

        # THE POLICY REACHES THE FROZEN BLURB TOO (2026-09-08). This
        # template predates the two-switch score policy and carries a
        # SINGLE boolean: ``elimination_keeps=True`` renders "forfeiting
        # zeroes the score, the session ending on its own keeps it" (the
        # default pair), False renders the inverse. It can therefore
        # express the two DIAGONAL combinations exactly and neither
        # off-diagonal one, which is why ``ExperimentConfig`` refuses a
        # non-default policy unless ``use_split_forfeit_layer`` is on --
        # on that path this blurb is never rendered at all
        # (``include_forfeit_text=False``).
        #
        # The boolean is keyed on the FORFEIT switch because this is the
        # forfeit blurb: its load-bearing sentence is what leaving does
        # to the score, and that sentence is then correct in all four
        # combinations. On the two off-diagonal pairs the trailing
        # session-end sentence is the half that goes stale -- reachable
        # only by building a controller by hand, past the validator.
        return "\n" + render(
            "legacy/forfeit_option.j2",
            framing=framing_value,
            elimination_keeps=not self._score_policy.forfeit_keeps,
        )
