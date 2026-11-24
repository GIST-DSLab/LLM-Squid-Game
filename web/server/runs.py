"""Where the site's runs live and the game-log tools (tools/monitor) that read them, shared by the pages that show
runs: the arena (its rooms write run dirs and link to their logs), the leaderboard and the game-log viewer.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

from squid.core.config import repo_root

from .store import REPO

NO_STORE = {"Cache-Control": "no-store"}  # the viewer polls; serve.py sends the same header


def default_runs_root() -> Path:
    env = os.environ.get("WEB5_RUNS_ROOT")
    return Path(env).expanduser() if env else repo_root() / "result" / "2026-10-05" / "web5_arena" / "runs"


SERVE = REPO / "tools" / "monitor" / "serve.py"


def load_serve():
    """tools/monitor/serve.py (not a package), loaded once by path so its run-index caches are shared."""
    name = "squid5_monitor_serve"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, SERVE)
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    return mod


def load_compare():
    """tools/monitor/compare.py, bound to the same loaded serve module (one cache)."""
    name = "squid5_monitor_compare"
    mod = sys.modules.get(name)
    if mod is None:
        spec = importlib.util.spec_from_file_location(name, SERVE.parent / "compare.py")
        mod = importlib.util.module_from_spec(spec)
        sys.modules[name] = mod
        spec.loader.exec_module(mod)
    mod.serve = load_serve()
    return mod


def default_monitor_root(runs_root: Path) -> Path:
    """WEB5_MONITOR_ROOT; else result/ of the main checkout when the rooms' runs live there (experiment runs and web
    rooms both show), else the parent of ``runs_root``."""
    env = os.environ.get("WEB5_MONITOR_ROOT")
    if env:
        return Path(env).expanduser()
    from squid.core.config import repo_root
    result, runs = repo_root() / "result", Path(runs_root).expanduser()
    return result if result in runs.parents else runs.parent


def run_rel(root: Path, run_dir: Path | None) -> str | None:
    """``run_dir`` relative to the monitor root (the page's ``?run=``), or None if it lies outside."""
    if run_dir is None:
        return None
    try:
        return Path(run_dir).resolve().relative_to(Path(root).resolve()).as_posix()
    except ValueError:
        return None
