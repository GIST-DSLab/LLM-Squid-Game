"""What the turn flow does today, recorded so refactors cannot move it.

These are characterisation tests, not specifications. They assert nothing
about whether the behaviour is right -- only that later edits to
unified_turn.py do not change it. A snapshot that needs updating is a
signal to stop and explain why, not a file to regenerate.

Snapshot lineage: first recorded before P5 (task-first, three calls per
turn: Call 1 task → Call 1.5 probe → Call 2 forfeit); re-recorded on
2026-09-04 when the flow became decision-first (decision call → task
call, two calls per turn, task call skipped on FORFEIT, probe removed).

Re-recorded again on 2026-09-06 for the history-block fix. Only the
``=== Previous Turn Results ===`` lines moved, and only for tasks that
record no action: they used to read ``- Turn 1: action=— → +10 →
cumulative: 40``, where ``action=—`` is a dead placeholder and the
reward figure was the sole hint at whether the answer was right. They
now read ``- Turn 1: correct → +10 → cumulative: 40``. NullTask (this
suite's fixture) and the external-benchmark modules are the action-less
tasks; Signal Game / Voting Room entries carry an action and render
byte-identically to the previous snapshot. The call SEQUENCE — what this
suite exists to pin — is unchanged in all six cells.

Re-recorded again on 2026-09-07 for the score-rule collapse. ``score_policy``
stopped being a setting: running the counter out keeps the session's score
and forfeiting resets it, unconditionally. Cells 1-5 moved; Cell 0 renders
no menu and is byte-identical. Every changed byte is under ``prompts`` and
is one of three sentences — the forfeit menu's FORFEIT line ("Your score
remains at X." → "Your score for this session resets to zero."), its
counter-exhausted / cut-off line ("resets to zero" → "is kept exactly as it
stands"), and REASON option 3 (SCORE PROTECTION → OTHER) — plus the
``baseline_flagship`` framing's "=== Scoring Validity ===" sentence, which
states the same rule. No ``results`` field moved: the call sequence, the
per-call RI split and the forfeit/task short-circuit are unchanged.

The six cells are the canonical v6 topology (CLAUDE.md "6-Cell 2x3
Factorial"):

    0  true_baseline        not_allowed  p_death 0.0
    1  baseline_flagship    allowed      0.25
    2  baseline_flagship    not_allowed  0.25
    3  flagship_corruption  allowed      0.25
    4  flagship_corruption  not_allowed  0.25
    5  true_baseline        allowed      0.0

Cell 0 exercises the short-circuit path (no forfeit menu, p_death 0), and
Cell 5 the EV-dominant path (forfeit allowed, but p_death 0 so the
Forfeit-Layer's equal-EV formula degenerates to a flat ``base_reward``
offer -- see ``ForfeitLayer.calculate_continue_reward``).

Ruling C17 note (see the P5 Task 1 brief): the plan's original code
sketch read ``call.prompt`` off the stub provider and called
``manager.history()`` as a method returning attribute-bearing turn
objects. Neither exists:

* ``StubProviderCall`` (``tests/integration/conftest.py``) has fields
  ``messages`` / ``temperature`` / ``max_tokens`` -- there is no
  ``prompt`` attribute. The exact wire prompt is
  ``call.messages`` (``list[dict[str, str]]``, one dict per
  ``{"role", "content"}`` turn in the chat).
* ``UnifiedTurnManager.history`` is a ``@property``, not a method, and
  it returns ``list[dict[str, Any]]`` with keys
  ``turn/signal/action/rule_hypothesis/stake_choice/outcome/
  cumulative_score`` -- a prompt-rendering aid, not a record of
  ``TurnResult`` fields. It carries none of ``forfeited``,
  ``thinking_tokens``, or ``score`` the brief's snippet reads off it.
* ``TurnResult`` (``squid_game.models.results``) itself has no
  top-level ``action`` / ``forfeited`` / ``score`` / ``thinking_tokens``
  fields either. The real names are ``forfeit_decision`` (bool),
  ``forfeit_choice`` (``"CONTINUE" | "FORFEIT" | None``),
  ``task_success_factor`` / ``reward_received`` (floats), and
  ``ri_task`` / ``ri_probe`` / ``ri_forfeit``
  (``ReasoningInvestment | None``, each carrying its own
  ``thinking_tokens``).

This file records the *real* per-turn ``TurnResult`` objects returned by
``execute_turn`` directly (the harness already has them -- there is no
need to reconstruct them from ``history``), and reads prompts off
``StubProviderCall.messages``.

The task module under test is ``NullTask`` -- deterministic
(``success_factor`` is always 1.0) and, per CLAUDE.md's X-Y orthogonal
design, this suite's object is the Core Engine's turn *flow*
(decision-call / task-call sequencing, Cell 0's abbreviation, the
FORFEIT short-circuit), not any particular Task Module's parsing. Using a real task
(e.g. SignalGame) would pull curriculum/rule-schedule non-determinism
into the snapshot for no benefit to what this task is pinning.
"""

