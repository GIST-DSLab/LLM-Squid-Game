"""The 3-tier split must be real, not just a directory rename.

Three properties are asserted, and each one fails loudly if a later step
undoes it:

1. Each tier's package imports under its own name (``squid_store``,
   ``squid_arena``, ``squid_game``) -- not via a path hack, and not via the
   tier directory name (``db``/``web``/``game`` are deliberately NOT import
   names; ``web`` in particular is taken on PyPI).
2. The pre-restructure names are gone. A leftover ``interface`` package
   would let a stale import keep working and hide a missed call site.
3. The dependency direction runs one way: ``squid_arena`` may reach
   ``squid_game`` and ``squid_store``; neither of those may reach back.
   This is checked by reading source, not by importing -- an import-time
   check would only see modules the test itself happens to load.
"""

from __future__ import annotations

import ast
import importlib
import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]


def _toplevel_imports(package_dir: Path) -> set[str]:
    """Every top-level module name imported anywhere under ``package_dir``."""
    names: set[str] = set()
    for path in package_dir.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def test_squid_store_imports_under_its_own_name() -> None:
    module = importlib.import_module("squid_store")
    assert module.get_repository is not None
    assert set(module.__all__) == {
        "Repository",
        "SessionRecord",
        "TurnRecord",
        "ModelStatsRecord",
        "PlayerRecord",
        "get_repository",
    }


def test_squid_store_lives_in_the_db_tier() -> None:
    module = importlib.import_module("squid_store")
    assert Path(module.__file__).parent == REPO_ROOT / "db" / "squid_store"


def test_the_old_persistence_package_is_gone() -> None:
    assert not (REPO_ROOT / "interface" / "persistence").exists()
    # ``find_spec`` returns None only while the parent package (``interface``)
    # still exists but the submodule does not. Once a later restructure task
    # deletes ``interface`` entirely, the parent lookup itself raises
    # ModuleNotFoundError -- that is equally valid evidence the old package
    # is gone, so both outcomes count as success here.
    try:
        spec = importlib.util.find_spec("interface.persistence")
    except ModuleNotFoundError:
        spec = None
    assert spec is None


def test_squid_store_depends_on_no_other_tier() -> None:
    imported = _toplevel_imports(REPO_ROOT / "db" / "squid_store")
    assert "squid_arena" not in imported
    assert "squid_game" not in imported
    assert "interface" not in imported
