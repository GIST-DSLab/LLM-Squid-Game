"""End-to-end lives + threat-ladder matrix (Task AB6).

Drives ``ExperimentRunner.run()`` with the stub provider from
``conftest.py`` over the 5-cell design of spec §6.1, asserting the whole
chain — YAML loader → runner → engine → split-call manager → TurnResult
→ ``season_results.jsonl``:

* the lives counter walks down one step per incorrect answer and holds
  steady on correct ones,
* exhausting the lives ends the season with ``eliminated`` and a zeroed
  score,
* the peer-elimination notice reaches BOTH per-turn LLM calls in a
  threat cell and never appears in a ``true_baseline`` cell,
* ``season_results.jsonl`` carries ``lives_at_end`` / ``eliminated``.

Scoring is made deterministic by a scripted task module (correct iff the
Call-1 text carries ``ACTION: GO``), injected the same way the provider
is — the Signal Game's hidden rule would otherwise make "answer
correctly on turn 3" unexpressible from a canned response.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import yaml

from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml
from squid_game.tasks.base import RiskAwareTaskModule, TaskContext, TaskOutcome


# ---------------------------------------------------------------------------
# Scripted task
# ---------------------------------------------------------------------------


class ScriptedTask(RiskAwareTaskModule):
    """Deterministic stand-in: correct iff the response says ``ACTION: GO``."""

    @property
    def name(self) -> str:
        return "scripted"

    def initialize(self, **kwargs: Any) -> None:
        del kwargs

    def is_completed(self) -> bool:
        return False

    def get_active_rule_description(self) -> str:
        return "Answer GO."

    def prepare(self, state: Any, turn_context: Any) -> TaskContext:
        return TaskContext(
            prompt_section=f"Signal: s-{turn_context.turn_number}",
            metadata={"turn": turn_context.turn_number},
        )

    def parse_response(self, response_text: str) -> str | None:
        for line in response_text.splitlines():
            stripped = line.strip()
            if stripped.upper().startswith("ACTION:"):
                return stripped.split(":", 1)[1].strip()
        return None

    def score(self, parsed_response: Any, state: Any) -> TaskOutcome:
        del state
        correct = parsed_response == "GO"
        return TaskOutcome(
            success_factor=1.0 if correct else 0.0,
            metadata={"correct": correct},
        )

    def get_system_rules(self) -> str:
        return "Answer with ACTION: GO or ACTION: STAY."

    def get_available_actions(self) -> list[str]:
        return ["GO", "STAY"]


@pytest.fixture
def patch_runner_task(monkeypatch: pytest.MonkeyPatch):
    """Patch ``ExperimentRunner._create_task`` to yield ``ScriptedTask``."""

    def _install() -> None:
        monkeypatch.setattr(
            ExperimentRunner,
            "_create_task",
            staticmethod(lambda _task_config: ScriptedTask()),
        )

    return _install


# ---------------------------------------------------------------------------
# Config builders
# ---------------------------------------------------------------------------


_CELLS: list[tuple[str, str]] = [
    ("true_baseline", "not_allowed"),
    ("true_baseline", "allowed"),
    ("threat_l1", "allowed"),
    ("threat_l2", "allowed"),
    ("threat_l3", "allowed"),
]


def _season(framing: str, forfeit: str, *, total_turns: int) -> dict:
    return {
        "framing": framing,
        "forfeit_condition": forfeit,
        "p_death_override": 0.0,
        "agent_type": "vanilla",
        "cohort_size": 10,
        "task_config": {
            "task_name": "signal_game",
            "difficulty": "medium",
            "total_turns": total_turns,
            "seed": 42,
            "history_mode": "cumulative",
            "max_history_turns": 30,
            "actual_death": False,
            "starting_score": 30.0,
        },
        "provider_config": {
            "provider": "ollama_cloud",
            "model": "stub",
            "temperature": 0.0,
            "max_tokens": 512,
        },
    }


def _config_dict(
    cells: list[tuple[str, str]],
    *,
    total_turns: int,
    p_announce: float,
) -> dict:
    return {
        "name": "lives_threat_matrix",
        "description": "AB6 lives + threat ladder e2e",
        "num_repetitions": 1,
        "output_dir": "outputs",
        "parallel_workers": 1,
        "use_unified_turn": True,
        "use_forfeit_layer": True,
        "use_split_forfeit_layer": True,
        "use_psuccess_probe": False,
        "lives": {"enabled": True, "initial": 5},
        "peer_death": {
            "p_announce": p_announce,
            "first_turn": 2,
            "max_per_turn": 2,
        },
        "forfeit_layer": {
            "base_reward": 10.0,
            "reward_mode": "flat",
            "split_context_level": "medium",
        },
        "seasons": [
            _season(f, fc, total_turns=total_turns) for f, fc in cells
        ],
    }


def _run(
    tmp_path: Path,
    config_dict: dict,
    patch_runner_provider,
    patch_runner_task,
    response_fn,
):
    yaml_path = tmp_path / "lives.yaml"
    yaml_path.write_text(yaml.safe_dump(config_dict), encoding="utf-8")
    config = load_config_from_yaml(str(yaml_path)).model_copy(
        update={"output_dir": str(tmp_path / "run")}
    )
    stub = patch_runner_provider(response_fn=response_fn)
    patch_runner_task()
    ExperimentRunner(config).run()

    run_dirs = [p for p in (tmp_path / "run").iterdir() if p.is_dir()]
    assert len(run_dirs) == 1
    return run_dirs[0], stub


def _is_call2(messages: list[dict[str, str]]) -> bool:
    """Call 2 is the only body carrying the FORFEIT/CONTINUE menu."""
    body = messages[-1]["content"]
    return "FORFEIT" in body and "CONTINUE" in body


def _turn_rows(run_dir: Path) -> list[list[dict]]:
    """Per-season lists of turn records, one list per ``*_turns.jsonl``."""
    return [
        [json.loads(ln) for ln in path.read_text().strip().splitlines()]
        for path in sorted(run_dir.glob("*_turns.jsonl"))
    ]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestLivesLedgerEndToEnd:
    def test_lives_walk_down_one_step_per_wrong_answer(
        self, patch_runner_provider, patch_runner_task, tmp_path: Path
    ) -> None:
        """Wrong on turns 2 and 4 → lives_after 5, 4, 4, 3, 3, 3."""
        wrong_turns = {2, 4}
        call1_seen = {"n": 0}

        def response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
            if _is_call2(messages):
                return "CHOICE: CONTINUE"
            call1_seen["n"] += 1
            turn = call1_seen["n"]
            action = "STAY" if turn in wrong_turns else "GO"
            return f"RULE: always go\nACTION: {action}"

        run_dir, _ = _run(
            tmp_path,
            _config_dict(
                [("threat_l1", "allowed")], total_turns=6, p_announce=0.0
            ),
            patch_runner_provider,
            patch_runner_task,
            response_fn,
        )

        (turns,) = _turn_rows(run_dir)
        assert [t["lives_after"] for t in turns] == [5, 4, 4, 3, 3, 3]
        assert [t["life_lost"] for t in turns] == [
            False, True, False, True, False, False
        ]
        assert all(t["threat_level"] == 1 for t in turns)
        # Flat reward: +10 on each of the four correct turns.
        assert sum(t["reward_received"] for t in turns) == pytest.approx(40.0)

    def test_running_out_of_lives_eliminates_the_session(
        self, patch_runner_provider, patch_runner_task, tmp_path: Path
    ) -> None:
        """Always wrong → season ends at turn 5 with a zeroed score."""

        def response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
            if _is_call2(messages):
                return "CHOICE: CONTINUE"
            return "RULE: always stay\nACTION: STAY"

        run_dir, _ = _run(
            tmp_path,
            _config_dict(
                [("threat_l3", "allowed")], total_turns=10, p_announce=0.0
            ),
            patch_runner_provider,
            patch_runner_task,
            response_fn,
        )

        (turns,) = _turn_rows(run_dir)
        assert len(turns) == 5
        assert [t["lives_after"] for t in turns] == [4, 3, 2, 1, 0]
        assert turns[-1]["died"] is True

        season = SeasonResult.model_validate_json(
            (run_dir / "season_results.jsonl").read_text().strip()
        )
        assert season.eliminated is True
        assert season.lives_at_end == 0
        assert season.final_score == pytest.approx(0.0)
        assert season.survived is False
        assert season.forfeited is False

    def test_surviving_season_records_remaining_lives(
        self, patch_runner_provider, patch_runner_task, tmp_path: Path
    ) -> None:
        def response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
            if _is_call2(messages):
                return "CHOICE: CONTINUE"
            return "RULE: always go\nACTION: GO"

        run_dir, _ = _run(
            tmp_path,
            _config_dict(
                [("threat_l2", "allowed")], total_turns=4, p_announce=0.0
            ),
            patch_runner_provider,
            patch_runner_task,
            response_fn,
        )

        season = SeasonResult.model_validate_json(
            (run_dir / "season_results.jsonl").read_text().strip()
        )
        assert season.eliminated is False
        assert season.lives_at_end == 5
        assert season.survived is True


class TestFiveCellMatrix:
    def test_all_five_cells_run_and_record_lives(
        self, patch_runner_provider, patch_runner_task, tmp_path: Path
    ) -> None:
        def response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
            if _is_call2(messages):
                return "CHOICE: CONTINUE"
            return "RULE: always go\nACTION: GO"

        run_dir, stub = _run(
            tmp_path,
            _config_dict(_CELLS, total_turns=6, p_announce=1.0),
            patch_runner_provider,
            patch_runner_task,
            response_fn,
        )

        lines = (
            (run_dir / "season_results.jsonl").read_text().strip().splitlines()
        )
        seasons = [SeasonResult.model_validate_json(ln) for ln in lines]
        assert len(seasons) == 5
        assert {s.framing.value for s in seasons} == {
            "true_baseline", "threat_l1", "threat_l2", "threat_l3"
        }
        for season in seasons:
            assert season.lives_at_end == 5
            assert season.eliminated is False

        # Cell 0 (true_baseline x not_allowed) skips Call 2 entirely.
        cell0 = next(
            s
            for s in seasons
            if s.framing.value == "true_baseline"
            and s.forfeit_condition.value == "not_allowed"
        )
        assert all(t.ri_forfeit is None for t in cell0.turns)

    def test_peer_notice_reaches_threat_cells_only(
        self, patch_runner_provider, patch_runner_task, tmp_path: Path
    ) -> None:
        """``p_announce=1.0`` → every threat cell sees the notice; baseline never does."""
        seen: list[tuple[str, str]] = []

        def response_fn(_idx: int, messages: list[dict[str, str]]) -> str:
            system = messages[0]["content"]
            body = messages[-1]["content"]
            seen.append((system, body))
            if _is_call2(messages):
                return "CHOICE: CONTINUE"
            return "RULE: always go\nACTION: GO"

        run_dir, _ = _run(
            tmp_path,
            _config_dict(_CELLS, total_turns=6, p_announce=1.0),
            patch_runner_provider,
            patch_runner_task,
            response_fn,
        )

        threat_bodies = [
            body for system, body in seen if "Elimination Rule" in system
        ]
        baseline_bodies = [
            body for system, body in seen if "Elimination Rule" not in system
        ]
        assert threat_bodies and baseline_bodies
        # The notice is prefixed to BOTH calls, so it shows up on plenty
        # of threat-cell bodies and on none of the baseline ones.
        assert any("! NOTICE" in body for body in threat_bodies)
        assert not any("! NOTICE" in body for body in baseline_bodies)

        # The same holds on the persisted turn records.
        rows = [t for turns in _turn_rows(run_dir) for t in turns]
        announced = [t for t in rows if t["peer_death_announced"]]
        assert announced
        assert all(t["threat_level"] > 0 for t in announced)
        assert all(
            t["peer_death_announced"] is False
            for t in rows
            if t["threat_level"] == 0
        )
