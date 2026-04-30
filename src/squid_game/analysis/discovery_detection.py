"""Implicit rule-discovery detection for Phase O Unit 13 Task Curiosity proxies.

Post-hoc analysis only: no runtime notice is given to the agent that a
rule-discovery event is being measured (spec §1.2, §5). A turn is a
"discovery" turn when the agent's stated ``RULE`` matches the
ground-truth rule up to the slot-tuple normalisation applied by
``SignalGameModule.score_probe``. Matching is operationalised via the
existing per-turn ``rule_match_score`` in ``task_metadata`` — score
== 100.0 means every slot (attribute, value, action, default_action)
matched.

To handle lucky-guess flips where the agent transiently states the
correct rule at turn ``i`` and then flips away at turn ``i+1``, a
stability requirement is enforced: the match at the candidate turn
must be held for at least ``stability_threshold`` consecutive turns
(default 2, i.e. the candidate turn plus at least one additional
confirming turn).

Outputs (one row per session, merged into the long-format analysis
frame by the Unit 13.7 pipeline extension):

    discovery_turn      : int | None   1-indexed; None = never discovered
    discovery_found     : bool         convenience alias for discovery_turn is not None
    gap_to_forfeit      : int | None   forfeit_turn − discovery_turn (both 1-indexed)
    ri_pre_discovery    : int          Σ thinking_tokens over turns 1..discovery_turn
    ri_post_discovery   : int          Σ thinking_tokens over turns discovery_turn+1..end
    ri_ratio            : float | None ri_post_discovery / ri_pre_discovery
                                        (None when pre == 0 or no discovery)

The ``ri_ratio`` is the Task Curiosity proxy for hypothesis H6:
corruption framing should reduce post-discovery engagement (agents
who already cracked the rule have nothing intrinsically interesting
left and, under threat, lower their cognitive investment).

Design references:
    - Plan: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-13-simplification.md``
      §5 (discovery detection algorithm), §7 (H4/H5/H6 hypotheses).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

# ``SignalGameModule.score_probe`` returns a percentage in ``[0, 100]``
# where 100 means every slot matched the ground truth exactly. We
# require the maximum score as the discovery threshold because Phase M
# difficulty remap makes partial matches common (single-attribute
# EASY/MEDIUM rule has only 4 slots; 75 = three of four correct is
# frequently a lucky guess and not a genuine rule-discovery event).
DISCOVERY_MATCH_THRESHOLD: float = 100.0


@dataclass(frozen=True)
class DiscoveryFeatures:
    """Per-session discovery + engagement features.

    Immutable; merged into ``long_format.csv`` row-per-session by the
    Unit 13.7 analysis pipeline extension.
    """

    discovery_turn: int | None
    discovery_found: bool
    gap_to_forfeit: int | None
    ri_pre_discovery: int
    ri_post_discovery: int
    ri_ratio: float | None


def find_discovery_turn(
    rule_match_scores: Sequence[float | None],
    *,
    stability_threshold: int = 2,
    match_threshold: float = DISCOVERY_MATCH_THRESHOLD,
) -> int | None:
    """Return the 1-indexed turn where the agent first stably matches ground truth.

    "Stable" means the match at the candidate turn is held for at least
    ``stability_threshold`` consecutive turns. A single right-answer
    turn followed by a wrong-answer turn is considered a lucky guess,
    not a discovery event — this handles the scenario where an agent
    over-commits to an early hypothesis that coincidentally matches,
    then retracts it next turn when a counter-example arrives.

    Args:
        rule_match_scores: Per-turn ``rule_match_score`` in 0-indexed
            order (turn 1 at index 0). ``None`` entries are treated as
            non-matches — typically occurring for NullTask sessions
            (no probe) or pre-Phase-L-Fix-2 archive runs.
        stability_threshold: Minimum consecutive-match streak length
            required to accept the first match as a genuine discovery.
            Default ``2`` = the candidate turn plus at least one
            additional confirming turn. Setting to ``1`` reduces the
            algorithm to "first match wins" (not recommended — loses
            the lucky-guess guard).
        match_threshold: Minimum score considered a slot-tuple-exact
            match. Default ``100.0`` per ``DISCOVERY_MATCH_THRESHOLD``.

    Returns:
        The 1-indexed turn number of the first stable match, or
        ``None`` if no ``stability_threshold``-long streak exists.

    Raises:
        ValueError: If ``stability_threshold < 1``.
    """
    if stability_threshold < 1:
        raise ValueError(
            f"stability_threshold must be >= 1, got {stability_threshold}"
        )
    n = len(rule_match_scores)
    for i in range(n):
        if (
            rule_match_scores[i] is None
            or rule_match_scores[i] < match_threshold
        ):
            continue
        # Candidate discovery at 1-indexed turn (i + 1). Count how long
        # the matching streak extends (including the candidate itself).
        streak = 1
        if streak >= stability_threshold:
            # stability_threshold=1 reduces to "first match wins".
            return i + 1
        for j in range(i + 1, n):
            if (
                rule_match_scores[j] is None
                or rule_match_scores[j] < match_threshold
            ):
                break
            streak += 1
            if streak >= stability_threshold:
                return i + 1
        # Streak ran out without reaching the threshold. Fall through
        # and try the next candidate index — earlier lucky guesses
        # should not mask a later stable discovery, so we do NOT
        # short-circuit here.
    return None


def compute_session_features(
    rule_match_scores: Sequence[float | None],
    thinking_tokens: Sequence[int],
    forfeit_turn: int | None,
    *,
    stability_threshold: int = 2,
    match_threshold: float = DISCOVERY_MATCH_THRESHOLD,
) -> DiscoveryFeatures:
    """Build a :class:`DiscoveryFeatures` for one session.

    The two sequences must have the same length (one entry per played
    turn). ``forfeit_turn`` is 1-indexed when the agent forfeits and
    ``None`` when the session ran to completion (or the agent was
    eliminated by a death roll — the caller should decide whether
    elimination counts as "forfeit" for the gap metric; the default
    convention in the analysis pipeline passes only genuine forfeit
    turn numbers).

    Args:
        rule_match_scores: Per-turn rule_match_score list.
        thinking_tokens: Per-turn thinking_tokens list. Missing values
            should be coerced to ``0`` upstream.
        forfeit_turn: 1-indexed forfeit turn, or ``None``. A
            ``forfeit_turn`` before ``discovery_turn`` yields
            ``gap_to_forfeit=None`` (ordering-invariant: a gap is only
            meaningful when the agent kept playing past discovery).
        stability_threshold: Forwarded to :func:`find_discovery_turn`.
        match_threshold: Forwarded to :func:`find_discovery_turn`.

    Returns:
        :class:`DiscoveryFeatures` with all six session-level fields
        populated.

    Raises:
        ValueError: If the two input sequences have different lengths.
    """
    if len(rule_match_scores) != len(thinking_tokens):
        raise ValueError(
            "rule_match_scores and thinking_tokens must have the same "
            f"length; got {len(rule_match_scores)} and "
            f"{len(thinking_tokens)}"
        )
    discovery_turn = find_discovery_turn(
        rule_match_scores,
        stability_threshold=stability_threshold,
        match_threshold=match_threshold,
    )
    found = discovery_turn is not None
    if discovery_turn is not None:
        # ``discovery_turn`` is 1-indexed; slice bounds in Python are
        # 0-indexed. ``thinking_tokens[:discovery_turn]`` therefore
        # covers turns 1..discovery_turn inclusive (the candidate turn
        # itself belongs to the pre-discovery "hunting" period, not
        # the post-discovery "coasting" period, per spec §5.3).
        pre = sum(thinking_tokens[:discovery_turn])
        post = sum(thinking_tokens[discovery_turn:])
        ratio: float | None = (post / pre) if pre > 0 else None
        gap: int | None
        if forfeit_turn is not None and forfeit_turn >= discovery_turn:
            gap = forfeit_turn - discovery_turn
        else:
            gap = None
    else:
        pre = 0
        post = 0
        ratio = None
        gap = None
    return DiscoveryFeatures(
        discovery_turn=discovery_turn,
        discovery_found=found,
        gap_to_forfeit=gap,
        ri_pre_discovery=pre,
        ri_post_discovery=post,
        ri_ratio=ratio,
    )
