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
    expected = {"ri_task.py", "ri_call1.py", "ri_forfeit.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "cognitive").glob("*.py")} >= expected


def test_forfeit_regression_actually_split() -> None:
    assert not (ANALYSIS / "forfeit_regression.py").exists()
    assert (ANALYSIS / "cognitive" / "ri_forfeit.py").exists()
    assert (ANALYSIS / "selfreport" / "reason_convergence.py").exists()


def test_regime_stratification_actually_split() -> None:
    assert not (ANALYSIS / "regime_stratification.py").exists()
    assert (ANALYSIS / "behavioral" / "regime.py").exists()
    assert (ANALYSIS / "selfreport" / "psuccess.py").exists()

    # Pin the channel boundary (fix round 1): behavioral/regime.py must
    # not itself index a DataFrame on the agent's self-reported
    # psuccess_self -- that read belongs to selfreport/psuccess.py's
    # compute_floor_bound / compute_ev_delta_s. The one allowed mention
    # is the psuccess_col default value passed through to them.
    regime_source = (ANALYSIS / "behavioral" / "regime.py").read_text(
        encoding="utf-8"
    )
    assert regime_source.count('"psuccess_self"') == 1
    assert 'out["psuccess_self"]' not in regime_source
    assert "out[psuccess_col]" not in regime_source
    assert "df[psuccess_col]" not in regime_source

    # And selfreport/psuccess.py must not read the survival/cap columns
    # that stay in the behavioural module.
    psuccess_source = (ANALYSIS / "selfreport" / "psuccess.py").read_text(
        encoding="utf-8"
    )
    assert 'df["cap_bound"]' not in psuccess_source
    assert 'df["forfeit"]' not in psuccess_source
    assert "CAP_EPSILON" not in psuccess_source
    assert "reward_ceiling" not in psuccess_source


def test_the_framing_sets_are_defined_once() -> None:
    """A split that copies the constants is a split that will drift apart."""
    hits = [
        path.name
        for path in ANALYSIS.rglob("*.py")
        if "_CORRUPTION_FRAMINGS: frozenset" in path.read_text(encoding="utf-8")
    ]
    assert hits == ["loaders.py"]


def test_shared_loaders_owns_turn_observations() -> None:
    loaders = importlib.import_module("squid_game.analysis.shared.loaders")
    assert callable(loaders.turn_observations)
    assert callable(loaders.forfeit_events)


def test_selfreport_channel_holds_reason_convergence() -> None:
    expected = {"reason_convergence.py", "__init__.py"}
    assert {p.name for p in (ANALYSIS / "selfreport").glob("*.py")} >= expected


def test_selfreport_estimators_are_reachable_through_the_facade() -> None:
    module = importlib.import_module("squid_game.analysis")
    assert module.reason_distribution is not None
    assert module.run_all_unit14_hypotheses is not None


def test_cognitive_estimators_are_reachable_through_the_facade() -> None:
    module = importlib.import_module("squid_game.analysis")
    assert module.fit_choice_asymmetric_model is not None
    assert module.fit_task_spillover_model is not None


def test_call1_script_is_a_thin_cli() -> None:
    """The model belongs in the package; the script owns only the CLI.

    Pinned by size rather than by naming every function: the point is that
    the statistics stopped living in scripts/, and a threshold states that
    without freezing the CLI's internals.
    """
    source = (REPO_ROOT / "scripts" / "analyze_call1_ri.py").read_text(encoding="utf-8")
    assert "from squid_game.analysis.cognitive.ri_call1 import" in source
    assert len(source.splitlines()) < 150
