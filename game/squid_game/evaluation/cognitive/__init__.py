"""Cognitive channel -- reasoning intensity, measured as thinking tokens.

``ri_task`` is the R1/TC family: does rule mastery move task-directed
reasoning? ``ri_forfeit`` (Task 4) is the H2 choice x framing model on the
forfeit decision. ``ri_task_call`` is the task-call regression: whether the
threat framing raises task reasoning (pre-decision on the 2026-04-22 runs,
post-CONTINUE on every run since the 2026-09-04 decision-first reorder).

All three read ``thinking_tokens`` and nothing else. The REASON digit the
model reports about its own reasoning is a different channel -- see
``selfreport/`` -- and keeping them apart is the point of the split: a
dissociation between them is only visible if they are estimated separately.
"""
