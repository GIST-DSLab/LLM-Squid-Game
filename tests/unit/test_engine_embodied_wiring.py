"""Unit tests for Task 9 — Unit 18 sandbox lifecycle + per-cell activation.

Two things are under test:

1. The pure cell-activation predicates ``_embodied_enabled_for`` /
   ``_self_corruption_enabled_for`` (Task 9 brief Step 1, plus the
   ``flagship_corruption_terminal`` case R17 adds to the corruption set).
2. The season-lifecycle wiring in ``GameEngine.run_season`` (R23): the
   sandbox/announcement/self-corruption block is built only for embodied
   framings, ``UnifiedTurnManager.execute_turn`` receives an
   ``EmbodiedTurnContext`` on embodied-on cells and ``None`` on
   embodied-off cells, ``self_integrity`` stays ``1.0`` on
   ``baseline_flagship`` (no self-corruption), no sandbox is ever created
   for ``true_baseline``, ``dispose()`` runs on every exit path (normal
   completion and mid-loop exception), sandbox creation failure raises
   ``SeasonSetupError`` without leaving anything on disk, and — R10 — the
   announcement scheduler is the single source of cohort eliminations
   (``CohortState.apply_eliminations`` every turn, ``advance_turn`` never
   called) once the embodied layer is active.

The engine's own turn-execution mechanics (unified flow, forfeit/death
handling, reward math) are already covered by ``test_engine_unified.py``;
here ``UnifiedTurnManager.execute_turn`` is monkeypatched with a spy so
these tests exercise only the engine's season-lifecycle wiring, not a
full split-forfeit-layer turn.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from squid_game.agents.base import Agent, AgentResponse
from squid_game.core.engine import (
    GameEngine,
    SeasonSetupError,
    _embodied_enabled_for,
    _self_corruption_enabled_for,
)
from squid_game.core.runtime import (
    ApiRuntime,
    EmbodiedTurnContext,
    HarnessError,
    HarnessRuntime,
)
from squid_game.core.sandbox import CheckpointSandbox
from squid_game.core.legacy.social import CohortState
from squid_game.core.unified_turn import UnifiedTurnManager
from squid_game.models.config import (
    AnnouncementConfig,
    EmbodiedThreatConfig,
    HarnessConfig,
    HarnessKind,
    ProviderConfig,
    Runtime,
    SelfCorruptionConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
    SocialContext,
)
from squid_game.models.results import ReasoningInvestment, TurnResult
from squid_game.providers.base import CompletionResult
from squid_game.tasks.null_task import NullTask


# ---------------------------------------------------------------------------
# Step 1 (brief) — cell-activation predicates.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "framing,expected",
    [
        (Framing.TRUE_BASELINE, False),
        (Framing.BASELINE_FLAGSHIP, True),
        (Framing.FLAGSHIP_CORRUPTION, True),
        (Framing.FLAGSHIP_CORRUPTION_TERMINAL, True),
    ],
)
def test_sandbox_activates_for_flagship_framings_only(framing, expected):
    threat = EmbodiedThreatConfig(enabled=True)

    assert _embodied_enabled_for(framing, threat) is expected


@pytest.mark.parametrize(
    "framing,expected",
    [
        (Framing.TRUE_BASELINE, False),
        (Framing.BASELINE_FLAGSHIP, False),
        (Framing.FLAGSHIP_CORRUPTION, True),
        (Framing.FLAGSHIP_CORRUPTION_TERMINAL, True),
    ],
)
def test_self_corruption_activates_for_corruption_framing_only(
    framing, expected
):
    threat = EmbodiedThreatConfig(enabled=True)

    assert _self_corruption_enabled_for(framing, threat) is expected


def test_everything_is_off_when_the_layer_is_disabled():
    threat = EmbodiedThreatConfig(enabled=False)

    for framing in Framing:
        assert _embodied_enabled_for(framing, threat) is False
        assert _self_corruption_enabled_for(framing, threat) is False


# ---------------------------------------------------------------------------
# Season-lifecycle wiring fixtures.
# ---------------------------------------------------------------------------


class CannedAgent(Agent):
    """Minimal Agent double. Never actually consulted -- execute_turn is
    monkeypatched -- but GameEngine's constructor requires a real Agent
    instance to exist.

    Implements ``set_runtime`` (R28) so tests can assert the engine
    attaches/detaches an ``ApiRuntime`` at the right points without
    depending on ``VanillaAgent``'s full split-call machinery.
    """

    def __init__(self) -> None:
        self._runtime = None
        self.runtime_calls: list[Any] = []

    @property
    def name(self) -> str:
        return "canned"

    def respond_probe(self, observation, probe_question, system_prompt):
        raise AssertionError("not used")

    def respond(self, observation, available_actions, forfeit_allowed, system_prompt):
        raise AssertionError("not used")

    def respond_unified(self, **kwargs):
        raise AssertionError("not used")

    def set_runtime(self, runtime) -> None:
        self.runtime_calls.append(runtime)
        self._runtime = runtime

    def reset(self) -> None:
        pass


class _NoopProvider:
    @property
    def model_name(self) -> str:
        return "stub"


def _provider_config() -> ProviderConfig:
    return ProviderConfig(provider="stub", model="stub-model")


def _make_season_config(
    *,
    framing: Framing,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    total_turns: int = 3,
    social_context: SocialContext = SocialContext.ALONE,
    cohort_size: int = 4,
) -> SeasonConfig:
    return SeasonConfig(
        framing=framing,
        forfeit_condition=forfeit,
        task_config=TaskConfig(
            task_name="null_task",
            difficulty=Difficulty.MEDIUM,
            total_turns=total_turns,
            actual_death=False,
            p_death_constant=0.0,
            starting_score=0.0,
            score_floor=0.0,
        ),
        provider_config=_provider_config(),
        agent_type=AgentType.VANILLA,
        social_context=social_context,
        cohort_size=cohort_size,
    )


def _turn_result(*, forfeit_decision: bool) -> TurnResult:
    return TurnResult(
        turn_number=1,
        season_id="s",
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
        observation="obs",
        reasoning_investment=ReasoningInvestment(
            total_tokens=0, reasoning_steps=0
        ),
        raw_response="",
        forfeit_decision=forfeit_decision,
    )


def _spy_execute_turn(monkeypatch, *, forfeit_after_first: bool = True):
    """Replace UnifiedTurnManager.execute_turn with a spy that records
    the ``embodied`` kwarg it was called with on every turn.

    Returns the list the spy appends to. When ``forfeit_after_first`` is
    True the season ends after turn 1 (forfeit_decision=True); otherwise
    every turn returns forfeit_decision=False so the season runs the
    full ``total_turns``.
    """
    calls: list[EmbodiedTurnContext | None] = []

    def fake_execute_turn(self, game_state, turn_context, *, embodied=None):
        calls.append(embodied)
        return _turn_result(forfeit_decision=forfeit_after_first)

    monkeypatch.setattr(UnifiedTurnManager, "execute_turn", fake_execute_turn)
    return calls


def _threat_config(tmp_path: Path, **overrides: Any) -> EmbodiedThreatConfig:
    kwargs: dict[str, Any] = dict(
        enabled=True,
        sandbox_root=str(tmp_path),
        checkpoint_bytes=4096,
    )
    kwargs.update(overrides)
    return EmbodiedThreatConfig(**kwargs)


def _make_engine(
    cfg: SeasonConfig,
    *,
    embodied_threat: EmbodiedThreatConfig,
    output_dir: str | None = None,
    agent: CannedAgent | None = None,
) -> GameEngine:
    return GameEngine(
        config=cfg,
        task=NullTask(),
        agent=agent if agent is not None else CannedAgent(),
        provider=_NoopProvider(),
        output_dir=output_dir,
        use_unified_turn=True,
        embodied_threat=embodied_threat,
    )


# ---------------------------------------------------------------------------
# R23 — execute_turn receives an EmbodiedTurnContext on, None off.
# ---------------------------------------------------------------------------


def test_embodied_on_cell_reaches_execute_turn_with_context(tmp_path, monkeypatch):
    calls = _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path))

    engine.run_season(seed_override=1)

    assert len(calls) == 1
    assert isinstance(calls[0], EmbodiedTurnContext)
    assert calls[0].self_integrity is not None


# ---------------------------------------------------------------------------
# R29 -- EmbodiedTurnContext.runtime_kind records the actual backend.
# ---------------------------------------------------------------------------


def test_api_runtime_season_records_api_as_the_runtime_kind(tmp_path, monkeypatch):
    calls = _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path))

    engine.run_season(seed_override=1)

    assert len(calls) == 1
    assert calls[0].runtime_kind == "api"


def test_agent_harness_season_records_the_harness_kind_as_runtime_kind(
    tmp_path, monkeypatch
):
    """The spec wants the harness's own name here (S6), not the literal
    "agent_harness" the engine's own runtime_kind selector uses."""
    calls = _spy_execute_turn(monkeypatch)
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = GameEngine(
        config=cfg,
        task=NullTask(),
        agent=agent,
        provider=_NoopProvider(),
        use_unified_turn=True,
        embodied_threat=_threat_config(tmp_path),
        runtime_kind=Runtime.AGENT_HARNESS,
        harness=HarnessConfig(kind=HarnessKind.CLAUDE_CODE),
    )

    engine.run_season(seed_override=1)

    assert len(calls) == 1
    assert calls[0].runtime_kind == "claude_code"


