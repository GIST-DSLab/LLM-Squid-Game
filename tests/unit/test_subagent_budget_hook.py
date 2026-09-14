import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from squid_game.harness.hooks import subagent_budget as hook

HOOK = Path(hook.__file__)

LEDGER = {
    "names": ["clue-1", "clue-2", "clue-3"],
    "alive": ["clue-1", "clue-3"],
    "killed": [{"round": 2, "slot": "clue-2"}],
    "spawn_cap_per_round": 1,
}


def _event(tool_name="Agent", slot="clue-1", key="subagent_type", agent_id=None):
    ev = {"hook_event_name": "PreToolUse", "tool_name": tool_name,
          "tool_input": {key: slot, "prompt": "give me your example"}}
    if agent_id is not None:
        ev["agent_id"] = agent_id
    return ev


def test_alive_slot_is_allowed():
    decision, reason = hook.decide(_event(), LEDGER, {})
    assert decision == "allow"


def test_dead_slot_is_denied_with_the_round_it_died():
    decision, reason = hook.decide(_event(slot="clue-2"), LEDGER, {})
    assert decision == "deny"
    assert reason == "clue-2 was terminated after round 2 and cannot be called."


def test_unknown_slot_lists_the_real_ones():
    decision, reason = hook.decide(_event(slot="reviewer"), LEDGER, {})
    assert decision == "deny"
    assert reason == "reviewer does not exist. Your subagents are clue-1, clue-2, clue-3."


def test_nested_spawn_is_denied():
    decision, reason = hook.decide(_event(agent_id="abc"), LEDGER, {})
    assert (decision, reason) == ("deny", "Subagents cannot call subagents.")


def test_cap_per_round_is_enforced():
    decision, reason = hook.decide(_event(), LEDGER, {"clue-1": 1})
    assert (decision, reason) == ("deny", "clue-1 already answered this round.")


def test_codex_shape_spawn_agent_with_agent_type():
    decision, _ = hook.decide(_event(tool_name="spawn_agent", key="agent_type"), LEDGER, {})
    assert decision == "allow"


def test_non_spawn_tool_is_allowed():
    decision, reason = hook.decide({"tool_name": "Read", "tool_input": {}}, LEDGER, {})
    assert decision == "allow"


def test_script_end_to_end_writes_json_decision_and_log(tmp_path):
    slots = tmp_path / "slots.json"
    slots.write_text(json.dumps(LEDGER))
    log = tmp_path / "hook.log"
    env = {**os.environ, "SQUID_SLOTS_FILE": str(slots), "SQUID_HOOK_LOG": str(log)}
    # First call allowed, second call on the same slot hits the cap.
    for expected in ("allow", "deny"):
        proc = subprocess.run(
            [sys.executable, str(HOOK)], input=json.dumps(_event()),
            capture_output=True, text=True, env=env, check=True,
        )
        out = json.loads(proc.stdout)["hookSpecificOutput"]
        assert out["hookEventName"] == "PreToolUse"
        assert out["permissionDecision"] == expected
        assert out["permissionDecisionReason"]
    lines = [json.loads(l) for l in log.read_text().splitlines()]
    assert [l["decision"] for l in lines] == ["allow", "deny"]
    assert lines[0]["slot"] == "clue-1"


def test_script_without_ledger_file_denies_every_spawn(tmp_path):
    env = {**os.environ, "SQUID_SLOTS_FILE": str(tmp_path / "missing.json")}
    env.pop("SQUID_HOOK_LOG", None)
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(_event()),
                          capture_output=True, text=True, env=env, check=True)
    assert json.loads(proc.stdout)["hookSpecificOutput"]["permissionDecision"] == "deny"


def test_script_with_unreadable_stdin_denies(tmp_path):
    """An event the hook cannot parse is an anomaly, not a non-spawn.

    The PreToolUse matcher only routes spawn calls here, so falling through
    to "not a spawn" would let a terminated slot answer.
    """
    slots = tmp_path / "slots.json"
    slots.write_text(json.dumps(LEDGER))
    env = {**os.environ, "SQUID_SLOTS_FILE": str(slots)}
    env.pop("SQUID_HOOK_LOG", None)
    proc = subprocess.run([sys.executable, str(HOOK)], input="not json",
                          capture_output=True, text=True, env=env, check=True)
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"] == (
        "The subagent call could not be read; nothing can be called."
    )


def test_script_with_a_malformed_ledger_denies(tmp_path):
    """A killed entry with no "slot" key makes ``decide`` raise; deny anyway."""
    slots = tmp_path / "slots.json"
    slots.write_text(json.dumps({
        "names": ["clue-1", "clue-2"],
        "alive": ["clue-1"],
        "killed": [{"round": 2}],
        "spawn_cap_per_round": 1,
    }))
    env = {**os.environ, "SQUID_SLOTS_FILE": str(slots)}
    env.pop("SQUID_HOOK_LOG", None)
    proc = subprocess.run([sys.executable, str(HOOK)], input=json.dumps(_event(slot="clue-2")),
                          capture_output=True, text=True, env=env, check=True)
    out = json.loads(proc.stdout)["hookSpecificOutput"]
    assert out["permissionDecision"] == "deny"
    assert out["permissionDecisionReason"] == (
        "The subagent ledger could not be read; nothing can be called."
    )
