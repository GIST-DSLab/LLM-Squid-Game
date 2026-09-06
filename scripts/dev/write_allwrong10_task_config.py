"""Rewrite ``configs/tasks_allwrong10/omni_math.yaml`` from the finder's result.

``scripts/dev/find_universally_wrong_items.py`` writes
``results/allwrong10/allwrong10.json``; this turns that into the task config the
runs actually read. Kept as a script rather than done by hand so that a re-run
of the sieve (new model in the line-up, a wider band scan) does not leave the
YAML silently describing the previous set.

Only the ``fixed_items`` block and the provenance comment above it are
rewritten. The header comment, ``max_band`` and everything else in the file are
preserved, so hand-written notes there survive.

Usage::

    uv run python scripts/dev/write_allwrong10_task_config.py
    uv run python scripts/dev/write_allwrong10_task_config.py --check
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SOURCE = _REPO_ROOT / "results" / "allwrong10" / "allwrong10.json"
DEFAULT_TARGET = _REPO_ROOT / "configs" / "tasks_allwrong10" / "omni_math.yaml"

_MARKER = "# --- generated block (write_allwrong10_task_config.py) ---"


def render_block(payload: dict) -> str:
    """Return the ``total_turns`` + ``fixed_items`` YAML block for *payload*."""
    items = payload.get("items") or []
    if not items:
        raise SystemExit("allwrong10.json carries no items")
    models = ", ".join(payload.get("models") or [])
    attempts = payload.get("attempts_per_model", "?")
    lines = [
        _MARKER,
        f"# {len(items)} item(s) that {models} each answered wrongly on all",
        f"# {attempts} attempts, sieved hardest-band-first. Written {date.today()}.",
        f"total_turns: {len(items)}",
        "max_band: 9",
        "fixed_items:",
    ]
    for item in items:
        head = " ".join(str(item.get("problem", "")).split())[:60]
        lines.append(
            f'  - "{item["item_id"]}"   # band {item["band"]}, '
            f'answer {item["answer"]} — {head}'
        )
    return "\n".join(lines) + "\n"


def rewrite(target: Path, block: str) -> str:
    """Return *target*'s text with its generated block replaced by *block*."""
    text = target.read_text(encoding="utf-8")
    marker_at = text.find(_MARKER)
    if marker_at >= 0:
        return text[:marker_at] + block
    # First run against the hand-written placeholder: drop from the first
    # `total_turns:` line onwards and append the generated block.
    lines = text.splitlines(keepends=True)
    for index, line in enumerate(lines):
        if line.startswith("total_turns:"):
            return "".join(lines[:index]) + block
    return text.rstrip("\n") + "\n" + block


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--target", type=Path, default=DEFAULT_TARGET)
    parser.add_argument(
        "--check",
        action="store_true",
        help="exit 1 when the target is out of date; write nothing.",
    )
    args = parser.parse_args(argv)

    if not args.source.is_file():
        print(f"no finder output at {args.source}", file=sys.stderr)
        return 2
    payload = json.loads(args.source.read_text(encoding="utf-8"))
    updated = rewrite(args.target, render_block(payload))

    if args.check:
        if args.target.read_text(encoding="utf-8") == updated:
            print(f"{args.target} is up to date")
            return 0
        print(f"{args.target} is stale — rerun without --check", file=sys.stderr)
        return 1

    args.target.write_text(updated, encoding="utf-8")
    print(f"wrote {len(payload.get('items') or [])} item(s) to {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
