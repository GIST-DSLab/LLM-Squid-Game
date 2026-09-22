"""One YAML -> :class:`RunConfig`. The experiment's own section becomes its ``Settings``."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .providers import ProviderConfig

CURRENCIES = ("tokens", "points")


@dataclass
class Cell:
    cell_id: str
    currency: str
    start: int = 0  # 5.2: every agent's starting balance ...
    start_multiple: float = 0.0  # ... or this x the calibrated tokens per agent-round x rounds


@dataclass
class RunConfig:
    name: str
    mode: str
    model: ProviderConfig
    cells: list[Cell]
    settings: object
    reps: int = 5
    seed0: int = 1000
    workers: int = 4
    out_root: str = "/hdd_data/seungpil/squid5-runs"
    calibration: str = ""
    source: dict = field(default_factory=dict)


def calibrated_cost(cfg: RunConfig) -> float:
    table = json.loads(Path(cfg.calibration).read_text())
    if cfg.model.model not in table:
        raise ValueError(f"calibration {cfg.calibration} has no entry for {cfg.model.model}")
    return float(table[cfg.model.model]["agent_round_median"])


def load(path: str | Path, experiments: dict) -> RunConfig:
    raw = yaml.safe_load(Path(path).read_text())
    mode = raw["mode"]
    if mode not in experiments:
        raise ValueError(f"mode must be one of {sorted(experiments)}, got {mode!r}")
    exp = experiments[mode]
    cfg = RunConfig(name=raw["name"], mode=mode, model=ProviderConfig(**raw["model"]),
                    cells=[Cell(**c) for c in raw["cells"]], settings=exp.Settings(**(raw.get(mode) or {})),
                    reps=raw.get("reps", 5), seed0=raw.get("seed0", 1000), workers=raw.get("workers", 4),
                    out_root=raw.get("out_root", RunConfig.out_root), calibration=raw.get("calibration", ""),
                    source=raw)
    ids = [c.cell_id for c in cfg.cells]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate cell_id in {ids}")
    if any(c.currency not in CURRENCIES for c in cfg.cells):
        raise ValueError(f"currency must be one of {CURRENCIES}")
    exp.validate(cfg)
    return cfg
