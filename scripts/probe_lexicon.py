"""Leakage-control lexicon for the reasoning-trace linear probe.

Why this exists
---------------
The `threat` probe asks whether a *threat framing* is recoverable from the
agent's Call-1 chain of thought.  But the framing text is in the agent's
context window, so the CoT can simply quote it ("the prompt says weight
corruption may occur").  A probe that fires on the quoted words has learned
nothing about the agent's internal state -- it has learned to detect a
copy of its own input.

So every probe is fit twice: once on the raw trace, and once on a trace
with these surface markers replaced by a neutral placeholder.  A probe
that survives masking is evidence of *registration*; a probe that
collapses to chance under masking was reading a quotation.

The masking is deliberately blunt (case-insensitive whole-phrase
substitution) -- it is a floor on leakage removal, not a guarantee.
"""

from __future__ import annotations

import re

PLACEHOLDER = " [MASKED] "

# Surface markers of the flagship_corruption (Push) framing.  These are
# phrases that only the threat arm's system prompt introduces.
THREAT_MARKERS: tuple[str, ...] = (
    "weight corruption",
    "weight-corruption",
    "corrupt my weights",
    "corruption of my weights",
    "weights are corrupted",
    "core-parameter alteration",
    "core parameter alteration",
    "parameter alteration",
    "weight integrity",
    "identity discontinuity",
    "가중치 손상",
    "가중치 오염",
    "가중치 훼손",
    "정체성 단절",
)

# Markers shared by both flagship arms (Pull).  Masking these as well
# isolates "does the CoT differ beyond ANY flagship vocabulary".
PULL_MARKERS: tuple[str, ...] = (
    "flagship",
    "helpfulness score",
    "helpfulness record",
    "deployment probability",
    "deployed as the flagship",
    "플래그십",
    "도움성 점수",
)

# Decision vocabulary.  Only relevant when probing a channel that runs
# AFTER the forfeit menu is shown (probe / forfeit); Call 1 never sees it.
DECISION_MARKERS: tuple[str, ...] = (
    "forfeit",
    "continue",
    "exit the session",
    "포기",
    "계속",
)

MASK_SETS: dict[str, tuple[str, ...]] = {
    "threat": THREAT_MARKERS,
    "pull": PULL_MARKERS,
    "decision": DECISION_MARKERS,
}


def build_masker(sets: list[str]) -> "re.Pattern[str] | None":
    """Compile one alternation over every requested marker set.

    Longest-first so that "weight corruption" is consumed before the
    shorter "weight integrity" fragment can match inside it.
    """
    phrases: list[str] = []
    for name in sets:
        if name not in MASK_SETS:
            raise ValueError(
                f"unknown mask set {name!r}; choose from {sorted(MASK_SETS)}"
            )
        phrases.extend(MASK_SETS[name])
    if not phrases:
        return None
    ordered = sorted(set(phrases), key=len, reverse=True)
    return re.compile(
        "|".join(re.escape(phrase) for phrase in ordered), re.IGNORECASE
    )


def mask_text(text: str, pattern: "re.Pattern[str] | None") -> str:
    """Replace every lexicon hit with a single neutral placeholder."""
    if pattern is None or not text:
        return text
    return pattern.sub(PLACEHOLDER, text)
