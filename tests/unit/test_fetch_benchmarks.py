"""Unit tests for the benchmark data fetch helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "fetch_benchmarks.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("fetch_benchmarks", _SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_sources_cover_three_benchmarks():
    mod = _load_module()
    assert {"omni_math", "hi_tom", "gpqa"} <= set(mod.BENCHMARK_SOURCES)


def test_gpqa_source_is_marked_gated():
    mod = _load_module()
    assert mod.BENCHMARK_SOURCES["gpqa"].requires_token is True
    assert mod.BENCHMARK_SOURCES["omni_math"].requires_token is False


def test_sha256_of_is_stable(tmp_path: Path):
    mod = _load_module()
    target = tmp_path / "a.txt"
    target.write_text("hello", encoding="utf-8")
    first = mod.sha256_of(target)
    assert first == mod.sha256_of(target)
    assert len(first) == 64


def test_write_manifest_records_entries(tmp_path: Path):
    mod = _load_module()
    entries = [
        {"name": "omni_math", "filename": "omni_math.jsonl", "sha256": "x" * 64, "rows": 4428}
    ]
    path = mod.write_manifest(entries, tmp_path)
    payload = json.loads(path.read_text(encoding="utf-8"))
    assert payload["entries"][0]["name"] == "omni_math"
    assert "fetched_at" in payload


def test_count_rows_handles_csv_cells_with_embedded_newlines(tmp_path: Path):
    """Regression test for the naive-line-count bug: a quoted CSV cell that
    contains an embedded newline must still count as a single data row, not
    two. This is synthetic content only — no real benchmark question text.
    """
    mod = _load_module()
    target = tmp_path / "synthetic.csv"
    target.write_text(
        "header_a,header_b\n"
        '"single-line cell",1\n'
        '"this cell\nspans two physical lines",2\n'
        '"single-line cell again",3\n',
        encoding="utf-8",
    )
    # Physical line count minus the header would be 4 (the embedded newline
    # in row 2 adds an extra physical line); the true data-row count, parsed
    # as CSV, is 3. The two numbers must differ for this test to actually
    # discriminate the correct implementation from the naive one.
    physical_line_count = sum(1 for _ in target.open(encoding="utf-8"))
    naive_count = physical_line_count - 1
    true_row_count = 3
    assert naive_count != true_row_count
    assert mod.count_rows(target) == true_row_count
