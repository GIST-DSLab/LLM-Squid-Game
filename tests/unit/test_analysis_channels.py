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