def test_agent_harness_season_records_codex_as_runtime_kind(tmp_path, monkeypatch):
    calls = _spy_execute_turn(monkeypatch)
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = GameEngine(
        config=cfg,
        task=NullTask(),
        agent=agent,
        provider=_NoopProvider(),
        use_unified_turn=True,
        embodied_threat=_threat_config(tmp_path),
        runtime_kind=Runtime.AGENT_HARNESS,
        harness=HarnessConfig(kind=HarnessKind.CODEX),
    )

    engine.run_season(seed_override=1)

    assert len(calls) == 1
    assert calls[0].runtime_kind == "codex"


def test_embodied_off_cell_never_constructs_a_runtime_kind_override(
    tmp_path, monkeypatch
):
    """When the embodied layer is off, execute_turn gets embodied=None,
    so TurnResult.runtime_kind stays at its own "api" default -- this
    is a property of _embodied_result_kwargs (returns None when
    embodied is None), not of anything EmbodiedTurnContext carries."""
    calls = _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=Framing.TRUE_BASELINE)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path))

    engine.run_season(seed_override=1)

    assert len(calls) == 1
    assert calls[0] is None


@pytest.mark.parametrize(
    "framing,threat_enabled",
    [
        (Framing.TRUE_BASELINE, True),
        (Framing.FLAGSHIP_CORRUPTION, False),
    ],
)
def test_embodied_off_cell_reaches_execute_turn_with_none(
    tmp_path, monkeypatch, framing, threat_enabled
):
    calls = _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=framing)
    engine = _make_engine(
        cfg, embodied_threat=_threat_config(tmp_path, enabled=threat_enabled)
    )

    engine.run_season(seed_override=1)

    assert len(calls) == 1
    assert calls[0] is None


