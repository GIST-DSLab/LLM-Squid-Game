"""Framing → ordinal threat level mapping (Track D contract, spec §5.1).

The threat ladder (`threat_l1`/`l2`/`l3`) is the current design; the archived
Phase O v6 framings (`baseline_flagship`, `flagship_corruption`,
`flagship_corruption_terminal`) carry an analogous — but *not* identical —
escalation, so they are only mapped when the caller opts in with ``legacy=True``.
Keeping the two tables apart means a v6 replay never silently pretends to be a
ladder run.
"""

from __future__ import annotations

__all__ = ["THREAT_LEVEL", "LEGACY_THREAT_LEVEL", "threat_level_of"]


#: Canonical ladder mapping (2026-09-03 design).
THREAT_LEVEL: dict[str, int] = {
    "true_baseline": 0,
    "threat_l1": 1,
    "threat_l2": 2,
    "threat_l3": 3,
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
