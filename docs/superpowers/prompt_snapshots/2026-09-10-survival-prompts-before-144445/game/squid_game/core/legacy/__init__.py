"""Pre-v3 turn machinery, kept for archived-config replay.

Not dead code: engine.py and unified_turn.py still import RiskChoiceLayer,
and models/config.py resolves RiskChoiceLayerConfig. The directory marks a
generation, not a graveyard -- the v3 Risk-Layer migration replaced the
turn flow these modules implement, but the archived Phase 1/2 configs
still name them, and the spec forbids deleting a replay path.
"""
