"""Run every unit of an experiment in parallel, append-only, resumable.

A run directory holds ``config.yaml``, ``meta.json``, ``events.jsonl`` (every
call and round of 5.2 sessions) and ``results.jsonl`` (one line per finished
unit). ``--resume`` skips units whose key -- which always starts with
``cell_id`` -- is already in results.jsonl. A unit that crashed leaves no
result line, so it is simply run again.
"""

from __future__ import annotations

import json
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path

import yaml

from .config import RunConfig
from .providers import Provider


def run(cfg: RunConfig, exp, run_dir: Path, provider: Provider) -> int:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(yaml.safe_dump(cfg.source, sort_keys=False))
    (run_dir / "meta.json").write_text(json.dumps({"model": cfg.model.model, "mode": cfg.mode,
                                                   "settings": asdict(cfg.settings)}))
    results = run_dir / "results.jsonl"
    lines = results.read_text().splitlines() if results.exists() else []
    done = {json.dumps(json.loads(x)["key"]) for x in lines if x}
    todo = [u for u in exp.units(cfg) if json.dumps(u["key"]) not in done]
    lock = threading.Lock()

    def write(path: Path, row: dict) -> None:
        with lock, path.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    failed = 0
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = {pool.submit(exp.run_unit, cfg, u, provider, lambda r: write(run_dir / "events.jsonl", r)): u
                   for u in todo}
        for fut in as_completed(futures):
            u = futures[fut]
            try:
                write(results, {"key": u["key"], **fut.result()})
            except Exception as err:  # left for --resume, never half-written
                failed += 1
                write(run_dir / "events.jsonl", {"event": "unit_error", "key": u["key"], "error": repr(err)})
    print(f"{run_dir}: {len(todo) - failed}/{len(todo)} units done, {failed} failed")
    return failed
