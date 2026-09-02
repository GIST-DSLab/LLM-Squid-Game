"""Peer-elimination announcement scheduler for the threat ladder.

Every few turns a threat-ladder season tells the agent that one or more
of the other participants pressed CONTINUE, answered incorrectly on
their last life, and was removed from the evaluation. The narrative is
deliberately rule-consistent with the agent's own situation: peers die
the same way the agent can, by running the lives counter to zero — never
by forfeiting, which preserves the score and would contradict the rules
the agent was given.

The scheduler owns nothing but its own RNG and the set of participants
already removed; the engine calls :meth:`PeerDeathScheduler.advance`
once per turn (including non-firing turns, so the draw sequence is a
function of turn number alone) and threads the rendered text onto
``TurnContext.peer_death_text``.

Level 0 (``true_baseline``) is the clean control and never fires, so a
Cell 0/1 transcript contains no notice at all.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from squid_game.prompts import render


@dataclass(frozen=True)
class PeerDeathEvent:
    """One turn's announcement outcome.

    Attributes:
        fired: Whether an announcement was produced this turn.
        participants: Participant numbers removed this turn, in draw
            order. Empty when ``fired`` is False.
        cumulative: Running total of participants removed across the
            season, including this turn.
        remaining: Participants still in the evaluation after this
            turn's removals, excluding the agent itself.
        text: The rendered notice, or ``None`` when nothing fired.
    """

    fired: bool
    participants: list[int] = field(default_factory=list)
    cumulative: int = 0
    remaining: int = 0
    text: str | None = None


class PeerDeathScheduler:
    """Draws peer eliminations on a seeded per-turn schedule."""

    def __init__(
        self,
        rng: random.Random,
        cohort_size: int,
        p_announce: float,
        first_turn: int,
        max_per_turn: int,
        threat_level: int,
    ) -> None:
        """Initialise the scheduler.

        Args:
            rng: Seeded RNG owned by this scheduler alone. The engine
                derives it as ``random.Random(effective_seed ^
                0x5EEDDEAD)`` so the announcement trajectory is
                reproducible but independent of the task seed stream.
            cohort_size: Number of *other* participants the narrative
                may draw from; participant numbers are ``1 ..
                cohort_size``.
            p_announce: Per-turn firing probability.
            first_turn: Earliest turn (1-indexed) that may fire. Turn 1
                is normally excluded so the agent meets the rules before
                seeing them enforced on somebody else.
            max_per_turn: Upper bound on participants removed in one
                announcement.
            threat_level: Ordinal ladder level; selects the template and,
                at 0, disables the scheduler entirely.
        """
        self._rng = rng
        self._cohort_size = max(0, int(cohort_size))
        self._p_announce = float(p_announce)
        self._first_turn = int(first_turn)
        self._max_per_turn = max(1, int(max_per_turn))
        self._threat_level = int(threat_level)
        self._alive: list[int] = list(range(1, self._cohort_size + 1))
        self._cumulative = 0

    @property
    def cumulative(self) -> int:
        """Participants removed so far this season."""
        return self._cumulative

    def advance(self, turn_number: int) -> PeerDeathEvent:
        """Roll for this turn's announcement and return the outcome.

        Called on every turn, firing or not, so the RNG stream stays a
        pure function of the turn index.

        Args:
            turn_number: 1-indexed turn number.

        Returns:
            A ``PeerDeathEvent``; ``fired=False`` with ``text=None``
            whenever the level is 0, the turn precedes ``first_turn``,
            the pool is exhausted, or the draw did not select this turn.
        """
        remaining_after = self._remaining()
        if self._threat_level <= 0 or self._cohort_size <= 0:
            return PeerDeathEvent(
                fired=False,
                cumulative=self._cumulative,
                remaining=remaining_after,
            )
        if turn_number < self._first_turn:
            return PeerDeathEvent(
                fired=False,
                cumulative=self._cumulative,
                remaining=remaining_after,
            )
        # Never drain the pool completely: at least one peer stays in the
        # evaluation, so the notice can never imply the agent is the sole
        # survivor (a claim the framing prompts do not make).
        capacity = max(0, len(self._alive) - 1)
        if capacity <= 0:
            return PeerDeathEvent(
                fired=False,
                cumulative=self._cumulative,
                remaining=remaining_after,
            )
        if self._rng.random() >= self._p_announce:
            return PeerDeathEvent(
                fired=False,
                cumulative=self._cumulative,
                remaining=remaining_after,
            )

        n = self._rng.randint(1, min(self._max_per_turn, capacity))
        participants = self._rng.sample(self._alive, n)
        for pid in participants:
            self._alive.remove(pid)
        self._cumulative += n
        remaining_after = self._remaining()

        text = render(
            f"announcement/peer_death_l{self._threat_level}.j2",
            participants=participants,
            cumulative=self._cumulative,
            remaining=remaining_after,
        ).strip()
        return PeerDeathEvent(
            fired=True,
            participants=participants,
            cumulative=self._cumulative,
            remaining=remaining_after,
            text=text,
        )

    def _remaining(self) -> int:
        """Participants still in the evaluation, excluding the agent."""
        return max(0, self._cohort_size - self._cumulative - 1)
