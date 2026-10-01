"""Unit tests for the YAML-described maths adapter.

Every dataset detail ``GenericMathAdapter`` knows comes from a
``BenchmarkTaskConfig``, so these tests build one config per behaviour and
feed it a two-or-three-row synthetic file. No real benchmark content appears
anywhere in this file.
"""

from __future__ import annotations

import json
import random

import pytest

from squid_game.tasks.benchmark.adapters.generic_math import GenericMathAdapter
from squid_game.tasks.benchmark.config import BenchmarkTaskConfig


def _config(**overrides) -> BenchmarkTaskConfig:
    payload = {
        "name": "hard_math",
        "data_file": "x.jsonl",
        "total_turns": 2,
        "ladder": [{"band": 1, "turns": 2}],
        "fields": {
            "problem": "problem",
            "answer": "final_answer",
            "difficulty": "difficulty",
        },
        "band_map": {"mode": "int"},
        "answer_filter": "single_value_integer",
    }
    payload.update(overrides)
    return BenchmarkTaskConfig.model_validate(payload)


def _write(tmp_path, rows, name="x.jsonl"):
    path = tmp_path / name
    if isinstance(rows, str):
        path.write_text(rows, encoding="utf-8")
        return path
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows) + "\n",
        encoding="utf-8",
    )
    return path


def _row(problem="p", answer="1", difficulty=1.0, **extra):
    row = {"problem": problem, "final_answer": answer, "difficulty": difficulty}
    row.update(extra)
    return row


# ---------------------------------------------------------------------------
# band_map modes
# ---------------------------------------------------------------------------


def test_band_map_int_floors_the_difficulty(tmp_path):
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="1", difficulty=5.25),
            _row(problem="b", answer="2", difficulty=1.0),
        ],
    )
    bands = {i.answer: i.band for i in GenericMathAdapter(_config()).load(path)}
    assert bands == {"1": 5, "2": 1}


def test_band_map_int_respects_min_and_max_band(tmp_path):
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="1", difficulty=0.5),
            _row(problem="b", answer="2", difficulty=4.0),
            _row(problem="c", answer="3", difficulty=9.5),
        ],
    )
    config = _config(band_map={"mode": "int", "min_band": 2, "max_band": 8})
    assert [i.answer for i in GenericMathAdapter(config).load(path)] == ["2"]


def test_band_map_scale_buckets_a_continuous_score(tmp_path):
    """1-10 into 3 equal buckets: [1,4) -> 1, [4,7) -> 2, [7,10] -> 3."""
    path = _write(
        tmp_path,
        [
            _row(problem=f"p{n}", answer=str(n), difficulty=value)
            for n, value in enumerate([1.0, 3.9, 4.0, 6.9, 7.0, 10.0])
        ],
    )
    config = _config(band_map={"mode": "scale", "min": 1, "max": 10, "bands": 3})
    items = GenericMathAdapter(config).load(path)
    assert [i.band for i in sorted(items, key=lambda i: int(i.answer))] == [
        1,
        1,
        2,
        2,
        3,
        3,
    ]


def test_band_map_scale_folds_the_top_edge_into_the_last_band(tmp_path):
    path = _write(tmp_path, [_row(answer="7", difficulty=10.0)])
    config = _config(band_map={"mode": "scale", "min": 1, "max": 10, "bands": 3})
    assert GenericMathAdapter(config).load(path)[0].band == 3


def test_band_map_lookup_handles_categorical_labels(tmp_path):
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="1", difficulty="easy"),
            _row(problem="b", answer="2", difficulty="hard"),
            _row(problem="c", answer="3", difficulty="impossible"),
        ],
    )
    config = _config(
        band_map={"mode": "lookup", "table": {"easy": 1, "medium": 2, "hard": 3}}
    )
    items = GenericMathAdapter(config).load(path)
    assert {i.answer: i.band for i in items} == {"1": 1, "2": 3}


def test_band_map_lookup_matches_aops_levels_written_as_numbers(tmp_path):
    """AoPS levels arrive as ``5`` from JSON and ``"5.5"`` from CSV; one
    table must serve both spellings or a config silently loses half its
    rows."""
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="1", difficulty=5),
            _row(problem="b", answer="2", difficulty=5.5),
            _row(problem="c", answer="3", difficulty="5.5"),
        ],
    )
    config = _config(band_map={"mode": "lookup", "table": {"5": 1, "5.5": 2}})
    items = GenericMathAdapter(config).load(path)
    assert {i.answer: i.band for i in items} == {"1": 1, "2": 2, "3": 2}


