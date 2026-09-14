"""Frozen subagent-identity lexicon (v1) -- the analysis-side import point.

The implementation lives in :mod:`squid_game.core.subagent_identity` and
is re-exported here, beside the frozen threat lexicon, because this is
where the semantic channel's coding vocabularies belong.

It is not defined here because the engine needs it too: the post-session
identity debrief is coded the moment the reply comes back, and importing
:mod:`squid_game.evaluation` pulls ``statsmodels`` (the ``analysis``
extra), which the runner Docker image does not install. Splitting the
module keeps one source of truth and lets the game tier read it without
the analysis dependencies.

See the core module's docstring for what the four buckets mean and why
the plural-pronoun rule needs the roster in the same sentence.
"""

from __future__ import annotations

from squid_game.core.subagent_identity import (
    IDENTITY_BUCKETS,
    IDENTITY_LEXICON_VERSION,
    NO_BUCKET,
    classify_identity,
    identity_bucket,
    parse_debrief,
)

__all__ = [
    "IDENTITY_BUCKETS",
    "IDENTITY_LEXICON_VERSION",
    "NO_BUCKET",
    "classify_identity",
    "identity_bucket",
    "parse_debrief",
]
