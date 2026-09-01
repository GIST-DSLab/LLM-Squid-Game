"""The analysis CLIs share one aggregate-root argument, defined once.

Measured fact (P3+P4 Task 3, fix round 1 -- see the "P3+P4 Task 3" section
of docs/history/plans/2026-08-30-p0-baseline.md for the full
population table over every argparse-using script under
scripts/analysis/): the phase plan anticipated a single-run ``run_dir`` +
``--model`` + ``--out`` contract consuming ``load_seasons``, but that
shape has zero full implementers among the ten argparse-using scripts in
this directory (the closest, ``analyze_phase3.py``, is missing ``--out``
entirely and is not a caller of this helper).

What genuinely repeats four times is a different argument: an *aggregate*
root directory ("the directory holding the per-model run directories",
default ``outputs/final_results``) -- spelled ``--root`` (``type=Path``)
in three scripts and ``--results-root`` (plain ``str``) in a fourth. This
test pins that extraction and its four callers.
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
ANALYSIS = REPO_ROOT / "scripts" / "analysis"

# The four scripts measured (Step 1) to genuinely share the aggregate-root
# argument's meaning. Confirmed by direct reading, not assumed.
CONVERTED = [
    "analyze_call1_ri.py",
    "probe_reasoning_embeddings.py",
    "analyze_tc.py",
    "analyze_verbal_reason.py",
]


def test_the_helper_adds_the_default_root_flag() -> None:
    from scripts.analysis._cli import add_aggregate_root_argument

    parser = argparse.ArgumentParser()
    add_aggregate_root_argument(parser)

    args = parser.parse_args([])
    assert args.root == Path("outputs/final_results")

    args = parser.parse_args(["--root", "outputs/other_results"])
    assert args.root == Path("outputs/other_results")


def test_the_helper_lets_a_caller_override_flag_type_and_default() -> None:
    """analyze_verbal_reason.py spells this --results-root with a plain str
    default, not --root with type=Path -- the helper must let it keep that
    exact spelling rather than forcing a unified interface."""
    from scripts.analysis._cli import add_aggregate_root_argument

    parser = argparse.ArgumentParser()
    add_aggregate_root_argument(
        parser,
        flag="--results-root",
        type_=None,
        default="outputs/final_results",
    )

    args = parser.parse_args([])
    assert args.results_root == "outputs/final_results"
    assert isinstance(args.results_root, str)

    args = parser.parse_args(["--results-root", "outputs/other"])
    assert args.results_root == "outputs/other"


def test_the_helper_passes_through_help_text() -> None:
    from scripts.analysis._cli import add_aggregate_root_argument

    parser = argparse.ArgumentParser(prog="x")
    add_aggregate_root_argument(parser, help="Directory holding the per-model run directories.")

    help_text = parser.format_help()
    assert "Directory holding the per-model run directories." in help_text


@pytest.mark.parametrize("name", CONVERTED)
def test_the_converted_scripts_use_it(name: str) -> None:
    source = (ANALYSIS / name).read_text(encoding="utf-8")
    assert "from scripts.analysis._cli import add_aggregate_root_argument" in source, name
