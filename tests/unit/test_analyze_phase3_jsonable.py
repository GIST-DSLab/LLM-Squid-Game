"""Regression tests for ``_jsonable`` in ``scripts/analyze_phase3.py``.

Unit 14 `_run_unit14` builds a three-way keyword convergence blob by
``groupby(["framing", "reason"])`` and serialises the resulting
MultiIndex DataFrame via ``_jsonable`` → ``json.dump``. Prior to the
Unit 14.8 fix, ``_jsonable`` returned tuple keys from
``DataFrame.to_dict(orient="index")`` and the subsequent ``json.dump``
crashed with::

    TypeError: keys must be str, int, float, bool or None, not tuple

blocking the rest of the Unit 14 analysis pipeline (unit14_results.md
was never rendered). These tests lock in MultiIndex-safe behaviour for
both DataFrames and Series.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pandas as pd
import pytest


@pytest.fixture(scope="module")
def cli_module():
    root = Path(__file__).resolve().parents[2]
    script_path = root / "scripts" / "analyze_phase3.py"
    spec = importlib.util.spec_from_file_location(
        "analyze_phase3_jsonable_test", script_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class TestJsonableMultiIndex:
    def test_multiindex_dataframe_flattens_tuple_keys_to_strings(
        self, cli_module
    ) -> None:
        """MultiIndex DataFrame dump must be JSON-serialisable."""
        df = pd.DataFrame(
            {
                "corruption_kw": [8.0, 5.0],
                "score_kw": [8.0, 3.0],
            },
            index=pd.MultiIndex.from_tuples(
                [
                    ("flagship_corruption", "survival"),
                    ("baseline_flagship", "curiosity"),
                ],
                names=["framing", "reason"],
            ),
        )
        projected = cli_module._jsonable(df)
        assert set(projected.keys()) == {
            "flagship_corruption | survival",
            "baseline_flagship | curiosity",
        }
        # Downstream must be ``json.dump``-safe end-to-end.
        json.dumps(projected)

    def test_multiindex_series_flattens_tuple_keys_to_strings(
        self, cli_module
    ) -> None:
        series = pd.Series(
            [8.0, 5.0],
            index=pd.MultiIndex.from_tuples(
                [("a", "x"), ("b", "y")],
                names=["outer", "inner"],
            ),
            name="val",
        )
        projected = cli_module._jsonable(series)
        assert projected == {"a | x": 8.0, "b | y": 5.0}
        json.dumps(projected)

    def test_flat_index_dataframe_preserves_legacy_shape(
        self, cli_module
    ) -> None:
        """Flat-index DataFrames keep the historical ``orient='index'`` shape."""
        df = pd.DataFrame(
            {"a": [1, 2], "b": [3, 4]},
            index=["row0", "row1"],
        )
        projected = cli_module._jsonable(df)
        assert projected == {
            "row0": {"a": 1, "b": 3},
            "row1": {"a": 2, "b": 4},
        }
        json.dumps(projected)

    def test_flat_index_series_preserves_legacy_shape(self, cli_module) -> None:
        series = pd.Series([1, 2], index=["x", "y"], name="val")
        projected = cli_module._jsonable(series)
        assert projected == {"x": 1, "y": 2}
        json.dumps(projected)
