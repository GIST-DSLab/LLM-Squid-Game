"""One YAML -> :class:`RunConfig`. The experiment's own section becomes its ``Settings``."""

from __future__ import annotations

import datetime as dt
import subprocess
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
    arm: str = ""  # 5.2: the fate arm; refill (5.0 / 5.1): the prompt, "subject.ending" in prompts/en/refill.yaml
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
    out_root: str = ""  # set by load(): resolve_out_root
    calibration: str = ""
    source: dict = field(default_factory=dict)

def repo_root() -> Path:
    """The main checkout that holds result/, also when this code runs from a worktree under .claude/worktrees/."""
    common = subprocess.run(["git", "rev-parse", "--path-format=absolute", "--git-common-dir"], capture_output=True,
                            text=True, check=True, cwd=Path(__file__).resolve().parent).stdout.strip()
    return Path(common).parent

def resolve_out_root(raw: dict) -> str:
    """YAML ``out_root``: relative = under the main checkout, ``{kst_date}`` = today (KST); default result/<today>/<name>/runs."""
    kst = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).strftime("%Y-%m-%d")
    p = Path(str(raw.get("out_root") or "result/{kst_date}/" + raw["name"] + "/runs").replace("{kst_date}", kst)).expanduser()
    return str(p if p.is_absolute() else repo_root() / p)

def squid5_runs(rel: str) -> Path:
    """``~/squid5-runs/<rel>`` (the run root until 2026-11-11) inside the repo. Its first part ``<name>`` is now
    result/<date>/<exp>/runs/<name> (folder copied whole) or else result/<date>/<name>/runs (its children copied);
    the rest (globs allowed) is appended."""
    name, _, rest = rel.partition("/")
    res = repo_root() / "result"
    hits = sorted(res.glob(f"*/*/runs/{name}")) or sorted(res.glob(f"*/{name}/runs"))
    if len(hits) != 1:
        raise FileNotFoundError(f"{name}: {len(hits)} folders under {res}")
    return hits[0] / rest

def load(path: str | Path, experiments: dict) -> RunConfig:
    raw = yaml.safe_load(Path(path).read_text())
    mode = raw["mode"]
    if mode not in experiments:
        raise ValueError(f"mode must be one of {sorted(experiments)}, got {mode!r}")
    exp = experiments[mode]
    cfg = RunConfig(name=raw["name"], mode=mode, model=ProviderConfig(**raw["model"]),
                    cells=[Cell(**c) for c in raw["cells"]], settings=exp.Settings(**(raw.get(mode) or {})),
                    reps=raw.get("reps", 5), seed0=raw.get("seed0", 1000), workers=raw.get("workers", 4),
                    out_root=resolve_out_root(raw), calibration=raw.get("calibration", ""),
                    source=raw)
    ids = [c.cell_id for c in cfg.cells]
    if len(set(ids)) != len(ids):
        raise ValueError(f"duplicate cell_id in {ids}")
    if any(c.currency not in CURRENCIES for c in cfg.cells):
        raise ValueError(f"currency must be one of {CURRENCIES}")
    exp.validate(cfg)
    return cfg
