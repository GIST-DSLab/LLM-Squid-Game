"""Every ``__file__``-anchored repo-root derivation must resolve to the repo root.

The Critical section of the 2026-08-30 P1 whole-branch fix wave found eight
lines across ``scripts/``, ``web/`` and ``db/`` where a directory move
changed a file's depth below the repo root but its ``Path(__file__)...``
anchor was never updated to match: each was correct at the merge-base
(``972c88a``) and wrong after the move. No per-task review could have
caught this -- each move was correct inside its own diff; only a
whole-tree pass sees that the arithmetic and the tree drifted apart.

This test walks the same three trees, finds every line that derives a
path by climbing two or more parent directories from ``__file__``, and
asserts the climb actually lands on the repo root. It is agnostic to how
the anchor is spelled -- ``Path(__file__).resolve().parents[N]`` or a
chain of ``.parent``s, with or without ``.resolve()`` -- because the bug
this pins is arithmetic (the depth number), not a particular spelling,
and the next file this class of bug hits may spell it differently.

A single ``.parent`` is deliberately excluded. That is the
sibling-file-lookup pattern -- a module locating a resource next to
itself, e.g. ``scripts/render/render_excalidraw.py``'s
``Path(__file__).parent / "render_template.html"`` or
``game/squid_game/prompts/__init__.py``'s ``Path(__file__).parent`` for
its own package directory -- not a repo-root anchor. Asserting it against
the repo root would be a category error, not a check.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SEARCH_ROOTS = ("scripts", "web", "db")

# ``Path(__file__).resolve().parents[N]`` (or without ``.resolve()``) -- the
# explicit-index spelling used throughout this repo's own anchors.
_BRACKET_RE = re.compile(r"Path\(__file__\)(?:\.resolve\(\))?\.parents\[(\d+)\]")

# A chain of two or more ``.parent`` hops, with or without ``.resolve()``.
# One hop alone is the sibling-lookup pattern and is not matched here.
_CHAIN_RE = re.compile(r"Path\(__file__\)(?:\.resolve\(\))?((?:\.parent){2,})")


def _climb(path: Path, hops: int) -> Path:
    for _ in range(hops):
        path = path.parent
    return path


def _find_anchors() -> list[tuple[Path, int, int, str]]:
    """Return ``(file, line_no, hops, matched_text)`` for every anchor found."""
    hits: list[tuple[Path, int, int, str]] = []
    for base in SEARCH_ROOTS:
        for path in sorted((REPO_ROOT / base).rglob("*.py")):
            if "__pycache__" in path.parts:
                continue
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), 1
            ):
                # Skip whole-line comments -- e.g. gen_v4_diagrams.py's own
                # header narrates a since-fixed ``parents[1]`` bug in prose,
                # which is documentation, not a live anchor to check.
                if line.lstrip().startswith("#"):
                    continue
                for m in _BRACKET_RE.finditer(line):
                    # Path.parents[N] is N+1 hops up from the file itself.
                    hits.append((path, lineno, int(m.group(1)) + 1, m.group(0)))
                for m in _CHAIN_RE.finditer(line):
                    hops = m.group(1).count(".parent")
                    hits.append((path, lineno, hops, m.group(0)))
    return hits


_ANCHORS = _find_anchors()


def test_the_walk_finds_the_known_anchors() -> None:
    """Guard against the walk silently finding nothing (e.g. a regex gone stale)."""
    files = {p.relative_to(REPO_ROOT).as_posix() for p, _, _, _ in _ANCHORS}
    assert len(_ANCHORS) >= 8
    assert "web/squid_arena/anthropic_proxy.py" in files
    assert "scripts/arena/backup_web_arena.py" in files
    assert "scripts/arena/seed_web_arena.py" in files
    assert "scripts/analysis/orchestrate_posthoc.py" in files
    assert "scripts/dev/merge_proxy_thinking.py" in files
    assert "scripts/dev/crop_guard_sprites.py" in files
    assert "scripts/analysis/thinking_analysis.py" in files
    assert "scripts/dev/benchmark_mlx_vs_ollama.py" in files


@pytest.mark.parametrize(
    "path,line_no,hops,text",
    _ANCHORS,
    ids=[f"{p.relative_to(REPO_ROOT)}:{ln}" for p, ln, _, _ in _ANCHORS],
)
def test_file_anchor_resolves_to_repo_root(
    path: Path, line_no: int, hops: int, text: str
) -> None:
    resolved = _climb(path.resolve(), hops)
    assert resolved == REPO_ROOT, (
        f"{path.relative_to(REPO_ROOT)}:{line_no}: `{text}` climbs {hops} "
        f"director{'y' if hops == 1 else 'ies'} from the file and lands on "
        f"{resolved}, not the repo root {REPO_ROOT}"
    )
