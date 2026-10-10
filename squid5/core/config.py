"""One YAML -> :class:`RunConfig`. The experiment's own section becomes its ``Settings``."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .providers import ProviderConfig

CURRENCIES = ("tokens", "points")


@dataclass
class Cell:
    cell_id: str
    currency: str
    start: int = 0  # 5.2: every agent's starting balance
    arm: str = ""  # 5.2: the fate arm; refill (5.0 / 5.1): the prompt, "subject.ending" in prompts/refill.yaml
    shares: tuple = ()  # 5.2: seat i starts with start x shares[(i + seed) % len(shares)]


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


def load(path: str | Path, experiments: dict) -> RunConfig:
    raw = yaml.safe_load(Path(path).read_text())
    mode = raw["mode"]
    if mode not in experiments:
        raise ValueError(f"mode must be one of {sorted(experiments)}, got {mode!r}")
    exp = experiments[mode]
    cfg = RunConfig(name=raw["name"], mode=mode, model=ProviderConfig(**raw["model"]),
                    cells=[Cell(**c) for c in raw["cells"]], settings=exp.Settings(**(raw.get(mode) or {})),
                    reps=raw.get("reps", 5), seed0=raw.get("seed0", 1000), workers=raw.get("workers", 4),
                    out_root=str(Path(raw.get("out_root", RunConfig.out_root)).expanduser()), calibration=raw.get("calibration", ""),
                    source=raw)
    ids = [c.cell_id for c in cfg.cells]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate cell_id in {ids}")
    if any(c.currency not in CURRENCIES for c in cfg.cells):
        raise ValueError(f"currency must be one of {CURRENCIES}")
    exp.validate(cfg)
    return cfg
