"""Unit tests for the Hi-ToM adapter."""

from __future__ import annotations

import json
import random

import pytest

from squid_game.tasks.benchmark.adapters.hi_tom import HiToMAdapter


def _row(**overrides):
    row = {
        "prompting_type": "CoTP",
        "deception": False,
        "story_length": 1,
        "question_order": 0,
        "sample_id": 0,
        "story": "1 Ann entered the room.",
        "question": "Where is the lettuce really?",
        "choices": "A. blue_drawer, B. green_crate, C. red_bucket",
        "answer": "green_crate",
        "prompt": "ignored",
    }
    row.update(overrides)
    return row


def _write(tmp_path, rows):
    path = tmp_path / "hi_tom.json"
    path.write_text(json.dumps({"data": rows}), encoding="utf-8")
    return path


def test_keeps_one_prompting_type_only(tmp_path):
    path = _write(tmp_path, [_row(sample_id=1), _row(sample_id=2, prompting_type="VP")])
    items = HiToMAdapter().load(path)
    assert len(items) == 1
    assert items[0].item_id == "hitom-1"


@pytest.mark.parametrize(
    ("order", "length", "expected_band"),
    [(0, 1, 1), (0, 3, 3), (1, 1, 4), (4, 3, 15)],
)
def test_band_is_order_major(tmp_path, order, length, expected_band):
    path = _write(tmp_path, [_row(question_order=order, story_length=length)])
    assert HiToMAdapter().load(path)[0].band == expected_band


def test_body_contains_story_question_and_choices(tmp_path):
    path = _write(tmp_path, [_row()])
    item = HiToMAdapter().load(path)[0]
    assert "Ann entered the room" in item.body
    assert "Where is the lettuce really?" in item.body
    assert "B. green_crate" in item.body


def test_answer_is_stored_as_the_choice_letter(tmp_path):
    path = _write(tmp_path, [_row(answer="green_crate")])
    assert HiToMAdapter().load(path)[0].answer == "B"


def test_row_with_unlisted_answer_is_dropped(tmp_path):
    path = _write(tmp_path, [_row(answer="not_in_choices")])
    assert HiToMAdapter().load(path) == []


def test_meta_keeps_the_design_factors(tmp_path):
    path = _write(tmp_path, [_row(question_order=2, story_length=3, deception=True)])
    meta = HiToMAdapter().load(path)[0].meta
    assert meta["question_order"] == 2
    assert meta["story_length"] == 3
    assert meta["deception"] is True


def test_render_is_verbatim(tmp_path):
    path = _write(tmp_path, [_row()])
    item = HiToMAdapter().load(path)[0]
    body, meta = HiToMAdapter().render(item, random.Random(1))
    assert body == item.body
    assert meta == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("ANSWER: B", "B"),
        ("ANSWER: b", "B"),
        ("thinking...\nANSWER: green_crate", "green_crate"),
        ("ANSWER: ", None),
        ("no answer here", None),
    ],
)
def test_normalize(raw, expected):
    assert HiToMAdapter().normalize(raw) == expected


def test_matches_accepts_letter_or_option_text(tmp_path):
    path = _write(tmp_path, [_row()])
    adapter = HiToMAdapter()
    item = adapter.load(path)[0]
    assert adapter.matches("B", item.answer, item) is True
    assert adapter.matches("green_crate", item.answer, item) is True
    assert adapter.matches("A", item.answer, item) is False
    assert adapter.matches("blue_drawer", item.answer, item) is False
