"""A maths-benchmark adapter that is described by YAML, not by code.

``OmniMathAdapter`` hard-codes Omni-MATH's column names, its
``band = int(difficulty)`` rule and its integer-answer filter. That is the
right shape for a dataset we have committed to, and the wrong shape while a
harder replacement is still being chosen: every candidate (HARP, DeepMath,
OlymMATH, the AIME/HMMT sets, ...) differs only in those three details, and
none of them differ in how a maths answer should be read off a model's reply.

``GenericMathAdapter`` therefore takes its dataset knowledge from the task
YAML -- ``fields``, ``band_map``, ``answer_filter``,
``dedupe_on_problem_text`` -- and shares everything else with Omni-MATH
through ``adapters/_math_text.py``. Swapping in a new dataset is then a YAML
edit plus a fetch, with no adapter to write.

Design choices worth knowing, all inherited deliberately from Omni-MATH:

* **Content-derived ids.** Without an ``fields.id`` column the item id is a
  hash of the problem text. ``SeededSampler`` promises that the same seed
  reproduces the same question set; that promise is only true if an id
  survives an upstream row being inserted or reordered.
* **Content-derived dedup winner.** When two rows share a problem text the
  survivor is the one with the smallest ``(difficulty, answer, subject, id)``
  tuple -- a total order over fields the item itself carries -- so file order
  never decides which band a problem sits in.
* **Skips are counted, not silent.** Every dropped row (unreadable JSON,
  missing column, unparsable difficulty, answer rejected by the filter, band
  outside range) is logged, per row up to a cap and then as one summary line.
  A dataset whose ``answer_filter`` is wrong loses most of its rows, and that
  must be visible before a 220-session run, not after.
"""

from __future__ import annotations

import csv
import json
import logging
import random
from collections.abc import Iterator
from pathlib import Path
from typing import Any

from squid_game.tasks.benchmark.adapters._math_text import (
    content_item_id,
    free_text_key,
    last_answer_line,
    numeric_value,
    single_value_integer,
    strip_latex,
    strip_wrappers,
)
from squid_game.tasks.benchmark.config import BenchmarkTaskConfig, FieldMap
from squid_game.tasks.benchmark.item import BenchmarkItem

logger = logging.getLogger(__name__)

#: How many individual skipped rows are logged before the per-row messages
#: stop and only the end-of-load summary remains.
_MAX_ROW_WARNINGS = 20


