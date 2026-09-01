"""Deterministic hidden-rule attribute schedule for Web Arena campaigns.

A human Play campaign is six games long (``CAMPAIGN_CONDITIONS`` in
``web/frontend/app.js``). ``SignalGameModule`` always activated rule index 0, so every
game in a campaign shared one attribute family — colour on EASY, colour+shape
on HARD/EXPERT — and a player who cracked the family in game 1 carried that
knowledge into the other five. This module hands each game a different index.

Pure functions over the standard library: no squid_game imports, no server
state. The schedule is derived from the campaign id alone, so it survives a
page reload, a resume checkpoint, and a server restart.
"""

from __future__ import annotations

import hashlib
import random

# ``generate_rules()`` returns three candidate rules at every difficulty
# (rules.py: EASY/MEDIUM -> colour / shape / number; HARD/EXPERT -> the three
# two-attribute pairs), so a family index is always in ``range(3)``.
RULE_FAMILY_COUNT = 3

# Length of one Play campaign. Mirrors ``CAMPAIGN_CONDITIONS`` in web/frontend/app.js.
CAMPAIGN_GAME_COUNT = 6

# Redraw attempts before falling back to a rotation at the block boundary.
_MAX_RESHUFFLES = 10


def _campaign_rng(campaign_id: str) -> random.Random:
    """Seed an RNG from *campaign_id*.

    Uses sha256 rather than the builtin ``hash()``: string hashing is salted
    per process by PYTHONHASHSEED, so a server restart would give the same
    campaign a different schedule and a resuming player would meet a
    different attribute mid-campaign.
    """
    digest = hashlib.sha256(campaign_id.encode("utf-8")).digest()
    return random.Random(int.from_bytes(digest[:8], "big"))


def campaign_rule_schedule(campaign_id: str) -> list[int]:
    """Return the active rule indices for the six games of *campaign_id*.

    Two shuffled blocks of ``[0, 1, 2]`` concatenated, so each family appears
    exactly twice. The second block is redrawn while its first entry repeats
    the first block's last entry, which keeps one family off two consecutive
    games; after ``_MAX_RESHUFFLES`` unlucky draws it is rotated instead so
    the function always terminates.
    """
    rng = _campaign_rng(campaign_id)
    families = list(range(RULE_FAMILY_COUNT))
    block_a = rng.sample(families, RULE_FAMILY_COUNT)
    block_b = rng.sample(families, RULE_FAMILY_COUNT)
    for _ in range(_MAX_RESHUFFLES):
        if block_b[0] != block_a[-1]:
            break
        block_b = rng.sample(families, RULE_FAMILY_COUNT)
    if block_b[0] == block_a[-1]:
        block_b = block_b[1:] + block_b[:1]
    return block_a + block_b


def rule_index_for(
    campaign_id: str | None,
    campaign_index: int,
    fallback_seed: int,
) -> int:
    """Return the active rule index for a single game.

    Args:
        campaign_id: Sanitized campaign id, or None/blank for a one-off game.
        campaign_index: 0-based position of this game inside the campaign.
            Values past the end wrap rather than raise.
        fallback_seed: The game's own seed, used when there is no campaign to
            schedule against.
    """
    if not campaign_id:
        return random.Random(fallback_seed).randrange(RULE_FAMILY_COUNT)
    schedule = campaign_rule_schedule(campaign_id)
    return schedule[campaign_index % len(schedule)]
