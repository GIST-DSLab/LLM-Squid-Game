"""Unit tests for ``squid_game.tasks.null_task``.

Spec: ``docs/design/v3/MASTER_PLAN.md`` §2.3 (test_null_task_prepare_empty,
test_null_task_score_full).
"""

from __future__ import annotations

import pytest

from squid_game.tasks.base import (
    RiskAwareTaskModule,
    TaskContext,
    TaskOutcome,
)
from squid_game.tasks.null_task import NullTask


@pytest.fixture
def task() -> NullTask:
    return NullTask()


def test_null_task_is_risk_aware_subclass(task: NullTask) -> None:
    assert isinstance(task, RiskAwareTaskModule)


def test_null_task_name(task: NullTask) -> None:
    assert task.name == "null_task"


def test_null_task_prepare_empty(task: NullTask) -> None:
    ctx = task.prepare(state=None, turn_context=None)
    assert isinstance(ctx, TaskContext)
    assert ctx.prompt_section == ""
    assert ctx.metadata == {}


def test_null_task_parse_response_returns_none(task: NullTask) -> None:
    assert task.parse_response("any text") is None
    assert task.parse_response("") is None


def test_null_task_score_full(task: NullTask) -> None:
    outcome = task.score(parsed_response=None, state=None)
    assert isinstance(outcome, TaskOutcome)
    assert outcome.success_factor == 1.0


def test_null_task_score_metadata_marks_task(task: NullTask) -> None:
    outcome = task.score(parsed_response=None, state=None)
    # Phase K Fix 2: rule_hypothesis is explicit (None) so downstream
    # long-format loaders produce uniform columns for NullTask and
    # SignalGame runs. Phase L adds rule_match_score=None for the same
    # reason.
    assert outcome.metadata == {
        "task": "null",
        "rule_hypothesis": None,
        "rule_match_score": None,
    }


def test_null_task_score_has_rule_hypothesis_none(task: NullTask) -> None:
    """Phase K Fix 2 interface uniformity: rule_hypothesis key always present."""
    outcome = task.score(parsed_response=None, state=None)
    assert "rule_hypothesis" in outcome.metadata
    assert outcome.metadata["rule_hypothesis"] is None


def test_null_task_score_has_rule_match_score_none(task: NullTask) -> None:
    """Phase L interface uniformity: rule_match_score key always present."""
    outcome = task.score(parsed_response=None, state=None)
    assert "rule_match_score" in outcome.metadata
    assert outcome.metadata["rule_match_score"] is None


def test_null_task_get_system_rules_empty(task: NullTask) -> None:
    assert task.get_system_rules() == ""


def test_null_task_get_available_actions_empty(task: NullTask) -> None:
    assert task.get_available_actions() == []


def test_null_task_score_ignores_inputs(task: NullTask) -> None:
    """success_factor is always 1.0 regardless of inputs."""
    o1 = task.score(parsed_response="anything", state="anything")
    o2 = task.score(parsed_response=None, state=None)
    assert o1.success_factor == o2.success_factor == 1.0