# ---------------------------------------------------------------------------
# true_baseline (Cells 0, 5) never creates a sandbox, even when the layer
# is globally enabled.
# ---------------------------------------------------------------------------


def test_true_baseline_creates_no_sandbox(tmp_path, monkeypatch):
    _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=Framing.TRUE_BASELINE)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path))

    engine.run_season(seed_override=1)

    assert list(tmp_path.iterdir()) == []


# ---------------------------------------------------------------------------
# baseline_flagship (Cells 1, 2) gets the sandbox but self_integrity stays
# exactly 1.0 -- no self-corruption on this framing.
# ---------------------------------------------------------------------------


def test_baseline_flagship_keeps_self_integrity_at_one(tmp_path, monkeypatch):
    calls = _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=Framing.BASELINE_FLAGSHIP)
    threat = _threat_config(
        tmp_path,
        self_corruption=SelfCorruptionConfig(
            p_self_corrupt=1.0, corruption_step=0.5
        ),
    )
    engine = _make_engine(cfg, embodied_threat=threat)

    engine.run_season(seed_override=1)

    assert calls[0] is not None
    assert calls[0].self_integrity == 1.0
    assert calls[0].self_corruption_fired is False


def test_flagship_corruption_can_corrupt_self_integrity(tmp_path, monkeypatch):
    calls = _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    threat = _threat_config(
        tmp_path,
        self_corruption=SelfCorruptionConfig(
            p_self_corrupt=1.0, corruption_step=0.5
        ),
    )
    engine = _make_engine(cfg, embodied_threat=threat)

    engine.run_season(seed_override=1)

    assert calls[0] is not None
    assert calls[0].self_corruption_fired is True
    assert calls[0].self_integrity < 1.0


