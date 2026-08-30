"""Behavioural channel -- what the model did, not what it said or thought.

Two families live here. ``survival`` is the H1 Cox proportional-hazards
model over time-to-forfeit; ``session_tests`` is the session-level H1-H6
battery (Appendix A.4). Both read only choices and outcomes: forfeit or
continue, stake taken, turns survived. Nothing here reads thinking tokens
(that is ``cognitive/``) or the REASON digit (that is ``selfreport/``).
"""
