"""Inputs and outputs every measurement channel shares.

Nothing here fits a single channel: ``loaders`` reads the run artefacts,
``export`` writes them, ``metrics`` computes descriptive summaries,
``discovery_detection`` locates the rule-discovery turn, and
``manipulation_check`` verifies the framing manipulation landed. Channel
estimators live in ``cognitive/``, ``selfreport/``, ``behavioral/`` and
``semantic/``; this package is what they read from and write to.

``mtmm`` joins them in Task 7: it sits ABOVE the channels rather than in
one, because it triangulates their estimates.

**Layering rule and its one exception:** modules in this package do not
import from a channel package (``cognitive/``, ``selfreport/``,
``behavioral/``, ``semantic/``) -- ``loaders``, ``export``, ``metrics``,
``discovery_detection`` and ``manipulation_check`` all import nothing
from any of the four. ``mtmm`` is the sole exception: it imports
``baseline_persistence_behavioral`` from
``squid_game.evaluation.behavioral.baseline_persistence``. That is by
design, not a crack in the layering -- design spec Sec 3.2 puts MTMM
above the channels precisely so its triangulation structure (it calls
each channel's estimator rather than re-implementing them) is visible
in the code structure, not just in a docstring. Do not read ``mtmm``'s
import as precedent for adding channel-consuming code elsewhere in
``shared/``, and do not treat the rest of this package as a safe import
target for a channel module -- the five modules above stay
channel-independent so nothing they're imported into can form a cycle.
"""
