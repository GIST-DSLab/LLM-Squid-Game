"""Immutable representation of a single benchmark question."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class BenchmarkItem(BaseModel):
    """One question drawn from an external benchmark dataset.

    Attributes:
        item_id: Stable identifier within the source dataset.
        band: 1-based difficulty band assigned by the adapter.
        body: Fully rendered question text shown to the agent, including
            answer choices for multiple-choice benchmarks.
        answer: Normalised ground-truth answer, comparable by ``==`` with
            the output of ``DatasetAdapter.normalize``.
        meta: Adapter-specific detail preserved for analysis (source
            difficulty value, domain, ``is_diamond``, ...).
    """

    model_config = {"frozen": True}

    item_id: str
    band: int = Field(ge=1)
    body: str
    answer: str
    meta: dict[str, Any] = Field(default_factory=dict)