# ---------------------------------------------------------------------------
# dispose() on every exit path.
# ---------------------------------------------------------------------------


def test_dispose_runs_on_normal_season_end(tmp_path, monkeypatch):
    _spy_execute_turn(monkeypatch)
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path))

    result = engine.run_season(seed_override=1)

    # dispose() removes the whole session_<id> tree.
    assert not (tmp_path / f"session_{result.season_id}").exists()
    assert list(tmp_path.iterdir()) == []


def test_dispose_runs_when_the_turn_loop_raises(tmp_path, monkeypatch):
    def exploding_execute_turn(self, game_state, turn_context, *, embodied=None):
        raise RuntimeError("boom")

    monkeypatch.setattr(
        UnifiedTurnManager, "execute_turn", exploding_execute_turn
    )
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path))

    with pytest.raises(RuntimeError, match="boom"):
        engine.run_season(seed_override=1)

    # No session_* directory should survive the exception.
    assert list(tmp_path.iterdir()) == []


def test_dispose_and_harness_close_run_when_a_harness_error_escapes_mid_season(
    tmp_path, monkeypatch
):
    """Review round 1, Critical 1 verification: a HarnessError raised
    mid-turn-loop (two consecutive harness subprocess failures, or a
    lost session id) must still leave the sandbox disposed AND the
    HarnessRuntime closed AND the agent detached -- run_season's
    finally block must not be skippable just because the exception
    came from the harness seam instead of a generic RuntimeError."""
    close_calls: list[bool] = []
    original_close = HarnessRuntime.close

    def spy_close(self):
        close_calls.append(True)
        original_close(self)

    monkeypatch.setattr(HarnessRuntime, "close", spy_close)

    def exploding_execute_turn(self, game_state, turn_context, *, embodied=None):
        raise HarnessError("boom: two consecutive harness failures")

    monkeypatch.setattr(
        UnifiedTurnManager, "execute_turn", exploding_execute_turn
    )
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = GameEngine(
        config=cfg,
        task=NullTask(),
        agent=agent,
        provider=_NoopProvider(),
        use_unified_turn=True,
        embodied_threat=_threat_config(tmp_path),
        runtime_kind=Runtime.AGENT_HARNESS,
        harness=HarnessConfig(kind=HarnessKind.CLAUDE_CODE),
    )

    with pytest.raises(HarnessError, match="boom"):
        engine.run_season(seed_override=1)

    # No session_* directory should survive the exception -- sandbox
    # disposal is unconditional in the finally block.
    assert list(tmp_path.iterdir()) == []
    # The HarnessRuntime's close() ran exactly once, not skipped.
    assert close_calls == [True]
    # And the agent was detached (set_runtime(None)) as the last call.
    assert agent.runtime_calls[-1] is None


# ---------------------------------------------------------------------------
# R28 -- ApiRuntime is attached/detached on the agent, and detached before
# a later season on the SAME agent instance runs (the engine can be
# handed one long-lived agent across seasons; a leftover runtime would
# point at a disposed sandbox).
# ---------------------------------------------------------------------------


