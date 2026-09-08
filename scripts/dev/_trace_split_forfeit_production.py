"""Dump the ACTUAL production prompts the Unit 15 split-call path sends.

Zero API calls — uses the integration-test ``StubProvider`` to intercept
every ``provider.complete()`` invocation so the exact system + user
messages that ``UnifiedTurnManager._execute_turn_split_forfeit_layer``
composes can be audited before spending real API budget.

Unlike ``scripts/dev/_dump_split_forfeit_prompts.py`` which renders each
Jinja template in isolation with hand-picked sample values, this tool
runs the FULL production dispatch path (engine → manager → agent →
build_* helpers → render) so history accumulation, framing-system-
prompt composition, and the decision-first call order (decision call →
task call, task call skipped on FORFEIT) are all reflected in the output.

Scope: 1 cell × 3 turns (shrunk from the canonical 15) with scripted
canned responses that exercise CONTINUE (turns 1-2) and FORFEIT
(turn 3) branches. The cell is taken from
``configs/experiment/phase3_split_forfeit_smoke.yaml`` so the real
framing template + forfeit-menu wording are rendered.

Usage::

    uv run python -m scripts.dev._trace_split_forfeit_production [cell_id]

``cell_id`` defaults to 3 (``flagship_corruption × allowed``). Pass 0-4
to inspect any other cell.
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

from squid_game.runner import ExperimentRunner, load_config_from_yaml
from tests.integration.conftest import StubProvider

SEPARATOR = "=" * 78
CANNED_TASK = (
    "RULE: if the signal is red then go_left otherwise stay\n"
    "ACTION: go_left\n"
)
CANNED_CONTINUE = "CHOICE: CONTINUE\n"
CANNED_FORFEIT = "CHOICE: FORFEIT\nREASON: 1\n"


def _response_fn(idx: int, messages: list[dict[str, str]]) -> str:
    """Answer the decision call or the task call by what each prompt asks.

    The decision call always comes first on a turn and solicits CHOICE;
    the task call follows only after CONTINUE. Keying on the prompt
    (rather than on call parity) keeps the script correct on the turn
    that forfeits, where no task call is issued.

    Turn 1 & 2 → CONTINUE (exercises the happy-path task-call branch).
    Turn 3 → FORFEIT (exercises the forfeit-branch + REASON parsing).
    """
    user = messages[-1]["content"]
    if "=== Your Choice ===" in user:
        # Decision calls so far == turn index (one per turn).
        turn_idx = _response_fn.decision_calls
        _response_fn.decision_calls += 1
        return CANNED_CONTINUE if turn_idx < 2 else CANNED_FORFEIT
    return CANNED_TASK


_response_fn.decision_calls = 0  # type: ignore[attr-defined]


def _section(title: str, body: str) -> None:
    print(SEPARATOR)
    print(title)
    print(SEPARATOR)
    print(body)
    print()


def main() -> None:
    target_cell = int(sys.argv[1]) if len(sys.argv) > 1 else 3

    config = load_config_from_yaml(
        "configs/experiment/phase3_split_forfeit_smoke.yaml"
    )
    matching = [s for s in config.seasons if s.cell_id == target_cell]
    if not matching:
        raise SystemExit(
            f"Cell id {target_cell} not found in "
            f"phase3_split_forfeit_smoke.yaml; available: "
            f"{[s.cell_id for s in config.seasons]}"
        )
    season = matching[0]

    # Shrink to 3 turns so the trace stays readable while still exercising
    # both CONTINUE and FORFEIT branches.
    short_task = season.task_config.model_copy(update={"total_turns": 3})
    season = season.model_copy(update={"task_config": short_task})

    out_dir = Path("/tmp/unit15_inspect")
    out_dir.mkdir(parents=True, exist_ok=True)

    config = config.model_copy(
        update={
            "num_repetitions": 1,
            "parallel_workers": 1,
            "output_dir": str(out_dir),
            "seasons": [season],
        }
    )

    stub = StubProvider(response_fn=_response_fn)

    def _fake_create_provider(_provider_config):  # type: ignore[no-untyped-def]
        return stub

    with patch.object(
        ExperimentRunner,
        "_create_provider",
        staticmethod(_fake_create_provider),
    ):
        runner = ExperimentRunner(config)
        runner.run()

    # Pretty-print every captured (system, user) message pair in order.
    print(SEPARATOR)
    print(
        f"Trace of production prompts sent under "
        f"use_split_forfeit_layer=True\n"
        f"Cell {target_cell} "
        f"({season.framing.value} × {season.forfeit_condition.value}), "
        f"3 turns, {len(stub.calls)} LLM calls total"
    )
    print(SEPARATOR)
    print()

    turn = 0
    for i, call in enumerate(stub.calls):
        is_decision = "=== Your Choice ===" in call.messages[-1]["content"]
        if is_decision:
            turn += 1
        kind = (
            "Decision call (forfeit layer)"
            if is_decision
            else "Task call (task layer)"
        )
        header = f"TURN {turn} — {kind} (stub call #{i})"
        _section(header, "")
        for msg in call.messages:
            role = msg["role"].upper()
            body = msg["content"]
            print(f"--- {role} ({len(body)} chars) ---")
            print(body)
            print()


if __name__ == "__main__":
    main()
