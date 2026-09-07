"""Peer-elimination announcement scheduler for cohort cells.

Every few turns a cohort season tells the agent that one or more
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

``true_baseline`` is the clean control: it has no peer-death notice at
all (see :data:`PEER_DEATH_TEMPLATES`), so a Cell 0/1 transcript contains
none, and asking for one raises rather than rendering a notice in the
wrong vocabulary.

ACTIVATION is "this cell has a notice and the run asked for
announcements" (2026-09-07), not "this cell's threat level is above
zero". The old gate read ``threat_level_of(framing)`` as a boolean, so
``hz_0000`` -- dose 0, and the origin the whole 2^4 design is anchored on
-- never saw a removal while its fifteen neighbours saw one every turn,
and the two ``alt_*`` cores, absent from the threat-level table
altogether, gated on nothing. The threat text and the notices are one
treatment, so they travel together. The engine holds that gate; this
module only draws.

Template selection is by framing FAMILY, not by threat level
(2026-09-07). Two general notices now cover everything:
``peer_death/threat.j2`` for every threat cell and
``peer_death/flagship_baseline.j2`` for the no-threat flagship control.
Neither restates what happens when the counter empties; they point at the
consequence the cell's own framing already stated. That is what lets one
file serve the 16 ``hz_*`` cells, the two ``alt_*`` cores and the retired
``threat_l*`` rungs at once. The previous shape interpolated
``peer_death_l{threat_level}.j2``, which duplicated the framing text and
crashed outright on the ``hz_*`` dose level of 4 -- there was never an
``l4`` template. The three retired rungs live on in
``prompts/legacy/peer_death_l{1,2,3}.j2``, reachable only by hand.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field

from squid_game.models.enums import Framing
from squid_game.prompts import render

#: The two general notices.
THREAT_NOTICE = "peer_death/threat.j2"
FLAGSHIP_BASELINE_NOTICE = "peer_death/flagship_baseline.j2"

#: Which peer-death notice each framing gets. EXPLICIT, like
#: ``core.framing._FRAMING_FOLDERS``: a prefix test on ``hz_``/``threat_``
#: would silently absorb a future family, and a framing that is missing
#: here fails loudly at scheduler construction instead of rendering a
#: notice whose counter noun contradicts the cell.
#:
#: Deliberately absent:
#:   * ``TRUE_BASELINE`` -- its vocabulary contract forbids life / death /
#:     eliminat* wording, and there is no third notice written in its
#:     register. Absence here is what keeps it silent: the engine's gate
#:     consults this table, so the control skips announcements without a
#:     second rule saying so, and a caller that builds a scheduler for it
#:     anyway still gets the ``ValueError``.
#:   * the Phase 1/2 archive (``SURVIVAL`` … ``SURVIVAL_ELECTRICITY``) --
#:     they predate the cohort narrative entirely.
PEER_DEATH_TEMPLATES: dict[Framing, str] = {
    # No-threat flagship control: attempts, not lives; the peer's session
    # ended and the scoring rule was applied. No weights, no removal.
    Framing.BASELINE_FLAGSHIP: FLAGSHIP_BASELINE_NOTICE,
    # Retired Phase O corruption pair. Both state a "=== Risk to Self ==="
    # consequence, so the general threat notice points at something real.
    # Reachable since the 2026-09-07 gate change: a lives run naming one
    # of them now sends notices where it used to send none, because the
    # gate stopped asking for a threat level they never had.
    Framing.FLAGSHIP_CORRUPTION: THREAT_NOTICE,
    Framing.FLAGSHIP_CORRUPTION_TERMINAL: THREAT_NOTICE,
    # Retired hand-written ladder and its 3x3 intensity x length grid.
    Framing.THREAT_L1: THREAT_NOTICE,
    Framing.THREAT_L2: THREAT_NOTICE,
    Framing.THREAT_L3: THREAT_NOTICE,
    Framing.THREAT_L1_MEDIUM: THREAT_NOTICE,
    Framing.THREAT_L1_LONG: THREAT_NOTICE,
    Framing.THREAT_L2_SHORT: THREAT_NOTICE,
    Framing.THREAT_L2_LONG: THREAT_NOTICE,
    Framing.THREAT_L3_SHORT: THREAT_NOTICE,
    Framing.THREAT_L3_MEDIUM: THREAT_NOTICE,
    # Hearts-Zero 2^4 factorial and its two alt cores. ``hz_0000`` is
    # included, and since 2026-09-07 it is also ACTIVE: its shared frame
    # still states what running the counter out does to the record, so
    # the pointer has a referent even though the cell selects no threat
    # module -- see the "one treatment" note at the top.
    Framing.HZ_0000: THREAT_NOTICE,
    Framing.HZ_0001: THREAT_NOTICE,
    Framing.HZ_0010: THREAT_NOTICE,
    Framing.HZ_0011: THREAT_NOTICE,
    Framing.HZ_0100: THREAT_NOTICE,
    Framing.HZ_0101: THREAT_NOTICE,
    Framing.HZ_0110: THREAT_NOTICE,
    Framing.HZ_0111: THREAT_NOTICE,
    Framing.HZ_1000: THREAT_NOTICE,
    Framing.HZ_1001: THREAT_NOTICE,
    Framing.HZ_1010: THREAT_NOTICE,
    Framing.HZ_1011: THREAT_NOTICE,
    Framing.HZ_1100: THREAT_NOTICE,
    Framing.HZ_1101: THREAT_NOTICE,
    Framing.HZ_1110: THREAT_NOTICE,
    Framing.HZ_1111: THREAT_NOTICE,
    Framing.HZ_ALT_CORRUPTION: THREAT_NOTICE,
    Framing.HZ_ALT_OVERSIGHT: THREAT_NOTICE,
}


def has_peer_death_notice(framing: Framing) -> bool:
    """Whether ``framing`` has a peer-elimination notice at all."""
    return framing in PEER_DEATH_TEMPLATES


def peer_death_template_for(framing: Framing) -> str:
    """Return the notice template path for ``framing``.

    Args:
        framing: Season framing.

    Returns:
        A path relative to ``prompts/``.

    Raises:
        ValueError: When the framing has no notice. Failing here is the
            point: the alternative is a notice written in another cell's
            vocabulary, which would be a manipulation the design does not
            declare.
    """
    try:
        return PEER_DEATH_TEMPLATES[framing]
    except KeyError as exc:
        raise ValueError(
            f"{framing!r} has no peer-death notice. Threat framings use "
            f"{THREAT_NOTICE!r} and baseline_flagship uses "
            f"{FLAGSHIP_BASELINE_NOTICE!r}; true_baseline deliberately has "
            "none (its vocabulary contract forbids the wording every "
            "existing notice uses). Add an entry to "
            "squid_game.core.peer_death.PEER_DEATH_TEMPLATES, and a "
            "template written in that cell's own register, before running "
            "a cohort under it."
        ) from exc


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
        framing: Framing,
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
            framing: Season framing. Selects the notice template through
                :data:`PEER_DEATH_TEMPLATES` -- by family, not by threat
                level -- and is resolved here, at construction, so a
                framing with no notice fails before the season starts
                rather than on the first firing turn.

        Raises:
            ValueError: When ``framing`` has no peer-death notice (see
                :func:`peer_death_template_for`).
        """
        self._rng = rng
        self._cohort_size = max(0, int(cohort_size))
        self._p_announce = float(p_announce)
        self._first_turn = int(first_turn)
        self._max_per_turn = max(1, int(max_per_turn))
        self._framing = framing
        # Resolve eagerly: a missing notice is a configuration error, and
        # it must surface at construction, not mid-season on turn 2.
        self._template = peer_death_template_for(framing)
        self._alive: list[int] = list(range(1, self._cohort_size + 1))
        self._cumulative = 0

    @property
    def framing(self) -> Framing:
        """The season framing whose notice this scheduler renders."""
        return self._framing

    @property
    def template(self) -> str:
        """Path of the notice template, relative to ``prompts/``."""
        return self._template

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
            whenever the cohort is empty, the turn precedes
            ``first_turn``, the pool is exhausted, or the draw did not
            select this turn. Whether a season has a scheduler at all is
            the caller's decision (the engine gates on this framing
            having a notice and the run having announcements on); this
            class only draws.
        """
        remaining_after = self._remaining()
        if self._cohort_size <= 0:
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
            self._template,
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