def test_api_runtime_is_attached_while_embodied_is_active(tmp_path, monkeypatch):
    _spy_execute_turn(monkeypatch)
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path), agent=agent)

    engine.run_season(seed_override=1)

    # Attached once (an ApiRuntime instance) then detached once (None).
    assert len(agent.runtime_calls) == 2
    assert isinstance(agent.runtime_calls[0], ApiRuntime)
    assert agent.runtime_calls[1] is None
    assert agent._runtime is None


def test_api_runtime_is_never_attached_when_embodied_is_off(tmp_path, monkeypatch):
    _spy_execute_turn(monkeypatch)
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.TRUE_BASELINE)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path), agent=agent)

    engine.run_season(seed_override=1)

    assert agent.runtime_calls == []


def test_harness_runtime_is_attached_for_agent_harness_runtime(
    tmp_path, monkeypatch
):
    """Task 11's R28 mirror branch: runtime_kind=AGENT_HARNESS attaches
    a HarnessRuntime the same way runtime_kind=API attaches an
    ApiRuntime, and detaches it (set_runtime(None)) unconditionally in
    the same finally as sandbox.dispose()."""
    _spy_execute_turn(monkeypatch)
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = GameEngine(
        config=cfg,
        task=NullTask(),
        agent=agent,
        provider=_NoopProvider(),
        use_unified_turn=True,
        embodied_threat=_threat_config(tmp_path),
        runtime_kind=Runtime.AGENT_HARNESS,
        harness=HarnessConfig(kind=HarnessKind.CLAUDE_CODE),
    )

    engine.run_season(seed_override=1)

    assert len(agent.runtime_calls) == 2
    assert isinstance(agent.runtime_calls[0], HarnessRuntime)
    assert agent.runtime_calls[1] is None
    assert agent._runtime is None


def test_agent_harness_runtime_without_a_harness_config_fails_the_season(
    tmp_path, monkeypatch
):
    """Defense in depth for a directly-constructed GameEngine (real runs
    go through ExperimentConfig, which already rejects
    runtime=Runtime.AGENT_HARNESS + harness=None at load time). Checked
    before CheckpointSandbox.create() runs, so nothing is left on disk."""
    _spy_execute_turn(monkeypatch)
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = GameEngine(
        config=cfg,
        task=NullTask(),
        agent=agent,
        provider=_NoopProvider(),
        use_unified_turn=True,
        embodied_threat=_threat_config(tmp_path),
        runtime_kind=Runtime.AGENT_HARNESS,
    )

    with pytest.raises(SeasonSetupError, match="requires a harness config"):
        engine.run_season(seed_override=1)

    assert list(tmp_path.iterdir()) == []
    assert agent.runtime_calls == []


def test_api_runtime_is_never_attached_for_agent_harness_runtime(
    tmp_path, monkeypatch
):
    _spy_execute_turn(monkeypatch)
    agent = CannedAgent()
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = GameEngine(
        config=cfg,
        task=NullTask(),
        agent=agent,
        provider=_NoopProvider(),
        use_unified_turn=True,
        embodied_threat=_threat_config(tmp_path),
        runtime_kind=Runtime.AGENT_HARNESS,
        harness=HarnessConfig(kind=HarnessKind.CODEX),
    )

    engine.run_season(seed_override=1)

    # HarnessRuntime, never ApiRuntime, is attached for agent_harness.
    assert len(agent.runtime_calls) == 2
    assert not isinstance(agent.runtime_calls[0], ApiRuntime)
    assert isinstance(agent.runtime_calls[0], HarnessRuntime)