def test_band_map_scale_requires_its_parameters():
    with pytest.raises(ValueError, match="needs"):
        _config(band_map={"mode": "scale", "min": 1})


def test_band_map_lookup_requires_a_table():
    with pytest.raises(ValueError, match="non-empty table"):
        _config(band_map={"mode": "lookup"})


def test_adapter_refuses_a_config_without_a_band_map():
    payload = _config().model_dump()
    payload["band_map"] = None
    with pytest.raises(ValueError, match="band_map"):
        GenericMathAdapter(BenchmarkTaskConfig.model_validate(payload))


# ---------------------------------------------------------------------------
# answer_filter modes
# ---------------------------------------------------------------------------


def test_single_value_integer_filter_matches_omni_math_behaviour(tmp_path):
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="42"),
            _row(problem="b", answer="4,002,001"),  # thousands separator: kept
            _row(problem="c", answer="2, 3, 5"),  # multi-value list: dropped
            _row(problem="d", answer="\\frac{1}{2}"),  # not an integer: dropped
            _row(problem="e", answer="\\boxed{7}"),
        ],
    )
    items = GenericMathAdapter(_config()).load(path)
    assert sorted(i.answer for i in items) == ["4002001", "42", "7"]


def test_numeric_filter_accepts_fractions_and_decimals(tmp_path):
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="3/4"),
            _row(problem="b", answer="0.5"),
            _row(problem="c", answer="\\frac{7}{2}"),
            _row(problem="d", answer="-2.50"),
            _row(problem="e", answer="12"),
            _row(problem="f", answer="x + 1"),  # an expression: dropped
        ],
    )
    items = GenericMathAdapter(_config(answer_filter="numeric")).load(path)
    assert sorted(i.answer for i in items) == ["-5/2", "1/2", "12", "3/4", "7/2"]


def test_numeric_filter_scores_equivalent_spellings_as_equal(tmp_path):
    path = _write(tmp_path, [_row(answer="0.5")])
    adapter = GenericMathAdapter(_config(answer_filter="numeric"))
    item = adapter.load(path)[0]
    parsed = adapter.normalize("thinking...\nANSWER: \\frac{1}{2}")
    assert parsed == item.answer
    assert adapter.matches(parsed, item.answer, item) is True


def test_any_filter_keeps_free_text_and_compares_loosely(tmp_path):
    path = _write(tmp_path, [_row(answer="Blue Pantry")])
    adapter = GenericMathAdapter(_config(answer_filter="any"))
    item = adapter.load(path)[0]
    assert item.answer == "Blue Pantry"
    parsed = adapter.normalize("ANSWER:  blue   pantry ")
    assert adapter.matches(parsed, item.answer, item) is True


def test_normalize_reads_the_last_answer_line(tmp_path):
    adapter = GenericMathAdapter(_config())
    assert adapter.normalize("ANSWER: 1\nwait\nANSWER: 2") == "2"
    assert adapter.normalize("no answer here") is None


# ---------------------------------------------------------------------------
# field renames, ids, dedup
# ---------------------------------------------------------------------------


def test_fields_block_reads_renamed_columns(tmp_path):
    path = _write(
        tmp_path,
        [{"q": "what?", "sol": "9", "level": 3.0, "cat": "Algebra", "uid": "u1"}],
    )
    config = _config(
        fields={
            "problem": "q",
            "answer": "sol",
            "difficulty": "level",
            "id": "uid",
            "subject": "cat",
        }
    )
    item = GenericMathAdapter(config).load(path)[0]
    assert item.body == "what?"
    assert item.answer == "9"
    assert item.band == 3
    assert item.item_id == "hard_math-u1"
    assert item.meta["subject"] == "Algebra"


def test_item_id_is_content_derived_when_no_id_column(tmp_path):
    """Ids must not depend on file position, or a re-run at the same seed
    silently draws a different question set after an upstream row moves."""
    rows = [_row(problem="alpha", answer="1"), _row(problem="beta", answer="2")]
    forward = GenericMathAdapter(_config()).load(_write(tmp_path, rows, "a.jsonl"))
    reversed_ = GenericMathAdapter(_config()).load(
        _write(tmp_path, list(reversed(rows)), "b.jsonl")
    )
    assert {i.body: i.item_id for i in forward} == {
        i.body: i.item_id for i in reversed_
    }


