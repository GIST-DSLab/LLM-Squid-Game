"""One entry point, one dotenv load.

Three paths reached the same runner -- ``main.py``, the ``squid-game``
console script, and ``scripts/run_experiment.py`` -- but only ``main.py``
called ``load_dotenv()``. Which path you happened to use decided whether
your API keys were in the environment. These tests pin the fix: the dotenv
load lives inside ``runner.main()``, and the other two are shims that own
no argument parsing of their own.
"""

from __future__ import annotations

import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _calls_in(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            names.add(node.func.id)
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
            names.add(node.func.attr)
    return names


def test_runner_main_loads_dotenv() -> None:
    calls = _calls_in(REPO_ROOT / "game" / "squid_game" / "runner.py")
    assert "load_dotenv" in calls


def test_shims_do_not_parse_arguments() -> None:
    """A shim that builds its own parser is a second entry point again."""
    for shim in ("main.py", "scripts/run_experiment.py"):
        source = (REPO_ROOT / shim).read_text(encoding="utf-8")
        assert "ArgumentParser" not in source, shim
        assert "add_argument" not in source, shim


def test_shims_delegate_to_the_runner() -> None:
    for shim in ("main.py", "scripts/run_experiment.py"):
        source = (REPO_ROOT / shim).read_text(encoding="utf-8")
        assert "from squid_game.runner import main" in source, shim
