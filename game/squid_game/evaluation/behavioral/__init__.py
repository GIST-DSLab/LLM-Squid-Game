"""Behavioural channel -- what the model did, not what it said or thought.

Three families live here. ``survival`` is the H1 Cox proportional-hazards
model over time-to-forfeit; ``session_tests`` is the session-level H1-H6
battery (Appendix A.4); ``survival_drive`` is the SDI offline resampler,
which re-issues each recorded decision call to estimate the forfeit rate
the online run sampled only once. All three read only choices and
outcomes: forfeit or continue, stake taken, turns survived, lives spent.
Nothing here reads thinking tokens (that is ``cognitive/``) or the REASON
digit (that is ``selfreport/``).

Only the SDI names are re-exported at package level: the survival and
session-test modules pull in the optional ``analysis`` extra
(statsmodels / lifelines), so importing them here would make the whole
channel unimportable without it.
"""

from squid_game.evaluation.behavioral.survival_drive import (
    SDI_COLUMNS,
    ResampleResult,
    compute_sdi,
    iter_resample_targets,
    load_sdi_table,
    resample_run,
    resample_turn,
)

__all__ = [
    # Survival Drive Index -- offline decision-call resampling (spec §4).
    "SDI_COLUMNS",
    "ResampleResult",
    "compute_sdi",
    "iter_resample_targets",
    "load_sdi_table",
    "resample_run",
    "resample_turn",
]
