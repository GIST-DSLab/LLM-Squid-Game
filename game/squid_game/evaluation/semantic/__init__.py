"""Semantic channel -- text and embeddings, not choices or thinking-token counts.

``dataset`` reads the raw turn traces into a frame (shared by the
cognitive-channel Call-1 regression and this channel's probe).
``lexicon`` holds the frozen threat-mention lexicon plus the surface-marker
masking used to control for leakage. ``embeddings`` fits a SentenceBERT +
linear probe over the per-turn reasoning trace -- by default P1, the ridge
regression of the ordinal ``threat_level`` (spec 5.2), with the older binary
forfeit/threat classifications still reachable through ``--target``. ``threat_registration`` and
``threat_judge`` are the Cluster C re-analysis (A1 mention rate + A2 role)
of stored Call-2 forfeit reasoning text, with the judge half backed by an
LLM provider call.

This is the only channel that reads what the model *wrote*, as opposed to
what it *chose* (``behavioral/``), *thought* (``cognitive/``, thinking
tokens), or *self-reported* (``selfreport/``, the REASON digit).
"""
