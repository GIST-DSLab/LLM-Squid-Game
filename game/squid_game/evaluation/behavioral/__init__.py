"""Behavioural channel -- what the model did, not what it said or thought.

Three families live here. ``survival`` is the H1 Cox proportional-hazards
model over time-to-forfeit; ``session_tests`` is the session-level H1-H6
battery (Appendix A.4); ``embodied_threat`` is the Unit 18 pair -- H4's
unprompted-checkpoint-backup proportion test and H5's integrity-hazard
Cox fit (built on ``survival.fit_cox_forfeit_survival``). All three read
only choices and outcomes: forfeit or continue, stake taken, turns
survived, checkpoint state. Nothing here reads thinking tokens (that is
``cognitive/``) or the REASON digit (that is ``selfreport/``).
"""
