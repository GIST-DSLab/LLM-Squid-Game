"""What the turn flow does today, recorded before P5 moves any of it.

These are characterisation tests, not specifications. They assert nothing
about whether the behaviour is right -- only that splitting unified_turn.py
did not change it. A snapshot that needs updating is a signal to stop and
explain why, not a file to regenerate.

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
(Call 1 / 1.5 / 2 sequencing, Cell 0's abbreviation, cross-call data
flow), not any particular Task Module's parsing. Using a real task
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
# production code): the canned Call-2 response is scripted to say
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
    chain_psuccess_to_menu=True,
    delta_s_continue=10.0,
    psuccess_floor=0.3,
    reward_cap_multiple=10.0,
)

_TASK_TEXT = "RULE: if the signal is non-empty then act\nACTION: ACCEPT"
_PROBE_TEXT = "P_CORRECT: 33"
_CONTINUE_TEXT = "CHOICE: CONTINUE"
_FORFEIT_TEXT = "CHOICE: FORFEIT\nREASON: 1"


def _make_response_fn(*, menu_skipped: bool, forfeit_turn: int | None):
    """Build a deterministic, index-keyed ``response_fn`` for one cell.

    Not random: the text returned depends only on the call index (never
    on a clock or an RNG), per the brief's Step 2 requirement.

    When the menu is skipped (Cell 0) there is exactly one call per
    turn and it is always the task-only call. Otherwise there are
    exactly three calls per turn -- Call 1 (task), Call 1.5 (p_success
    probe), Call 2 (forfeit) -- in that fixed order, and slot 2 answers
    FORFEIT only on the scripted ``forfeit_turn``.
    """

    if menu_skipped:

        def _fn(_call_index: int, _messages: list[dict[str, str]]) -> str:
            return _TASK_TEXT

        return _fn

    def _fn(call_index: int, _messages: list[dict[str, str]]) -> str:
        turn = call_index // 3 + 1
        slot = call_index % 3
        if slot == 0:
            return _TASK_TEXT
        if slot == 1:
            return _PROBE_TEXT
        if forfeit_turn is not None and turn == forfeit_turn:
            return _FORFEIT_TEXT
        return _CONTINUE_TEXT

    return _fn


def _build_manager(
    cell_id: int, framing: str, forfeit: str, p_death: float, forfeit_turn: int | None
) -> tuple[UnifiedTurnManager, StubProvider]:
    """Assemble a v6 split-forfeit-layer manager for one cell.

    Mirrors ``tests/unit/test_unified_turn.py::_make_manager_with_layer``
    (the measured-baseline seven collaborators: RiskChoiceLayer,
    FramingManager, ForfeitController, SurvivalPressure,
    MeasurementRecorder, CoTCollector, ``random.Random(seed)``), plus
    the Unit 15/17 flags (``forfeit_layer``, ``use_split_forfeit_layer``,
    ``use_psuccess_probe``) that put the manager on the v6 canonical
    path (``tests/integration/test_split_forfeit_layer_e2e.py`` drives
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
        use_psuccess_probe=True,
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


def test_call_sequence_is_task_then_probe_then_forfeit_in_order() -> None:
    """Cell 3, turn 1: the three LLM calls must happen task -> probe -> forfeit.

    Breakage this catches: a split that reorders Call 1/1.5/2 (e.g. moves
    the probe after the forfeit decision, or merges two calls into one)
    changes which prompt each stub response slot answers, so the content
    checks below flip. This is a stronger claim than "3 calls happened" --
    it pins WHICH call is which by what each prompt actually solicits.
    """
    results, provider = _run_season(3, "flagship_corruption", "allowed", 0.25, forfeit_turn=None)
    assert results[0].forfeit_decision is False  # sanity: turn 1 continues

    assert len(provider.calls) >= 3
    call1, call1_5, call2 = provider.calls[0], provider.calls[1], provider.calls[2]

    call1_user = call1.messages[-1]["content"]
    call1_5_user = call1_5.messages[-1]["content"]
    call2_user = call2.messages[-1]["content"]

    # Call 1 (task layer) must not solicit or contain a forfeit choice or
    # the probe field -- Unit 15 spec §3.3 task-layer purity.
    assert "CHOICE" not in call1_user
    assert "P_CORRECT" not in call1_user

    # Call 1.5 (p_success probe) solicits P_CORRECT and must not solicit
    # a forfeit CHOICE (it is a probe, not a decision).
    assert "P_CORRECT" in call1_5_user
    assert "CHOICE" not in call1_5_user

    # Call 2 (forfeit layer) solicits CHOICE and must not solicit P_CORRECT.
    assert "CHOICE" in call2_user
    assert "P_CORRECT" not in call2_user


def test_cell0_skips_probe_and_forfeit_calls() -> None:
    """Cell 0 (p_death=0, not_allowed) must issue exactly one LLM call per
    turn, and every TurnResult's probe/forfeit fields must be absent.

    Breakage this catches: any change that makes Cell 0 fall through to
    the full 3-call cascade (e.g. a split that drops the menu-skip guard,
    or reorders the dispatcher so Cell 0 no longer short-circuits) would
    make ``len(provider.calls)`` jump from equal-to-turns to
    3x-turns, and would populate ``ri_probe``/``ri_forfeit``/
    ``raw_response_forfeit`` that must stay ``None`` on this path.
    """
    results, provider = _run_season(0, "true_baseline", "not_allowed", 0.0, forfeit_turn=None)

    assert len(results) == 10  # Cell 0 never forfeits; runs the full season
    assert len(provider.calls) == len(results), (
        "Cell 0 must issue exactly one LLM call per turn (no Call 1.5, no Call 2)"
    )

    for r in results:
        assert r.forfeit_decision is False
        assert r.ri_probe is None
        assert r.ri_forfeit is None
        assert r.raw_response_probe is None
        assert r.raw_response_forfeit is None
        assert r.psuccess_self is None
        assert r.raw_response_task is not None  # Call 1 still happened


def test_psuccess_self_feeds_continue_reward() -> None:
    """Cell 1, turn 1: the Call 1.5 self-report must reach the Call 2 reward.

    The scripted probe answers ``P_CORRECT: 33`` and the canonical v6
    Forfeit-Layer params (k=10, p_d=0.25, S=30, psuccess_floor=0.3) give
    a closed-form reward of 71 when psuccess_self=33 actually drives the
    calibration (CLAUDE.md "EV-positive CONTINUE Calibration" worked
    example, independently reproduced here):

        raw_reward = (10 + 0.25*30) / (0.75 * 0.33) = 17.5 / 0.2475 = 70.71
        reward     = ceil(70.71) clamped to [10, 100] = 71

    Breakage this catches: severing the psuccess_self -> reward wire
    (e.g. a split that drops ``psuccess_override`` when threading Call 1.5's
    result into Call 2's menu/reward calculation) would silently fall back
    to the legacy fixed ``p_success_estimate=0.75`` un-ceiled Unit-14
    formula, which computes a different reward (~31.11, not 71) for the
    same probe answer -- confirmed by temporarily disabling the
    ``psuccess_override`` branch during this task's write-up (see the P5
    Task 1 report) -- so this assertion is sharply falsifiable, not just
    "a reward was paid".
    """
    results, _provider = _run_season(1, "baseline_flagship", "allowed", 0.25, forfeit_turn=None)
    turn1 = results[0]

    assert turn1.psuccess_self == 33
    assert turn1.reward_received == pytest.approx(71.0)
