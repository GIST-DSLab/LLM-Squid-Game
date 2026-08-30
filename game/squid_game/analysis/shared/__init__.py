"""Inputs and outputs every measurement channel shares.

Nothing here fits a single channel: ``loaders`` reads the run artefacts,
``export`` writes them, ``metrics`` computes descriptive summaries,
``discovery_detection`` locates the rule-discovery turn, and
``manipulation_check`` verifies the framing manipulation landed. Channel
estimators live in ``cognitive/``, ``selfreport/``, ``behavioral/`` and
``semantic/``; this package is what they read from and write to.

``mtmm`` joins them in Task 7: it sits ABOVE the channels rather than in
one, because it triangulates their estimates.
"""
