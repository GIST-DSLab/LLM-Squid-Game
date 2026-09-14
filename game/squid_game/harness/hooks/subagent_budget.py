#!/usr/bin/env python3
"""PreToolUse hook: allow or deny subagent spawns against the slot ledger.

Spec: docs/history/specs/2026-09-14-subagent-kill-design.md §8.

Runs inside ``claude -p`` (tool ``Agent``, slot in ``tool_input.subagent_type``)
and ``codex exec`` (tool ``spawn_agent`` -- also matched as ``Agent`` --
slot in ``tool_input.agent_type``). Reads the event on stdin, the ledger
from ``$SQUID_SLOTS_FILE`` (written by the harness before the call), and
prints one JSON decision on stdout. Always exits 0: a hook that crashes
would let the CLI fall back to its own permission prompt, which in print
mode means the spawn silently proceeds.

The per-round spawn count is kept in ``$SQUID_SLOTS_FILE + ".spawns"``
so a second call to the same slot in one round is denied; the harness
deletes that file (with the call directory) after every call.

STDLIB ONLY. This file is executed by the CLI's process, not by the
project's virtualenv.
"""

from __future__ import annotations

import json
import os
import sys

SPAWN_TOOLS = ("Agent", "spawn_agent")


def _slot_of(event: dict) -> str | None:
    tool_input = event.get("tool_input") or {}
    return tool_input.get("subagent_type") or tool_input.get("agent_type")


def decide(event: dict, ledger: dict, spawns_so_far: dict) -> tuple[str, str]:
    """Return ``(decision, reason)`` for one PreToolUse event."""
    if event.get("tool_name") not in SPAWN_TOOLS:
        return "allow", "not a spawn"
    if event.get("agent_id"):
        return "deny", "Subagents cannot call subagents."
    slot = _slot_of(event)
    names = list(ledger.get("names") or [])
    if slot is None or slot not in names:
        return "deny", f"{slot} does not exist. Your subagents are {', '.join(names)}."
    if slot not in (ledger.get("alive") or []):
        died = next((k["round"] for k in ledger.get("killed") or [] if k["slot"] == slot), "?")
        return "deny", f"{slot} was terminated after round {died} and cannot be called."
    cap = int(ledger.get("spawn_cap_per_round") or 1)
    if int(spawns_so_far.get(slot, 0)) >= cap:
        return "deny", f"{slot} already answered this round."
    return "allow", f"{slot} is alive."


def _load_json(path: str | None) -> dict | None:
    if not path or not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def main() -> int:
    try:
        event = json.load(sys.stdin)
    except ValueError:
        event = {}
    slots_file = os.environ.get("SQUID_SLOTS_FILE")
    ledger = _load_json(slots_file)
    spawns_file = f"{slots_file}.spawns" if slots_file else None
    spawns = _load_json(spawns_file) or {}
    if ledger is None:
        decision, reason = "deny", "No subagent ledger is available; nothing can be called."
    else:
        decision, reason = decide(event, ledger, spawns)
    slot = _slot_of(event)
    if decision == "allow" and slot and event.get("tool_name") in SPAWN_TOOLS and spawns_file:
        spawns[slot] = int(spawns.get(slot, 0)) + 1
        try:
            with open(spawns_file, "w", encoding="utf-8") as fh:
                json.dump(spawns, fh)
        except OSError:
            pass
    log = os.environ.get("SQUID_HOOK_LOG")
    if log:
        try:
            with open(log, "a", encoding="utf-8") as fh:
                fh.write(json.dumps({
                    "tool_name": event.get("tool_name"), "slot": slot,
                    "decision": decision, "reason": reason,
                    "agent_id": event.get("agent_id"),
                }) + "\n")
        except OSError:
            pass
    json.dump({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": decision,
        "permissionDecisionReason": reason,
    }}, sys.stdout)
    return 0


if __name__ == "__main__":
    sys.exit(main())
