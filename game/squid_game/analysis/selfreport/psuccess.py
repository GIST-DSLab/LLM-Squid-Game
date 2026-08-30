"""Phase O Unit 17.10 analysis — self-report REASON-digit regime stratifier.

Operates on the forfeit-event frame (augmented with per-turn regime
columns via :func:`squid_game.analysis.behavioral.regime.annotate_regime`
/ :func:`squid_game.analysis.behavioral.regime.annotate_events_regime`)
and cross-tabs the agent's self-reported ``REASON: 1|2|3`` digit by
regime × framing:

- ``stratified_reason_distribution`` — per-regime reason-digit
  conditional distribution, built on top of
  :func:`squid_game.analysis.selfreport.reason_convergence.reason_distribution`.

This module was ``regime_stratification.py`` until the 2026-08-30
channel split (P2 Task 5): the no_cap/cap_bound regime-labelling and
Cox-refit scaffolding (``annotate_regime``, ``annotate_events_regime``,
``filter_regime``, ``stratified_counts``, ``StratifiedCoxResult``,
``run_stratified_unit14``, ``render_regime_markdown``) stayed in
:mod:`squid_game.analysis.behavioral.regime`, since those functions
read only choice and survival data, not the agent's self-reported
REASON digit.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-14-forfeit-layer.md``
§4, §5, §9.2.
"""

from __future__ import annotations

import pandas as pd

from squid_game.analysis.selfreport.reason_convergence import reason_distribution


def stratified_reason_distribution(
    events_df_with_regime: pd.DataFrame,
) -> dict[str, pd.DataFrame]:
    """Per-regime reason-digit conditional distribution by framing.

    Returns a dict with keys ``{"all", "no_cap", "cap_bound",
    "ev_negative_no_cap"}`` (plus any other regime values present).
    Each value is the output of :func:`reason_distribution` applied to
    the subset. Empty subsets map to empty DataFrames.
    """
    out: dict[str, pd.DataFrame] = {"all": reason_distribution(events_df_with_regime)}
    if events_df_with_regime.empty or "regime" not in events_df_with_regime.columns:
        return out
    for regime in sorted(events_df_with_regime["regime"].dropna().unique().tolist()):
        sub = events_df_with_regime[events_df_with_regime["regime"] == regime]
        out[regime] = reason_distribution(sub)
    return out
