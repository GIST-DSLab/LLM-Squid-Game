"""Every module in the tree must still import after the restructure.

P1 rewrites imports across ``game/squid_game/``, ``scripts/``,
``web/squid_arena/`` and ``db/squid_store/`` and removes eleven
``sys.path`` hacks. A module that neither the
unit suite nor ``scripts/analysis/analyze_phase3.py`` reaches can acquire a broken
import while both of those nets stay green -- the golden snapshot only
exercises the analysis entry point, and most of ``scripts/`` has no test
at all.

This test closes that hole the cheapest way there is: walk the tree and
import every module found.

Three rules keep it honest:

1. There is **no blanket ``try``/``except ImportError``**. A swallowed
   ImportError is exactly the failure this test exists to catch, so an
   unexpected one propagates and fails the test.
2. Everything not imported is named individually in ``SKIPPED`` below with
   its reason. A skip list that is a list of names can be audited; a
   predicate cannot.
3. **Importing must not write anything.** Several modules do real work at
   module scope, and a unit test that opens write paths into ``outputs/`` is
   worse than the gap it fills -- especially since neither effect below is
   visible to ``git status`` (git does not track empty directories, and
   ``outputs/web_arena/`` is gitignored). ``_sandbox_module_scope_side_effects``
   redirects the two that are redirectable; the three that are not are
   skipped and named.

An audit of module-scope filesystem calls across ``game/squid_game/``,
``scripts/``, ``web/squid_arena/`` and ``db/squid_store/``::

    grep -rn --include='*.py' -E \\
      '^[A-Za-z_][^ =]*.*(\\.mkdir\\(|sqlite3\\.connect|\\.write_text\\(|\\.touch\\(|makedirs\\(|get_repository\\(\\))' \\
      game scripts web/squid_arena db

finds exactly five hits: the three ``build_*_diagram`` scripts (skipped),
``web/squid_arena/anthropic_proxy.py:57`` and ``web/squid_arena/deps.py:84``
(both sandboxed by the fixture). ``web/squid_arena/deps.py:84`` replaces the
former ``web/squid_arena/api.py:144`` hit -- P5 Task 4 moved the module-scope
``_repository = get_repository()`` singleton out of ``api.py`` into
``deps.py`` (Ruling C3); ``squid_arena.api`` still triggers the same side
effect transitively, since it imports ``squid_arena.deps``. Re-run it after
any restructure step that moves code into a new module.

The environment assumed is the documented baseline,
``uv sync --extra dev --extra analysis`` (see
``docs/history/plans/2026-08-30-p0-baseline.md``). ``matplotlib`` arrives
transitively with ``lifelines``, so the ``plot_*`` scripts import under it.
Running the suite without the ``analysis`` extra will fail this test rather
than skip it -- that is deliberate: a missing extra silently narrows
coverage elsewhere in the suite, and here it is at least loud.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# Roots to walk, paired with the directory their module paths are relative to.
PACKAGE_ROOTS: list[tuple[str, Path]] = [
    ("scripts", REPO_ROOT),
    ("game/squid_game", REPO_ROOT / "game"),
    ("db/squid_store", REPO_ROOT / "db"),
    ("web/squid_arena", REPO_ROOT / "web"),
]

# Module name -> why it is not imported here. One line each; nothing else is
# skipped. Keep this list short and keep every entry justified.
SKIPPED: dict[str, str] = {
    # Optional dependency, not declared in any pyproject extra.
    "squid_arena.app": "needs streamlit, which is not a declared dependency",
    # Module-level side effects: these three write .excalidraw files into
    # assets/figures/v4/ at import time (repointed from docs/design/v4/assets/
    # by the P1 fix-wave, 2026-08-30, Ruling C40), with no __main__ guard.
    # Importing them would make the test suite dirty the working tree.
    "scripts.plots.build_llm_experience_diagram": "writes a .excalidraw file at import time",
    "scripts.plots.build_posthoc_analysis_diagram": "writes a .excalidraw file at import time",
    "scripts.plots.build_prompt_flow_diagram": "writes a .excalidraw file at import time",
}


@pytest.fixture(autouse=True)
def _sandbox_module_scope_side_effects(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Redirect the two import-time write paths into ``outputs/`` at tmp_path.

    Both modules are redirectable through environment variables read at
    module scope, so they can stay covered rather than skipped -- a skip in
    the test whose entire purpose is coverage is the worse trade.

    ``squid_arena.anthropic_proxy`` (line 57) does
    ``LOG_DIR.mkdir(parents=True, exist_ok=True)`` on
    ``SQUID_THINKING_LOG_DIR``, defaulting to
    ``<repo>/outputs/api_sessions/thinking_traces``. This test is the only
    importer of that module in the repo, and the directories it created were
    invisible to ``git status`` because git does not track empty directories.

    ``squid_arena.deps`` (line 84) does ``_repository = get_repository()``,
    which with no ``WEB_ARENA_DSN`` falls back to
    ``outputs/web_arena/web_arena.db`` (``squid_store/factory.py:16,32``) and
    runs ``mkdir`` + ``sqlite3.connect`` + ``init_schema()`` -- an
    ``executescript`` and guarded ``ALTER TABLE``s -- against the live dev
    DB. That path is gitignored, so ``git status`` could not see it either.
    ``":memory:"`` short-circuits the mkdir in ``SQLiteRepository.__init__``
    (``sqlite_repository.py:119-121``) and touches no file at all. P5 Task 4
    moved this statement out of ``squid_arena.api`` (formerly line 144) into
    ``squid_arena.deps`` (Ruling C3); importing ``squid_arena.api`` still
    triggers it transitively, since ``api.py`` imports ``deps`` at its own
    top level.

    The hazard is order-dependent, which is why it went unnoticed: in a full
    ``pytest tests/unit`` run, ``test_api_web_arena.py`` imports
    ``squid_arena.api`` (and so ``squid_arena.deps``) first, inside a fixture
    that already sets ``WEB_ARENA_DSN=":memory:"``, so this test gets a
    harmless cache hit. Running this file ALONE is what opens the real DB.
    """
    monkeypatch.setenv("WEB_ARENA_DSN", ":memory:")
    monkeypatch.setenv("SQUID_THINKING_LOG_DIR", str(tmp_path / "thinking_traces"))