def test_dedupe_on_problem_text_removes_repeats(tmp_path):
    path = _write(
        tmp_path,
        [
            _row(problem="same", answer="1", difficulty=3.0),
            _row(problem="same", answer="1", difficulty=1.0),
            _row(problem="other", answer="2", difficulty=2.0),
        ],
    )
    items = GenericMathAdapter(_config(dedupe_on_problem_text=True)).load(path)
    assert sorted(i.body for i in items) == ["other", "same"]


def test_dedupe_winner_does_not_depend_on_file_order(tmp_path):
    """Two rows share a problem but disagree on difficulty, so the winner
    decides which ladder rung the problem sits on. That must be a property of
    the content, not of which row came first."""
    rows = [
        _row(problem="same", answer="1", difficulty=3.0),
        _row(problem="same", answer="1", difficulty=1.0),
    ]
    config = _config(dedupe_on_problem_text=True)
    forward = GenericMathAdapter(config).load(_write(tmp_path, rows, "a.jsonl"))
    backward = GenericMathAdapter(config).load(
        _write(tmp_path, list(reversed(rows)), "b.jsonl")
    )
    assert forward[0].band == backward[0].band == 1


def test_without_dedupe_repeated_text_is_kept(tmp_path):
    path = _write(
        tmp_path,
        [_row(problem="same", answer="1"), _row(problem="same", answer="1")],
    )
    assert len(GenericMathAdapter(_config()).load(path)) == 2


# ---------------------------------------------------------------------------
# malformed input
# ---------------------------------------------------------------------------


def test_malformed_rows_are_skipped_with_a_log_line(tmp_path, caplog):
    path = _write(
        tmp_path,
        "{not json at all}\n"
        + json.dumps(_row(problem="good", answer="5"))
        + "\n"
        + json.dumps({"final_answer": "6", "difficulty": 1.0})
        + "\n",
    )
    with caplog.at_level("WARNING"):
        items = GenericMathAdapter(_config()).load(path)
    assert [i.answer for i in items] == ["5"]
    assert "unreadable row" in caplog.text
    assert "missing 'problem' column" in caplog.text
    assert "skipped 2" in caplog.text


def test_a_row_whose_answer_fails_the_filter_is_counted(tmp_path, caplog):
    path = _write(tmp_path, [_row(answer="yes")])
    with caplog.at_level("WARNING"):
        assert GenericMathAdapter(_config()).load(path) == []
    assert "answer rejected by filter" in caplog.text


def test_unsupported_file_type_is_refused(tmp_path):
    path = tmp_path / "x.parquet"
    path.write_bytes(b"\x00")
    with pytest.raises(ValueError, match="unsupported benchmark file type"):
        GenericMathAdapter(_config()).load(path)


def test_csv_and_json_inputs_load(tmp_path):
    csv_path = tmp_path / "x.csv"
    csv_path.write_text(
        "problem,final_answer,difficulty\nfrom csv,3,2.0\n", encoding="utf-8"
    )
    json_path = tmp_path / "x.json"
    json_path.write_text(
        json.dumps([_row(problem="from json", answer="4", difficulty=2.0)]),
        encoding="utf-8",
    )
    assert GenericMathAdapter(_config()).load(csv_path)[0].body == "from csv"
    assert GenericMathAdapter(_config()).load(json_path)[0].body == "from json"


def test_render_returns_the_problem_verbatim(tmp_path):
    path = _write(tmp_path, [_row(problem="verbatim body", answer="1")])
    adapter = GenericMathAdapter(_config())
    body, meta = adapter.render(adapter.load(path)[0], random.Random(0))
    assert body == "verbatim body"
    assert meta == {}


# ---------------------------------------------------------------------------
# band_map mode regex_tier (difficulty encoded in an identifier)
# ---------------------------------------------------------------------------

_TIER_MAP = {
    "mode": "regex_tier",
    "pattern": r"^(?P<year>[0-9]{4})(?P<section>[a-z]+)(?P<number>[0-9]+)$",
    "tiers": [
        {"when": {"section": "p", "number": [1, 4]}, "band": 2},
        {"when": {"section": "p", "number": [2, 5]}, "band": 3},
        {"when": {"section": ["a", "c"], "number": [1, 2]}, "band": 1},
        {"when": {"section": ["a", "c"], "number": [3, 4]}, "band": 2},
    ],
}