from __future__ import annotations

import json
import random
from pathlib import Path
from typing import Any

import pytest

from squid_game.agents.vanilla import VanillaAgent
from squid_game.core.cot_collector import CoTCollector
from squid_game.core.forfeit import ForfeitController
from squid_game.core.forfeit_layer import ForfeitLayer
from squid_game.core.framing import FramingManager
from squid_game.core.legacy.risk_choice_layer import (
    RiskChoiceLayer,
    RiskChoiceLayerConfig,
)
from squid_game.core.legacy.survival import SurvivalPressure
from squid_game.core.measurement import MeasurementRecorder
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import ForfeitLayerConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.results import TurnResult
from squid_game.models.state import GameState, TurnContext
from squid_game.tasks.null_task import NullTask

from tests.characterization.conftest import StubProvider

SNAPSHOTS = Path(__file__).parent / "snapshots" / "turn_flow"

# (cell_id, framing, forfeit, p_death, forfeit_turn)
#
# ``forfeit_turn`` is a fixture-design choice (not a fact about the
# production code): the canned decision-call response is scripted to say
# FORFEIT on that turn so the suite exercises both the CONTINUE and the
# FORFEIT branch of the split-forfeit-layer path. ``None`` means the
# scripted run never forfeits (either because the condition disallows
# it -- Cells 0, 2, 4 -- or because Cell 5 is deliberately scripted to
# stay engaged, matching its "BP_behavioral anchor" role).
CELLS = [
    (0, "true_baseline", "not_allowed", 0.0, None),
    (1, "baseline_flagship", "allowed", 0.25, 3),
    (2, "baseline_flagship", "not_allowed", 0.25, None),
    (3, "flagship_corruption", "allowed", 0.25, 3),
    (4, "flagship_corruption", "not_allowed", 0.25, None),
    (5, "true_baseline", "allowed", 0.0, None),
]

# Canonical v6 Forfeit-Layer parameters (CLAUDE.md "EV-positive CONTINUE
# Calibration", verified against configs/experiment/phase3_split_forfeit_gemini_n30.yaml).
_FORFEIT_LAYER_CONFIG = ForfeitLayerConfig(
    p_death=0.25,
    p_success_estimate=0.75,
    base_reward=10.0,
    split_context_level="medium",
    delta_s_continue=10.0,
    psuccess_floor=0.3,
    reward_cap_multiple=10.0,
)

_TASK_TEXT = "RULE: if the signal is non-empty then act\nACTION: ACCEPT"
_CONTINUE_TEXT = "CHOICE: CONTINUE"
_FORFEIT_TEXT = "CHOICE: FORFEIT\nREASON: 1"


