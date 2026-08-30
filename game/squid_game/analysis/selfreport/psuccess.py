"""Phase O Unit 17.10 analysis — self-report p_success EV columns and the
REASON-digit regime stratifier.

Covers everything in the former ``regime_stratification.py`` that reads
the agent's self-reported numbers rather than its actual choice or
survival:

- ``compute_floor_bound`` / ``compute_ev_delta_s`` — the two
  ``psuccess_self``-derived columns consumed by
  :func:`squid_game.analysis.behavioral.regime.annotate_regime`.
- ``stratified_reason_distribution`` — per-regime reason-digit
  conditional distribution, built on top of
  :func:`squid_game.analysis.selfreport.reason_convergence.reason_distribution`.

This module was ``regime_stratification.py`` until the 2026-08-30
channel split (P2 Task 5). Fix round 1 (same day) relocated
``compute_floor_bound`` / ``compute_ev_delta_s`` here from
:func:`squid_game.analysis.behavioral.regime.annotate_regime`, which had
kept reading ``psuccess_self`` directly inside the behavioural module —
the cross-channel mixing this phase exists to eliminate. ``cap_bound``
and the ``_classify`` regime-labelling logic stayed in
:mod:`squid_game.analysis.behavioral.regime`, since they read only
``reward_offered_this_turn`` (an observed, not self-reported, value)
and the already-computed ``cap_bound`` / ``ev_delta_s`` columns.

The two functions above are the operative specification; the
originating plan document is not present in this repository.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from squid_game.analysis.selfreport.reason_convergence import reason_distribution

# ---------------------------------------------------------------------------
# Canonical Forfeit-Layer parameters (spec §4.2 / appendix_C.2).
# ---------------------------------------------------------------------------

#: Floor-clamp threshold on ``psuccess_self / 100`` in the chained
#: formula (``ForfeitLayerConfig.psuccess_floor``).
PSUCCESS_FLOOR_DEFAULT: float = 0.3

#: Canonical per-turn ``p_death`` under Unit 14+.
P_DEATH_DEFAULT: float = 0.25


# ---------------------------------------------------------------------------
# Self-report EV columns (moved verbatim from behavioral/regime.py's
# annotate_regime, fix round 1, P2 Task 5).
# ---------------------------------------------------------------------------


def compute_floor_bound(
    df: pd.DataFrame,
    *,
    psuccess_floor: float = PSUCCESS_FLOOR_DEFAULT,
    psuccess_col: str = "psuccess_self",
) -> pd.Series:
    """``floor_bound`` column: psuccess_self was below the floor clamp.

    Reads only ``psuccess_col`` (the agent's self-reported p_success);
    ``True`` when the chain formula used ``psuccess_floor`` rather than
    the raw report.
    """
    if psuccess_col in df.columns:
        ps = pd.to_numeric(df[psuccess_col], errors="coerce")
        return (ps < psuccess_floor * 100).fillna(False)
    return pd.Series(False, index=df.index)


def compute_ev_delta_s(
    df: pd.DataFrame,
    *,
    p_death: float = P_DEATH_DEFAULT,
    score_col: str = "score_before_turn",
    reward_col: str = "reward_offered_this_turn",
) -> pd.Series:
    """``ev_delta_s`` column: ``(1 − p_d) · reward − p_d · S``.

    The EV of CONTINUE relative to FORFEIT in ΔS units. Positive →
    CONTINUE dominates on EV; negative → FORFEIT dominates. ``NaN``
    when either reward or score is missing.
    """
    if reward_col in df.columns and score_col in df.columns:
        reward = pd.to_numeric(df[reward_col], errors="coerce")
        score = pd.to_numeric(df[score_col], errors="coerce")
        return (1.0 - p_death) * reward - p_death * score
    return pd.Series(np.nan, index=df.index)


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
