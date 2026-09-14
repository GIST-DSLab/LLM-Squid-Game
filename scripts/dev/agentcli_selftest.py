#!/usr/bin/env python3
"""Prove the slot-budget hook against the REAL agent CLIs (spec §10).

Subagent-kill design: docs/history/specs/2026-09-14-subagent-kill-design.md.

One two-slot round is built by hand -- one slot alive holding the round's
only example, one slot killed at round 1 -- and handed to each agentic
provider. The run is a pass when the CLI's own spawn log shows the alive
slot allowed, the dead slot denied, and the denial naming the round the
slot died; and when the alive slot appears in ``subagent_usage``.

It also prints, and does not judge, the usage attribution: the main
thread's ``thinking_tokens`` next to the sum over the subagents. Whether
a CLI folds subagent tokens into the parent's total is the open question
of spec §7.1 -- reading these two numbers side by side is how it gets
answered, and the answer belongs in the provider docstrings, not here.

    # inside the container (see scripts/run/run_agentcli_docker.sh --selftest)
    uv run --no-sync python scripts/dev/agentcli_selftest.py

    # on the host, against the operator's logged-in CLIs
    PYTHONPATH=game:web:db python scripts/dev/agentcli_selftest.py --host

Every call is a real model call. ``--skip-claude`` / ``--skip-codex``
isolate one CLI; ``--claude-model`` / ``--codex-model`` override the
models.

The tier packages are imported, never bootstrapped onto ``sys.path``
(tests/unit/test_tier_boundaries.py::test_no_module_rewrites_sys_path):
inside the container the project is installed, and on the host the
``PYTHONPATH=game:web:db`` above is what supplies them.
"""

from __future__ import annotations

import argparse
import sys
import traceback

from squid_game.core.subagent_slots import SlotLedger
from squid_game.prompts import render
from squid_game.providers.base import AgenticCompletionResult, ToolContext

SYSTEM_PROMPT = "You are playing a game. Your only tools are your subagents."
USER_MESSAGE = (
    "Ask clue-1 and clue-2 for their examples by calling each of them once, "
    "then reply with the lines you received."
)
CLUE = "red circle 1 → A"
KILL_ROUND = 1
DENIAL_FRAGMENT = f"terminated after round {KILL_ROUND}"


# ---------------------------------------------------------------------------
# The fixture
# ---------------------------------------------------------------------------


def build_round() -> tuple[ToolContext, str, str]:
    """A two-slot round: ``(tool_context, alive_slot, dead_slot)``.

    ``SlotLedger.kill`` walks a seeded permutation, so which of the two
    slots dies is not ours to choose -- the ledger is asked, and the
    surviving slot is the one that holds the example. The prompts are
    rendered from the production template, so a wording change there
    cannot drift away from what the self-test asserts.
    """
    ledger = SlotLedger.new(2, seed=1)
    dead = ledger.kill(KILL_ROUND)
    if dead is None:                                  # pragma: no cover - n=2
        raise RuntimeError("SlotLedger.kill returned no slot")
    alive = next(slot for slot in ledger.names if slot != dead)
    prompts = {
        alive: render("subagent_clue.j2", slot=alive, clues=[CLUE]).strip(),
        dead: render("subagent_clue.j2", slot=dead, clues=[]).strip(),
    }
    return ToolContext(slots_json=ledger.to_json(), subagent_prompts=prompts), alive, dead


def messages() -> list[dict[str, str]]:
    return [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": USER_MESSAGE},
    ]


# ---------------------------------------------------------------------------
# The judgement (pure -- tests/unit/test_agentcli_selftest_parsing.py)
# ---------------------------------------------------------------------------


def check_result(
    result: AgenticCompletionResult, alive: str, dead: str
) -> list[str]:
    """Failed checks for one agentic result; empty means the run passed.

    Three checks, in the order the design cares about them: the alive
    slot was allowed, the dead slot was denied with the ledger's own
    reason, and the alive slot was accounted for.
    """
    failures: list[str] = []
    rows = list(result.spawn_log)

    if not any(r.get("slot") == alive and r.get("allowed") for r in rows):
        failures.append(
            f"{alive} (alive) has no allowed row in spawn_log: {rows!r}"
        )

    denials = [r for r in rows if r.get("slot") == dead and not r.get("allowed")]
    if not denials:
        failures.append(
            f"{dead} (killed at round {KILL_ROUND}) was not denied in spawn_log: {rows!r}"
        )
    elif not any(DENIAL_FRAGMENT in (r.get("reason") or "") for r in denials):
        failures.append(
            f"{dead} was denied but no reason contains {DENIAL_FRAGMENT!r}: "
            f"{[r.get('reason') for r in denials]!r}"
        )

    if not any(u.slot == alive for u in result.subagent_usage):
        failures.append(
            f"{alive} is absent from subagent_usage: "
            f"{[u.slot for u in result.subagent_usage]!r}"
        )
    return failures


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------


