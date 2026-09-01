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

The band clamp ``min(max(band, 2), 6)`` folds in BOTH directions. Upward, it
merges everything below band 2 into band 2: the sparse band-1 items (3 of
them) AND the raw band-0 items (writer level 0 with non-expert accuracy above
1/3). Band 2 therefore mixes writer levels 0 and 1, not just two non-expert
accuracy buckets of one writer level — the bottom rung is the mirror of the
top rung's inhomogeneity described below. Downward, it folds band-7 items
into band 6. Only the top writer level ("Post-graduate
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
import logging
import random
import re
from pathlib import Path

from squid_game.tasks.benchmark.adapters.base import exact_match
from squid_game.tasks.benchmark.item import BenchmarkItem

logger = logging.getLogger(__name__)

_ANSWER_LINE = re.compile(r"ANSWER\s*:\s*([A-Za-z])\b", re.IGNORECASE)
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
        """Return quality-filtered, banded GPQA items.

        Rows with an answer/distractor text collision after strip -- either
        the ``Correct Answer`` duplicating one of the ``Incorrect Answer``
        fields, or two ``Incorrect Answer`` fields duplicating each other --
        are dropped and counted: see the comment at the guard. The count is
        logged at WARNING so the filter is visible rather than silent. On the
        real gpqa_main.csv it drops 3 of the 419 quality-filtered rows
        (measured 2026-09-01): 1 answer/distractor collision and 2
        distractor/distractor collisions, leaving 416; every band still
        exceeds its 6-turn ladder demand. Only the answer/distractor kind
        could have made ``options.index`` in ``render`` pick the wrong
        position -- a duplicated pair of distractors doesn't touch where the
        answer sits -- but the guard drops all three anyway, since a
        duplicated option makes the item a defective multiple-choice question
        regardless of which pair collides.
        """
        diamond_ids = _read_diamond_ids(raw_path)
        items: list[BenchmarkItem] = []
        collisions = 0
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
                answer = row["Correct Answer"].strip()
                distractors = [
                    row["Incorrect Answer 1"].strip(),
                    row["Incorrect Answer 2"].strip(),
                    row["Incorrect Answer 3"].strip(),
                ]
                # ``render`` locates the answer with ``options.index``, which
                # returns the FIRST match. A Correct Answer textually equal to
                # one of the Incorrect Answer fields (after strip) would give a
                # duplicated choice list and a correct_letter that may point at
                # the wrong position -- a silent scoring corruption. Drop such
                # rows instead, so the failure is a visible, countable filter.
                if len({answer, *distractors}) != 4:
                    collisions += 1
                    logger.debug(
                        "GPQA %s dropped: answer/distractor text collision",
                        record_id,
                    )
                    continue
                items.append(
                    BenchmarkItem(
                        item_id=f"gpqa-{record_id}",
                        band=band,
                        body=row["Question"].strip(),
                        answer=answer,
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
        if collisions:
            logger.warning(
                "GPQA: dropped %d item(s) for an answer/distractor text "
                "collision (the answer duplicating a distractor, or two "
                "identical distractors); a duplicated option makes the item "
                "a defective multiple-choice question either way, though "
                "only an answer/distractor collision could have made "
                "render() misidentify the correct option position.",
                collisions,
            )
        return items

    def render(self, item: BenchmarkItem, rng: random.Random) -> tuple[str, dict]:
        """Shuffle the four options and report where the answer landed.

        The raw CSV always stores the answer in ``Correct Answer``. Rendering
        without a shuffle would pin the answer to one position and let a model
        score above chance from position alone.

        ``options.index`` is safe here because ``load`` has already dropped any
        row whose answer text duplicates a distractor.
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
