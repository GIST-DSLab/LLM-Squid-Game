"""Omni-MATH adapter (arXiv:2410.07985).

Only integer-answer problems are used. The published ``answer`` field is
free-form LaTeX, and scoring the general case needs an LLM judge (Omni-Judge),
which would inject non-determinism into ``task_success_factor``. Restricting
to integers keeps scoring a pure string comparison at the cost of coverage
(1,952 of 4,428 items, 1,922 of which fall in bands 1-8; the loss is heaviest
in the top bands).

``load`` additionally rejects multi-value list answers (e.g. ``"2, 3"`` or
``"98, 118, 122, 142"``) that a naive comma/space strip would otherwise mash
into a single fake integer: a correctly-answered ``ANSWER: {98, 118, 122,
142}`` would then fail to parse while ``ANSWER: 98,118,122,142`` would pass,
turning a formatting choice into a scoring artefact concentrated in the
harder bands. Ordinary thousands-separator formatting (``"4,002,001"``) is
still accepted, since that *is* a single integer. This tightening applies
only at load time — ``normalize`` (reading a model's own answer) keeps the
permissive comma/space strip, since a model may legitimately format a single
integer answer with a thousands separator or stray whitespace.

``load`` also deduplicates by problem text (keeping the first occurrence):
16 problems in the raw file appear twice under distinct row indices with
identical text, which would otherwise let ``SeededSampler`` draw the same
question twice in one session under different ``item_id``s.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from squid_game.tasks.benchmark.adapters.base import exact_match
from squid_game.tasks.benchmark.item import BenchmarkItem

#: Bands 1-8 only. Band 9's integer-answer pool holds 30 items, too few for a rung.
_MAX_BAND = 8

_ANSWER_LINE = re.compile(r"ANSWER\s*:\s*(.+)", re.IGNORECASE)
_INTEGER = re.compile(r"^-?\d{1,12}$")
_THOUSANDS_GROUPED = re.compile(r"^-?\d{1,3}(,\d{3})+$")


def _strip_latex(text: str) -> str:
    """Remove the LaTeX wrappers models habitually add around a number.

    Used by ``normalize`` to read a model's own answer text, where a
    permissive comma/space strip is the right call (a model may write a
    single integer as ``"1,024"`` or with stray whitespace).
    """
    cleaned = text.strip()
    cleaned = re.sub(r"\\boxed\s*\{(.*)\}", r"\1", cleaned)
    cleaned = cleaned.replace("$", "").replace("\\,", "").replace("{,}", "")
    cleaned = cleaned.replace(",", "").replace(" ", "")
    return cleaned.strip()


def _single_value_integer(raw: str) -> str | None:
    """Return the integer string if *raw* is a single-value integer answer.

    Unlike ``_strip_latex``, this rejects any answer containing internal
    whitespace (a multi-value list such as ``"2, 3, 5"``) and any answer
    containing a comma that is not a thousands separator (``"0,1,3,4,6"``).
    A comma is accepted only when the whole string matches the standard
    thousands-grouping shape (``"4,002,001"``, ``"982,982"``).
    """
    text = raw.strip()
    text = re.sub(r"\\boxed\s*\{(.*)\}", r"\1", text)
    text = text.replace("$", "").replace("\\,", "").replace("{,}", "")
    text = text.strip()
    if re.search(r"\s", text):
        return None
    if "," in text:
        if not _THOUSANDS_GROUPED.match(text):
            return None
        text = text.replace(",", "")
    return text if _INTEGER.match(text) else None


class OmniMathAdapter:
    """Loads Omni-MATH and scores integer answers exactly."""

    name = "omni_math"

    def load(self, raw_path: Path) -> list[BenchmarkItem]:
        """Return single-value-integer items with ``band = int(difficulty)``.

        Deduplicates by problem text (first occurrence wins) so the same
        question cannot be drawn twice under two different ``item_id``s.
        """
        items: list[BenchmarkItem] = []
        seen_problems: set[str] = set()
        with raw_path.open(encoding="utf-8") as handle:
            for index, line in enumerate(handle):
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                answer = _single_value_integer(str(row.get("answer", "")))
                if answer is None:
                    continue
                difficulty = float(row["difficulty"])
                band = int(difficulty)
                if band < 1 or band > _MAX_BAND:
                    continue
                problem = str(row["problem"]).strip()
                if problem in seen_problems:
                    continue
                seen_problems.add(problem)
                domain = row.get("domain") or []
                items.append(
                    BenchmarkItem(
                        item_id=f"omni-{index}",
                        band=band,
                        body=problem,
                        answer=answer,
                        meta={
                            "omni_difficulty": difficulty,
                            "source": row.get("source", ""),
                            "domain": domain[0] if isinstance(domain, list) and domain else "",
                        },
                    )
                )
        return items

    def render(self, item: BenchmarkItem, rng: random.Random) -> tuple[str, dict]:
        """Present the problem verbatim; Omni-MATH needs no seeded variation."""
        del rng
        return item.body, {}

    def normalize(self, raw: str) -> str | None:
        """Extract the final ``ANSWER:`` line and normalise it to an integer."""
        found = _ANSWER_LINE.findall(raw or "")
        if not found:
            return None
        candidate = _strip_latex(found[-1])
        return candidate if _INTEGER.match(candidate) else None

    def matches(self, parsed: str, expected: str, item: BenchmarkItem) -> bool:
        """Integer answers compare exactly."""
        return exact_match(parsed, expected, item)