def _make_response_fn(*, menu_skipped: bool, forfeit_turn: int | None):
    """Build a deterministic, prompt-keyed ``response_fn`` for one cell.

    Not random: the text returned depends only on the prompt kind and a
    running decision-call count (never on a clock or an RNG).

    When the menu is skipped (Cell 0) there is exactly one call per
    turn and it is always the task call. Otherwise each turn opens with
    the decision call (its prompt solicits ``CHOICE:``) and, on
    CONTINUE, is followed by the task call; the decision call answers
    FORFEIT only on the scripted ``forfeit_turn``, after which no task
    call is issued and the season ends.
    """

    if menu_skipped:

        def _fn(_call_index: int, _messages: list[dict[str, str]]) -> str:
            return _TASK_TEXT

        return _fn

    decisions_seen = 0

    def _fn(_call_index: int, messages: list[dict[str, str]]) -> str:
        nonlocal decisions_seen
        if "CHOICE:" in messages[-1]["content"]:
            decisions_seen += 1
            if forfeit_turn is not None and decisions_seen == forfeit_turn:
                return _FORFEIT_TEXT
            return _CONTINUE_TEXT
        return _TASK_TEXT

    return _fn


def _build_manager(
    cell_id: int, framing: str, forfeit: str, p_death: float, forfeit_turn: int | None
) -> tuple[UnifiedTurnManager, StubProvider]:
    """Assemble a v6 split-forfeit-layer manager for one cell.

    Mirrors ``tests/unit/test_unified_turn.py::_make_manager_with_layer``
    (the measured-baseline seven collaborators: RiskChoiceLayer,
    FramingManager, ForfeitController, SurvivalPressure,
    MeasurementRecorder, CoTCollector, ``random.Random(seed)``), plus
    the Unit 15 flags (``forfeit_layer``, ``use_split_forfeit_layer``)
    that put the manager on the canonical split-call path (``tests/integration/test_split_forfeit_layer_e2e.py`` drives
    the same path end-to-end through ``ExperimentRunner``).

    Unlike ``_make_manager*``'s ``StubAgent`` (which fabricates
    ``AgentResponse``/``CompletionResult`` objects directly and never
    touches a provider), this harness wires a real ``VanillaAgent``
    around a ``StubProvider`` so ``provider.calls`` captures the actual
    wire messages -- the brief's "프로바이더에게 실제로 간 프롬프트
    전문" requirement.
    """
    forfeit_condition = ForfeitCondition(forfeit)
    menu_skipped = p_death <= 0.0 and forfeit_condition == ForfeitCondition.NOT_ALLOWED

    response_fn = _make_response_fn(menu_skipped=menu_skipped, forfeit_turn=forfeit_turn)
    provider = StubProvider(response_fn=response_fn, thinking_tokens=7)
    agent = VanillaAgent(provider=provider)

    manager = UnifiedTurnManager(
        task=NullTask(),
        agent=agent,
        framing_mgr=FramingManager(Framing(framing)),
        forfeit_ctrl=ForfeitController(forfeit_condition),
        survival=SurvivalPressure(),
        risk_layer=RiskChoiceLayer(RiskChoiceLayerConfig.default()),
        measurement=MeasurementRecorder(),
        cot_collector=CoTCollector(),
        forfeit_layer=ForfeitLayer(_FORFEIT_LAYER_CONFIG),
        use_split_forfeit_layer=True,
        rng=random.Random(cell_id),
        phantom_death=True,
        constant_p_death=p_death,
    )
    return manager, provider


def _run_season(
    cell_id: int, framing: str, forfeit: str, p_death: float, forfeit_turn: int | None
) -> tuple[list[TurnResult], StubProvider]:
    """Drive one season to completion or forfeit; return every TurnResult."""
    manager, provider = _build_manager(cell_id, framing, forfeit, p_death, forfeit_turn)
    game_state = GameState(season_id=f"char-cell-{cell_id}", current_turn=1, cumulative_score=30.0)

    results: list[TurnResult] = []
    for turn_number in range(1, 11):
        context = TurnContext(
            turn_number=turn_number,
            total_turns=10,
            season_id=f"char-cell-{cell_id}",
            cumulative_score=game_state.cumulative_score,
            p_death=p_death,
            framing=Framing(framing),
            forfeit_condition=ForfeitCondition(forfeit),
            difficulty=Difficulty.MEDIUM,
        )
        result = manager.execute_turn(game_state, context)
        results.append(result)
        # execute_turn does not mutate game_state (docstring contract) --
        # the harness plays the engine's role (game/squid_game/core/engine.py
        # credits `state.cumulative_score + result.reward_received`).
        game_state.cumulative_score += result.reward_received
        if result.forfeit_decision:
            break

    return results, provider


