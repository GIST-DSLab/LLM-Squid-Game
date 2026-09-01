"""Unit tests for the GPQA adapter."""

from __future__ import annotations

import csv
import random

import pytest

from squid_game.tasks.benchmark.adapters.gpqa import GPQAAdapter

_HARD_UG = (
    "Hard undergraduate level (could be a question on a hard undergraduate "
    "exam for students majoring in the subject)"
)
_HARD_GRAD = (
    "Hard graduate level (could be a question on a hard graduate exam for "
    "PhD students in the domain)"
)
_POSTGRAD = (
    "Post-graduate level or harder (only individuals with years of highly "
    "specialized expertise could reliably answer correctly)"
)

_COLUMNS = [
    "Question",
    "Correct Answer",
    "Incorrect Answer 1",
    "Incorrect Answer 2",
    "Incorrect Answer 3",
    "Writer's Difficulty Estimate",
    "Non-Expert Validator Accuracy",
    "Expert Validator Accuracy",
    "Record ID",
    "High-level domain",
    "Subdomain",
]


def _row(**overrides):
    row = {
        "Question": "Why is the sky blue?",
        "Correct Answer": "Rayleigh scattering",
        "Incorrect Answer 1": "Absorption",
        "Incorrect Answer 2": "Refraction",
        "Incorrect Answer 3": "Diffraction",
        "Writer's Difficulty Estimate": _HARD_UG,
        "Non-Expert Validator Accuracy": "0.3333333333333333",
        "Expert Validator Accuracy": "1.0",
        "Record ID": "rec_1",
        "High-level domain": "Physics",
        "Subdomain": "Optics",
    }
    row.update(overrides)
    return row


def _write(tmp_path, rows, diamond_ids=()):
    path = tmp_path / "gpqa_main.csv"
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
        writer.writeheader()
        writer.writerows(rows)
    if diamond_ids:
        diamond = tmp_path / "gpqa_diamond.csv"
        with diamond.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=_COLUMNS)
            writer.writeheader()
            for rid in diamond_ids:
                writer.writerow(_row(**{"Record ID": rid}))
    return path


def test_drops_low_expert_accuracy_rows(tmp_path):
    path = _write(
        tmp_path,
        [_row(**{"Expert Validator Accuracy": "0.0", "Record ID": "bad"}), _row()],
    )
    items = GPQAAdapter().load(path)
    assert [item.item_id for item in items] == ["gpqa-rec_1"]


@pytest.mark.parametrize(
    ("writer", "non_expert_acc", "expected_band"),
    [
        (_HARD_UG, "0.6666666666666666", 2),
        (_HARD_UG, "0.0", 3),
        (_HARD_GRAD, "0.6666666666666666", 4),
        (_HARD_GRAD, "0.3333333333333333", 5),
        (_POSTGRAD, "0.6666666666666666", 6),
        (_POSTGRAD, "0.0", 6),
    ],
)
def test_band_formula(tmp_path, writer, non_expert_acc, expected_band):
    path = _write(
        tmp_path,
        [
            _row(
                **{
                    "Writer's Difficulty Estimate": writer,
                    "Non-Expert Validator Accuracy": non_expert_acc,
                }
            )
        ],
    )
    assert GPQAAdapter().load(path)[0].band == expected_band


def test_band_one_is_merged_into_band_two(tmp_path):
    path = _write(
        tmp_path,
        [
            _row(
                **{
                    "Writer's Difficulty Estimate": "Easy undergraduate level (or easier)",
                    "Non-Expert Validator Accuracy": "0.6666666666666666",
                }
            )
        ],
    )
    assert GPQAAdapter().load(path)[0].band == 2


def test_answer_holds_the_correct_option_text(tmp_path):
    path = _write(tmp_path, [_row()])
    assert GPQAAdapter().load(path)[0].answer == "Rayleigh scattering"


def test_is_diamond_flag_is_set(tmp_path):
    path = _write(tmp_path, [_row()], diamond_ids=("rec_1",))
    assert GPQAAdapter().load(path)[0].meta["is_diamond"] is True


def test_render_shuffles_and_reports_the_correct_letter(tmp_path):
    path = _write(tmp_path, [_row()])
    item = GPQAAdapter().load(path)[0]
    body, meta = GPQAAdapter().render(item, random.Random(5))
    assert body.count("\n") >= 4
    letter = meta["correct_letter"]
    assert letter in "ABCD"
    assert f"{letter}. Rayleigh scattering" in body
    assert sorted(meta["choice_order"]) == sorted(
        ["Rayleigh scattering", "Absorption", "Refraction", "Diffraction"]
    )


def test_render_is_reproducible_for_the_same_rng_seed(tmp_path):
    path = _write(tmp_path, [_row()])
    item = GPQAAdapter().load(path)[0]
    first = GPQAAdapter().render(item, random.Random(9))
    second = GPQAAdapter().render(item, random.Random(9))
    assert first == second


def test_render_moves_the_answer_across_seeds(tmp_path):
    path = _write(tmp_path, [_row()])
    item = GPQAAdapter().load(path)[0]
    letters = {
        GPQAAdapter().render(item, random.Random(seed))[1]["correct_letter"]
        for seed in range(30)
    }
    assert len(letters) > 1


@pytest.mark.parametrize(
    ("raw", "expected"),
    [("ANSWER: C", "C"), ("ANSWER: c", "C"), ("ANSWER: E", None), ("nope", None)],
)
def test_normalize(raw, expected):
    assert GPQAAdapter().normalize(raw) == expected