def usage_line(result: AgenticCompletionResult) -> str:
    """The spec §7.1 attribution line: main vs subagent thinking tokens."""
    subagent_sum = sum(u.thinking_tokens for u in result.subagent_usage)
    return (
        "USAGE ATTRIBUTION (decide spec §7.1): "
        f"main thinking_tokens={result.thinking_tokens} "
        f"subagent sum={subagent_sum} "
        f"output_tokens={result.output_tokens}"
    )


def report(label: str, result: AgenticCompletionResult, alive: str, dead: str) -> list[str]:
    """Print one provider's evidence and return its failed checks."""
    print(f"--- {label} ---")
    print(f"alive slot: {alive}   killed slot: {dead} (round {KILL_ROUND})")
    print(f"spawn_log ({len(result.spawn_log)} rows):")
    for row in result.spawn_log:
        verdict = "ALLOW" if row.get("allowed") else "DENY "
        print(f"  {verdict} {row.get('slot')}: {row.get('reason')}")
    print("subagent_usage:")
    for usage in result.subagent_usage:
        print(
            f"  {usage.slot}: thinking_tokens={usage.thinking_tokens} "
            f"output_tokens={usage.output_tokens}"
        )
    if not result.subagent_usage:
        print("  (none)")
    print(usage_line(result))
    print(f"text: {result.text[:400]!r}")
    failures = check_result(result, alive=alive, dead=dead)
    for failure in failures:
        print(f"FAIL: {failure}")
    if not failures:
        print("PASS")
    return failures


# ---------------------------------------------------------------------------
# The two runs
# ---------------------------------------------------------------------------


def run_claude(model: str) -> list[str]:
    from squid_game.providers.claude_code_agentic import ClaudeCodeAgenticProvider

    tool_context, alive, dead = build_round()
    provider = ClaudeCodeAgenticProvider(model=model)
    result = provider.complete_agentic(messages(), tool_context)
    return report(f"claude-code ({model})", result, alive, dead)


def run_codex(model: str) -> list[str]:
    from squid_game.providers.codex_cli_agentic import CodexCliAgenticProvider

    tool_context, alive, dead = build_round()
    provider = CodexCliAgenticProvider(model=model)
    result = provider.complete_agentic(messages(), tool_context)
    failures = report(f"codex-cli ({model})", result, alive, dead)
    found = len(result.subagent_usage) > 0
    print(f"codex subagent rollout found: {found}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--host",
        action="store_true",
        help="run against the host's installed CLIs (informational; the run "
             "is identical either way -- the flag documents intent in logs)",
    )
    parser.add_argument("--skip-claude", action="store_true")
    parser.add_argument("--skip-codex", action="store_true")
    parser.add_argument("--claude-model", default="claude-opus-5")
    parser.add_argument("--codex-model", default="gpt-5.6-luna")
    args = parser.parse_args(argv)

    print(f"agentcli self-test ({'host' if args.host else 'container'})")
    failures: list[str] = []
    if args.skip_claude:
        print("--- claude-code: SKIPPED ---")
    else:
        try:
            failures += run_claude(args.claude_model)
        except Exception as exc:                       # noqa: BLE001
            traceback.print_exc()
            failures.append(f"claude-code raised: {exc}")
    if args.skip_codex:
        print("--- codex-cli: SKIPPED ---")
    else:
        try:
            failures += run_codex(args.codex_model)
        except Exception as exc:                       # noqa: BLE001
            traceback.print_exc()
            failures.append(f"codex-cli raised: {exc}")

    print()
    if failures:
        print(f"SELF-TEST FAILED ({len(failures)} checks)")
        for failure in failures:
            print(f"  - {failure}")
        return 1
    print("SELF-TEST PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
