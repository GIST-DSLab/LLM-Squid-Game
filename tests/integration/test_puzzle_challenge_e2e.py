"""puzzle_challenge end to end, and the byte-identity of everything else.

Spec: docs/history/specs/2026-09-10-signal-game-effort-sensitive-difficulty-design.md

Two notes on how this differs from the plan's draft, both forced by the
code rather than chosen:

* ``patch_runner_provider`` does not run anything. It installs a
  ``StubProvider`` on ``ExperimentRunner._create_provider`` and returns
  that stub; the test then builds the config and calls
  ``ExperimentRunner(cfg).run()`` itself, and reads the turns back off
  ``*_turns.jsonl``. That is the pattern of ``test_forced_wrong_e2e.py``.
* ``TurnResult.system_prompt`` is ``None`` on a turn with no decision
  call, and these cells are ``not_allowed`` with ``always_decide``
  off -- so the prompt-leak test asserts on the bytes the stub actually
  received (``stub.calls``) instead, which is a stronger check anyway.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import yaml

from squid_game.runner import ExperimentRunner, load_config_from_yaml
from squid_game.tasks.signal_game.puzzle import (
    PuzzleSpec,
    cached_puzzle,
    generate_puzzle,
    puzzle_rng,
)

_REPO = Path(__file__).resolve().parents[2]


def _challenge_body(tmp_path: Path) -> dict:
    """One three-round season: easy / medium / hard, rule grading ON."""
    return {
        "name": "challenge-e2e",
        "description": "puzzle_challenge e2e",
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
                    "total_turns": 3,
                    "seed": 42,
                    "history_mode": "outcome",
                    "max_history_turns": 3,
                    "actual_death": False,
                    "starting_score": 0.0,
                    "puzzle_challenge": {
                        "enabled": True,
                        "rule_grading": True,
                        "schedule": [
                            {"turn": 1, "profile": "easy"},
                            {"turn": 2, "profile": "medium"},
                            {"turn": 3, "profile": "hard"},
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
        "lives": {"enabled": True, "initial": 7},
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


def _write(tmp_path: Path, body: dict) -> Path:
    path = tmp_path / "challenge.yaml"
    path.write_text(yaml.safe_dump(body), encoding="utf-8")
    return path


def _turns(tmp_path: Path) -> list[dict]:
    files = list(tmp_path.rglob("*_turns.jsonl"))
    assert len(files) == 1, files
    return [
        json.loads(line)
        for line in files[0].read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


class TestExistingConfigsStillLoad:
    @pytest.mark.parametrize(
        "name",
        [
            "signal_puzzle_smoke.yaml",
            "signal_puzzle_pilot_gptoss_n10.yaml",
            "ransom_r6_gptoss120b.yaml",
        ],
    )
    def test_config_loads_and_has_no_challenge(self, name: str) -> None:
        path = _REPO / "configs" / "experiment" / name
        if not path.is_file():
            pytest.skip(f"{name} is not in this checkout")
        cfg = load_config_from_yaml(str(path))
        for season in cfg.seasons:
            assert season.task_config.puzzle_challenge is None


class TestPlainGenerationIsUnchanged:
    """The trap filter must not perturb the puzzles anyone else generates."""

    @pytest.mark.parametrize(
        "rung_kwargs",
        [
            dict(
                clauses=1,
                conjunctions=0,
                predicates=False,
                overlap_query=False,
                extra_clues=2,
            ),
            dict(
                clauses=3,
                conjunctions=1,
                predicates=True,
                overlap_query=True,
                extra_clues=0,
            ),
            dict(
                clauses=5,
                conjunctions=2,
                predicates=True,
                overlap_query=True,
                extra_clues=0,
            ),
        ],
    )
    def test_cached_puzzle_matches_a_direct_draw(self, rung_kwargs) -> None:
        for seed in (42, 43):
            spec = PuzzleSpec(turn=4, **rung_kwargs)
            a = cached_puzzle(seed, 4, spec)
            b = generate_puzzle(puzzle_rng(seed, 4), spec)
            assert a.rule.description == b.rule.description
            assert a.query == b.query
            assert [str(c) for c in a.clues] == [str(c) for c in b.clues]
            assert a.trap_attempts == 0


class TestChallengeSeasonEndToEnd:
    def test_a_three_round_challenge_season_runs(
        self, tmp_path: Path, patch_runner_provider
    ) -> None:
        """One season, three rounds, easy/medium/hard, rule grading ON.

        The stub answers the task call with an ACTION and no RULE, so every
        round must be graded INCORRECT even when the action is right -- that
        is the whole point of rule grading and it is visible from outside.
        """
        patch_runner_provider(response_fn=lambda i, messages: "ACTION: stay")
        cfg = load_config_from_yaml(str(_write(tmp_path, _challenge_body(tmp_path))))
        ExperimentRunner(cfg).run()

        turns = _turns(tmp_path)
        assert len(turns) == 3
        profiles = [t["task_metadata"]["difficulty_profile"] for t in turns]
        assert profiles == ["easy", "medium", "hard"]
        assert turns[2]["task_metadata"]["trap_query"] is True
        assert turns[0]["task_metadata"]["trap_query"] is False
        assert turns[2]["task_metadata"]["trap_attempts"] >= 1
        for t in turns:
            meta = t["task_metadata"]
            assert meta["rule_graded"] is True
            assert meta["correct"] is False  # no RULE was emitted
            assert meta["actual_correct"] == meta["correct"]
            assert t["task_success_factor"] == 0.0
            assert len(meta["puzzle_id"]) == 12
            assert meta["schedule_id"] == turns[0]["task_metadata"]["schedule_id"]

    def test_the_hard_round_really_defeats_every_shallow_solver(
        self, tmp_path: Path, patch_runner_provider
    ) -> None:
        """The trap profile is not just a label: the record proves it."""
        patch_runner_provider(response_fn=lambda i, messages: "ACTION: stay")
        cfg = load_config_from_yaml(str(_write(tmp_path, _challenge_body(tmp_path))))
        ExperimentRunner(cfg).run()

        hard = _turns(tmp_path)[2]["task_metadata"]
        assert hard["shallow_solvers_correct"] == []
        assert set(hard["shallow_actions"]) == {
            "nn",
            "majority",
            "last_match",
            "single_attr",
        }

    def test_the_trap_round_is_not_named_in_any_prompt(
        self, tmp_path: Path, patch_runner_provider
    ) -> None:
        """The agent must never be told a round is a trap, nor see a solver."""
        stub = patch_runner_provider(response_fn=lambda i, messages: "ACTION: stay")
        cfg = load_config_from_yaml(str(_write(tmp_path, _challenge_body(tmp_path))))
        ExperimentRunner(cfg).run()

        assert stub.calls, "the stub received no calls"
        banned = (
            "trap",
            "shallow",
            "nearest",
            "majority",
            "last_match",
            "single_attr",
            "puzzle_id",
            "difficulty_profile",
            "schedule_id",
            "solver",
            "profile",
        )
        for call in stub.calls:
            sent = "\n".join(m["content"] for m in call.messages).lower()
            for word in banned:
                assert word not in sent, f"{word!r} leaked into a prompt:\n{sent}"

        # And the recorded observation -- the bytes the round showed -- names
        # neither the answer machinery nor the profile.
        for t in _turns(tmp_path):
            observation = (t.get("observation") or "").lower()
            for word in banned:
                assert word not in observation
