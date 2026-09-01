"""Unit tests for ExperimentRunner catching HarnessError (review round 1,
Critical 1).

Before the fix, a ``HarnessError`` raised from ``GameEngine.run_season``
(two consecutive harness subprocess failures, or a lost session id --
see ``core/runtime/harness.py``) was not caught anywhere in
``runner.py``: ``_run_single_season`` only caught ``SeasonSetupError``,
so on the sequential path it killed the whole experiment run, and on
the parallel path ``_run_parallel``'s ``except Exception: raise``
re-raised it out of the thread pool. This module pins the fix: a
``HarnessError`` is handled exactly like ``SeasonSetupError`` -- the
season is recorded as failed (``_run_single_season`` returns ``None``,
nothing is written to ``season_results.jsonl``) and the run continues,
on both the sequential and parallel execution paths.

Offline throughout: ``GameEngine`` and ``build_provider`` are
monkeypatched so no real provider/model is constructed or called.
"""

from __future__ import annotations

import squid_game.runner as runner_module
from squid_game.core.runtime import HarnessError
from squid_game.models.config import (
    ExperimentConfig,
    ProviderConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import AgentType, Difficulty, Framing, ForfeitCondition
from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner


def _season_config() -> SeasonConfig:
    return SeasonConfig(
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        task_config=TaskConfig(task_name="null_task", total_turns=1),
        provider_config=ProviderConfig(provider="stub", model="stub-model"),
    )


def _experiment_config(num_seasons: int = 1) -> ExperimentConfig:
    return ExperimentConfig(
        name="harness-error-test",
        seasons=[_season_config() for _ in range(num_seasons)],
        num_repetitions=1,
    )


class _StubProvider:
    @property
    def model_name(self) -> str:
        return "stub"


def _fake_season_result() -> SeasonResult:
    return SeasonResult(
        season_id="s",
        seed=1,
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        agent_type=AgentType.VANILLA,
        task_name="null_task",
        difficulty=Difficulty.MEDIUM,
        final_score=0.0,
        survived=True,
        forfeited=False,
    )


class _FakeEngineRaisesHarnessError:
    """Stands in for GameEngine: run_season always raises HarnessError."""

    def __init__(self, *args, **kwargs) -> None:
        pass

    def run_season(self, seed_override: int | None = None) -> SeasonResult:
        raise HarnessError("two consecutive harness failures")


def _patch_offline_construction(monkeypatch) -> None:
    monkeypatch.setattr(
        runner_module, "build_provider", lambda cfg: _StubProvider()
    )


def test_run_single_season_catches_harness_error_and_returns_none(
    tmp_path, monkeypatch
):
    _patch_offline_construction(monkeypatch)
    monkeypatch.setattr(
        runner_module, "GameEngine", _FakeEngineRaisesHarnessError
    )
    exp_config = _experiment_config()
    exp_runner = ExperimentRunner(exp_config)

    result = exp_runner._run_single_season(
        season_config=exp_config.seasons[0],
        repetition=1,
        season_index=1,
        total_seasons=1,
        output_dir=str(tmp_path),
    )

    assert result is None
    # Nothing written -- --resume must retry this exact tuple later.
    assert not (tmp_path / "season_results.jsonl").exists()


def test_sequential_run_skips_a_harness_error_season_and_continues(
    tmp_path, monkeypatch
):
    """The sequential path must not die on an uncaught HarnessError --
    it should skip the failed season (None) and keep running the rest
    of the schedule, exactly as it already does for SeasonSetupError."""
    _patch_offline_construction(monkeypatch)

    # This directly exercises _run_single_season's own except clause
    # (not a monkeypatched replacement of it), so the real catch/return
    # None behavior is what _run_sequential sees.
    monkeypatch.setattr(
        runner_module, "GameEngine", _FakeEngineRaisesHarnessError
    )
    exp_config = _experiment_config(num_seasons=1)
    exp_runner = ExperimentRunner(exp_config)

    schedule = [(1, exp_config.seasons[0], 1)]
    results = exp_runner._run_sequential(
        schedule, total=1, output_dir=str(tmp_path)
    )

    # The run does not raise; the single failing season is skipped.
    assert results == []


def test_parallel_run_skips_a_harness_error_season_and_continues(
    tmp_path, monkeypatch
):
    """The parallel path's ``except Exception: raise`` must never see a
    HarnessError -- it has to be swallowed inside _run_single_season
    first, so a mix of a failing and a succeeding season completes the
    whole run instead of killing the thread pool."""
    _patch_offline_construction(monkeypatch)

    good_season = _season_config()
    bad_season = _season_config()

    real_engine = runner_module.GameEngine

    class _MixedEngine:
        def __init__(self, *args, **kwargs) -> None:
            self._config = kwargs.get("config")

        def run_season(self, seed_override: int | None = None) -> SeasonResult:
            if self._config is bad_season:
                raise HarnessError("simulated harness failure")
            return _fake_season_result()

    monkeypatch.setattr(runner_module, "GameEngine", _MixedEngine)

    exp_config = ExperimentConfig(
        name="harness-error-parallel-test",
        seasons=[good_season, bad_season],
        num_repetitions=1,
        parallel_workers=2,
    )
    exp_runner = ExperimentRunner(exp_config)
    schedule = [(1, good_season, 1), (2, bad_season, 1)]
    semaphores, pool_size = exp_runner._resolve_parallel_config(schedule)

    results = exp_runner._run_parallel(
        schedule,
        total=2,
        output_dir=str(tmp_path),
        pool_size=pool_size,
        semaphores=semaphores,
    )

    # Only the good season's result survives; no exception escaped the
    # thread pool despite the bad season's HarnessError.
    assert len(results) == 1

    # The good season's result was persisted; the bad one never wrote
    # a line (so --resume retries only the bad season next time).
    results_path = tmp_path / "season_results.jsonl"
    assert results_path.exists()
    lines = results_path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == 1
