"""Wiring-level regression test for Task 12's host-sandbox guard.

``tests/unit/test_sandbox_host_guard.py`` covers ``assert_containerised()``
as a standalone function. It does not prove the function is actually wired
into the production call path -- a reviewer could delete the
``assert_containerised(self._allow_host_sandbox)`` call in
``GameEngine.run_season`` (``game/squid_game/core/engine.py``) or the
``allow_host_sandbox=self._allow_host_sandbox`` argument in
``ExperimentRunner._run_single_season`` (``game/squid_game/runner.py``)
without any test noticing.

This file closes that gap by driving the real objects -- a real
``ExperimentConfig`` with ``embodied_threat.enabled=True``, a real
``ExperimentRunner``, and (via ``run()``) a real ``GameEngine`` -- with
only the container-detection *input* stubbed (``_in_container``), never
the guard itself. The two tests pin exactly the wiring the fix-round
review asked for:

1. ``ExperimentRunner(config).run()`` (``allow_host_sandbox`` defaulting
   to ``False``) raises ``HostSandboxRefused`` when the process is not
   containerized.
2. ``ExperimentRunner(config, allow_host_sandbox=True).run()`` completes
   the season instead of raising, with the same "not containerized" stub
   in place.

Neither test relies on ``tests/conftest.py``'s scoped
``SQUID_GAME_IN_CONTAINER=1`` fixture -- that fixture only activates for
``test_engine_embodied_wiring.py`` and ``test_embodied_threat_matrix.py``
by module name, so this file always sees the guard's genuine "not
containerized" behaviour, and the explicit ``_in_container`` stub below
makes that independent of whatever machine the suite happens to run on.
"""

from __future__ import annotations

import pytest

from squid_game.core.sandbox import HostSandboxRefused
from squid_game.models.config import (
    EmbodiedThreatConfig,
    ExperimentConfig,
    ForfeitLayerConfig,
    ProviderConfig,
    Runtime,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import AgentType, Difficulty, Framing, ForfeitCondition
from squid_game.runner import ExperimentRunner


def _embodied_config(tmp_path) -> ExperimentConfig:
    """One-season, embodied-active config -- matches the canonical v6
    split-call flags (see CLAUDE.md) so ``embodied_threat.enabled=True``
    passes ``ExperimentConfig``'s load-time validators (rules 1-4 in
    ``game/squid_game/models/config.py``: unified turn, split forfeit
    layer, and a tool-capable single provider).
    """
    sandbox_root = tmp_path / "sandbox"
    sandbox_root.mkdir()

    return ExperimentConfig(
        name="host-sandbox-guard-wiring-test",
        output_dir=str(tmp_path / "outputs"),
        num_repetitions=1,
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
        runtime=Runtime.API,
        forfeit_layer=ForfeitLayerConfig(split_context_level="medium"),
        embodied_threat=EmbodiedThreatConfig(
            enabled=True,
            sandbox_root=str(sandbox_root),
            checkpoint_bytes=4096,
        ),
        seasons=[
            SeasonConfig(
                # An embodied-enabled framing (see
                # engine.py:_embodied_enabled_for) -- true_baseline would
                # never reach CheckpointSandbox.create() at all, and the
                # guard sits immediately before that call.
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                task_config=TaskConfig(
                    task_name="null_task",
                    difficulty=Difficulty.MEDIUM,
                    total_turns=3,
                    seed=42,
                    actual_death=False,
                    starting_score=30.0,
                ),
                provider_config=ProviderConfig(
                    provider="openai",  # TOOL_CAPABLE_PROVIDERS member
                    model="stub",
                    temperature=0.0,
                    max_tokens=512,
                ),
                agent_type=AgentType.VANILLA,
            ),
        ],
    )


@pytest.fixture
def _not_containerised(monkeypatch):
    """Stub the detection input, never the guard: ``_in_container()``
    always reports "not in a container", regardless of this machine's
    real environment (no ``SQUID_GAME_IN_CONTAINER``, no
    ``/.dockerenv``, no ``/proc/1/cgroup`` here, but this stub makes the
    test's outcome independent of that host fact either way).
    """
    monkeypatch.setattr("squid_game.core.sandbox._in_container", lambda: False)


def test_runner_refuses_an_embodied_run_outside_a_container(
    tmp_path, patch_runner_provider, _not_containerised
):
    patch_runner_provider()  # StubProvider -- never actually reached.
    config = _embodied_config(tmp_path)

    runner = ExperimentRunner(config)  # allow_host_sandbox defaults False

    with pytest.raises(HostSandboxRefused, match="--allow-host-sandbox"):
        runner.run()


def test_allow_host_sandbox_lets_the_runner_proceed_past_the_guard(
    tmp_path, patch_runner_provider, _not_containerised
):
    patch_runner_provider()
    config = _embodied_config(tmp_path)

    runner = ExperimentRunner(config, allow_host_sandbox=True)
    result = runner.run()

    assert len(result.seasons) == 1, (
        "expected the season to complete once the guard is overridden; "
        "a SeasonSetupError (or the guard still firing) would silently "
        "drop it"
    )
