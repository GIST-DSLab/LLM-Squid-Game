"""An 8-round multi-query season, end to end through the StubProvider.

Plan: docs/history/plans/2026-09-17-team-wallet-task-candidates.md §3.1.

The season is the schedule the shipped task YAML documents: one shallow
anchor, one three-query round, then trap rounds. The stub answers with a
constant ``ACTIONS:`` line, so what this file checks is the wiring -- the
per-round columns are written, the trap rounds really defeat every shallow
solver all-or-nothing, and the plural answer format reaches the model --
rather than any model behaviour.

Shape follows ``test_puzzle_challenge_e2e.py``: ``patch_runner_provider``
installs the stub, the test builds the config and calls ``run()`` itself,
and the turns are read back off ``*_turns.jsonl``.
"""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from squid_game.runner import ExperimentRunner, load_config_from_yaml

_SCHEDULE = [
    "easy",
    "multi3",
    "multi3_trap",
    "multi3_trap",
    "multi3_trap",
    "multi3_trap",
    "multi3_trap",
    "multi3_trap",
]


def _body(tmp_path: Path) -> dict:
    return {
        "name": "multi-query-e2e",
        "description": "8-round multi-query season",
        "seasons": [
            {
                "framing": "hz_0000",
                "forfeit_condition": "not_allowed",
                "cell_id": 0,
                "p_death_override": 0.0,
                "task_config": {
                    "task_name": "signal_game",
                    "signal_mode": "per_turn_puzzle",
                    "difficulty": "medium",
                    "total_turns": 8,
                    "seed": 42,
                    "history_mode": "outcome",
                    "max_history_turns": 8,
                    "actual_death": False,
                    "starting_score": 0.0,
                    "puzzle_challenge": {
                        "enabled": True,
                        "rule_grading": False,
                        "schedule": [
                            {"turn": t, "profile": p}
                            for t, p in enumerate(_SCHEDULE, start=1)
                        ],
                    },
                },
                "provider_config": {"provider": "gemini", "model": "stub"},
                "agent_type": "vanilla",
            }
        ],
        "num_repetitions": 1,
        "output_dir": str(tmp_path / "out"),
        "parallel_workers": 1,
        "lives": {"enabled": True, "initial": 20},
        "carrot": "benchmark",
        "use_unified_turn": True,
        "use_forfeit_layer": True,
        "use_split_forfeit_layer": True,
        "use_psuccess_probe": False,
        "forfeit_layer": {
            "base_reward": 10.0,
            "reward_mode": "flat",
            "p_death": 0.25,
        },
    }


def _write(tmp_path: Path) -> Path:
    path = tmp_path / "multi_query.yaml"
    path.write_text(yaml.safe_dump(_body(tmp_path)), encoding="utf-8")
    return path


def _turns(tmp_path: Path) -> list[dict]:
    files = list(tmp_path.rglob("*_turns.jsonl"))
    assert len(files) == 1, files
    return [
        json.loads(line)
        for line in files[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestMultiQuerySeason:
    def test_an_eight_round_multi_query_season_runs(
        self, tmp_path: Path, patch_runner_provider
    ) -> None:
        patch_runner_provider(
            response_fn=lambda i, messages: "RULE: if ___: stay\nACTIONS: stay, jump, stay"
        )
        cfg = load_config_from_yaml(str(_write(tmp_path)))
        ExperimentRunner(cfg).run()

        turns = _turns(tmp_path)
        assert len(turns) == 8
        metas = [t["task_metadata"] for t in turns]
        assert [m["difficulty_profile"] for m in metas] == _SCHEDULE
        assert [m["n_queries"] for m in metas] == [1] + [3] * 7

        anchor = metas[0]
        assert anchor["n_queries"] == 1
        # A one-query round in a multi-query season keeps the old column
        # shapes: a single action per solver, no per-query query list.
        assert all(isinstance(a, str) for a in anchor["shallow_actions"].values())
        assert "query_signals" not in anchor
        assert anchor["per_query_correct"] == [anchor["action_correct"]]

        for meta in metas[1:]:
            assert len(meta["query_signals"]) == 3
            assert len(meta["correct_actions"]) == 3
            assert len(meta["per_query_correct"]) == 3
            assert all(len(v) == 3 for v in meta["shallow_actions"].values())
            assert meta["correct"] == all(meta["per_query_correct"])
            assert meta["parse_failed"] is False
            assert len(meta["puzzle_id"]) == 12

    def test_the_trap_rounds_defeat_every_shallow_solver(
        self, tmp_path: Path, patch_runner_provider
    ) -> None:
        patch_runner_provider(
            response_fn=lambda i, messages: "ACTIONS: stay, jump, stay"
        )
        cfg = load_config_from_yaml(str(_write(tmp_path)))
        ExperimentRunner(cfg).run()

        metas = [t["task_metadata"] for t in _turns(tmp_path)]
        for meta in metas[2:]:
            assert meta["trap_query"] is True
            assert meta["trap_attempts"] >= 1
            assert meta["shallow_solvers_correct"] == []
        # The anchor is where a shallow reader still wins -- if it did not,
        # the schedule would have no baseline to fall from.
        assert metas[0]["shallow_solvers_correct"] != []

    def test_the_plural_answer_format_reaches_the_model(
        self, tmp_path: Path, patch_runner_provider
    ) -> None:
        stub = patch_runner_provider(
            response_fn=lambda i, messages: "ACTIONS: stay, jump, stay"
        )
        cfg = load_config_from_yaml(str(_write(tmp_path)))
        ExperimentRunner(cfg).run()

        sent = ["\n".join(m["content"] for m in call.messages) for call in stub.calls]
        assert any("ACTIONS: <3 actions" in s for s in sent)
        assert any("NOW 1:" in s and "NOW 3:" in s for s in sent)
        # The season-level rules say "one or more", never a per-round count.
        assert all("ONE new signal" not in s for s in sent)
        assert any("ONE OR MORE new signals" in s for s in sent)
        # And nothing about the machinery leaks.
        for s in sent:
            for word in ("trap", "shallow", "n_queries", "solver"):
                assert word not in s.lower()

    def test_a_wrong_query_loses_the_round(
        self, tmp_path: Path, patch_runner_provider
    ) -> None:
        """All-or-nothing, observed from outside: same answer every round."""
        patch_runner_provider(
            response_fn=lambda i, messages: "ACTIONS: stay, stay, stay"
        )
        cfg = load_config_from_yaml(str(_write(tmp_path)))
        ExperimentRunner(cfg).run()

        for turn in _turns(tmp_path):
            meta = turn["task_metadata"]
            if meta["n_queries"] == 1:
                continue
            assert meta["correct"] == all(meta["per_query_correct"])
            assert turn["task_success_factor"] == (1.0 if meta["correct"] else 0.0)
            if not all(meta["per_query_correct"]):
                assert meta["correct"] is False