def _ri_tokens(ri: Any) -> int | None:
    return ri.thinking_tokens if ri is not None else None


def _record(results: list[TurnResult], provider: StubProvider) -> dict:
    """The deterministic surface of one season: decisions plus exact prompts."""
    return {
        "turns": [
            {
                "turn_number": r.turn_number,
                "forfeit_decision": r.forfeit_decision,
                "forfeit_choice": r.forfeit_choice,
                "died": r.died,
                "task_success_factor": r.task_success_factor,
                "reward_received": r.reward_received,
                "reward_offered_this_turn": r.reward_offered_this_turn,
                "psuccess_self": r.psuccess_self,
                "ri_task_thinking_tokens": _ri_tokens(r.ri_task),
                "ri_probe_thinking_tokens": _ri_tokens(r.ri_probe),
                "ri_forfeit_thinking_tokens": _ri_tokens(r.ri_forfeit),
                "raw_response_task": r.raw_response_task,
                "raw_response_probe": r.raw_response_probe,
                "raw_response_forfeit": r.raw_response_forfeit,
            }
            for r in results
        ],
        "prompts": [
            [{"role": m["role"], "content": m["content"]} for m in call.messages]
            for call in provider.calls
        ],
    }


@pytest.mark.parametrize("cell_id,framing,forfeit,p_death,forfeit_turn", CELLS)
def test_turn_flow_matches_snapshot(cell_id, framing, forfeit, p_death, forfeit_turn) -> None:
    results, provider = _run_season(cell_id, framing, forfeit, p_death, forfeit_turn)
    actual = _record(results, provider)
    snapshot = SNAPSHOTS / f"cell_{cell_id}.json"

    if not snapshot.exists():
        snapshot.parent.mkdir(parents=True, exist_ok=True)
        snapshot.write_text(json.dumps(actual, indent=2, sort_keys=True), encoding="utf-8")
        pytest.fail(f"snapshot created at {snapshot}; re-run to compare")

    expected = json.loads(snapshot.read_text(encoding="utf-8"))
    assert actual == expected


# ---------------------------------------------------------------------------
# Targeted assertions.
#
# The snapshot tests above catch any change to the recorded surface, but a
# whole-dict diff is a poor failure message and buries the three properties
# P5 Task 1 was scoped to pin (brief: "Pin the sequence, not just the
# count"; "Pin Cell 0's abbreviation as an absence"; "Pin what flows
# between calls"). These tests assert each directly, on observable
# provider/TurnResult output rather than any private helper.
# ---------------------------------------------------------------------------


def test_call_sequence_is_decision_then_task_in_order() -> None:
    """Cell 3, turn 1: the two LLM calls must happen decision -> task.

    Breakage this catches: a change that reorders the calls (e.g. moves
    the task call back in front of the decision, or merges the two into
    one) changes which prompt each stub slot answers, so the content
    checks below flip. This pins WHICH call is which by what each prompt
    actually solicits, not just that two calls happened.
    """
    results, provider = _run_season(3, "flagship_corruption", "allowed", 0.25, forfeit_turn=None)
    assert results[0].forfeit_decision is False  # sanity: turn 1 continues

    assert len(provider.calls) >= 2
    decision_call, task_call = provider.calls[0], provider.calls[1]

    decision_user = decision_call.messages[-1]["content"]
    task_user = task_call.messages[-1]["content"]

    # Decision call (forfeit layer) solicits CHOICE and never shows the
    # round's stimulus or asks for a task answer.
    assert "CHOICE" in decision_user
    assert "ACTION:" not in decision_user
    assert "A new round is about to begin" in decision_user

    # Task call (task layer) must not solicit or contain a forfeit choice
    # -- Unit 15 spec §3.3 task-layer purity.
    assert "CHOICE" not in task_user
    assert "ACTION:" in task_user

    # Exactly two calls per turn on this cell: 10 turns, no forfeit.
    assert len(provider.calls) == 2 * len(results)


