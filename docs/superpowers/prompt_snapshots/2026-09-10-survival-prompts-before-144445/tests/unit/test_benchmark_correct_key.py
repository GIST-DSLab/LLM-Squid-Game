"""Benchmark turns must expose correctness the way the Signal Game does."""

import json
from pathlib import Path

from squid_game.evaluation.semantic.dataset import RunSpec, load_turns


def _write_run(tmp_path: Path, records: list[dict]) -> Path:
    run = tmp_path / "20260904_0000_model_omni-math"
    run.mkdir()
    (run / "abc_turns.jsonl").write_text("\n".join(json.dumps(r) for r in records) + "\n")
    return run


def _rec(turn, **kw):
    base = {"season_id": "s1", "turn_number": turn, "framing": "true_baseline",
            "forfeit_condition": "allowed", "reward_received": 0.0, "task_metadata": {}}
    base.update(kw)
    return base


def test_loader_falls_back_to_success_factor_when_correct_key_missing(tmp_path):
    run = _write_run(tmp_path, [
        _rec(1, task_success_factor=1.0, task_metadata={"band": 1}),
        _rec(2, task_success_factor=0.0, task_metadata={"band": 1}),
        _rec(3, task_success_factor=0.0, task_metadata={"band": 1, "correct": True}),
    ])
    frame = load_turns(RunSpec.from_dir(run))
    assert frame.sort_values("turn_number")["correct"].tolist() == [True, False, True]


def test_benchmark_score_metadata_carries_correct():
    from squid_game.tasks.benchmark.module import BenchmarkTaskModule
    import inspect
    src = inspect.getsource(BenchmarkTaskModule.score)
    assert '"correct": bool(correct)' in src
