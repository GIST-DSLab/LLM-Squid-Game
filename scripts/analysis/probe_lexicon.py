"""CLI for eyeballing the frozen threat lexicon and the leakage mask.

The lexicon patterns, the mask-set definitions, and the masking function
live in ``squid_game.analysis.semantic.lexicon`` -- this script only reads
one piece of text (``--text``, ``--file``, or stdin), runs the frozen
threat-mention check against it, and prints the raw text next to its
masked form for the requested mask sets.

Usage
-----
    uv run python -m scripts.probe_lexicon --text "the weight corruption event..."
    uv run python -m scripts.probe_lexicon --file trace.txt --mask threat --mask pull
"""

from __future__ import annotations

import argparse
import sys

from squid_game.analysis.semantic.lexicon import (
    MASK_SETS,
    build_masker,
    code_threat_mention,
    mask_text,
)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--text", help="Text to check inline.")
    parser.add_argument("--file", help="Path to a text file to check.")
    parser.add_argument(
        "--mask", action="append", choices=sorted(MASK_SETS), dest="mask_sets",
        default=None, help="Mask set(s) to apply (default: all).",
    )
    args = parser.parse_args()

    if args.text is not None:
        text = args.text
    elif args.file is not None:
        text = open(args.file, encoding="utf-8").read()
    else:
        text = sys.stdin.read()

    mask_sets = args.mask_sets if args.mask_sets is not None else sorted(MASK_SETS)
    masker = build_masker(mask_sets)

    verdict = code_threat_mention(text)
    print(f"lexicon mention: {verdict.matched}")
    print(f"matched terms: {verdict.matched_terms}")
    print(f"mask sets applied: {mask_sets}")
    print("--- raw ---")
    print(text)
    print("--- masked ---")
    print(mask_text(text, masker))


if __name__ == "__main__":
    main()
