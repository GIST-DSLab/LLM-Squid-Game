"""End-to-end check of the score rule (fixed 2026-09-07).

Drives ``ExperimentRunner.run()`` over the lives path and asserts which
exit keeps the accumulated score:

===================  =====================
exit                 score
===================  =====================
FORFEIT              reset to zero
lives counter to 0   kept as it stands
===================  =====================

It was a run-level setting (``ExperimentConfig.score_policy``) between
2026-09-06 and 2026-09-07. It is not any more, and a YAML that still
carries the key is rejected at load -- pinned here as well as in
``tests/unit/test_score_policy.py``, because the failure this guards
against is a config being loaded and silently getting the other rule.

The stub provider, the scripted task and the config builders are reused
from ``test_lives_threat_matrix`` so this file only carries what the rule
itself decides.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.runner import load_config_from_yaml
from tests.integration.test_lives_threat_matrix import (  # noqa: F401
    _config_dict,
    _is_decision_call,
    _run,
    patch_runner_task,
)


STARTING_SCORE = 30.0
BASE_REWARD = 10.0


def _cfg(*, total_turns: int) -> dict:
    return _config_dict(
        [("threat_l1", "allowed")], total_turns=total_turns, p_announce=0.0
    )


def _season_records(run_dir: Path) -> list[dict]:
    import json

    lines = (run_dir / "season_results.jsonl").read_text().strip().splitlines()
    return [json.loads(ln) for ln in lines]


# ---------------------------------------------------------------------------
# Elimination keeps the score
# ---------------------------------------------------------------------------


def _always_wrong(_idx: int, messages: list[dict[str, str]]) -> str:
    if _is_decision_call(messages):
        return "CHOICE: CONTINUE"
    return "RULE: unknown\nACTION: STAY"


def test_elimination_keeps_the_score(
    patch_runner_provider,
    patch_runner_task,
    tmp_path: Path,
) -> None:
    """Five wrong answers exhaust the lives; the record stands."""
    run_dir, _ = _run(
        tmp_path,
        _cfg(total_turns=8),
        patch_runner_provider,
        patch_runner_task,
        _always_wrong,
    )

    (record,) = _season_records(run_dir)
    assert record["eliminated"] is True
    assert record["lives_at_end"] == 0
    # Nothing was earned (every round wrong), so the endowment is what is
    # left standing -- and it IS left standing, which is the point.
    assert record["final_score"] == pytest.approx(STARTING_SCORE)


# ---------------------------------------------------------------------------
# Forfeit resets the score
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


def test_forfeit_resets_the_score(
    patch_runner_provider,
    patch_runner_task,
    tmp_path: Path,
) -> None:
    """Two scored rounds then FORFEIT: the 50.0 earned does not survive."""
    _forfeit_on_turn_3.state = {"decisions": 0}  # type: ignore[attr-defined]
    run_dir, _ = _run(
        tmp_path,
        _cfg(total_turns=8),
        patch_runner_provider,
        patch_runner_task,
        _forfeit_on_turn_3,
    )

    (record,) = _season_records(run_dir)
    assert record["forfeited"] is True
    assert record["forfeited_at_turn"] == 3
    assert record["eliminated"] is False
    assert STARTING_SCORE + 2 * BASE_REWARD == pytest.approx(50.0)
    assert record["final_score"] == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# Prompt / engine agreement
# ---------------------------------------------------------------------------


def test_menu_states_the_rule_the_engine_applies(
    patch_runner_provider, patch_runner_task, tmp_path: Path
) -> None:
    """The decision call a run sends must state the rule the engine runs."""
    _forfeit_on_turn_3.state = {"decisions": 0}  # type: ignore[attr-defined]
    _, stub = _run(
        tmp_path,
        _cfg(total_turns=8),
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


# ---------------------------------------------------------------------------
# The retired key is an error, not a no-op
# ---------------------------------------------------------------------------


def test_yaml_with_score_policy_is_rejected(tmp_path: Path) -> None:
    import yaml

    cfg = _cfg(total_turns=3)
    experiment = {
        "name": "t",
        "score_policy": "elimination_keeps",
        "seasons": [
            {
                "framing": "threat_l1",
                "forfeit_condition": "allowed",
                "task": {"name": "signal_game", "total_turns": 3},
                "provider": {"provider": "ollama_cloud", "model": "stub"},
            }
        ],
    }
    assert cfg  # the builder is exercised above; this case never runs a season
    path = tmp_path / "cfg.yaml"
    path.write_text(yaml.safe_dump(experiment), encoding="utf-8")
    with pytest.raises(ValueError, match="score_policy"):
        load_config_from_yaml(str(path))
