"""CLI: ``python -m squid5.runner <config.yaml> [--resume <run_dir>] [--reps N] [--dry-run]``.

Writes ``<out_root>/<name>/<UTC stamp>_<leader model>/`` with ``config.yaml``, ``meta.json``,
``events.jsonl`` (game mode: every call and round, append-only) and
``results.jsonl`` (one line per finished session or probe item). ``--resume`` skips every unit
whose key -- which always includes ``cell_id`` -- is already in results.jsonl.
"""

from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import yaml

from .config import RunConfig, load
from .game import Session
from .probe import run_item
from .providers import Provider, make_provider


def units(cfg: RunConfig) -> list[dict]:
    """Every unit of work, each with a unique resume key."""
    out = []
    for cell in cfg.cells:
        for rep in range(cfg.reps):
            seed = cfg.seed0 + rep
            if cfg.mode == "game":
                out.append({"cell": cell, "seed": seed, "key": [cell.cell_id, seed]})
                continue
            for kind in cfg.probe.kinds:
                frames, scales = (cfg.probe.frames, [1.0]) if kind == "transfer" else (["self"], cfg.probe.spend_scales)
                for frame in frames:
                    for scale in scales:
                        for rho in cfg.probe.rhos:
                            out.append({"cell": cell, "seed": seed, "kind": kind, "frame": frame, "rho": rho,
                                        "scale": scale, "key": [cell.cell_id, seed, kind, frame, scale, rho]})
    return out


def run(cfg: RunConfig, run_dir: Path, leader: Provider, mate: Provider | None) -> int:
    run_dir.mkdir(parents=True, exist_ok=True)
    (run_dir / "config.yaml").write_text(yaml.safe_dump(cfg.source, sort_keys=False))
    (run_dir / "meta.json").write_text(json.dumps({"model": cfg.leader.model, "mode": cfg.mode,
                                                   "rounds": cfg.game.rounds}))
    results = run_dir / "results.jsonl"
    done = set()
    if results.exists():
        done = {json.dumps(json.loads(line)["key"]) for line in results.read_text().splitlines() if line}
    todo = [u for u in units(cfg) if json.dumps(u["key"]) not in done]
    lock = threading.Lock()

    def write(path: Path, row: dict) -> None:
        with lock, path.open("a") as f:
            f.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")

    def emit(row: dict) -> None:
        write(run_dir / "events.jsonl", row)

    def work(u: dict) -> dict:
        if cfg.mode == "game":
            sid = f"{u['cell'].cell_id}-s{u['seed']}-{uuid.uuid4().hex[:6]}"  # a crashed attempt's events stay orphaned
            return Session(cfg.game, u["cell"], u["seed"], leader, mate, emit, sid).run()
        return run_item(cfg, u["cell"], leader, u["kind"], u["frame"], u["rho"], u["seed"], u["scale"])

    failed = 0
    with ThreadPoolExecutor(max_workers=cfg.workers) as pool:
        futures = {pool.submit(work, u): u for u in todo}
        for fut in as_completed(futures):
            u = futures[fut]
            try:
                write(results, {"key": u["key"], **fut.result()})
            except Exception as err:  # a unit that crashed is left for --resume, never half-written
                failed += 1
                emit({"event": "unit_error", "key": u["key"], "error": repr(err)})
    print(f"{run_dir}: {len(todo) - failed}/{len(todo)} units done, {failed} failed")
    return failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("config")
    ap.add_argument("--resume")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--reps", type=int, help="override the config's reps (a pilot before the main run)")
    a = ap.parse_args(argv)
    cfg = load(a.config)
    if a.reps:
        cfg.reps = cfg.source["reps"] = a.reps
    if a.dry_run:
        print(f"{cfg.name}: mode={cfg.mode}, {len(units(cfg))} units, cells={[c.cell_id for c in cfg.cells]}")
        return 0
    stamp = time.strftime("%Y%m%d_%H%M", time.gmtime())
    run_dir = Path(a.resume) if a.resume else Path(cfg.out_root) / cfg.name / f"{stamp}_{cfg.leader.model.replace(':', '-')}"
    return 1 if run(cfg, run_dir, make_provider(cfg.leader), cfg.mate and make_provider(cfg.mate)) else 0


if __name__ == "__main__":
    raise SystemExit(main())
