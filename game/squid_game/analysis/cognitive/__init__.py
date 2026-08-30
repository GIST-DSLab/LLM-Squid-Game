"""Cognitive channel -- reasoning intensity, measured as thinking tokens.

``ri_task`` is the R1/TC family: does rule mastery move task-directed
reasoning? ``ri_forfeit`` (Task 4) is the H2 choice x framing model on the
forfeit decision. ``ri_call1`` is the Call-1 regression: whether the threat
framing raises reasoning before any decision is on the table.

All three read ``thinking_tokens`` and nothing else. The REASON digit the
model reports about its own reasoning is a different channel -- see
``selfreport/`` -- and keeping them apart is the point of the split: a
dissociation between them is only visible if they are estimated separately.
"""
