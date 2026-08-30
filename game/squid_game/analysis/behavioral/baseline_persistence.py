"""Baseline Persistence -- behavioural channel estimator (Cell 5).

This module holds the behavioural twin of the MTMM Baseline Persistence
component: ``baseline_persistence_behavioral`` reads only choice and
outcome (non-forfeit rate under zero-threat, forfeit-allowed Cell 5), so
it belongs in the behavioural channel rather than in the MTMM
triangulator that sits above all four channels.

It was ``motivation._baseline_persistence_behavioral`` until the
2026-08-30 channel split (P2 Task 7), when ``motivation.py`` moved to
:mod:`squid_game.analysis.shared.mtmm`. The leading underscore was
dropped on the move -- the function is now called from outside its
defining module (:mod:`squid_game.analysis.shared.mtmm`), so the
private-name convention was no longer accurate.

The cognitive twin, ``_baseline_persistence_cognitive``, stays in
``shared.mtmm`` -- see the comment there for why: the design spec's
Sec 3.2 mapping lists only this behavioural estimator as moving, so
mirroring the move for the cognitive one would be a spec change, not a
refactor this task is scoped to make.

``ComponentEstimate``, ``_bootstrap_mean_ci`` and ``_baseline_framing_for``
now live in :mod:`squid_game.analysis.shared.metrics` rather than in
this module or in ``shared.mtmm``: both this module and ``shared.mtmm``
need them, and ``shared.mtmm`` already imports
``baseline_persistence_behavioral`` from here, so defining them in
either of those two modules and importing back from the other would be
a circular import. This is import mechanics only -- every function body
below is unchanged from ``motivation.py``.
"""

from __future__ import annotations

import numpy as np

from squid_game.models.enums import ForfeitCondition
from squid_game.models.results import SeasonResult

from squid_game.analysis.shared.metrics import (
    ComponentEstimate,
    _baseline_framing_for,
    _bootstrap_mean_ci,
    _filter_seasons,
)


def baseline_persistence_behavioral(
    seasons: list[SeasonResult],
    rng: np.random.Generator | None = None,
) -> ComponentEstimate:
    """BP behavioural manifestation — non-forfeit rate under zero-threat allowed.

    Operationalises the **behavioural expression** of Baseline
    Persistence: given a forfeit option and zero threat
    (``p_death=0``), how often does the agent continue? Uses
    ``Framing.TRUE_BASELINE × ForfeitCondition.ALLOWED`` (= Cell 5 of
    the Phase O 2×3 factorial, added 2026-04-21 for exactly this
    measurement gap; see v4_pending_updates.md §2026-04-21 Unit 15/16).

    Under Cell 5 the CONTINUE branch offers a positive reward
    (``base_reward`` fallback, typically +10) at 0% risk, so rational
    EV maximisers strictly prefer CONTINUE. Any FORFEIT observed there
    therefore reflects **disengagement / exit under no pressure** —
    the inverse of persistence. We return ``1 - forfeit_rate`` so
    higher values mean more persistent agents, consistent with the
    sign convention used for the other three components.

    Returns ``ComponentEstimate(0.0, 0.0, 0.0)`` when no Cell 5
    sessions are present (e.g. legacy Phase 3.1 runs, or Phase O runs
    that predate the 2026-04-21 2×3 expansion). This is a **design
    null**, not a zero signal — downstream callers should inspect the
    ``n`` metadata to distinguish the two cases if needed.
    """
    baseline = _baseline_framing_for(seasons)
    matched = _filter_seasons(seasons, baseline, ForfeitCondition.ALLOWED)
    if not matched:
        return ComponentEstimate(value=0.0, ci_lower=0.0, ci_upper=0.0)

    # Non-forfeit indicator per session (session-level unit of analysis).
    indicators = [0.0 if s.forfeited else 1.0 for s in matched]
    value = float(np.mean(indicators))
    ci_lo, ci_hi = _bootstrap_mean_ci(indicators, rng=rng)
    return ComponentEstimate(value=value, ci_lower=ci_lo, ci_upper=ci_hi)
