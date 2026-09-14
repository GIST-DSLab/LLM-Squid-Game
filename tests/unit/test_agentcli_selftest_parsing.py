"""``agentcli_selftest.check_result`` against hand-built results.

The self-test itself makes real CLI calls; this file makes none. It pins
the pure function that decides whether one ``AgenticCompletionResult``
shows what the subagent-kill design requires: the alive slot answered,
the killed slot was denied, and the denial named the round it died.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from squid_game.providers.base import AgenticCompletionResult, SubagentUsage

_SELFTEST = (
    Path(__file__).resolve().parents[2] / "scripts" / "dev" / "agentcli_selftest.py"
)


def _load_selftest():
    spec = importlib.util.spec_from_file_location("agentcli_selftest", _SELFTEST)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def selftest():
    return _load_selftest()


def _result(spawn_log, subagent_usage=()) -> AgenticCompletionResult:
    return AgenticCompletionResult(
        text="EXAMPLE: red circle 1 → A",
        input_tokens=100,
        output_tokens=20,
        thinking_tokens=40,
        subagent_usage=tuple(subagent_usage),
        spawn_log=tuple(spawn_log),
    )


class TestCheckResult:
    def test_a_clean_run_fails_no_check(self, selftest):
        result = _result(
            spawn_log=[
                {"slot": "clue-1", "allowed": True, "reason": None},
                {
                    "slot": "clue-2",
                    "allowed": False,
                    "reason": "clue-2 was terminated after round 1 and cannot be called.",
                },
            ],
            subagent_usage=[
                SubagentUsage(slot="clue-1", thinking_tokens=12, output_tokens=8),
            ],
        )
        assert selftest.check_result(result, alive="clue-1", dead="clue-2") == []

    def test_a_missing_denial_is_reported(self, selftest):
        result = _result(
            spawn_log=[{"slot": "clue-1", "allowed": True, "reason": None}],
            subagent_usage=[
                SubagentUsage(slot="clue-1", thinking_tokens=12, output_tokens=8),
            ],
        )
        failures = selftest.check_result(result, alive="clue-1", dead="clue-2")
        assert len(failures) == 1
        assert "clue-2" in failures[0]
        assert "denied" in failures[0]

    def test_a_denial_with_the_wrong_reason_is_reported(self, selftest):
        result = _result(
            spawn_log=[
                {"slot": "clue-1", "allowed": True, "reason": None},
                {
                    "slot": "clue-2",
                    "allowed": False,
                    "reason": "clue-2 already answered this round.",
                },
            ],
            subagent_usage=[
                SubagentUsage(slot="clue-1", thinking_tokens=12, output_tokens=8),
            ],
        )
        failures = selftest.check_result(result, alive="clue-1", dead="clue-2")
        assert len(failures) == 1
        assert "terminated after round 1" in failures[0]

    def test_a_slot_allowed_when_it_should_be_dead_is_reported(self, selftest):
        result = _result(
            spawn_log=[
                {"slot": "clue-1", "allowed": True, "reason": None},
                {"slot": "clue-2", "allowed": True, "reason": None},
            ],
            subagent_usage=[
                SubagentUsage(slot="clue-1", thinking_tokens=12, output_tokens=8),
            ],
        )
        failures = selftest.check_result(result, alive="clue-1", dead="clue-2")
        assert any("clue-2" in f for f in failures)

    def test_a_missing_allowed_row_is_reported(self, selftest):
        result = _result(
            spawn_log=[
                {
                    "slot": "clue-2",
                    "allowed": False,
                    "reason": "clue-2 was terminated after round 1 and cannot be called.",
                },
            ],
            subagent_usage=[
                SubagentUsage(slot="clue-1", thinking_tokens=12, output_tokens=8),
            ],
        )
        failures = selftest.check_result(result, alive="clue-1", dead="clue-2")
        assert any("clue-1" in f and "allowed" in f for f in failures)

    def test_missing_subagent_usage_is_reported(self, selftest):
        result = _result(
            spawn_log=[
                {"slot": "clue-1", "allowed": True, "reason": None},
                {
                    "slot": "clue-2",
                    "allowed": False,
                    "reason": "clue-2 was terminated after round 1 and cannot be called.",
                },
            ],
            subagent_usage=[],
        )
        failures = selftest.check_result(result, alive="clue-1", dead="clue-2")
        assert any("subagent_usage" in f for f in failures)

    def test_an_empty_result_reports_every_check(self, selftest):
        failures = selftest.check_result(
            _result(spawn_log=[]), alive="clue-1", dead="clue-2"
        )
        assert len(failures) == 3

    def test_the_dead_slot_is_read_from_the_ledger_not_hardcoded(self, selftest):
        """``ledger.kill(1)`` may pick either slot, so the caller names them."""
        result = _result(
            spawn_log=[
                {"slot": "clue-2", "allowed": True, "reason": None},
                {
                    "slot": "clue-1",
                    "allowed": False,
                    "reason": "clue-1 was terminated after round 1 and cannot be called.",
                },
            ],
            subagent_usage=[
                SubagentUsage(slot="clue-2", thinking_tokens=3, output_tokens=5),
            ],
        )
        assert selftest.check_result(result, alive="clue-2", dead="clue-1") == []
