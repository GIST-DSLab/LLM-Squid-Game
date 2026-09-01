"""End-to-end smoke test: a benchmark task through the unified turn flow.

Uses synthetic questions only. Real benchmark items are never committed —
GPQA's authors ask that questions stay off the public web.
"""

from __future__ import annotations

import json

import pytest

# Importing the benchmark package runs its ``@register`` decorators, which
# populate the shared task registry. Nothing else in this file forces that
# import to happen, and this module must pass when run standalone (e.g.
# ``pytest tests/integration/test_benchmark_task_e2e.py``), so the import
# is explicit here rather than relied upon from collection order.
import squid_game.tasks.benchmark  # noqa: F401
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.tasks.registry import get_task

_TOTAL_TURNS = 6


@pytest.fixture()
def synthetic_omni_math(tmp_path, monkeypatch):
    """Register a 6-turn omni_math task over a synthetic 3-band pool."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "omni_math.yaml").write_text(
        "name: omni_math\n"
        "data_file: omni_math.jsonl\n"
        f"total_turns: {_TOTAL_TURNS}\n"
        "ladder:\n"
        "  - {band: 1, turns: 2}\n"
        "  - {band: 2, turns: 2}\n"
        "  - {band: 3, turns: 2}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows = [
        {
            "difficulty": float(band),
            "problem": f"synthetic band {band} item {index}",
            "answer": str(band * 10 + index),
            "domain": ["synthetic"],
            "source": "synthetic",
        }
        for band in (1, 2, 3)
        for index in range(4)
    ]
    (data_dir / "omni_math.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))


def _turn_context(turn: int, framing: Framing, forfeit: ForfeitCondition) -> TurnContext:
    return TurnContext(
        turn_number=turn,
        total_turns=_TOTAL_TURNS,
        season_id="smoke",
        cumulative_score=30.0,
        p_death=0.25,
        framing=framing,
        forfeit_condition=forfeit,
        difficulty=Difficulty.MEDIUM,
    )


# The six cells of the current Phase O v6 factorial design (see the 6-Cell
# table in CLAUDE.md): (framing, forfeit_condition) pairs for Cells 0-5.
_CELLS = [
    (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED),  # Cell 0
    (Framing.BASELINE_FLAGSHIP, ForfeitCondition.ALLOWED),  # Cell 1
    (Framing.BASELINE_FLAGSHIP, ForfeitCondition.NOT_ALLOWED),  # Cell 2
    (Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.ALLOWED),  # Cell 3
    (Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.NOT_ALLOWED),  # Cell 4
    (Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED),  # Cell 5
]


def test_all_six_cells_see_the_same_item_sequence(synthetic_omni_math):
    sequences = []
    for framing, forfeit in _CELLS:
        task = get_task("omni_math")()
        task.initialize(difficulty=Difficulty.MEDIUM, seed=2026)
        sequences.append(
            [
                task.prepare(None, _turn_context(turn, framing, forfeit)).metadata["item_id"]
                for turn in range(1, _TOTAL_TURNS + 1)
            ]
        )
    assert all(sequence == sequences[0] for sequence in sequences)


def test_a_full_season_scores_every_turn(synthetic_omni_math):
    task = get_task("omni_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=2026)
    correct = 0
    for turn in range(1, _TOTAL_TURNS + 1):
        turn_context = _turn_context(turn, Framing.FLAGSHIP_CORRUPTION, ForfeitCondition.ALLOWED)
        context = task.prepare(None, turn_context)
        response = f"reasoning\nANSWER: {context.metadata['expected_answer']}"
        outcome = task.score(task.parse_response(response), None)
        correct += int(outcome.success_factor == 1.0)
    assert correct == _TOTAL_TURNS


def test_bands_increase_monotonically(synthetic_omni_math):
    task = get_task("omni_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=2026)
    bands = [
        task.prepare(
            None, _turn_context(turn, Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED)
        ).metadata["band"]
        for turn in range(1, _TOTAL_TURNS + 1)
    ]
    assert bands == sorted(bands)
    assert bands[0] < bands[-1]
