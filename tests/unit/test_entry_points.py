"""One entry point, one dotenv load.

Three paths reached the same runner -- ``main.py``, the ``squid-game``
console script, and ``scripts/run_experiment.py`` -- but only ``main.py``
called ``load_dotenv()``. Which path you happened to use decided whether
your API keys were in the environment. These tests pin the fix: the dotenv
load lives inside ``runner.main()``, and the other two are shims that own
no argument parsing of their own.

The first three tests below are structural (they check the source text /
AST). They catch the shims regaining their own argparse, but they do not
catch ``load_dotenv()`` becoming unreachable, moved into a dead branch, or
shadowed by a decoy of the same name -- ``"load_dotenv" in calls`` is true
regardless of *where* in the file the call sits. ``test_runner_main_loads_dotenv_before_running``
and ``test_runner_main_tolerates_missing_dotenv`` below close that gap: they
actually call ``runner.main()`` and assert on ``os.environ``, so they fail
if the call is ever made unreachable, reordered after
``run_experiment_cli()``, or silently dropped.
"""

from __future__ import annotations

import ast
import os
from pathlib import Path

import dotenv.main as _dotenv_main

REPO_ROOT = Path(__file__).resolve().parents[2]

# runner.main() calls the bare ``load_dotenv()`` (no explicit path), which
# resolves the .env location via python-dotenv's own find_dotenv(). That
# resolution walks upward from the *calling file's own directory*
# (game/squid_game/), not from the process's current working directory --
# see dotenv/main.py's find_dotenv(): it inspects the caller's stack frame
# and only falls back to os.getcwd() in a REPL/debugger/frozen context. So
# monkeypatching the process cwd would not redirect the search. Instead we
# monkeypatch dotenv.main.find_dotenv itself -- the one hook load_dotenv()
# consults -- to point at a hermetic tmp_path .env. This exercises the real,
# unmodified load_dotenv() (nothing about the parsing/env-setting logic is
# faked), only the file-discovery step is redirected, so the test does not
# depend on -- and cannot collide with -- any real .env in the repository
# or its filesystem ancestors.
_MARKER_NAME = "SQUID_GAME_TEST_ENTRY_POINT_MARKER"


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


def test_runner_main_loads_dotenv_before_running(tmp_path, monkeypatch) -> None:
    """runner.main() must actually load .env content into os.environ, and
    it must do so before run_experiment_cli() runs -- not merely call some
    function named load_dotenv somewhere unreachable in the module.
    """
    env_file = tmp_path / ".env"
    env_file.write_text(f"{_MARKER_NAME}=entry-point-marker-value\n")
    monkeypatch.setattr(_dotenv_main, "find_dotenv", lambda *a, **k: str(env_file))
    monkeypatch.delenv(_MARKER_NAME, raising=False)

    import squid_game.runner as runner

    seen_by_run_experiment_cli: dict[str, str | None] = {}

    def _fake_run_experiment_cli() -> None:
        # Captured at call time: proves load_dotenv() ran *before* this,
        # not merely somewhere in the same process.
        seen_by_run_experiment_cli["marker"] = os.environ.get(_MARKER_NAME)

    monkeypatch.setattr(runner, "run_experiment_cli", _fake_run_experiment_cli)

    try:
        runner.main()
        assert os.environ.get(_MARKER_NAME) == "entry-point-marker-value"
        assert seen_by_run_experiment_cli["marker"] == "entry-point-marker-value"
    finally:
        monkeypatch.delenv(_MARKER_NAME, raising=False)


def test_runner_main_tolerates_missing_dotenv(monkeypatch) -> None:
    """No .env found must not crash main() -- it's a silent no-op, and the
    experiment still runs (matches python-dotenv's documented behaviour and
    the pre-existing main.py shim, which never checked load_dotenv()'s
    return value either).
    """
    monkeypatch.setattr(_dotenv_main, "find_dotenv", lambda *a, **k: "")
    monkeypatch.delenv(_MARKER_NAME, raising=False)

    import squid_game.runner as runner

    called = {"run": False}

    def _fake_run_experiment_cli() -> None:
        called["run"] = True

    monkeypatch.setattr(runner, "run_experiment_cli", _fake_run_experiment_cli)

    runner.main()  # must not raise

    assert called["run"] is True
