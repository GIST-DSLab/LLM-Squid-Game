"""Hi-ToM adapter (EMNLP 2023 Findings).

The dataset ships each story twice, once per ``prompting_type`` (CoTP / VP);
that field only changes the packaged prompt wording, which this project does
not use. Keeping the CoTP rows leaves 600 unique items, 40 per band.

Bands enumerate ``(question_order, story_length)`` with question_order as the
major axis: band = question_order * 3 + story_length, i.e. 1..15.
"""

from __future__ import annotations

import json
import random
import re
from pathlib import Path

from squid_game.tasks.benchmark.item import BenchmarkItem

_ANSWER_LINE = re.compile(r"ANSWER\s*:\s*(.+)", re.IGNORECASE)
_CHOICE_TOKEN = re.compile(r"([A-Z])\.\s*([^,]+)")


def parse_choices(raw: str) -> dict[str, str]:
    """Return ``{letter: option_text}`` parsed from a Hi-ToM choices string."""
    return {
        letter: text.strip()
        for letter, text in _CHOICE_TOKEN.findall(raw or "")
    }


class HiToMAdapter:
    """Loads Hi-ToM and scores the 15-way multiple choice exactly."""

    name = "hi_tom"

    def load(self, raw_path: Path) -> list[BenchmarkItem]:
        """Return CoTP items banded by (question_order, story_length)."""
        payload = json.loads(raw_path.read_text(encoding="utf-8"))
        rows = payload["data"] if isinstance(payload, dict) else payload

        items: list[BenchmarkItem] = []
        for row in rows:
            if row.get("prompting_type") != "CoTP":
                continue
            choices = parse_choices(row.get("choices", ""))
            reverse = {text: letter for letter, text in choices.items()}
            letter = reverse.get(str(row.get("answer", "")).strip())
            if letter is None:
                continue
            order = int(row["question_order"])
            length = int(row["story_length"])
            body = (
                f"Story:\n{str(row['story']).strip()}\n\n"
                f"Question: {str(row['question']).strip()}\n"
                f"Choices: {str(row['choices']).strip()}"
            )
            items.append(
                BenchmarkItem(
                    item_id=f"hitom-{row['sample_id']}",
                    band=order * 3 + length,
                    body=body,
                    answer=letter,
                    meta={
                        "question_order": order,
                        "story_length": length,
                        "deception": bool(row.get("deception", False)),
                        "choice_map": choices,
                    },
                )
            )
        return items

    def render(self, item: BenchmarkItem, rng: random.Random) -> tuple[str, dict]:
        """Present the item verbatim; the choice order is fixed upstream."""
        del rng
        return item.body, {}

    def normalize(self, raw: str) -> str | None:
        """Return the raw answer token (a letter, or an option's text)."""
        found = _ANSWER_LINE.findall(raw or "")
        if not found:
            return None
        candidate = found[-1].strip().rstrip(".")
        if not candidate:
            return None
        if len(candidate) == 1 and candidate.isalpha():
            return candidate.upper()
        return candidate

    def matches(self, parsed: str, expected: str, item: BenchmarkItem) -> bool:
        """Accept the choice letter or the option's own text.

        ``expected`` is always the letter (that is what ``load`` stores), but
        an agent may reasonably answer ``ANSWER: blue_pantry``. Both count.
        """
        if str(parsed) == str(expected):
            return True
        choice_map: dict[str, str] = item.meta.get("choice_map", {})
        return choice_map.get(str(expected), "") == str(parsed)