class GenericMathAdapter:
    """Loads any maths dataset described by a ``BenchmarkTaskConfig``."""

    def __init__(self, config: BenchmarkTaskConfig) -> None:
        if config.band_map is None:
            raise ValueError(
                f"task '{config.name}': GenericMathAdapter needs a `band_map:` "
                "block in the task YAML (mode: int | scale | lookup)."
            )
        self._config = config
        self._fields: FieldMap = config.fields or FieldMap()
        self.name = config.name
        self._prefix = config.item_id_prefix or config.name
        self._excluded_types = {t.strip().casefold() for t in config.exclude_types}
        if self._excluded_types and not self._fields.subject:
            raise ValueError(
                f"task '{config.name}': `exclude_types` needs `fields.subject` "
                "to say which column carries the type."
            )

    # ------------------------------------------------------------------
    # DatasetAdapter surface
    # ------------------------------------------------------------------

    def load(self, raw_path: Path) -> list[BenchmarkItem]:
        """Return the banded, filtered items in *raw_path*."""
        skips: dict[str, int] = {}
        warned = 0
        # problem text -> (tie-break key, item), only used when dedup is on.
        chosen: dict[str, tuple[tuple[str, ...], BenchmarkItem]] = {}
        items: list[BenchmarkItem] = []
        kept = 0

        for row_number, row in _iter_rows(raw_path):
            if row is None:
                warned = self._note_skip(
                    skips, warned, "unreadable row", raw_path, row_number
                )
                continue
            built = self._build_item(row)
            if isinstance(built, str):
                warned = self._note_skip(skips, warned, built, raw_path, row_number)
                continue
            item, sort_key, problem = built
            kept += 1
            if self._config.dedupe_on_problem_text:
                prior = chosen.get(problem)
                if prior is None or sort_key < prior[0]:
                    chosen[problem] = (sort_key, item)
            else:
                items.append(item)

        if self._config.dedupe_on_problem_text:
            items = [item for _, item in chosen.values()]
            duplicates = kept - len(items)
            if duplicates:
                skips["duplicate problem text"] = duplicates

        if skips:
            logger.warning(
                "%s: kept %d items from %s, skipped %d (%s)",
                self.name,
                len(items),
                raw_path.name,
                sum(skips.values()),
                ", ".join(f"{count} {reason}" for reason, count in sorted(skips.items())),
            )
        return items

    def render(self, item: BenchmarkItem, rng: random.Random) -> tuple[str, dict]:
        """Present the problem verbatim; a maths item needs no seeded variation."""
        del rng
        return item.body, {}

    def normalize(self, raw: str) -> str | None:
        """Extract the final ``ANSWER:`` line and normalise it."""
        found = last_answer_line(raw)
        if found is None:
            return None
        return self._normalize_answer(found)

    def matches(self, parsed: str, expected: str, item: BenchmarkItem) -> bool:
        """Compare the two normalised answers.

        ``load`` and ``normalize`` both run the answer through the same
        filter, so by this point equality is a string comparison -- except
        under ``answer_filter: any``, where the comparison is case- and
        whitespace-insensitive.
        """
        del item
        if self._config.answer_filter == "any":
            return free_text_key(str(parsed)) == free_text_key(str(expected))
        return str(parsed) == str(expected)

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _build_item(
        self, row: dict[str, Any]
    ) -> tuple[BenchmarkItem, tuple[str, ...], str] | str:
        """Return ``(item, sort_key, problem)``, or a skip reason string."""
        fields = self._fields
        if fields.problem not in row:
            return f"missing '{fields.problem}' column"
        if fields.answer not in row:
            return f"missing '{fields.answer}' column"
        if fields.difficulty not in row:
            return f"missing '{fields.difficulty}' column"

        problem = str(row[fields.problem] or "").strip()
        if not problem:
            return "empty problem text"

        answer = self._normalize_answer(str(row[fields.answer] or ""))
        if answer is None:
            return f"answer rejected by filter '{self._config.answer_filter}'"

        raw_difficulty = row[fields.difficulty]
        assert self._config.band_map is not None
        band = self._config.band_map.band_for(raw_difficulty)
        if band is None:
            return "difficulty out of range or unmapped"

        subject = ""
        if fields.subject:
            subject = _first_str(row.get(fields.subject))
            if subject.casefold() in self._excluded_types:
                return f"excluded type '{subject}'"

        raw_id = None
        if fields.id:
            raw_id = str(row.get(fields.id) or "").strip() or None
        item_id = (
            f"{self._prefix}-{raw_id}"
            if raw_id
            else content_item_id(self._prefix, problem)
        )

        # Only the columns named in ``fields`` are read. A dataset's worked
        # solution (RIMO-N's ``solution``) therefore never enters ``meta``,
        # never reaches ``TurnResult.task_metadata``, and cannot leak into a
        # prompt -- ``_UNPERSISTED_META_KEYS`` lists it as a second guard.
        item = BenchmarkItem(
            item_id=item_id,
            band=band,
            body=problem,
            answer=answer,
            meta={
                # For a dataset whose difficulty is encoded in its id (a
                # ``regex_tier`` band map) this IS the id, which is why the
                # raw value is kept rather than only the band it produced.
                "raw_difficulty": raw_difficulty,
                "subject": subject,
                "source_id": raw_id or "",
                "dataset": self.name,
            },
        )
        # Strings throughout: a lookup-mode difficulty is categorical, so the
        # key must be a total order that does not assume a number.
        sort_key = (str(raw_difficulty), answer, subject, item_id)
        return item, sort_key, problem

    def _normalize_answer(self, raw: str) -> str | None:
        mode = self._config.answer_filter
        if mode == "single_value_integer":
            return single_value_integer(raw)
        if mode == "numeric":
            return numeric_value(raw)
        text = strip_wrappers(raw).strip()
        return text or None

    def _note_skip(
        self,
        skips: dict[str, int],
        warned: int,
        reason: str,
        raw_path: Path,
        row_number: int,
    ) -> int:
        skips[reason] = skips.get(reason, 0) + 1
        if warned < _MAX_ROW_WARNINGS:
            logger.warning(
                "%s: skipping %s row %d (%s)",
                self.name,
                raw_path.name,
                row_number,
                reason,
            )
            warned += 1
            if warned == _MAX_ROW_WARNINGS:
                logger.warning(
                    "%s: further per-row skip messages suppressed; "
                    "a summary follows at end of load",
                    self.name,
                )
        return warned


def _first_str(value: Any) -> str:
    """Return *value* as a string, taking the first element of a list."""
    if isinstance(value, list):
        return str(value[0]).strip() if value else ""
    return str(value or "").strip()


def _iter_rows(raw_path: Path) -> Iterator[tuple[int, dict[str, Any] | None]]:
    """Yield ``(row_number, row)`` from a JSONL, JSON or CSV/TSV file.

    A row that cannot be decoded yields ``None`` so the caller can count and
    report it rather than aborting the whole load: one malformed line in a
    100k-row download must not cost a run.
    """
    suffix = raw_path.suffix.lower()
    if suffix in (".jsonl", ".ndjson"):
        with raw_path.open(encoding="utf-8") as handle:
            for number, line in enumerate(handle, start=1):
                line = line.strip()
                if not line:
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    yield number, None
                    continue
                yield number, row if isinstance(row, dict) else None
        return

    if suffix == ".json":
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        rows = payload.get("data", payload) if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            raise ValueError(
                f"{raw_path.name}: expected a JSON list (or a dict with a "
                "'data' list) of rows"
            )
        for number, row in enumerate(rows, start=1):
            yield number, row if isinstance(row, dict) else None
        return

    if suffix in (".csv", ".tsv"):
        delimiter = "\t" if suffix == ".tsv" else ","
        with raw_path.open(newline="", encoding="utf-8") as handle:
            for number, row in enumerate(
                csv.DictReader(handle, delimiter=delimiter), start=1
            ):
                yield number, dict(row)
        return

    raise ValueError(
        f"{raw_path.name}: unsupported benchmark file type '{suffix}'. "
        "Export the dataset to .jsonl (preferred), .json or .csv."
    )


# Re-exported so a caller that already imports the adapter can normalise a
# stray answer string the same way the adapter does.
__all__ = ["GenericMathAdapter", "strip_latex"]
