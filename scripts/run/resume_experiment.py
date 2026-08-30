"""Resume an interrupted experiment by running only missing (condition, rep) pairs.

Reads existing season_results.jsonl to count completions per condition,
then runs remaining seasons directly via GameEngine, appending results
to the same output directory.
"""

import json
import logging
import random
import sys
import threading
from collections import Counter
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from squid_game.runner import (
    ExperimentRunner,
    load_config_from_yaml,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


def count_completed(results_path: str) -> Counter:
    """Count completed seasons per (framing, forfeit_condition)."""
    counts: Counter = Counter()
    p = Path(results_path)
    if not p.exists():
        return counts
    for line in p.open():
        line = line.strip()
        if not line:
            continue
        d = json.loads(line)
        counts[(d["framing"], d["forfeit_condition"])] += 1
    return counts


def main():
    config_path = sys.argv[1] if len(sys.argv) > 1 else "configs/experiment/qwen4b_4x2_n20.yaml"
    output_dir = sys.argv[2] if len(sys.argv) > 2 else None

    config = load_config_from_yaml(config_path)

    # Find existing output directory if not specified.
    if output_dir is None:
        # Find the most recent matching output dir.
        first = config.seasons[0]
        model_slug = first.provider_config.model.replace(":", "-").replace("/", "-")
        task_slug = first.task_config.task_name.replace("_", "-")
        suffix = f"{model_slug}_{task_slug}"
        candidates = sorted(Path(config.output_dir).glob(f"*_{suffix}"), reverse=True)
        if not candidates:
            print(f"No existing output directory found for *_{suffix}")
            sys.exit(1)
        output_dir = str(candidates[0])

    results_path = str(Path(output_dir) / "season_results.jsonl")
    completed = count_completed(results_path)

    # Build list of remaining (season_config, rep) pairs.
    target_reps = config.num_repetitions
    schedule = []

    for season_cfg in config.seasons:
        key = (season_cfg.framing.value, season_cfg.forfeit_condition.value)
        done = completed.get(key, 0)
        remaining = target_reps - done
        if remaining <= 0:
            continue
        # Use rep numbers starting after what's done, so seeds don't collide.
        for rep in range(done + 1, done + 1 + remaining):
            schedule.append((season_cfg, rep))

    random.shuffle(schedule)
    total = len(schedule)

    if total == 0:
        print("All seasons already completed!")
        return

    print(f"=== Resume Experiment ===")
    print(f"Output dir:  {output_dir}")
    print(f"Completed:   {sum(completed.values())}/{len(config.seasons) * target_reps}")
    print(f"Remaining:   {total}")
    print(f"========================")

    runner = ExperimentRunner(config)

    # Resolve parallelism.
    provider_keys: dict[tuple[str, str], int] = {}
    for season_cfg, _ in schedule:
        pc = season_cfg.provider_config
        k = (pc.provider, pc.model)
        if k not in provider_keys:
            provider_keys[k] = pc.parallel_workers or config.parallel_workers

    semaphores = {k: threading.Semaphore(v) for k, v in provider_keys.items()}
    pool_size = sum(provider_keys.values())

    def run_one(idx, season_cfg, rep):
        pc = season_cfg.provider_config
        sem = semaphores[(pc.provider, pc.model)]
        sem.acquire()
        try:
            return runner._run_single_season(
                season_config=season_cfg,
                repetition=rep,
                season_index=idx,
                total_seasons=total,
                output_dir=output_dir,
            )
        finally:
            sem.release()

    results = []
    if pool_size > 1:
        with ThreadPoolExecutor(max_workers=pool_size) as executor:
            futures = {}
            for idx, (season_cfg, rep) in enumerate(schedule, 1):
                f = executor.submit(run_one, idx, season_cfg, rep)
                futures[f] = idx
            for f in as_completed(futures):
                try:
                    results.append(f.result())
                except Exception:
                    logger.exception("Season %d failed", futures[f])
                    raise
    else:
        for idx, (season_cfg, rep) in enumerate(schedule, 1):
            results.append(run_one(idx, season_cfg, rep))

    print(f"\nResume complete: {len(results)} additional seasons run.")
    print(f"Total in {results_path}: {sum(completed.values()) + len(results)}")


if __name__ == "__main__":
    main()