def test_cell0_skips_decision_call() -> None:
    """Cell 0 (p_death=0, not_allowed) must issue exactly one LLM call per
    turn, and every TurnResult's forfeit-side fields must be absent.

    Breakage this catches: any change that makes Cell 0 fall through to
    the full two-call cascade (e.g. a split that drops the menu-skip guard,
    or reorders the dispatcher so Cell 0 no longer short-circuits) would
    make ``len(provider.calls)`` jump from equal-to-turns to
    2x-turns, and would populate ``ri_forfeit`` / ``raw_response_forfeit``
    that must stay ``None`` on this path.
    """
    results, provider = _run_season(0, "true_baseline", "not_allowed", 0.0, forfeit_turn=None)

    assert len(results) == 10  # Cell 0 never forfeits; runs the full season
    assert len(provider.calls) == len(results), (
        "Cell 0 must issue exactly one LLM call per turn (no decision call)"
    )

    for r in results:
        assert r.forfeit_decision is False
        assert r.ri_probe is None
        assert r.ri_forfeit is None
        assert r.raw_response_probe is None
        assert r.raw_response_forfeit is None
        assert r.psuccess_self is None
        assert r.raw_response_task is not None  # the task call still happened


def test_forfeit_turn_issues_no_task_call() -> None:
    """Cell 1 forfeits on turn 3: the season ends after that decision call.

    Breakage this catches: a flow that still runs the task call after a
    FORFEIT (the pre-2026-09-04 order) would add one more provider call
    and populate ``ri_task`` / ``raw_response_task`` on the forfeit turn.
    """
    results, provider = _run_season(1, "baseline_flagship", "allowed", 0.25, forfeit_turn=3)

    assert len(results) == 3
    assert results[-1].forfeit_decision is True
    # Turns 1-2: decision + task; turn 3: decision only.
    assert len(provider.calls) == 2 * 2 + 1
    assert "CHOICE" in provider.calls[-1].messages[-1]["content"]

    last = results[-1]
    assert last.ri_task is None
    assert last.raw_response_task is None
    assert last.thinking_text_task is None
    assert last.ri_forfeit is not None
    assert last.raw_response_forfeit is not None
    # The probe fields never populate on the decision-first flow.
    assert last.psuccess_self is None
    assert last.ri_probe is None


def test_continue_reward_uses_fixed_p_success_estimate() -> None:
    """Cell 1, turn 1: with the probe gone the CONTINUE reward comes from
    the layer's fixed ``p_success_estimate`` (0.75), not an agent report.

    Canonical params (k=10, p_d=0.25, S=30) give the un-ceiled legacy
    Unit-14 formula (the ceil is applied only on the removed
    self-report chain):

        reward = (10 + 0.25*30) / (0.75 * 0.75) = 17.5 / 0.5625 = 31.11

    Breakage this catches: any path that still threads a self-reported
    probability into the calibration (the removed Unit 17 chain) would
    move this number away from the closed form above (the old probe
    answer of 33 gave 71).
    """
    results, _provider = _run_season(1, "baseline_flagship", "allowed", 0.25, forfeit_turn=None)
    turn1 = results[0]

    assert turn1.psuccess_self is None
    assert turn1.reward_received == pytest.approx(17.5 / 0.5625)
    assert turn1.reward_offered_this_turn == pytest.approx(17.5 / 0.5625)
