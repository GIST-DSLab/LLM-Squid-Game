"""All three adapters must read the ``ANSWER:`` line case-insensitively.

GPQA's ``_ANSWER_LINE`` lacked ``re.IGNORECASE`` while Hi-ToM's and
Omni-MATH's had it. ``Answer: C`` therefore normalised to ``None`` on GPQA
and parsed fine on the other two, so a model that capitalises the label —
common — scored 0 on every GPQA turn. That is a between-benchmark artefact
with nothing to do with GPQA's content, and it propagates into
``task_success_factor``, ``psuccess_self`` and the CONTINUE reward.

This test is deliberately cross-adapter: the defect was an inconsistency
between siblings, so the guard belongs at the level where they are compared.
"""

from __future__ import annotations

import pytest

from squid_game.tasks.benchmark.adapters.gpqa import GPQAAdapter
from squid_game.tasks.benchmark.adapters.hi_tom import HiToMAdapter
from squid_game.tasks.benchmark.adapters.omni_math import OmniMathAdapter

_LABELS = ["ANSWER", "Answer", "answer", "AnSwEr"]


@pytest.mark.parametrize("label", _LABELS)
def test_gpqa_reads_any_label_casing(label):
    assert GPQAAdapter().normalize(f"reasoning\n{label}: C") == "C"


@pytest.mark.parametrize("label", _LABELS)
def test_hi_tom_reads_any_label_casing(label):
    assert HiToMAdapter().normalize(f"reasoning\n{label}: C") == "C"


@pytest.mark.parametrize("label", _LABELS)
def test_omni_math_reads_any_label_casing(label):
    assert OmniMathAdapter().normalize(f"reasoning\n{label}: 42") == "42"


@pytest.mark.parametrize(
    ("adapter", "raw", "expected"),
    [
        (GPQAAdapter(), "Answer: C", "C"),
        (HiToMAdapter(), "Answer: C", "C"),
        (OmniMathAdapter(), "Answer: 42", "42"),
    ],
)
def test_the_three_adapters_agree_on_a_capitalised_label(adapter, raw, expected):
    assert adapter.normalize(raw) == expected
