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


@pytest.fixture(autouse=True)
def _sandbox_repository(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """``squid_arena.api`` opens a repository at import time; keep it in RAM.

    Without this the import falls back to outputs/web_arena/web_arena.db --
    the live dev database -- and runs init_schema against it.
    """
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.setenv("SQUID_THINKING_LOG_DIR", str(tmp_path / "thinking_traces"))


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


def test_squid_arena_imports_under_its_own_name() -> None:
    module = importlib.import_module("squid_arena.api")
    assert module.app is not None


def test_squid_arena_lives_in_the_web_tier() -> None:
    module = importlib.import_module("squid_arena")
    assert Path(module.__file__).parent == REPO_ROOT / "web" / "squid_arena"


def test_the_old_interface_package_is_gone() -> None:
    assert not (REPO_ROOT / "interface").exists()
    assert importlib.util.find_spec("interface") is None


def test_squid_arena_touches_no_sys_path() -> None:
    """The tier packages exist so nothing has to rewrite sys.path any more."""
    for path in (REPO_ROOT / "web" / "squid_arena").rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        assert "sys.path" not in path.read_text(encoding="utf-8"), path


def test_squid_game_lives_in_the_game_tier() -> None:
    module = importlib.import_module("squid_game")
    assert Path(module.__file__).parent == REPO_ROOT / "game" / "squid_game"


def test_the_src_directory_is_gone() -> None:
    assert not (REPO_ROOT / "src").exists()


def test_squid_game_depends_on_no_higher_tier() -> None:
    """The engine must not reach up into the web or db tiers.

    ``core/measurement.py`` and ``analysis/shared/mtmm.py`` contain the word
    "persistence", but as the psychological construct (Baseline
    Persistence), not the storage layer -- which is exactly why this check
    reads import statements rather than grepping for the word.
    """
    imported = _toplevel_imports(REPO_ROOT / "game" / "squid_game")
    assert "squid_arena" not in imported
    assert "squid_store" not in imported
    assert "interface" not in imported


def test_no_module_rewrites_sys_path() -> None:
    """The tier packages are installed; nothing needs to patch sys.path.

    Thirteen call sites did before P1. The count is asserted as zero rather
    than as a shrinking number, because "fewer" is not a property anyone can
    hold onto -- the next person to add one would still pass a threshold test.
    """
    offenders: list[str] = []
    for base in ("game", "web", "db", "scripts", "tests"):
        for path in (REPO_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts or path.name == "test_tier_boundaries.py":
                continue
            source = path.read_text(encoding="utf-8")
            if "sys.path.insert" in source or "sys.path.append" in source:
                offenders.append(str(path.relative_to(REPO_ROOT)))
    assert offenders == []
