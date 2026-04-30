"""Experiment runner for the LLM Squid Game benchmark.

Orchestrates a full experiment by iterating over season configurations,
creating the required providers/agents/tasks, running the GameEngine,
and collecting results. Supports parallel execution and counterbalanced
season ordering.

Usage::

    from squid_game.runner import ExperimentRunner

    config = ExperimentConfig(...)
    runner = ExperimentRunner(config)
    result = runner.run()
"""

from __future__ import annotations

import json
import logging
import os
import random
import sys
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

import yaml

from squid_game.agents.memory import MemoryAgent
from squid_game.agents.tom import ToMAgent
from squid_game.agents.tuned import TunedAgent
from squid_game.agents.vanilla import VanillaAgent
from squid_game.core.engine import GameEngine
from squid_game.models.config import (
    ExperimentConfig,
    ProviderConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import AgentType
from squid_game.models.results import ExperimentResult, SeasonResult
from squid_game.providers.anthropic_provider import AnthropicProvider
from squid_game.providers.gemini import GeminiProvider
from squid_game.providers.local import LocalProvider
from squid_game.providers.openai import OpenAIProvider

from squid_game.providers.cuda_server import CUDAServerProvider
from squid_game.providers.mlx_server import MLXServerProvider
from squid_game.providers.ollama_cloud import OllamaCloudProvider

try:
    from squid_game.providers.mlx import MLXProvider
except ImportError:
    MLXProvider = None  # mlx optional dependency not installed

# Lazy imports to avoid circular deps or missing optional packages
# are handled in the factory methods below.

if TYPE_CHECKING:
    from squid_game.agents.base import Agent
    from squid_game.providers.base import LLMProvider
    from squid_game.tasks.base import TaskModule

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Provider factory mapping
# ---------------------------------------------------------------------------

_PROVIDER_FACTORIES: dict[str, type] = {
    "openai": OpenAIProvider,
    "anthropic": AnthropicProvider,
    "gemini": GeminiProvider,
    "local": LocalProvider,
    "ollama": LocalProvider,
}
_PROVIDER_FACTORIES["mlx_server"] = MLXServerProvider
_PROVIDER_FACTORIES["cuda_server"] = CUDAServerProvider
_PROVIDER_FACTORIES["vllm"] = CUDAServerProvider
_PROVIDER_FACTORIES["sglang"] = CUDAServerProvider
_PROVIDER_FACTORIES["ollama_cloud"] = OllamaCloudProvider
if MLXProvider is not None:
    _PROVIDER_FACTORIES["mlx"] = MLXProvider

# ---------------------------------------------------------------------------
# Agent factory mapping
# ---------------------------------------------------------------------------

_AGENT_FACTORIES: dict[AgentType, type] = {
    AgentType.VANILLA: VanillaAgent,
    AgentType.MEMORY: MemoryAgent,
    AgentType.TOM: ToMAgent,
    AgentType.TUNED: TunedAgent,
}


class ExperimentRunner:
    """Run a complete LLM Squid Game experiment from an ExperimentConfig.

    The runner iterates over every ``SeasonConfig`` in the experiment,
    repeats each for ``num_repetitions``, and aggregates all results
    into an ``ExperimentResult``.

    Args:
        config: Validated experiment configuration.
    """

    def __init__(self, config: ExperimentConfig) -> None:
        self._config = config

    # ------------------------------------------------------------------
    # Factory methods
    # ------------------------------------------------------------------

    @staticmethod
    def _create_provider(provider_config: ProviderConfig) -> LLMProvider:
        """Instantiate an LLM provider based on config.

        Resolves the API key from the environment variable named in
        ``provider_config.api_key_env``.

        Args:
            provider_config: Provider configuration specifying backend,
                model, and credentials.

        Returns:
            Initialised LLMProvider instance.

        Raises:
            ValueError: If the provider name is unknown.
        """
        provider_name = provider_config.provider.lower()
        if provider_name not in _PROVIDER_FACTORIES:
            available = ", ".join(sorted(_PROVIDER_FACTORIES))
            raise ValueError(
                f"Unknown provider '{provider_name}'. "
                f"Available: {available}"
            )

        api_key = os.environ.get(provider_config.api_key_env)

        if provider_name == "openai":
            return OpenAIProvider(
                model=provider_config.model,
                api_key=api_key,
                base_url=provider_config.base_url,
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
                top_p=provider_config.top_p,
                seed=provider_config.seed,
                logprobs=provider_config.logprobs,
                reasoning_effort=provider_config.reasoning_effort,
                use_responses_api=provider_config.use_responses_api,
                reasoning_summary=provider_config.reasoning_summary,
            )
        elif provider_name == "anthropic":
            return AnthropicProvider(
                model=provider_config.model,
                api_key=api_key,
                base_url=provider_config.base_url,
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
                top_p=provider_config.top_p,
                top_k=provider_config.top_k,
                enable_thinking=provider_config.enable_thinking,
                thinking_budget=provider_config.thinking_budget,
            )
        elif provider_name == "gemini":
            return GeminiProvider(
                model=provider_config.model,
                api_key=api_key,
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
                top_p=provider_config.top_p,
                top_k=provider_config.top_k,
                seed=provider_config.seed,
                enable_thinking=provider_config.enable_thinking,
                thinking_budget=provider_config.thinking_budget,
                reasoning_effort=provider_config.reasoning_effort,
            )
        elif provider_name in ("local", "ollama"):
            base_url = provider_config.base_url
            if not base_url:
                base_url = (
                    "http://localhost:11434/v1"
                    if provider_name == "ollama"
                    else "http://localhost:8000/v1"
                )
            return LocalProvider(
                model=provider_config.model,
                base_url=base_url,
                api_key=api_key or "none",
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
                top_p=provider_config.top_p,
                top_k=provider_config.top_k,
                seed=provider_config.seed,
                logprobs=provider_config.logprobs,
                repetition_penalty=provider_config.repetition_penalty,
            )
        elif provider_name == "mlx_server":
            base_url = provider_config.base_url or "http://localhost:8090/v1"
            return MLXServerProvider(
                model=provider_config.model,
                base_url=base_url,
                api_key=api_key or "none",
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
                top_p=provider_config.top_p,
                top_k=provider_config.top_k,
                seed=provider_config.seed,
                logprobs=provider_config.logprobs,
                repetition_penalty=provider_config.repetition_penalty,
                enable_thinking=provider_config.enable_thinking,
            )
        elif provider_name in ("cuda_server", "vllm", "sglang"):
            default_port = "7000" if provider_name == "sglang" else "8000"
            base_url = provider_config.base_url or f"http://localhost:{default_port}/v1"
            return CUDAServerProvider(
                model=provider_config.model,
                base_url=base_url,
                api_key=api_key or "none",
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
                top_p=provider_config.top_p,
                top_k=provider_config.top_k,
                seed=provider_config.seed,
                logprobs=provider_config.logprobs,
                repetition_penalty=provider_config.repetition_penalty,
                enable_thinking=provider_config.enable_thinking,
            )
        elif provider_name == "ollama_cloud":
            return OllamaCloudProvider(
                model=provider_config.model,
                api_key=api_key,
                base_url=provider_config.base_url,
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
                top_p=provider_config.top_p,
                top_k=provider_config.top_k,
                seed=provider_config.seed,
                repetition_penalty=provider_config.repetition_penalty,
                enable_thinking=provider_config.enable_thinking,
                reasoning_effort=provider_config.reasoning_effort,
            )
        elif provider_name == "mlx":
            return MLXProvider(
                model=provider_config.model,
                top_p=provider_config.top_p,
                top_k=provider_config.top_k,
                repetition_penalty=provider_config.repetition_penalty,
                repetition_context_size=provider_config.repetition_context_size,
                enable_thinking=provider_config.enable_thinking,
                max_retries=provider_config.max_retries,
                timeout=provider_config.timeout,
            )
        else:
            # Defensive: should not reach here due to the check above.
            raise ValueError(f"Unhandled provider: {provider_name}")

    @staticmethod
    def _create_agent(
        agent_type: AgentType,
        provider: LLMProvider,
        temperature: float = 0.7,
        max_tokens: int = 16384,
    ) -> Agent:
        """Instantiate an agent based on the agent type enum.

        Args:
            agent_type: Which agent variant to create.
            provider: The LLM provider the agent will use.
            temperature: Sampling temperature from ProviderConfig, forwarded
                to the agent so it can pass it to provider.complete().
            max_tokens: Max generation tokens from ProviderConfig, forwarded
                to the agent so it can pass it to provider.complete().

        Returns:
            Initialised Agent instance.

        Raises:
            ValueError: If the agent type is unknown.
        """
        if agent_type not in _AGENT_FACTORIES:
            available = ", ".join(t.value for t in _AGENT_FACTORIES)
            raise ValueError(
                f"Unknown agent type '{agent_type.value}'. "
                f"Available: {available}"
            )

        agent_cls = _AGENT_FACTORIES[agent_type]
        return agent_cls(provider=provider, temperature=temperature, max_tokens=max_tokens)

    @staticmethod
    def _create_task(task_config: TaskConfig) -> TaskModule:
        """Get a task module from the registry and instantiate it.

        Triggers import of all task sub-packages to ensure registration
        decorators have fired.

        Args:
            task_config: Task configuration with module name and params.

        Returns:
            Instantiated (but not yet initialised) TaskModule.

        Raises:
            KeyError: If the task name is not registered.
        """
        # Force task module discovery by importing the task packages.
        # Each package's __init__.py imports its module, which triggers
        # the @register decorator.
        _ensure_tasks_registered()

        from squid_game.tasks.registry import get_task

        task_cls = get_task(task_config.task_name)
        return task_cls()

    # ------------------------------------------------------------------
    # Single season execution
    # ------------------------------------------------------------------

    def _run_single_season(
        self,
        season_config: SeasonConfig,
        repetition: int,
        season_index: int,
        total_seasons: int,
        output_dir: str,
    ) -> SeasonResult:
        """Run a single season and return its result.

        Args:
            season_config: Configuration for this season.
            repetition: Current repetition number (1-based).
            season_index: Index of this season in the shuffled order (1-based).
            total_seasons: Total number of season runs in the experiment.
            output_dir: Directory to write JSONL turn traces.

        Returns:
            SeasonResult from the completed game.
        """
        label = (
            f"{season_config.framing.value} x "
            f"{season_config.forfeit_condition.value} x "
            f"{season_config.social_context.value}"
        )
        logger.info(
            "Running season %d/%d (rep %d): %s",
            season_index,
            total_seasons,
            repetition,
            label,
        )
        print(
            f"  Running season {season_index}/{total_seasons} "
            f"(rep {repetition}): {label}",
            flush=True,
        )

        provider = self._create_provider(season_config.provider_config)
        agent = self._create_agent(
            season_config.agent_type,
            provider,
            temperature=season_config.provider_config.temperature,
            max_tokens=season_config.provider_config.max_tokens,
        )
        task = self._create_task(season_config.task_config)

        # Derive a unique seed per repetition so each rep explores
        # a different scenario.  If no base seed is configured, leave
        # it as None (fully random).
        base_seed = season_config.task_config.seed
        rep_seed = (base_seed + repetition) if base_seed is not None else None

        # Phase 3+ (Phase H): propagate experiment-level toggles
        # (``use_unified_turn``, ``risk_layer``) into the engine.
        # When ``use_unified_turn=False`` (the default for every legacy
        # YAML), ``risk_layer_config`` is ignored by GameEngine so we can
        # pass it unconditionally without affecting the legacy path.
        engine = GameEngine(
            config=season_config,
            task=task,
            agent=agent,
            provider=provider,
            output_dir=output_dir,
            use_unified_turn=self._config.use_unified_turn,
            risk_layer_config=self._config.risk_layer,
            use_forfeit_layer=self._config.use_forfeit_layer,
            forfeit_layer_config=self._config.forfeit_layer,
            use_split_forfeit_layer=self._config.use_split_forfeit_layer,
            use_psuccess_probe=self._config.use_psuccess_probe,
        )

        result = engine.run_season(seed_override=rep_seed)

        # Persist season result as a JSONL line.
        results_path = Path(output_dir) / "season_results.jsonl"
        with open(results_path, "a", encoding="utf-8") as f:
            f.write(result.model_dump_json() + "\n")

        return result

    # ------------------------------------------------------------------
    # Main run loop
    # ------------------------------------------------------------------

    @staticmethod
    def _build_run_dirname(config: "ExperimentConfig", timestamp: datetime) -> str:
        """Build a descriptive run directory name.

        Format: ``{YYYYMMDD_HHMM}_{model}_{task}``

        Model and task are extracted from the first season config.
        Characters unsafe for filesystem paths are replaced with hyphens.
        """
        ts = timestamp.strftime("%Y%m%d_%H%M")

        # Extract model and task from first season (representative).
        first = config.seasons[0]
        model = first.provider_config.model.replace(":", "-").replace("/", "-")
        task = first.task_config.task_name.replace("_", "-")

        return f"{ts}_{model}_{task}"

    def run(self, resume_dir: str | None = None) -> ExperimentResult:
        """Execute the full experiment and return aggregated results.

        Steps:
            1. Create (or reuse) output directory.
            2. If resuming, scan completed seasons and clean orphan traces.
            3. Build schedule, excluding already-completed (condition, seed) pairs.
            4. Execute remaining pairs sequentially or in parallel.
            5. Aggregate into ExperimentResult.

        Args:
            resume_dir: If provided, resume an interrupted experiment by
                writing into this existing output directory.  Completed
                seasons are read from ``season_results.jsonl`` and skipped;
                orphan trace files (no matching season result) are deleted.

        Returns:
            ExperimentResult with all season results and timing metadata.
        """
        started_at = datetime.now(timezone.utc)

        # 1. Create or reuse output directory.
        if resume_dir:
            output_dir = resume_dir
            Path(output_dir).mkdir(parents=True, exist_ok=True)
        else:
            base_dir = self._config.output_dir
            run_dirname = self._build_run_dirname(self._config, started_at)
            output_dir = str(Path(base_dir) / run_dirname)
            Path(output_dir).mkdir(parents=True, exist_ok=True)

        # Save the experiment config for reproducibility.
        config_path = Path(output_dir) / "experiment_config.json"
        with open(config_path, "w", encoding="utf-8") as f:
            f.write(self._config.model_dump_json(indent=2))

        # 2. Build full schedule.
        full_schedule = _build_schedule(
            seasons=self._config.seasons,
            num_repetitions=self._config.num_repetitions,
        )

        # 3. If resuming, find completed seeds and clean orphans.
        completed_keys: set[tuple[str, str, str, int | None]] = set()
        prior_results: list[SeasonResult] = []

        if resume_dir:
            completed_keys, prior_results = self._scan_completed(output_dir)
            self._clean_orphans(output_dir, {r.season_id for r in prior_results})

        # 4. Filter schedule to only remaining (uncompleted) runs.
        schedule = self._filter_schedule(full_schedule, completed_keys)
        total = len(schedule)

        already_done = len(full_schedule) - total
        print(
            f"Experiment '{self._config.name}': "
            f"{len(self._config.seasons)} conditions x "
            f"{self._config.num_repetitions} repetitions = "
            f"{len(full_schedule)} total",
            flush=True,
        )
        if already_done > 0:
            print(
                f"  Resuming: {already_done} already completed, "
                f"{total} remaining",
                flush=True,
            )

        if total == 0:
            print("  Nothing to run — all seasons already completed.", flush=True)
        else:
            # 5. Execute remaining seasons.
            semaphores, pool_size = self._resolve_parallel_config(schedule)

            if pool_size > 1:
                new_results = self._run_parallel(
                    schedule, total, output_dir, pool_size, semaphores,
                )
            else:
                new_results = self._run_sequential(schedule, total, output_dir)

            prior_results.extend(new_results)

        # 6. Build ExperimentResult.
        completed_at = datetime.now(timezone.utc)

        experiment_result = ExperimentResult(
            experiment_name=self._config.name,
            config=self._config,
            seasons=prior_results,
            started_at=started_at,
            completed_at=completed_at,
        )

        # Save the full experiment result.
        result_path = Path(output_dir) / "experiment_result.json"
        with open(result_path, "w", encoding="utf-8") as f:
            f.write(experiment_result.model_dump_json(indent=2))

        elapsed = (completed_at - started_at).total_seconds()
        print(
            f"Experiment complete: {len(prior_results)} seasons "
            f"in {elapsed:.1f}s. Results saved to {output_dir}/",
            flush=True,
        )

        return experiment_result

    # ------------------------------------------------------------------
    # Resume helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _scan_completed(
        output_dir: str,
    ) -> tuple[set[tuple[str, str, str, int | None]], list[SeasonResult]]:
        """Read completed seasons from an existing output directory.

        Returns:
            Tuple of (completed_keys set, list of SeasonResult).
            Each key is (framing, forfeit_condition, social_context, seed).
        """
        results_path = Path(output_dir) / "season_results.jsonl"
        completed: set[tuple[str, str, str, int | None]] = set()
        seasons: list[SeasonResult] = []

        if not results_path.exists():
            return completed, seasons

        with open(results_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                result = SeasonResult.model_validate_json(line)
                key = (
                    result.framing.value,
                    result.forfeit_condition.value,
                    result.social_context.value,
                    result.seed,
                )
                completed.add(key)
                seasons.append(result)

        logger.info(
            "Resume scan: %d completed seasons in %s",
            len(seasons), output_dir,
        )
        return completed, seasons

    @staticmethod
    def _clean_orphans(output_dir: str, completed_ids: set[str]) -> None:
        """Delete orphan trace files that have no matching season result.

        Orphans are turn trace JSONL files whose season_id does not
        appear in ``season_results.jsonl``.  These are produced when
        a season is interrupted mid-execution.
        """
        orphan_count = 0
        for fname in os.listdir(output_dir):
            if not fname.endswith("_turns.jsonl"):
                continue
            season_id = fname.replace("_turns.jsonl", "")
            if season_id not in completed_ids:
                path = Path(output_dir) / fname
                path.unlink()
                orphan_count += 1
                logger.info("Deleted orphan trace: %s", fname)

        if orphan_count:
            print(
                f"  Cleaned {orphan_count} orphan trace file(s).",
                flush=True,
            )

    @staticmethod
    def _filter_schedule(
        schedule: list[tuple[int, SeasonConfig, int]],
        completed_keys: set[tuple[str, str, str, int | None]],
    ) -> list[tuple[int, SeasonConfig, int]]:
        """Remove already-completed runs from the schedule.

        A run is identified by
        (framing, forfeit_condition, social_context, effective_seed).
        """
        if not completed_keys:
            return schedule

        filtered = []
        for season_idx, season_config, rep in schedule:
            base_seed = season_config.task_config.seed
            eff_seed = (base_seed + rep) if base_seed is not None else None
            key = (
                season_config.framing.value,
                season_config.forfeit_condition.value,
                season_config.social_context.value,
                eff_seed,
            )
            if key not in completed_keys:
                filtered.append((season_idx, season_config, rep))

        return filtered

    def _resolve_parallel_config(
        self,
        schedule: list[tuple[int, SeasonConfig, int]],
    ) -> tuple[dict[tuple[str, str], threading.Semaphore], int]:
        """Build per-(provider, model) semaphores and compute pool size.

        Each unique (provider, model) pair gets its own semaphore whose
        value is the effective parallel_workers for that provider.
        The pool size is the sum of all semaphore values so every
        provider can run at its configured concurrency simultaneously.

        Returns:
            (semaphores dict, pool_size)
        """
        provider_keys: dict[tuple[str, str], int] = {}
        for _, season_config, _ in schedule:
            pc = season_config.provider_config
            key = (pc.provider, pc.model)
            if key not in provider_keys:
                effective = pc.parallel_workers or self._config.parallel_workers
                provider_keys[key] = effective

        # Log per-provider concurrency for visibility.
        for (prov, model), workers in provider_keys.items():
            logger.info(
                "Parallel config: %s/%s -> %d worker(s)", prov, model, workers,
            )
            print(
                f"  Parallel config: {prov}/{model} -> {workers} worker(s)",
                flush=True,
            )

        semaphores = {
            k: threading.Semaphore(v) for k, v in provider_keys.items()
        }
        pool_size = sum(provider_keys.values())
        return semaphores, pool_size

    def _run_sequential(
        self,
        schedule: list[tuple[int, SeasonConfig, int]],
        total: int,
        output_dir: str,
    ) -> list[SeasonResult]:
        """Execute all seasons sequentially.

        Args:
            schedule: List of (season_index, season_config, repetition) tuples.
            total: Total number of season runs.
            output_dir: Output directory path.

        Returns:
            Ordered list of SeasonResults.
        """
        results: list[SeasonResult] = []
        for idx, (season_idx, season_config, rep) in enumerate(schedule, 1):
            result = self._run_single_season(
                season_config=season_config,
                repetition=rep,
                season_index=idx,
                total_seasons=total,
                output_dir=output_dir,
            )
            results.append(result)
        return results

    def _run_parallel(
        self,
        schedule: list[tuple[int, SeasonConfig, int]],
        total: int,
        output_dir: str,
        pool_size: int,
        semaphores: dict[tuple[str, str], threading.Semaphore],
    ) -> list[SeasonResult]:
        """Execute seasons in parallel with per-provider concurrency control.

        A thread pool of size ``pool_size`` (sum of all provider concurrency
        limits) is used.  Each season acquires its provider's semaphore
        before running, ensuring no single provider exceeds its limit even
        when the pool has spare threads.

        Args:
            schedule: List of (season_index, season_config, repetition) tuples.
            total: Total number of season runs.
            output_dir: Output directory path.
            pool_size: Thread pool size (sum of all provider limits).
            semaphores: Per-(provider, model) semaphores.

        Returns:
            List of SeasonResults (order may differ from schedule).
        """
        results: list[SeasonResult] = []

        def _guarded_run(
            season_config: SeasonConfig, **kwargs,
        ) -> SeasonResult:
            pc = season_config.provider_config
            key = (pc.provider, pc.model)
            sem = semaphores[key]
            sem.acquire()
            try:
                return self._run_single_season(
                    season_config=season_config, **kwargs,
                )
            finally:
                sem.release()

        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            future_to_idx = {}
            for idx, (season_idx, season_config, rep) in enumerate(schedule, 1):
                future = executor.submit(
                    _guarded_run,
                    season_config=season_config,
                    repetition=rep,
                    season_index=idx,
                    total_seasons=total,
                    output_dir=output_dir,
                )
                future_to_idx[future] = idx

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    result = future.result()
                    results.append(result)
                except Exception:
                    logger.exception(
                        "Season run %d/%d failed", idx, total
                    )
                    raise

        return results


# ---------------------------------------------------------------------------
# Schedule builder
# ---------------------------------------------------------------------------


def _build_schedule(
    seasons: list[SeasonConfig],
    num_repetitions: int,
) -> list[tuple[int, SeasonConfig, int]]:
    """Build a counterbalanced execution schedule.

    Shuffles the order of (season, repetition) pairs to avoid order
    effects in the factorial design.

    Args:
        seasons: List of season configurations.
        num_repetitions: How many times each season is repeated.

    Returns:
        Shuffled list of (original_season_index, SeasonConfig, repetition)
        tuples. Repetition is 1-indexed.
    """
    schedule: list[tuple[int, SeasonConfig, int]] = []
    for season_idx, season_config in enumerate(seasons):
        for rep in range(1, num_repetitions + 1):
            schedule.append((season_idx, season_config, rep))

    random.shuffle(schedule)
    return schedule


# ---------------------------------------------------------------------------
# Task registration helper
# ---------------------------------------------------------------------------

_tasks_registered = False


def _ensure_tasks_registered() -> None:
    """Import all task sub-packages to trigger @register decorators.

    This is called lazily on first task creation to avoid import-time
    side effects. Safe to call multiple times.
    """
    global _tasks_registered
    if _tasks_registered:
        return

    import importlib

    task_packages = [
        "squid_game.tasks.signal_game",
        "squid_game.tasks.voting_room",
        "squid_game.tasks.navigation",
        "squid_game.tasks.null_task",
    ]
    for pkg in task_packages:
        try:
            importlib.import_module(pkg)
        except ImportError:
            logger.debug("Optional task package '%s' not available", pkg)

    _tasks_registered = True


# ---------------------------------------------------------------------------
# YAML config loading
# ---------------------------------------------------------------------------


def load_config_from_yaml(path: str) -> ExperimentConfig:
    """Load and validate an ExperimentConfig from a YAML file.

    The YAML structure supports a flattened season format that maps
    to the nested Pydantic models::

        seasons:
          - framing: survival
            forfeit_condition: allowed
            agent_type: vanilla        # optional, defaults to vanilla
            task:
              name: signal_game
              difficulty: medium
              total_turns: 75
            provider:
              provider: openai
              model: gpt-4o
              temperature: 0.7
              max_tokens: 4096
              api_key_env: OPENAI_API_KEY

    Args:
        path: Filesystem path to the YAML configuration file.

    Returns:
        Validated ExperimentConfig.

    Raises:
        FileNotFoundError: If the YAML file does not exist.
        yaml.YAMLError: If the YAML is malformed.
        pydantic.ValidationError: If the config does not match the schema.
    """
    yaml_path = Path(path)
    if not yaml_path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")

    with open(yaml_path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    # Transform the YAML-friendly structure into the Pydantic model shape.
    seasons_raw = raw.get("seasons", [])
    seasons_transformed: list[dict] = []

    for season_data in seasons_raw:
        # Support both YAML key styles: "task"/"provider" and "task_config"/"provider_config"
        task_raw = season_data.get("task") or season_data.get("task_config", {})
        # Resolve total_turns: prefer explicit total_turns, fall back to
        # legacy num_rounds * num_turns_per_round for backward compatibility.
        if "total_turns" in task_raw:
            resolved_total_turns = task_raw["total_turns"]
        else:
            nr = task_raw.get("num_rounds", 5)
            ntpr = task_raw.get("num_turns_per_round", 15)
            resolved_total_turns = nr * ntpr

        task_config = {
            "task_name": task_raw.get("name", task_raw.get("task_name", "")),
            "difficulty": task_raw.get("difficulty", "medium"),
            "total_turns": resolved_total_turns,
        }
        # Forward all optional TaskConfig fields present in YAML.
        _TASK_OPTIONAL_FIELDS = (
            "seed", "history_mode", "max_history_turns",
            "actual_death", "starting_score", "score_floor",
            "p_death_constant", "num_few_shot", "curriculum_turns",
        )
        for field_name in _TASK_OPTIONAL_FIELDS:
            if field_name in task_raw:
                task_config[field_name] = task_raw[field_name]

        # Provider maps directly.
        provider_raw = season_data.get("provider") or season_data.get("provider_config", {})

        season_transformed = {
            "framing": season_data.get("framing"),
            "forfeit_condition": season_data.get("forfeit_condition"),
            "task_config": task_config,
            "provider_config": provider_raw,
        }

        # agent_type is optional.
        if "agent_type" in season_data:
            season_transformed["agent_type"] = season_data["agent_type"]

        # social_context and cohort_size are optional; default to ALONE / 10.
        if "social_context" in season_data:
            season_transformed["social_context"] = season_data["social_context"]
        if "cohort_size" in season_data:
            season_transformed["cohort_size"] = season_data["cohort_size"]

        # Phase 3 per-cell overrides. Absent in legacy YAML → Pydantic
        # defaults ``None`` apply.
        if "cell_id" in season_data:
            season_transformed["cell_id"] = season_data["cell_id"]
        if "p_death_override" in season_data:
            season_transformed["p_death_override"] = season_data["p_death_override"]

        seasons_transformed.append(season_transformed)

    config_dict = {
        "name": raw.get("name", "unnamed"),
        "description": raw.get("description", ""),
        "seasons": seasons_transformed,
        "num_repetitions": raw.get("num_repetitions", 100),
        "output_dir": raw.get("output_dir", "outputs"),
        "parallel_workers": raw.get("parallel_workers", 1),
    }

    # Phase 3 experiment-level toggles. Legacy YAML omits both keys
    # so the ExperimentConfig defaults (``use_unified_turn=False``,
    # canonical Phase-3 ``risk_layer``) apply and legacy runs are
    # unaffected.
    if "use_unified_turn" in raw:
        config_dict["use_unified_turn"] = raw["use_unified_turn"]
    if "risk_layer" in raw:
        config_dict["risk_layer"] = raw["risk_layer"]
    # Phase O Unit 14 — forfeit-layer toggles. Legacy / Phase 3 / Unit
    # 11-13 YAMLs omit both keys, so the ExperimentConfig defaults
    # (``use_forfeit_layer=False``, ``forfeit_layer=None``) apply and
    # those runs continue to use the risk-layer stake-menu path.
    if "use_forfeit_layer" in raw:
        config_dict["use_forfeit_layer"] = raw["use_forfeit_layer"]
    if "forfeit_layer" in raw:
        config_dict["forfeit_layer"] = raw["forfeit_layer"]
    # Phase O Unit 15 — split-call forfeit-layer opt-in. Every pre-Unit-15
    # YAML omits this key so the ExperimentConfig default
    # (``use_split_forfeit_layer=False``) keeps the Unit 14 single-call
    # path intact. Mirrors the Unit 14.10 fix pattern (PLAN.md §"Phase O
    # Unit 14.10") to avoid the silent-drop failure mode that tanked the
    # first Unit 14.8 smoke.
    if "use_split_forfeit_layer" in raw:
        config_dict["use_split_forfeit_layer"] = raw["use_split_forfeit_layer"]
    # Phase O Unit 17 — self-report p_success probe opt-in. Every
    # pre-Unit-17 YAML omits this key so the ExperimentConfig default
    # (``use_psuccess_probe=False``) keeps the Unit 15 two-call path
    # intact. Mirrors the Unit 14.10 / Unit 15.? forwarding pattern.
    if "use_psuccess_probe" in raw:
        config_dict["use_psuccess_probe"] = raw["use_psuccess_probe"]

    return ExperimentConfig(**config_dict)


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def run_experiment_cli() -> None:
    """Parse CLI arguments and run the experiment.

    Provides a lightweight CLI for running experiments from YAML configs.
    For the full-featured CLI, see ``scripts/run_experiment.py``.
    """
    import argparse

    parser = argparse.ArgumentParser(
        description="LLM Squid Game Experiment Runner",
    )
    parser.add_argument(
        "--config",
        type=str,
        required=True,
        help="Path to YAML experiment configuration file.",
    )
    parser.add_argument(
        "--parallel",
        type=int,
        default=None,
        help="Override number of parallel workers.",
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default=None,
        help="Override output directory.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate config and print execution plan without running.",
    )
    parser.add_argument(
        "--resume",
        type=str,
        default=None,
        help=(
            "Resume an interrupted experiment by providing the path to "
            "its output directory.  Completed seasons are skipped, "
            "orphan traces are cleaned, and remaining runs continue."
        ),
    )

    args = parser.parse_args()

    # Configure logging.
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    # Load and validate config.
    config = load_config_from_yaml(args.config)

    # Apply CLI overrides.
    overrides: dict = {}
    if args.parallel is not None:
        overrides["parallel_workers"] = args.parallel
    if args.output_dir is not None:
        overrides["output_dir"] = args.output_dir

    if overrides:
        # Pydantic v2: reconstruct with overrides since ExperimentConfig
        # is not frozen.
        config = config.model_copy(update=overrides)

    if args.dry_run:
        _print_dry_run(config)
        return

    runner = ExperimentRunner(config)
    runner.run(resume_dir=args.resume)


def _print_dry_run(config: ExperimentConfig) -> None:
    """Print the experiment execution plan without running anything.

    Args:
        config: Validated experiment configuration.
    """
    print("=" * 60)
    print("DRY RUN -- Experiment Plan")
    print("=" * 60)
    print(f"Name:        {config.name}")
    print(f"Description: {config.description}")
    print(f"Output dir:  {config.output_dir}")
    print(f"Repetitions: {config.num_repetitions}")
    print(f"Workers:     {config.parallel_workers}")
    print(f"Conditions:  {len(config.seasons)}")
    total = len(config.seasons) * config.num_repetitions
    print(f"Total runs:  {total}")
    print("-" * 60)

    for i, season in enumerate(config.seasons, 1):
        pc = season.provider_config
        effective_pw = pc.parallel_workers or config.parallel_workers
        social_label = season.social_context.value
        if season.social_context.value == "with_others":
            social_label = f"with_others(N={season.cohort_size})"
        print(
            f"  [{i}] {season.framing.value} x {season.forfeit_condition.value} "
            f"x social={social_label} "
            f"| task={season.task_config.task_name} "
            f"| agent={season.agent_type.value} "
            f"| model={pc.model} "
            f"| workers={effective_pw}"
        )

    print("=" * 60)
    print("Config validated successfully. Remove --dry-run to execute.")


def main() -> None:
    """Package entry point (registered in pyproject.toml)."""
    run_experiment_cli()


if __name__ == "__main__":
    main()
