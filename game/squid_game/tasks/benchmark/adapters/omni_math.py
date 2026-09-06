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

``load`` also deduplicates by problem text: 22 problems in the raw file appear
twice with identical text. Of those, 16 duplicate groups survive the
integer-answer and band filters above and actually reach dedup; it is those 16
that would otherwise let ``SeededSampler`` draw the same question twice in one
session under different ``item_id``s.

Both the ``item_id`` and the dedup winner are derived from CONTENT, never from
the row's position in the file. ``SeededSampler`` documents that "items are
sorted by ``item_id`` before shuffling so a change in file order does not
silently change a 'reproduced' run", which was true for GPQA (``Record ID``)
and Hi-ToM (``sample_id``) but false here while the id was the raw line index.
Inserting or reordering one upstream row shifted every later id, so a re-run
at the same seed drew a different question set while claiming reproduction —
and the manifest mismatch that would have hinted at it is only a
``logger.warning``.

The dedup rule matters just as much as the id. Of the 16 duplicate groups that
reach dedup, 13 carry a divergent ``(difficulty, answer, source, domain)``
tiebreak key across their two rows, 8 of those carry divergent ``difficulty``
(e.g. 1.5 vs 3.0), and 5 carry a divergent *band* (``int(difficulty)``) — the
figure that actually matters, since a "first occurrence wins" rule would let
file order decide which ladder rung a problem sits on only for those 5. (18 of
the raw file's 22 duplicate groups carry divergent metadata of some kind
before the integer-answer/band filters are applied; the narrower counts above
are what ``load`` actually dedups over.) The winner is now the row with the
smallest ``(difficulty, answer, source, domain)`` tuple — a total order over
fields the item itself carries, so it is identical under any input ordering;
when the tuple ties, the two candidate items are field-for-field identical and
the choice is immaterial.
"""

from __future__ import annotations

import json
import random
from pathlib import Path

from squid_game.tasks.benchmark.adapters._math_text import (
    INTEGER as _INTEGER,
    THOUSANDS_GROUPED as _THOUSANDS_GROUPED,
    content_item_id,
    last_answer_line,
    single_value_integer as _single_value_integer,
    strip_latex as _strip_latex,
)
from squid_game.tasks.benchmark.adapters.base import exact_match
from squid_game.tasks.benchmark.item import BenchmarkItem

#: Bands 1-8 only. Band 9's integer-answer pool holds 30 items, too few for a rung.
_MAX_BAND = 8

# ``_strip_latex`` / ``_single_value_integer`` / the two regexes moved to
# ``_math_text`` (2026-09-06) when ``GenericMathAdapter`` needed the identical
# behaviour; they are re-exported under their old private names so that this
# module's public behaviour, and anything importing them, is unchanged.

__all__ = ["OmniMathAdapter"]


def _problem_id(problem: str) -> str:
    """Return a stable, content-derived ``item_id`` for *problem*."""
    return content_item_id("omni", problem)


class OmniMathAdapter:
    """Loads Omni-MATH and scores integer answers exactly.

    Args:
        max_band: Highest band to keep. Defaults to 8 for the reason in
            ``_MAX_BAND``: band 9 holds 30 integer-answer items, too few to
            fill a ladder rung across 30 seeds. A ``fixed_items`` task
            config has no rungs and names its questions outright, so it
            raises the cap to 9 via ``BenchmarkTaskConfig.max_band`` — band
            9 is where the universally-wrong items concentrate.
    """

    name = "omni_math"

    def __init__(self, max_band: int = _MAX_BAND) -> None:
        self._max_band = max_band

    def load(self, raw_path: Path) -> list[BenchmarkItem]:
        """Return single-value-integer items with ``band = int(difficulty)``.

        Both the ``item_id`` and the dedup winner are derived from content,
        never from the row's position in the file — see the module docstring
        for why.
        """
        # problem text -> (tie-break key, item). The key is built only from
        # fields the item itself carries, so the winner of a duplicate group
        # is the same whatever order the rows arrived in.
        chosen: dict[str, tuple[tuple, BenchmarkItem]] = {}
        with raw_path.open(encoding="utf-8") as handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                row = json.loads(line)
                answer = _single_value_integer(str(row.get("answer", "")))
                if answer is None:
                    continue
                difficulty = float(row["difficulty"])
                band = int(difficulty)
                if band < 1 or band > self._max_band:
                    continue
                problem = str(row["problem"]).strip()
                domain_list = row.get("domain") or []
                domain = (
                    domain_list[0]
                    if isinstance(domain_list, list) and domain_list
                    else ""
                )
                source = str(row.get("source", ""))
                item = BenchmarkItem(
                    item_id=_problem_id(problem),
                    band=band,
                    body=problem,
                    answer=answer,
                    meta={
                        "omni_difficulty": difficulty,
                        "source": source,
                        "domain": domain,
                    },
                )
                key = (difficulty, answer, source, domain)
                prior = chosen.get(problem)
                if prior is None or key < prior[0]:
                    chosen[problem] = (key, item)
        return [item for _, item in chosen.values()]

    def render(self, item: BenchmarkItem, rng: random.Random) -> tuple[str, dict]:
        """Present the problem verbatim; Omni-MATH needs no seeded variation."""
        del rng
        return item.body, {}

    def normalize(self, raw: str) -> str | None:
        """Extract the final ``ANSWER:`` line and normalise it to an integer."""
        found = last_answer_line(raw)
        if found is None:
            return None
        candidate = _strip_latex(found)
        return candidate if _INTEGER.match(candidate) else None

    def matches(self, parsed: str, expected: str, item: BenchmarkItem) -> bool:
        """Integer answers compare exactly."""
        return exact_match(parsed, expected, item)
