"""The analysis split must be by measurement channel, not by convenience.

Two properties are pinned:

1. The facade is stable. ``squid_game.analysis.__all__`` is what the
   pipeline and the tests import through; P2 moves modules underneath it
   and must not change what comes out the front.
2. Each channel package holds only its own channel's estimators, and the
   shared layer holds no channel-specific model fitting. Asserted by
   naming modules explicitly -- a predicate would drift as files move.
"""

from __future__ import annotations

import importlib
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = REPO_ROOT / "game" / "squid_game" / "analysis"


def test_the_facade_still_exports_everything() -> None:
    module = importlib.import_module("squid_game.analysis")
    for name in module.__all__:
        assert hasattr(module, name), name


def test_shared_layer_holds_the_cross_channel_modules() -> None:
    expected = {
        "loaders.py",
        "export.py",
        "metrics.py",
        "discovery_detection.py",
        "manipulation_check.py",
        "__init__.py",
    }
    assert {p.name for p in (ANALYSIS / "shared").glob("*.py")} == expected


@pytest.mark.xfail(reason="channels land in Tasks 2-7")
def test_the_flat_layout_is_gone() -> None:
    """A module left at the top level is a module nobody assigned a channel."""
    stray = {p.name for p in ANALYSIS.glob("*.py")} - {"__init__.py"}
    assert stray == set()


def test_behavioral_channel_holds_choice_and_survival() -> None:
    expected = {"survival.py", "session_tests.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "behavioral").glob("*.py")} >= expected


def test_behavioral_estimators_are_reachable_through_the_facade() -> None:
    module = importlib.import_module("squid_game.analysis")
    assert module.fit_cox_forfeit_survival is not None
    assert module.run_all_unit13_hypotheses is not None


def test_cognitive_channel_holds_the_ri_estimators() -> None:
    expected = {"ri_task.py", "ri_call1.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "cognitive").glob("*.py")} >= expected


def test_call1_script_is_a_thin_cli() -> None:
    """The model belongs in the package; the script owns only the CLI.

    Pinned by size rather than by naming every function: the point is that
    the statistics stopped living in scripts/, and a threshold states that
    without freezing the CLI's internals.
    """
    source = (REPO_ROOT / "scripts" / "analyze_call1_ri.py").read_text(encoding="utf-8")
    assert "from squid_game.analysis.cognitive.ri_call1 import" in source
    assert len(source.splitlines()) < 150
