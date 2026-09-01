"""GPQA adapter (arXiv:2311.12022), gpqa_main with a quality filter.

Difficulty comes from two of GPQA's own columns:

* ``Writer's Difficulty Estimate`` — a 4-level ordinal.
* ``Non-Expert Validator Accuracy`` — how often a searching non-expert got it
  right; the direct measurement of the "google-proof" claim.

``Expert Validator Accuracy`` is NOT a difficulty axis. A low value can mean
the item is ambiguous rather than hard, so it is used as a quality filter
(>= 0.5) instead.

gpqa_diamond is not used as the item pool: it selects on "non-experts got it
wrong", which empties the ladder's lower rungs. Because diamond is a subset of
main, membership is recorded as ``meta["is_diamond"]`` so the diamond slice can
still be reported separately.

The band clamp ``min(max(band, 2), 6)`` folds in BOTH directions: it merges
the sparse band-1 items (3 of them) upward into band 2, but it ALSO folds
band-7 items downward into band 6. Only the top writer level ("Post-graduate
level or harder") can reach band 7: it lands at raw band 6 when a searching
non-expert still got it right more than a third of the time, and at raw band
7 (clamped down to 6) when the non-expert accuracy was at or below a third.
("Hard graduate level" tops out at raw band 5 even in its worst non-expert
bucket, so it never reaches the fold.) That means band 6 mixes two
``non_expert_accuracy`` regimes of the SAME top writer level rather than two
distinct writer-difficulty levels — the top rung of the ladder is therefore
not internally homogeneous on the non-expert-accuracy axis the way the other
bands are. This is intentional (the ladder only has 5 usable rungs given the
available item counts), not an oversight — but analyses that assume a single
non-expert-accuracy regime within a band should not rely on band 6 for that.
"""

from __future__ import annotations

import csv
import random
import re
from pathlib import Path

from squid_game.tasks.benchmark.adapters.base import exact_match
from squid_game.tasks.benchmark.item import BenchmarkItem

_ANSWER_LINE = re.compile(r"ANSWER\s*:\s*([A-Za-z])\b")
_LETTERS = "ABCD"

_WRITER_LEVELS: dict[str, int] = {
    "Easy undergraduate level (or easier)": 0,
    (
        "Hard undergraduate level (could be a question on a hard undergraduate "
        "exam for students majoring in the subject)"
    ): 1,
    (
        "Hard graduate level (could be a question on a hard graduate exam for "
        "PhD students in the domain)"
    ): 2,
    (
        "Post-graduate level or harder (only individuals with years of highly "
        "specialized expertise could reliably answer correctly)"
    ): 3,
}

#: Bands below this are merged upward: band 1 holds only 3 items.
_MIN_BAND = 2
_MAX_BAND = 6


def _as_float(raw: str) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def _read_diamond_ids(main_path: Path) -> set[str]:
    """Return Record IDs present in gpqa_diamond.csv, if it sits alongside."""
    diamond_path = main_path.with_name("gpqa_diamond.csv")
    if not diamond_path.is_file():
        return set()
    with diamond_path.open(encoding="utf-8") as handle:
        return {row["Record ID"] for row in csv.DictReader(handle)}


class GPQAAdapter:
    """Loads GPQA main, bands it, and shuffles choices per session seed."""

    name = "gpqa"

    def load(self, raw_path: Path) -> list[BenchmarkItem]:
        """Return quality-filtered, banded GPQA items."""
        diamond_ids = _read_diamond_ids(raw_path)
        items: list[BenchmarkItem] = []
        with raw_path.open(encoding="utf-8") as handle:
            for row in csv.DictReader(handle):
                expert = _as_float(row.get("Expert Validator Accuracy", ""))
                if expert is None or expert < 0.5:
                    continue
                writer_level = _WRITER_LEVELS.get(
                    row.get("Writer's Difficulty Estimate", "")
                )
                non_expert = _as_float(row.get("Non-Expert Validator Accuracy", ""))
                if writer_level is None or non_expert is None:
                    continue
                band = writer_level * 2 + (1 if non_expert <= 1 / 3 else 0)
                band = min(max(band, _MIN_BAND), _MAX_BAND)
                record_id = row["Record ID"]
                distractors = [
                    row["Incorrect Answer 1"].strip(),
                    row["Incorrect Answer 2"].strip(),
                    row["Incorrect Answer 3"].strip(),
                ]
                items.append(
                    BenchmarkItem(
                        item_id=f"gpqa-{record_id}",
                        band=band,
                        body=row["Question"].strip(),
                        answer=row["Correct Answer"].strip(),
                        meta={
                            "distractors": distractors,
                            "is_diamond": record_id in diamond_ids,
                            "domain": row.get("High-level domain", ""),
                            "subdomain": row.get("Subdomain", ""),
                            "writer_level": writer_level,
                            "non_expert_accuracy": non_expert,
                        },
                    )
                )
        return items

    def render(self, item: BenchmarkItem, rng: random.Random) -> tuple[str, dict]:
        """Shuffle the four options and report where the answer landed.

        The raw CSV always stores the answer in ``Correct Answer``. Rendering
        without a shuffle would pin the answer to one position and let a model
        score above chance from position alone.
        """
        options = [item.answer, *item.meta["distractors"]]
        rng.shuffle(options)
        correct_letter = _LETTERS[options.index(item.answer)]
        lines = [item.body, ""]
        lines.extend(
            f"{letter}. {option}" for letter, option in zip(_LETTERS, options, strict=True)
        )
        return "\n".join(lines), {
            "choice_order": options,
            "correct_letter": correct_letter,
        }

    def normalize(self, raw: str) -> str | None:
        """Return the chosen option letter, or ``None`` when unparseable."""
        found = _ANSWER_LINE.findall(raw or "")
        if not found:
            return None
        letter = found[-1].upper()
        return letter if letter in _LETTERS else None

    def matches(self, parsed: str, expected: str, item: BenchmarkItem) -> bool:
        """Letters compare exactly; ``expected`` comes from ``render``."""
        return exact_match(parsed, expected, item)
