"""No comment may point at a directory that does not exist.

``docs/design/`` was referenced dozens of times across the repo and has
never existed in the git history -- not deleted, never committed. A
reader following one of those references finds nothing and cannot tell
whether the spec is lost or they are looking in the wrong place. Each
reference is now either a summary of the spec inline, or an explicit
``# spec: lost`` saying what went missing.

Three narrow exemptions apply (see the sets below): Ruling C15 (a live
runtime write path that happens to sit under ``docs/design/v4/assets/``),
a small set of legacy plotting scripts whose input/output path constants
point at Phase 3/4 data that has never been recoverable -- rewriting
those constants would mean fabricating a path nobody can verify, which
is worse than leaving them broken with an honest ``# spec: lost``
comment attached -- and one golden-snapshot-frozen string in
``analyze_phase3.py`` (see the comment there) that cannot be edited
without invalidating ``~/golden/squid-restructure``.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
DEAD = re.compile(r"docs/design/|(?<![\w.])archive/")
SEARCH_ROOTS = ("game", "web", "db", "scripts", "tests")

# Ruling C15: scripts/plots/build_*_diagram.py write .excalidraw files
# into docs/design/v4/assets/ at runtime -- a live write path, not a
# dead documentation citation. test_import_smoke.py documents the same
# path in its SKIPPED list for the same reason.
#
# gen_v4_diagrams.py joined this set in P6 Task 5. At P3+P4 Task 5 it was
# deliberately left OUT: its asset_dir was built from
# Path(__file__).resolve().parents[1], which from
# scripts/plots/gen_v4_diagrams.py resolved to scripts/, not the repo
# root -- an off-by-one that made it write to a different,
# non-overlapping directory than the three scripts below, so exempting
# it then would have hidden a real bug behind the same rationale as the
# three genuine C15 cases. P6 Task 3 fixed that off-by-one
# (parents[1] -> parents[2], proven by running the script); its
# asset_dir now resolves to the same repo-root-relative
# docs/design/v4/assets/ the three siblings write to. The original
# reason for the exclusion is gone, so the exclusion is gone too --
# gen_v4_diagrams.py is now a fourth genuine live-write path, not a
# dead reference and not a bug report. (It happens to build that path
# from split segments -- "docs" / "design" / ... -- rather than the
# literal substring "docs/design/", so DEAD does not even match its
# current source; the file is listed here anyway so its status reflects
# what it actually is, not an accident of string formatting that a
# future edit could flip.)
_C15_LIVE_WRITE_PATH_FILES = frozenset(
    {
        "scripts/plots/build_llm_experience_diagram.py",
        "scripts/plots/build_posthoc_analysis_diagram.py",
        "scripts/plots/build_prompt_flow_diagram.py",
        "scripts/plots/gen_v4_diagrams.py",
        "tests/unit/test_import_smoke.py",
    }
)

# Legacy Phase 3/4 plotting scripts whose PHASE3_DIR/PHASE4_DIR/OUT_DIR
# constants point at an archive/ tree that has never existed in git
# history. Marked "spec: lost" inline (see each file); kept unchanged
# rather than rewritten to an unverifiable replacement path, per the
# no-delete-legacy-code constraint.
_LOST_LEGACY_DATA_PATH_FILES = frozenset(
    {
        "scripts/plots/plot_gemini_heatmaps.py",
        "scripts/plots/plot_gemini_results.py",
    }
)

# One sentence in _render_unit14_md() is baked byte-for-byte into
# unit14_results.md, a golden-snapshot-hashed artefact (see the NOTE
# above that function in analyze_phase3.py). Editing it invalidates
# ~/golden/squid-restructure with no in-place update path available;
# left for whoever owns golden-snapshot re-capture policy to resolve.
_GOLDEN_SNAPSHOT_FROZEN_FILES = frozenset({"scripts/analysis/analyze_phase3.py"})

_EXEMPT_FILES = (
    _C15_LIVE_WRITE_PATH_FILES
    | _LOST_LEGACY_DATA_PATH_FILES
    | _GOLDEN_SNAPSHOT_FROZEN_FILES
)


def test_no_source_file_points_at_a_missing_directory() -> None:
    offenders: list[str] = []
    for base in SEARCH_ROOTS:
        for path in (REPO_ROOT / base).rglob("*.py"):
            if "__pycache__" in path.parts or path.name == Path(__file__).name:
                continue
            rel = path.relative_to(REPO_ROOT).as_posix()
            if rel in _EXEMPT_FILES:
                continue
            for i, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
                if DEAD.search(line):
                    offenders.append(f"{path.relative_to(REPO_ROOT)}:{i}")
    assert offenders == []
