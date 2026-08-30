"""Every module in the tree must still import after the restructure.

P1 rewrites imports across ``src/``, ``scripts/`` and ``interface/`` and
removes eleven ``sys.path`` hacks. A module that neither the unit suite nor
``scripts/analyze_phase3.py`` reaches can acquire a broken import while both
of those nets stay green -- the golden snapshot only exercises the analysis
entry point, and most of ``scripts/`` has no test at all.

This test closes that hole the cheapest way there is: walk the tree and
import every module found.

Two rules keep it honest:

1. There is **no blanket ``try``/``except ImportError``**. A swallowed
   ImportError is exactly the failure this test exists to catch, so an
   unexpected one propagates and fails the test.
2. Everything not imported is named individually in ``SKIPPED`` below with
   its reason. A skip list that is a list of names can be audited; a
   predicate cannot.

The environment assumed is the documented baseline,
``uv sync --extra dev --extra analysis`` (see
``docs/superpowers/plans/2026-08-30-p0-baseline.md``). ``matplotlib`` arrives
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
    ("src", REPO_ROOT / "src"),
    ("scripts", REPO_ROOT),
    ("interface", REPO_ROOT),
]

# Module name -> why it is not imported here. One line each; nothing else is
# skipped. Keep this list short and keep every entry justified.
SKIPPED: dict[str, str] = {
    # Optional dependency, not declared in any pyproject extra.
    "interface.app": "needs streamlit, which is not a declared dependency",
    # Module-level side effects: these three write .excalidraw files into
    # docs/design/v4/assets/ at import time, with no __main__ guard. Importing
    # them would make the test suite dirty the working tree.
    "scripts.build_llm_experience_diagram": "writes a .excalidraw file at import time",
    "scripts.build_posthoc_analysis_diagram": "writes a .excalidraw file at import time",
    "scripts.build_prompt_flow_diagram": "writes a .excalidraw file at import time",
}


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
    assert "squid_game.analysis.forfeit_regression" in MODULE_NAMES
    assert "scripts.analyze_phase3" in MODULE_NAMES
    assert "interface.api" in MODULE_NAMES


def test_skip_list_names_only_modules_that_exist() -> None:
    """A stale skip entry would quietly stop gating a module that still exists."""
    assert set(SKIPPED) <= set(MODULE_NAMES)


@pytest.mark.parametrize("module_name", [n for n in MODULE_NAMES if n not in SKIPPED])
def test_module_imports(module_name: str) -> None:
    importlib.import_module(module_name)