def _module_names() -> list[str]:
    names: set[str] = set()
    for base, anchor in PACKAGE_ROOTS:
        for path in sorted((REPO_ROOT / base).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            parts = list(path.relative_to(anchor).parts)
            if parts[-1] == "__init__.py":
                parts.pop()
            else:
                parts[-1] = parts[-1].removesuffix(".py")
            if parts:
                names.add(".".join(parts))
    return sorted(names)


MODULE_NAMES = _module_names()


def test_the_walk_actually_finds_the_tree() -> None:
    """Guard against the walk silently finding nothing after a move.

    A restructure step that relocates a package must make this test fail
    loudly, not turn it into a no-op that reports zero modules and passes.
    """
    assert len(MODULE_NAMES) > 100
    assert "squid_game.runner" in MODULE_NAMES
    # forfeit_regression.py was split 2026-08-30 (P2 Task 4); its two
    # successor modules are the walk-discoverability check now.
    assert "squid_game.analysis.cognitive.ri_forfeit" in MODULE_NAMES
    assert "squid_game.analysis.selfreport.reason_convergence" in MODULE_NAMES
    assert "scripts.analysis.analyze_phase3" in MODULE_NAMES
    assert "squid_arena.api" in MODULE_NAMES
    assert "squid_store.factory" in MODULE_NAMES


def test_skip_list_names_only_modules_that_exist() -> None:
    """A stale skip entry would quietly stop gating a module that still exists."""
    assert set(SKIPPED) <= set(MODULE_NAMES)


@pytest.mark.parametrize("module_name", [n for n in MODULE_NAMES if n not in SKIPPED])
def test_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)


def test_importing_writes_nothing_into_outputs() -> None:
    """The sandbox fixture must actually hold, not merely be present.

    Asserted directly because neither escape is visible to ``git status``:
    ``outputs/api_sessions/`` would be an untracked EMPTY directory (git does
    not track those) and ``outputs/web_arena/`` is gitignored
    (``.gitignore:32``). If a later change hardcodes either path and stops
    honouring the env var, the fixture would go on passing while quietly
    doing nothing -- this test is what fails instead.

    The second assertion below is widened past just the correct
    ``outputs/api_sessions`` path (P1 fix-wave, 2026-08-30): before that fix,
    ``anthropic_proxy.LOG_DIR``'s ``__file__``-anchor was one level too
    shallow and its unsandboxed default resolved to
    ``<repo>/web/outputs/api_sessions/thinking_traces`` instead of
    ``<repo>/outputs/api_sessions/thinking_traces``. A check against only the
    correct path would have stayed green through that whole regression --
    the wrong-location write never lands under ``outputs/api_sessions``, so
    it would never trip -- which is exactly how the bug went unnoticed. The
    ``web/outputs`` check below is what would have caught it.
    """
    proxy = importlib.import_module("squid_arena.anthropic_proxy")
    importlib.import_module("squid_arena.api")

    outputs = REPO_ROOT / "outputs"
    assert not proxy.LOG_DIR.is_relative_to(outputs), (
        f"anthropic_proxy.LOG_DIR escaped the sandbox: {proxy.LOG_DIR}"
    )
    assert not (outputs / "api_sessions").exists()
    assert not (REPO_ROOT / "web" / "outputs").exists()
