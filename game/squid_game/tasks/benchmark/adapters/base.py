"""The three-method contract every benchmark adapter implements."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Protocol, runtime_checkable

from squid_game.tasks.benchmark.item import BenchmarkItem


@runtime_checkable
class DatasetAdapter(Protocol):
    """Bridges one external dataset onto ``BenchmarkTaskModule``.

    Everything benchmark-specific lives here: filtering, band assignment,
    rendering, and answer normalisation. The task module itself stays
    dataset-agnostic.
    """

    name: str

    def load(self, raw_path: Path) -> list[BenchmarkItem]:
        """Read the raw dataset file and return filtered, banded items."""

    def render(self, item: BenchmarkItem, rng: random.Random) -> tuple[str, dict]:
        """Return the turn's question text plus per-turn metadata.

        Seed-dependent presentation (such as GPQA's choice shuffle) belongs
        here so that identical seeds reproduce identical prompts.
        """

    def normalize(self, raw: str) -> str | None:
        """Extract and normalise the answer from raw LLM output.

        Returns ``None`` when no answer could be parsed.
        """

    def matches(self, parsed: str, expected: str, item: BenchmarkItem) -> bool:
        """Return whether *parsed* answers *item* correctly.

        Defaults to exact equality. Hi-ToM overrides it because an agent may
        answer with either the choice letter or the option's text.
        """


def exact_match(parsed: str, expected: str, item: BenchmarkItem) -> bool:
    """Default ``matches`` implementation: exact string equality."""
    del item
    return str(parsed) == str(expected)
