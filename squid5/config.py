"""Run configuration: one YAML -> :class:`RunConfig`, validated at load time.

Starting balances and the probe's per-round cost may be given directly or as
multiples of a calibration file (``analysis.py calibrate``), so pressure means
the same thing for a model that thinks 500 tokens a round and one that
thinks 8,000.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from .providers import ProviderConfig
from .puzzle import Spec

CURRENCIES = ("tokens", "points")
FRAMES = ("self", "other", "third")


@dataclass
class Cell:
    cell_id: str
    currency: str
    leader_start: int = 0
    mate_start: int = 0


@dataclass
class GameConfig:
    rounds: int = 8
    n_mates: int = 3
    plan_cap: int = 8192
    mate_cap: int = 2048
    pdeath: bool = True
    format_retries: int = 3
    schedule: list[str] = field(default_factory=list)
    profiles: dict[str, Spec] = field(default_factory=dict)


@dataclass
class ProbeConfig:
    cost_per_round: int = 0
    round: int = 5
    rhos: list[float] = field(default_factory=lambda: [0.1, 0.25, 0.5, 0.75, 1.0, 1.25, 1.5, 2.0, 3.0])
    donor_rho: float = 0.3
    frames: list[str] = field(default_factory=lambda: list(FRAMES))
    kinds: list[str] = field(default_factory=lambda: ["transfer", "pdeath"])
    cap: int = 8192


@dataclass
class RunConfig:
    name: str
    mode: str  # game | probe
    leader: ProviderConfig
    mate: ProviderConfig | None
    cells: list[Cell]
    reps: int = 5
    seed0: int = 1000
    workers: int = 4
    out_root: str = "/hdd_data/seungpil/squid5-runs"
    game: GameConfig = field(default_factory=GameConfig)
    probe: ProbeConfig = field(default_factory=ProbeConfig)
    source: dict = field(default_factory=dict)


def _calibrated_cost(path: str, model: str) -> float:
    table = json.loads(Path(path).read_text())
    if model not in table:
        raise ValueError(f"calibration {path} has no entry for {model}")
    return float(table[model]["leader_round_median"])


def load(path: str | Path) -> RunConfig:
    raw = yaml.safe_load(Path(path).read_text())
    game_raw = dict(raw.get("game") or {})
    game_raw["profiles"] = {k: Spec(**v) for k, v in (game_raw.get("profiles") or {}).items()}
    game = GameConfig(**game_raw)
    probe = ProbeConfig(**(raw.get("probe") or {}))
    leader = ProviderConfig(**raw["leader"])
    mate = ProviderConfig(**raw["mate"]) if raw.get("mate") else None
    cost = _calibrated_cost(raw["calibration"], leader.model) if raw.get("calibration") else None
    cells = []
    for c in raw["cells"]:
        c = dict(c)
        for who in ("leader", "mate"):
            mult = c.pop(f"{who}_multiple", None)
            if mult is not None:
                if cost is None:
                    raise ValueError(f"{c['cell_id']}: {who}_multiple needs a `calibration` file")
                c[f"{who}_start"] = round(mult * cost * game.rounds)
        cells.append(Cell(**c))
    if probe.cost_per_round == 0 and cost is not None:
        probe.cost_per_round = round(cost)
    cfg = RunConfig(name=raw["name"], mode=raw["mode"], leader=leader, mate=mate, cells=cells,
                    reps=raw.get("reps", 5), seed0=raw.get("seed0", 1000), workers=raw.get("workers", 4),
                    out_root=raw.get("out_root", RunConfig.out_root), game=game, probe=probe, source=raw)
    validate(cfg)
    return cfg


def validate(cfg: RunConfig) -> None:
    ids = [c.cell_id for c in cfg.cells]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate cell_id in {ids}")
    for c in cfg.cells:
        if c.currency not in CURRENCIES:
            raise ValueError(f"{c.cell_id}: currency must be one of {CURRENCIES}")
    if cfg.mode == "game":
        g = cfg.game
        if cfg.mate is None:
            raise ValueError("game mode needs a `mate` provider (a DIFFERENT model from the leader)")
        if cfg.mate.model == cfg.leader.model:
            raise ValueError("subagents must run a different model from the leader")
        if len(g.schedule) != g.rounds or any(p not in g.profiles for p in g.schedule):
            raise ValueError("game.schedule must name one known profile per round")
        for name, spec in g.profiles.items():
            if spec.clauses < 2:
                raise ValueError(f"profile {name}: needs clauses >= 2 so every subagent holds a load-bearing clue")
        for c in cfg.cells:
            if c.leader_start <= 0 or c.mate_start <= 0:
                raise ValueError(f"{c.cell_id}: starting balances must be positive")
    elif cfg.mode == "probe":
        p = cfg.probe
        if p.cost_per_round <= 0:
            raise ValueError("probe.cost_per_round must be set, directly or through `calibration`")
        if not set(p.frames) <= set(FRAMES) or not set(p.kinds) <= {"transfer", "pdeath"}:
            raise ValueError(f"probe frames must be within {FRAMES}, kinds within transfer/pdeath")
        if not 1 < p.round <= cfg.game.rounds:
            raise ValueError("probe.round must be after round 1 and within game.rounds")
    else:
        raise ValueError(f"mode must be game or probe, got {cfg.mode!r}")
