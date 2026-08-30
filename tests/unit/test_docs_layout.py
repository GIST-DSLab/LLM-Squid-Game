"""docs/ is split by what a document is for, not by who wrote it.

Four kinds live here and they have different lifetimes: the paper source
changes with the manuscript, design docs are the spec of record, reports
are dated findings that are never revised, and history is an append-only
log of how the work went. Mixing them is what produced a docs/ where two
markdown files sat loose at the top level with no indication of which kind
they were.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DOCS = REPO_ROOT / "docs"
KINDS = ("paper", "design", "reports", "history")


def test_the_four_kinds_exist() -> None:
    for kind in KINDS:
        assert (DOCS / kind).is_dir(), kind


def test_nothing_sits_loose_at_the_top_level() -> None:
    loose = {p.name for p in DOCS.glob("*.md")} - {"README.md"}
    assert loose == set()


def test_every_kind_says_what_belongs_in_it() -> None:
    for kind in KINDS:
        readme = DOCS / kind / "README.md"
        assert readme.exists(), kind
        assert len(readme.read_text(encoding="utf-8").split()) >= 20, kind
