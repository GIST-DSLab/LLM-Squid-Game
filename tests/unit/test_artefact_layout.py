"""outputs/ is raw data; results/ is what the pipeline made from it.

The split is by cost of recreation. outputs/ holds 666 MB of LFS-tracked
session traces from four canonical runs that cost real API budget to
produce. results/ holds artefacts one command regenerates. Keeping them
in one directory meant every rule about one of them had to carve out an
exception for the other.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_outputs_holds_only_raw_data() -> None:
    subdirs = {p.name for p in (REPO_ROOT / "outputs").iterdir() if p.is_dir()}
    assert subdirs == {"final_results", "web_arena"}


def test_results_holds_the_regenerable_artefacts() -> None:
    results = REPO_ROOT / "results"
    assert (results / "call1_ri_analysis").is_dir()
    assert (results / "reasoning_probe").is_dir()


def test_no_jsonl_escaped_lfs_tracking() -> None:
    """A .jsonl outside outputs/ is only safe if .gitattributes says so."""
    attributes = (REPO_ROOT / ".gitattributes").read_text(encoding="utf-8")
    stray = list((REPO_ROOT / "results").rglob("*.jsonl"))
    if stray:
        assert "results/**/*.jsonl filter=lfs" in attributes, [str(p) for p in stray]


def test_figures_directory_no_longer_exists() -> None:
    """figures/ was split into assets/brand/ and assets/figures/ (P6 Task 3)."""
    assert not (REPO_ROOT / "figures").exists()


def test_assets_holds_brand_and_figures() -> None:
    assets = REPO_ROOT / "assets"
    brand = assets / "brand"
    figures = assets / "figures"
    assert (brand / "GistLab Logo").is_dir()
    assert (figures / "README.md").is_file()
    assert (figures / "rules-demo" / "how-to-play.gif").is_file()


def test_rules_demo_frames_are_not_tracked_intermediates() -> None:
    """The frame sequence is build_gif.py's input, not a committed asset."""
    ignore = (REPO_ROOT / "assets" / "figures" / "rules-demo" / ".gitignore").read_text(
        encoding="utf-8"
    )
    assert "frames/" in ignore