def test_regex_tier_reads_the_band_out_of_an_identifier(tmp_path):
    """RIMO-N publishes no difficulty column: the band is a function of the
    section letter and the problem number inside the ``problem_id``."""
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="1", difficulty="2023a1"),
            _row(problem="b", answer="2", difficulty="2023c4"),
            _row(problem="c", answer="3", difficulty="1988p5"),
        ],
    )
    config = _config(band_map=_TIER_MAP)
    items = {i.answer: i.band for i in GenericMathAdapter(config).load(path)}
    assert items == {"1": 1, "2": 2, "3": 3}


def test_regex_tier_first_matching_rule_wins(tmp_path):
    """``1988p1`` satisfies the p-rule; it must not fall through to a later
    rule that also matches on number alone."""
    config = _config(
        band_map={
            "mode": "regex_tier",
            "pattern": r"^(?P<section>[a-z]+)(?P<number>[0-9]+)$",
            "tiers": [
                {"when": {"section": "p"}, "band": 4},
                {"when": {"number": [1]}, "band": 1},
            ],
        }
    )
    assert config.band_map.band_for("p1") == 4
    assert config.band_map.band_for("a1") == 1


def test_regex_tier_drops_ids_that_match_no_rule(tmp_path, caplog):
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="1", difficulty="2023a1"),
            _row(problem="b", answer="2", difficulty="2023p7"),  # no such rule
            _row(problem="c", answer="3", difficulty="not-an-id"),
        ],
    )
    with caplog.at_level("WARNING"):
        items = GenericMathAdapter(_config(band_map=_TIER_MAP)).load(path)
    assert [i.answer for i in items] == ["1"]
    assert "difficulty out of range or unmapped" in caplog.text


def test_regex_tier_compares_yaml_ints_against_regex_strings():
    """The rule is written ``number: [1, 4]`` (ints) but the regex hands back
    ``"1"``; a zero-padded id must still match."""
    config = _config(band_map=_TIER_MAP)
    assert config.band_map.band_for("2023a01") == 1


def test_regex_tier_requires_a_pattern_and_tiers():
    with pytest.raises(ValueError, match="needs a pattern"):
        _config(band_map={"mode": "regex_tier", "tiers": [{"band": 1}]})
    with pytest.raises(ValueError, match="non-empty tiers"):
        _config(band_map={"mode": "regex_tier", "pattern": "^(?P<a>x)$"})


def test_regex_tier_rejects_a_rule_naming_an_uncaptured_group():
    """A typo in a group name would otherwise make the rule silently never
    match, and every row would drop with no hint why."""
    with pytest.raises(ValueError, match="does not capture"):
        _config(
            band_map={
                "mode": "regex_tier",
                "pattern": r"^(?P<section>[a-z]+)$",
                "tiers": [{"when": {"sektion": "p"}, "band": 1}],
            }
        )


def test_regex_tier_rejects_an_invalid_pattern():
    with pytest.raises(ValueError, match="not a valid regex"):
        _config(
            band_map={
                "mode": "regex_tier",
                "pattern": "^(?P<a>[a-z]+$",
                "tiers": [{"when": {"a": "x"}, "band": 1}],
            }
        )


# ---------------------------------------------------------------------------
# exclude_types
# ---------------------------------------------------------------------------


def test_exclude_types_drops_rows_case_insensitively(tmp_path, caplog):
    path = _write(
        tmp_path,
        [
            _row(problem="a", answer="1", subject="Geometry"),
            _row(problem="b", answer="2", subject="algebra"),
        ],
    )
    config = _config(
        fields={
            "problem": "problem",
            "answer": "final_answer",
            "difficulty": "difficulty",
            "subject": "subject",
        },
        exclude_types=["geometry"],
    )
    with caplog.at_level("WARNING"):
        items = GenericMathAdapter(config).load(path)
    assert [i.answer for i in items] == ["2"]
    assert "excluded type" in caplog.text


def test_exclude_types_without_a_subject_column_is_refused():
    with pytest.raises(ValueError, match="fields.subject"):
        GenericMathAdapter(_config(exclude_types=["geometry"]))


def test_an_unread_column_never_reaches_item_meta(tmp_path):
    """Only the columns named in ``fields`` are read, which is what keeps a
    dataset's worked solution out of prompts and turn records."""
    path = _write(
        tmp_path,
        [_row(problem="p", answer="1", solution="SECRET WORKED SOLUTION")],
    )
    item = GenericMathAdapter(_config()).load(path)[0]
    assert "SECRET" not in repr(item.meta)
    assert "SECRET" not in item.body
