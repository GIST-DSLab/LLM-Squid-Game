"""Unit tests for the Omni-MATH adapter."""

from __future__ import annotations

import json
import random

import pytest

from squid_game.tasks.benchmark.adapters.omni_math import OmniMathAdapter


def _write(tmp_path, rows):
    tmp_path.mkdir(parents=True, exist_ok=True)
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


# ---------------------------------------------------------------------------
# item_id / dedup must not depend on the row's position in the raw file.
# SeededSampler documents that sorting by item_id makes a reproduced run
# immune to a change in file order; that guarantee held for GPQA (Record ID)
# and Hi-ToM (sample_id) but not here while the id was the line index.
# ---------------------------------------------------------------------------


def _plain_rows():
    return [
        {"difficulty": 1.0, "problem": "alpha", "answer": "1", "domain": ["d"], "source": "s"},
        {"difficulty": 2.0, "problem": "beta", "answer": "2", "domain": ["d"], "source": "s"},
        {"difficulty": 3.0, "problem": "gamma", "answer": "3", "domain": ["d"], "source": "s"},
    ]


def test_item_id_is_derived_from_the_problem_text(tmp_path):
    """Same problem text -> same id, regardless of where the row sits."""
    first = OmniMathAdapter().load(_write(tmp_path / "a", _plain_rows()))
    second = OmniMathAdapter().load(
        _write(tmp_path / "b", list(reversed(_plain_rows())))
    )
    assert {item.body: item.item_id for item in first} == {
        item.body: item.item_id for item in second
    }


def test_inserting_a_row_upstream_does_not_shift_later_ids(tmp_path):
    """The concrete regression: a row prepended to the raw file used to
    renumber every id after it, so a re-run at seed 42 silently drew a
    different question set while claiming reproduction."""
    before = {
        item.body: item.item_id
        for item in OmniMathAdapter().load(_write(tmp_path / "before", _plain_rows()))
    }
    with_insert = [
        {
            "difficulty": 1.0,
            "problem": "brand new",
            "answer": "9",
            "domain": ["d"],
            "source": "s",
        },
        *_plain_rows(),
    ]
    after = {
        item.body: item.item_id
        for item in OmniMathAdapter().load(_write(tmp_path / "after", with_insert))
    }
    for body, item_id in before.items():
        assert after[body] == item_id


def test_dedup_winner_does_not_depend_on_file_order(tmp_path):
    """Of the 16 real duplicate groups that reach dedup, 5 carry a divergent
    *band* (``int(difficulty)``) -- so "first occurrence wins" would let file
    order decide which ladder rung a problem sat on for those 5."""
    dupes = [
        {
            "difficulty": 3.0,
            "problem": "same",
            "answer": "7",
            "domain": ["d"],
            "source": "fermat",
        },
        {
            "difficulty": 1.0,
            "problem": "same",
            "answer": "7",
            "domain": ["d"],
            "source": "pascal",
        },
    ]
    forward = OmniMathAdapter().load(_write(tmp_path / "fwd", dupes))
    reverse = OmniMathAdapter().load(_write(tmp_path / "rev", list(reversed(dupes))))
    assert len(forward) == len(reverse) == 1
    assert forward[0].band == reverse[0].band
    assert forward[0].meta == reverse[0].meta
    assert forward[0].item_id == reverse[0].item_id


def test_duplicate_problem_text_still_yields_one_item(tmp_path):
    path = _write(
        tmp_path,
        [
            {"difficulty": 2.0, "problem": "dup", "answer": "5", "domain": ["d"], "source": "s"},
            {"difficulty": 2.0, "problem": "dup", "answer": "5", "domain": ["d"], "source": "s"},
        ],
    )
    assert len(OmniMathAdapter().load(path)) == 1
