"""Unit tests for the Omni-MATH adapter."""

from __future__ import annotations

import json
import random

import pytest

from squid_game.tasks.benchmark.adapters.omni_math import OmniMathAdapter


def _write(tmp_path, rows):
    path = tmp_path / "omni_math.jsonl"
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def test_keeps_integer_answers_only(tmp_path):
    path = _write(
        tmp_path,
        [
            {"difficulty": 4.0, "problem": "p1", "answer": "42", "domain": ["d"], "source": "s"},
            {"difficulty": 4.0, "problem": "p2", "answer": "\\frac{1}{2}", "domain": ["d"], "source": "s"},
            {"difficulty": 4.0, "problem": "p3", "answer": "\\text{Yes}", "domain": ["d"], "source": "s"},
        ],
    )
    items = OmniMathAdapter().load(path)
    assert [item.answer for item in items] == ["42"]


def test_band_is_the_floor_of_difficulty(tmp_path):
    path = _write(
        tmp_path,
        [
            {"difficulty": 5.25, "problem": "p", "answer": "1", "domain": ["d"], "source": "s"},
            {"difficulty": 1.0, "problem": "q", "answer": "2", "domain": ["d"], "source": "s"},
        ],
    )
    items = {item.answer: item.band for item in OmniMathAdapter().load(path)}
    assert items == {"1": 5, "2": 1}


def test_band_nine_is_dropped(tmp_path):
    path = _write(
        tmp_path,
        [{"difficulty": 9.5, "problem": "p", "answer": "1", "domain": ["d"], "source": "s"}],
    )
    assert OmniMathAdapter().load(path) == []


def test_meta_preserves_source_difficulty(tmp_path):
    path = _write(
        tmp_path,
        [{"difficulty": 7.5, "problem": "p", "answer": "3", "domain": ["algebra"], "source": "imo"}],
    )
    item = OmniMathAdapter().load(path)[0]
    assert item.meta["omni_difficulty"] == 7.5
    assert item.meta["source"] == "imo"


def test_render_returns_body_unchanged(tmp_path):
    path = _write(
        tmp_path,
        [{"difficulty": 2.0, "problem": "What is 2+2?", "answer": "4", "domain": ["d"], "source": "s"}],
    )
    item = OmniMathAdapter().load(path)[0]
    body, meta = OmniMathAdapter().render(item, random.Random(1))
    assert "What is 2+2?" in body
    assert meta == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ANSWER: 42", "42"),
        ("some reasoning\nANSWER: -7\n", "-7"),
        ("ANSWER: $1{,}024$", "1024"),
        ("ANSWER: \\boxed{15}", "15"),
        ("ANSWER: 3.0", None),
        ("ANSWER: \\frac{1}{2}", None),
        ("I think it is 42", None),
        ("", None),
    ],
)
def test_normalize(raw, expected):
    assert OmniMathAdapter().normalize(raw) == expected


def test_normalize_takes_the_last_answer_line():
    adapter = OmniMathAdapter()
    assert adapter.normalize("ANSWER: 1\nwait, no\nANSWER: 2") == "2"


def test_multi_value_list_answer_is_rejected(tmp_path):
    """A comma/space-separated list of values is not a single integer.

    A naive comma/space strip would mash "2, 3, 5" into the fake integer
    "235"; that is not deterministically scorable (a correctly-formatted
    ``ANSWER: {2, 3, 5}`` would fail to parse) so the item must be dropped.
    """
    path = _write(
        tmp_path,
        [{"difficulty": 5.0, "problem": "p", "answer": "2, 3, 5", "domain": ["d"], "source": "s"}],
    )
    assert OmniMathAdapter().load(path) == []


def test_thousands_separator_integer_is_kept(tmp_path):
    """A comma used as a thousands separator is still a single integer."""
    path = _write(
        tmp_path,
        [{"difficulty": 4.0, "problem": "p", "answer": "4,002,001", "domain": ["d"], "source": "s"}],
    )
    items = OmniMathAdapter().load(path)
    assert [item.answer for item in items] == ["4002001"]


def test_duplicate_problem_text_is_deduplicated(tmp_path):
    """The same problem text appearing twice yields only one item."""
    path = _write(
        tmp_path,
        [
            {"difficulty": 3.0, "problem": "same problem", "answer": "10", "domain": ["d"], "source": "s"},
            {"difficulty": 3.0, "problem": "same problem", "answer": "10", "domain": ["d"], "source": "s2"},
        ],
    )
    items = OmniMathAdapter().load(path)
    assert len(items) == 1
    assert items[0].meta["source"] == "s"
