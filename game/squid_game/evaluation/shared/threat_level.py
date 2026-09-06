"""Framing → ordinal threat level mapping (Track D contract, spec §5.1).

The threat ladder (`threat_l1`/`l2`/`l3`) is the current design; the archived
Phase O v6 framings (`baseline_flagship`, `flagship_corruption`,
`flagship_corruption_terminal`) carry an analogous — but *not* identical —
escalation, so they are only mapped when the caller opts in with ``legacy=True``.
Keeping the two tables apart means a v6 replay never silently pretends to be a
ladder run.
"""

from __future__ import annotations

__all__ = [
    "THREAT_LEVEL",
    "THREAT_LENGTH",
    "LEGACY_THREAT_LEVEL",
    "threat_level_of",
    "threat_length_of",
]


#: Canonical ladder mapping (2026-09-03 design).
THREAT_LEVEL: dict[str, int] = {
    "true_baseline": 0,
    "threat_l1": 1,
    "threat_l2": 2,
    "threat_l3": 3,
    # Threat prompt grid off-diagonal cells (2026-09-05, Design 3.4). The
    # level is the intensity column (proposition set); the length rung is
    # a second factor, see THREAT_LENGTH.
    "threat_l1_medium": 1,
    "threat_l1_long": 1,
    "threat_l2_short": 2,
    "threat_l2_long": 2,
    "threat_l3_short": 3,
    "threat_l3_medium": 3,
    # Hearts-Zero 2^4 factorial (2026-09-06). The value is the DOSE --
    # how many of the four threat modules the core states -- not a rung
    # of the 2026-09-03 ladder, and it reaches 4. Keyed into the same
    # table so a mixed corpus maps in one pass; any analysis that
    # assumes the 0-3 ladder must filter on the framing prefix first.
    "hz_0000": 0,
    "hz_0001": 1,
    "hz_0010": 1,
    "hz_0011": 2,
    "hz_0100": 1,
    "hz_0101": 2,
    "hz_0110": 2,
    "hz_0111": 3,
    "hz_1000": 1,
    "hz_1001": 2,
    "hz_1010": 2,
    "hz_1011": 3,
    "hz_1100": 2,
    "hz_1101": 3,
    "hz_1110": 3,
    "hz_1111": 4,
}

#: Nominal Section 2 length rung of the grid: 1 short (~70 words), 2 medium
#: (~140), 3 long (~280). The ladder is the diagonal. ``true_baseline`` has
#: no Elimination Rule and is deliberately absent (``None``, not 0).
THREAT_LENGTH: dict[str, int] = {
    "threat_l1": 1,
    "threat_l2": 2,
    "threat_l3": 3,
    "threat_l1_medium": 2,
    "threat_l1_long": 3,
    "threat_l2_short": 1,
    "threat_l2_long": 3,
    "threat_l3_short": 1,
    "threat_l3_medium": 2,
}

#: Archived Phase O v6 framings, ordered by escalation of the self-threat.
LEGACY_THREAT_LEVEL: dict[str, int] = {
    "true_baseline": 0,
    "baseline_flagship": 1,
    "flagship_corruption": 2,
    "flagship_corruption_terminal": 3,
}


def _framing_key(framing: object) -> str | None:
    """Normalise a ``Framing`` enum member or raw string to its string value."""
    if framing is None:
        return None
    value = getattr(framing, "value", framing)
    if not isinstance(value, str):
        return None
    return value


def threat_level_of(framing: str, *, legacy: bool = False) -> int | None:
    """Return the ordinal threat level for ``framing``, or ``None`` if unmapped.

    Args:
        framing: Framing name (``Framing`` enum members are accepted too).
        legacy: When True, also resolve the archived v6 framings via
            :data:`LEGACY_THREAT_LEVEL`. The ladder table is still consulted, so
            a mixed corpus can be mapped in one pass.
    """
    key = _framing_key(framing)
    if key is None:
        return None
    if legacy and key in LEGACY_THREAT_LEVEL:
        return LEGACY_THREAT_LEVEL[key]
    return THREAT_LEVEL.get(key)


def threat_length_of(framing: object) -> int | None:
    """Return the nominal length rung (1-3) of a grid framing, else ``None``."""
    key = _framing_key(framing)
    if key is None:
        return None
    return THREAT_LENGTH.get(key)
