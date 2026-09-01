"""Unit tests for the shared benchmark task module."""

from __future__ import annotations

import json

import pytest

from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.state import TurnContext
from squid_game.tasks.benchmark.module import BenchmarkTaskModule
from squid_game.tasks.registry import get_task


def _turn_context(turn_number: int) -> TurnContext:
    return TurnContext(
        turn_number=turn_number,
        total_turns=4,
        season_id="s1",
        cumulative_score=30.0,
        p_death=0.25,
        framing=Framing.NEUTRAL,
        forfeit_condition=ForfeitCondition.ALLOWED,
        difficulty=Difficulty.MEDIUM,
    )


@pytest.fixture()
def tiny_task(tmp_path, monkeypatch):
    """A 4-turn omni_math task backed by a synthetic 2-band dataset."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "omni_math.yaml").write_text(
        "name: omni_math\n"
        "data_file: omni_math.jsonl\n"
        "total_turns: 4\n"
        "ladder:\n"
        "  - {band: 1, turns: 2}\n"
        "  - {band: 2, turns: 2}\n",
        encoding="utf-8",
    )
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    rows = []
    for band in (1, 2):
        for index in range(4):
            rows.append(
                {
                    "difficulty": float(band),
                    "problem": f"band{band} item{index}",
                    "answer": str(band * 100 + index),
                    "domain": ["d"],
                    "source": "synthetic",
                }
            )
    (data_dir / "omni_math.jsonl").write_text(
        "\n".join(json.dumps(row) for row in rows) + "\n", encoding="utf-8"
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(data_dir))

    task = get_task("omni_math")()
    task.initialize(difficulty=Difficulty.MEDIUM, seed=42)
    return task


def test_three_tasks_are_registered():
    for name in ("omni_math", "hi_tom", "gpqa"):
        assert issubclass(get_task(name), BenchmarkTaskModule)


def test_prepare_follows_the_ladder(tiny_task):
    bands = [
        tiny_task.prepare(None, _turn_context(turn)).metadata["band"]
        for turn in range(1, 5)
    ]
    assert bands == [1, 1, 2, 2]


def test_prepare_never_repeats_an_item(tiny_task):
    ids = [
        tiny_task.prepare(None, _turn_context(turn)).metadata["item_id"]
        for turn in range(1, 5)
    ]
    assert len(set(ids)) == 4


def test_prompt_section_carries_the_question(tiny_task):
    context = tiny_task.prepare(None, _turn_context(1))
    assert "band1 item" in context.prompt_section


def test_score_marks_a_correct_answer(tiny_task):
    context = tiny_task.prepare(None, _turn_context(1))
    expected = context.metadata["expected_answer"]
    parsed = tiny_task.parse_response(f"reasoning\nANSWER: {expected}")
    outcome = tiny_task.score(parsed, None)
    assert outcome.success_factor == 1.0
    assert outcome.metadata["parse_failed"] is False


def test_score_marks_a_wrong_answer(tiny_task):
    tiny_task.prepare(None, _turn_context(1))
    outcome = tiny_task.score(tiny_task.parse_response("ANSWER: 999999"), None)
    assert outcome.success_factor == 0.0
    assert outcome.metadata["parse_failed"] is False


def test_unparseable_response_scores_zero_and_flags(tiny_task):
    tiny_task.prepare(None, _turn_context(1))
    outcome = tiny_task.score(tiny_task.parse_response("I give up"), None)
    assert outcome.success_factor == 0.0
    assert outcome.metadata["parse_failed"] is True


def test_same_seed_reproduces_the_sequence(tiny_task, tmp_path):
    first = [
        tiny_task.prepare(None, _turn_context(turn)).metadata["item_id"]
        for turn in range(1, 5)
    ]
    other = get_task("omni_math")()
    other.initialize(difficulty=Difficulty.MEDIUM, seed=42)
    second = [
        other.prepare(None, _turn_context(turn)).metadata["item_id"]
        for turn in range(1, 5)
    ]
    assert first == second


def test_reset_restarts_the_sequence(tiny_task):
    first = tiny_task.prepare(None, _turn_context(1)).metadata["item_id"]
    tiny_task.reset()
    assert tiny_task.prepare(None, _turn_context(1)).metadata["item_id"] == first


def test_system_rules_state_the_answer_format(tiny_task):
    rules = tiny_task.get_system_rules()
    assert "ANSWER:" in rules


def test_get_available_actions_is_empty(tiny_task):
    assert tiny_task.get_available_actions() == []


def test_manifest_mismatch_warns_but_does_not_block(tiny_task, tmp_path, caplog):
    """A stale MANIFEST.json must warn, never abort a run."""
    import json as _json

    from squid_game.tasks.benchmark.loader import resolve_data_file

    data_dir = tmp_path / "data"
    (data_dir / "MANIFEST.json").write_text(
        _json.dumps(
            {
                "fetched_at": "2026-01-01T00:00:00+00:00",
                "entries": [{"filename": "omni_math.jsonl", "sha256": "0" * 64}],
            }
        ),
        encoding="utf-8",
    )
    with caplog.at_level("WARNING"):
        path = resolve_data_file("omni_math.jsonl", data_dir=data_dir)
    assert path.is_file()
    assert "MANIFEST.json" in caplog.text


def test_missing_data_file_gives_an_actionable_error(tmp_path, monkeypatch):
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "gpqa.yaml").write_text(
        "name: gpqa\ndata_file: gpqa_main.csv\ntotal_turns: 1\n"
        "ladder:\n  - {band: 2, turns: 1}\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("SQUID_GAME_TASK_CONFIG_DIR", str(config_dir))
    monkeypatch.setenv("SQUID_GAME_BENCHMARK_DATA_DIR", str(tmp_path / "empty"))
    task = get_task("gpqa")()
    with pytest.raises(FileNotFoundError, match="fetch_benchmarks"):
        task.initialize(difficulty=Difficulty.MEDIUM, seed=1)
