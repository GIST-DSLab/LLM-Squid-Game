"""Shared CLI argument-building helper for scripts/analysis/ drivers.

Measured fact (P3+P4 Task 3, fix round 1 -- see the "P3+P4 Task 3" section
of docs/history/plans/2026-08-30-p0-baseline.md for the full
population table over every argparse-using script in this directory):
the analysis CLIs do NOT share the single-run ``run_dir`` + ``--model`` +
``--out`` contract the phase plan anticipated -- only
``analyze_phase3.py`` implements part of that shape (it has no ``--out``
at all).

What genuinely repeats, four times, is a different argument: an
*aggregate* root directory -- "the directory holding the per-model run
directories" (as opposed to a single run directory), default
``outputs/final_results`` -- spelled ``--root`` (``type=Path``) in
``analyze_call1_ri.py``, ``probe_reasoning_embeddings.py`` and
``analyze_tc.py``, and ``--results-root`` (plain ``str``) in
``analyze_verbal_reason.py``.

``add_aggregate_root_argument`` is the one shared entry point for that
argument. It changes no caller's CLI surface: each caller supplies its
own flag spelling, type, default and help text explicitly, so ``--help``
output and ``args.<dest>`` stay byte-identical to what each script had
before this extraction.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any, Callable

# The value three of the four callers share verbatim
# (``analyze_call1_ri.py``, ``probe_reasoning_embeddings.py``,
# ``analyze_tc.py``): ``--root``, ``type=Path``,
# ``default=Path("outputs/final_results")``. The fourth
# (``analyze_verbal_reason.py``) overrides every one of these.
DEFAULT_ROOT_FLAG = "--root"
DEFAULT_ROOT = Path("outputs/final_results")


def add_aggregate_root_argument(
    parser: argparse.ArgumentParser,
    *,
    flag: str = DEFAULT_ROOT_FLAG,
    type_: Callable[[str], Any] | None = Path,
    default: Any = DEFAULT_ROOT,
    help: str | None = None,  # noqa: A002 -- matches argparse's own kwarg name
) -> argparse.Action:
    """Add the "directory holding the per-model run directories" argument.

    This is an *aggregate* root (many run directories underneath it), not
    a single run directory -- do not confuse it with a ``run_dir``
    positional or an ``output_dir`` (``analyze_phase3.py`` takes one of
    those instead and is not a caller of this helper).

    Every caller keeps its own flag spelling / type / default / help
    text via the keyword-only parameters below; this only centralises
    the shared *meaning* in one place instead of four near-identical
    ``add_argument`` blocks.
    """
    kwargs: dict[str, Any] = {"default": default}
    if type_ is not None:
        kwargs["type"] = type_
    if help is not None:
        kwargs["help"] = help
    return parser.add_argument(flag, **kwargs)
