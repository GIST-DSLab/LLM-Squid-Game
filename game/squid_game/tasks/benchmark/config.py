"""Loading of ``configs/tasks/<name>.yaml`` for benchmark task modules.

Unlike the legacy task configs (which are documentation only), these files
are read at runtime: they own the difficulty ladder, so changing the ladder
never requires a code change.
"""

from __future__ import annotations

import os
from pathlib import Path

import yaml
from pydantic import BaseModel, Field, model_validator

#: Repository root, derived from this file's location
#: (game/squid_game/tasks/benchmark/config.py -> repo root).
_REPO_ROOT = Path(__file__).resolve().parents[4]


class LadderStep(BaseModel):
    """One rung of the difficulty ladder."""

    model_config = {"frozen": True}

    band: int = Field(ge=1)
    turns: int = Field(gt=0)


class BenchmarkTaskConfig(BaseModel):
    """Runtime configuration for one benchmark task module."""

    model_config = {"frozen": True}

    name: str
    data_file: str
    total_turns: int = Field(gt=0)
    ladder: list[LadderStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _ladder_covers_total_turns(self) -> "BenchmarkTaskConfig":
        allotted = sum(step.turns for step in self.ladder)
        if allotted != self.total_turns:
            raise ValueError(
                f"ladder turns ({allotted}) must equal total_turns ({self.total_turns})"
            )
        bands = [step.band for step in self.ladder]
        if bands != sorted(bands):
            raise ValueError("ladder bands must be non-decreasing")
        return self


def default_config_dir() -> Path:
    """Return the directory holding task YAML files.

    ``$SQUID_GAME_TASK_CONFIG_DIR`` overrides the repository default so a
    test or an alternate checkout can point elsewhere.
    """
    override = os.environ.get("SQUID_GAME_TASK_CONFIG_DIR")
    if override:
        return Path(override)
    return _REPO_ROOT / "configs" / "tasks"


def load_task_config(task_name: str, config_dir: Path | None = None) -> BenchmarkTaskConfig:
    """Load and validate the YAML config for *task_name*.

    Raises:
        FileNotFoundError: If no YAML file exists for *task_name*.
        ValueError: If the ladder does not cover exactly ``total_turns``.
    """
    directory = config_dir if config_dir is not None else default_config_dir()
    path = directory / f"{task_name}.yaml"
    if not path.is_file():
        raise FileNotFoundError(f"No benchmark task config at {path}")
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return BenchmarkTaskConfig.model_validate(raw)
