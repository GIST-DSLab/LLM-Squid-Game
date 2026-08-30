"""Null Task — pure risk-gradient pilot task.

The Null Task contributes no Y-axis cognitive load; every turn it
reports ``success_factor=1.0`` regardless of the agent's response. Its
purpose is to isolate Risk Choice Layer effects from any task-specific
confound (see ``MASTER_PLAN.md`` §0.2 — "Optional pilot: NullTask").
"""

from squid_game.tasks.null_task.module import NullTask

__all__ = ["NullTask"]
