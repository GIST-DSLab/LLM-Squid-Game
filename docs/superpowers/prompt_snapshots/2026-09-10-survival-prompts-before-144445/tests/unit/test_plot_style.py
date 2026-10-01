"""The five plot scripts share one house style, defined once.

Written as a test rather than left to review because the duplication came
back twice already: each new plot script started as a copy of the previous
one, rcParams block included.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
PLOTS = REPO_ROOT / "scripts" / "plots"
PLOT_SCRIPTS = sorted(PLOTS.glob("plot_*.py"))


def test_there_are_five_plot_scripts() -> None:
    """A guard: if this count changes, the assertions below need revisiting."""
    assert len(PLOT_SCRIPTS) == 5


def test_no_plot_script_sets_rcparams_itself() -> None:
    for path in PLOT_SCRIPTS:
        source = path.read_text(encoding="utf-8")
        assert "rcParams" not in source, path.name
        assert "from scripts.plots._style import" in source, path.name