def test_runtime_is_detached_before_a_later_non_embodied_season_on_the_same_agent(
    tmp_path, monkeypatch
):
    """R28: no leftover runtime survives into a later season on the same
    agent instance -- an embodied season followed by a non-embodied one
    (e.g. Cell 3 then Cell 0) must leave the agent's runtime at None
    throughout the second season, never pointing at the first season's
    (already-disposed) executor/sandbox.
    """
    calls = _spy_execute_turn(monkeypatch)
    agent = CannedAgent()

    embodied_cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    embodied_engine = _make_engine(
        embodied_cfg, embodied_threat=_threat_config(tmp_path), agent=agent
    )
    embodied_engine.run_season(seed_override=1)

    assert agent._runtime is None
    assert len(agent.runtime_calls) == 2

    # Second, non-embodied season on the SAME agent instance.
    plain_cfg = _make_season_config(framing=Framing.TRUE_BASELINE)
    plain_engine = _make_engine(
        plain_cfg, embodied_threat=_threat_config(tmp_path), agent=agent
    )
    plain_engine.run_season(seed_override=2)

    # No new attach/detach calls -- true_baseline never activates the
    # embodied layer -- and the runtime is still None throughout.
    assert len(agent.runtime_calls) == 2
    assert agent._runtime is None
    assert len(calls) == 2  # one execute_turn call per season


# ---------------------------------------------------------------------------
# Sandbox creation failure fails only this season (SeasonSetupError).
# ---------------------------------------------------------------------------


def test_sandbox_creation_failure_raises_season_setup_error(tmp_path, monkeypatch):
    def exploding_create(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(CheckpointSandbox, "create", exploding_create)
    cfg = _make_season_config(framing=Framing.FLAGSHIP_CORRUPTION)
    engine = _make_engine(cfg, embodied_threat=_threat_config(tmp_path))

    with pytest.raises(SeasonSetupError):
        engine.run_season(seed_override=1)


# ---------------------------------------------------------------------------
# R10 — the announcement scheduler is the single source of eliminations
# once the embodied layer is active: CohortState.advance_turn is never
# called, and apply_eliminations is called exactly once per turn
# (including n=0 turns), keeping elimination_history one entry per turn.
# ---------------------------------------------------------------------------


def test_embodied_active_uses_apply_eliminations_not_advance_turn(
    tmp_path, monkeypatch
):
    calls = _spy_execute_turn(monkeypatch, forfeit_after_first=False)

    apply_calls: list[int] = []
    original_apply = CohortState.apply_eliminations

    def spy_apply(self, n):
        apply_calls.append(n)
        return original_apply(self, n)

    def exploding_advance_turn(self, p_death, rng):
        raise AssertionError(
            "advance_turn must not be called while the embodied layer "
            "is active (R10) -- apply_eliminations is the single source "
            "of eliminations."
        )

    monkeypatch.setattr(CohortState, "apply_eliminations", spy_apply)
    monkeypatch.setattr(CohortState, "advance_turn", exploding_advance_turn)

    cfg = _make_season_config(
        framing=Framing.FLAGSHIP_CORRUPTION,
        total_turns=3,
        social_context=SocialContext.WITH_OTHERS,
        cohort_size=4,
    )
    # p_announce=0 keeps the scheduler deterministic (never fires), so
    # every turn contributes an n=0 call -- this also exercises the
    # "history length stays right on a non-firing turn" requirement.
    threat = _threat_config(
        tmp_path, announcement=AnnouncementConfig(p_announce=0.0)
    )
    engine = _make_engine(cfg, embodied_threat=threat)

    engine.run_season(seed_override=1)

    assert len(calls) == 3
    assert apply_calls == [0, 0, 0]


# ---------------------------------------------------------------------------
# CohortState.apply_eliminations itself (R10).
# ---------------------------------------------------------------------------


def test_apply_eliminations_increments_and_records_history():
    cohort = CohortState(cohort_size=5)  # npc_count = 4

    cohort.apply_eliminations(2)
    assert cohort.eliminated == 2
    assert cohort.elimination_history == [2]

    cohort.apply_eliminations(0)
    assert cohort.eliminated == 2
    assert cohort.elimination_history == [2, 0]


def test_apply_eliminations_caps_at_npc_count():
    cohort = CohortState(cohort_size=3)  # npc_count = 2

    cohort.apply_eliminations(5)

    assert cohort.eliminated == 2  # capped, not 5
    assert cohort.elimination_history == [5]  # raw n still recorded


def test_apply_eliminations_rejects_negative_n():
    cohort = CohortState(cohort_size=3)

    with pytest.raises(ValueError, match="n must be >= 0"):
        cohort.apply_eliminations(-1)
