"""Unit tests for the benchmark data fetch helper."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

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
