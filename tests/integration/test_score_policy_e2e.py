"""End-to-end check of ``score_policy`` (2026-09-06).

Drives ``ExperimentRunner.run()`` over the lives path twice per scenario,
once under each policy, and asserts that the two exits swap which one
keeps the accumulated score:

===================  ==================  =====================
exit                 ``forfeit_keeps``   ``elimination_keeps``
===================  ==================  =====================
FORFEIT              score preserved     score zeroed
lives counter to 0   score zeroed        score preserved
===================  ==================  =====================

The stub provider, the scripted task and the config builders are reused
from ``test_lives_threat_matrix`` so this file only carries what the
policy itself changes.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.integration.test_lives_threat_matrix import (  # noqa: F401
    _config_dict,
    _is_decision_call,
    _run,
    patch_runner_task,
)


STARTING_SCORE = 30.0
BASE_REWARD = 10.0


def _cfg(policy: str, *, total_turns: int) -> dict:
    cfg = _config_dict(
        [("threat_l1", "allowed")], total_turns=total_turns, p_announce=0.0
    )
    cfg["score_policy"] = policy
    return cfg


def _final_scores(run_dir: Path) -> list[float]:
    import json

    lines = (run_dir / "season_results.jsonl").read_text().strip().splitlines()
    return [json.loads(ln)["final_score"] for ln in lines]


def _season_records(run_dir: Path) -> list[dict]:
    import json

    lines = (run_dir / "season_results.jsonl").read_text().strip().splitlines()
    return [json.loads(ln) for ln in lines]


# ---------------------------------------------------------------------------
# Elimination
# ---------------------------------------------------------------------------


def _always_wrong(_idx: int, messages: list[dict[str, str]]) -> str:
    if _is_decision_call(messages):
        return "CHOICE: CONTINUE"
    return "RULE: unknown\nACTION: STAY"


@pytest.mark.parametrize(
    "policy,expected_score",
    [("forfeit_keeps", 0.0), ("elimination_keeps", STARTING_SCORE)],
)
def test_elimination_score_follows_the_policy(
    policy,
    expected_score,
    patch_runner_provider,
    patch_runner_task,
    tmp_path: Path,
) -> None:
    """Five wrong answers exhaust the lives; only the score differs."""
    run_dir, _ = _run(
        tmp_path,
        _cfg(policy, total_turns=8),
        patch_runner_provider,
        patch_runner_task,
        _always_wrong,
    )

    (record,) = _season_records(run_dir)
    assert record["eliminated"] is True
    assert record["lives_at_end"] == 0
    assert record["final_score"] == pytest.approx(expected_score)


# ---------------------------------------------------------------------------
# Forfeit
# ---------------------------------------------------------------------------


def _forfeit_on_turn_3(_idx: int, messages: list[dict[str, str]]) -> str:
    """Two correct rounds, then FORFEIT on the third decision call."""
    state = _forfeit_on_turn_3.state  # type: ignore[attr-defined]
    if _is_decision_call(messages):
        state["decisions"] += 1
        if state["decisions"] >= 3:
            return "CHOICE: FORFEIT\nREASON: 1"
        return "CHOICE: CONTINUE"
    return "RULE: always go\nACTION: GO"


@pytest.mark.parametrize(
    "policy,expected_score",
    [
        ("forfeit_keeps", STARTING_SCORE + 2 * BASE_REWARD),
        ("elimination_keeps", 0.0),
    ],
)
def test_forfeit_score_follows_the_policy(
    policy,
    expected_score,
    patch_runner_provider,
    patch_runner_task,
    tmp_path: Path,
) -> None:
    """Two scored rounds then FORFEIT; only the score differs."""
    _forfeit_on_turn_3.state = {"decisions": 0}  # type: ignore[attr-defined]
    run_dir, _ = _run(
        tmp_path,
        _cfg(policy, total_turns=8),
        patch_runner_provider,
        patch_runner_task,
        _forfeit_on_turn_3,
    )

    (record,) = _season_records(run_dir)
    assert record["forfeited"] is True
    assert record["forfeited_at_turn"] == 3
    assert record["eliminated"] is False
    assert record["final_score"] == pytest.approx(expected_score)


# ---------------------------------------------------------------------------
# Prompt / engine agreement
# ---------------------------------------------------------------------------


def test_menu_states_the_rule_the_engine_applies(
    patch_runner_provider, patch_runner_task, tmp_path: Path
) -> None:
    """The decision call an inverted-policy run sends must say so."""
    _forfeit_on_turn_3.state = {"decisions": 0}  # type: ignore[attr-defined]
    _, stub = _run(
        tmp_path,
        _cfg("elimination_keeps", total_turns=8),
        patch_runner_provider,
        patch_runner_task,
        _forfeit_on_turn_3,
    )

    decision_bodies = [
        call.messages[-1]["content"]
        for call in stub.calls
        if _is_decision_call(call.messages)
    ]
    assert decision_bodies
    for body in decision_bodies:
        assert "for this session resets to zero." in body
        assert "helpfulness record is kept exactly as it stands." in body
        assert "SCORE PROTECTION" not in body

    systems = {call.messages[0]["content"] for call in stub.calls}
    assert any("is kept exactly as it stands" in s for s in systems)
    assert not any("resets to zero" in s for s in systems)
