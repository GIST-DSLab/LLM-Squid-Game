"""Every script must declare what kind of thing it is by where it lives.

A flat scripts/ directory of forty files says nothing about which of them
the canonical pipeline runs and which were one-off. The five directories
answer that, and this test keeps the answer from decaying: a new file
dropped at the top level fails here rather than quietly joining the pile.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"
CATEGORIES = ("run", "analysis", "plots", "arena", "dev", "render")


def test_no_python_script_sits_at_the_top_level() -> None:
    stray = {p.name for p in SCRIPTS.glob("*.py")} - {"__init__.py"}
    assert stray == set()


def test_every_category_exists_and_is_a_package() -> None:
    for name in CATEGORIES:
        directory = SCRIPTS / name
        assert directory.is_dir(), name
        if name != "render":
            assert (directory / "__init__.py").exists(), name


def test_every_category_says_what_it_is_for() -> None:
    """A directory without a README is a directory whose rule is in someone's head."""
    for name in CATEGORIES:
        readme = SCRIPTS / name / "README.md"
        assert readme.exists(), name
        assert len(readme.read_text(encoding="utf-8").split()) >= 15, name
