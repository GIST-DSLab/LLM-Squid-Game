"""pytest configuration must be explicit, not inherited from rootdir side effects.

Before this test, ``pyproject.toml`` carried no ``[tool.pytest.ini_options]``
section. Imports such as ``from squid_store import ...`` resolved
only because pytest inserts the rootdir into ``sys.path`` when it finds no
``__init__.py`` beside the test file. That is an accident, and it breaks the
moment the tree is split into several installed packages. Pin the settings
so the accident becomes a contract.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def ini_options() -> dict:
    root = Path(__file__).resolve().parents[2]
    with (root / "pyproject.toml").open("rb") as fh:
        data = tomllib.load(fh)
    return data["tool"]["pytest"]["ini_options"]


def test_testpaths_covers_every_suite(ini_options: dict) -> None:
    assert ini_options["testpaths"] == ["tests/unit", "tests/integration"]


def test_pythonpath_includes_repo_root_and_every_tier(ini_options: dict) -> None:
    assert ini_options["pythonpath"] == [".", "src", "db", "web"]


def test_asyncio_mode_is_auto(ini_options: dict) -> None:
    assert ini_options["asyncio_mode"] == "auto"
