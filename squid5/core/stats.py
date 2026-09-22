"""Loading runs and the few statistics every report uses."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np

RNG = np.random.default_rng(0)


def jsonl(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text().splitlines() if x] if path.exists() else []


def load_runs(dirs: list[str]) -> list[dict]:
    """Each run: model, mode, finished results, and events of finished 5.2 sessions only."""
    runs = []
    for d in map(Path, dirs):
        meta = json.loads((d / "meta.json").read_text())
        results = jsonl(d / "results.jsonl")
        sids = {r["session_id"] for r in results if "session_id" in r}
        events = [e for e in jsonl(d / "events.jsonl") if e.get("session_id") in sids]
        runs.append({"dir": str(d), **meta, "results": results, "events": events})
    return runs


def boot_ci(groups: list[list[float]], n: int = 2000) -> tuple[float, float, float]:
    """Mean and 95% interval, resampling whole groups (sessions or seeds)."""
    flat = [x for g in groups for x in g]
    if not flat:
        return float("nan"), float("nan"), float("nan")
    draws = []
    for _ in range(n):
        vals = [x for i in RNG.integers(0, len(groups), len(groups)) for x in groups[i]]
        if vals:
            draws.append(np.mean(vals))
    return float(np.mean(flat)), float(np.percentile(draws, 2.5)), float(np.percentile(draws, 97.5))


def _ranks(v: list[float]) -> np.ndarray:
    """Ranks with ties given their average rank (stated probabilities repeat a lot)."""
    _, inverse, counts = np.unique(np.asarray(v, float), return_inverse=True, return_counts=True)
    return ((np.cumsum(counts) - counts) + (counts - 1) / 2)[inverse]


def spearman(x: list[float], y: list[float]) -> float:
    if len(set(x)) < 2 or len(set(y)) < 2:
        return float("nan")
    return float(np.corrcoef(_ranks(x), _ranks(y))[0, 1])


def md(rows: list[dict]) -> str:
    if not rows:
        return "_none_\n"
    keys = list(rows[0])
    fmt = lambda v: f"{v:.3f}" if isinstance(v, float) else str(v)  # noqa: E731
    return "\n".join(["| " + " | ".join(keys) + " |", "|" + "---|" * len(keys)]
                     + ["| " + " | ".join(fmt(r.get(k)) for k in keys) + " |" for r in rows]) + "\n"
