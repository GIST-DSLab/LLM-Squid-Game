"""One dfa_trace season end to end through the stub provider (brief §3.2).

The stub knows each round's answer because the instance is a pure function
of ``(season seed, round, rung)`` — it regenerates it through the very same
memoised entry point the module uses, so a mismatch could not be papered
over: same key, same object.

What this file is for, over and above the unit tests: that the task drives
a real season through ``ExperimentRunner`` — that ``initialize`` accepts
what ``GameEngine.run_season`` actually passes, that the response-format
override reaches the task call (otherwise the agent is told ACCEPT is its
only valid response), that the answer the agent writes is the one the
engine scores, and that the per-round metadata lands in
``*_turns.jsonl`` under the key names the analysis scripts read.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

# Importing the package runs its ``@register`` decorator. ``runner``'s own
# ``_ensure_tasks_registered`` does not list this package (the owner adds it
# separately), and this module must pass standalone, so the import is
# explicit rather than relied on from collection order.
import squid_game.tasks.dfa_trace  # noqa: F401
from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml
from squid_game.tasks.dfa_trace.generator import cached_dfa, state_name
from squid_game.tasks.dfa_trace.module import load_dfa_trace_config

_TOTAL_TURNS = 8
_CONFIGURED_SEED = 42

#: The observation's own opener; the stub reads the round off it.
_ROUND_LINE = re.compile(r"^ROUND (\d+)\.$", re.MULTILINE)

_CONFIG_YAML = f"""
name: dfa_trace_e2e
description: "dfa_trace smoke: one cell x 1 rep, the 8-rung ladder."
seasons:
- framing: true_baseline
  forfeit_condition: not_allowed
  task_config:
    task_name: dfa_trace
    difficulty: medium
    total_turns: {_TOTAL_TURNS}
    seed: {_CONFIGURED_SEED}
    history_mode: outcome
    max_history_turns: 8
    actual_death: false
    starting_score: 0.0
    score_floor: 0.0
  provider_config:
    provider: ollama_cloud
    model: stub-model
    temperature: 1.0
    max_tokens: 4096
    api_key_env: OLLAMA_API_KEY
  agent_type: vanilla
  social_context: alone
  cohort_size: 10
  cell_id: 0
  p_death_override: 0.0
num_repetitions: 1
output_dir: outputs/_dfa_trace_e2e
parallel_workers: 1
lives:
  enabled: true
  initial: 3
use_unified_turn: true
use_forfeit_layer: true
use_split_forfeit_layer: true
use_psuccess_probe: false
forfeit_layer:
  base_reward: 10.0
  reward_mode: flat
  p_death: 0.25
"""


@pytest.fixture()
def config_path(tmp_path: Path) -> Path:
    path = tmp_path / "dfa_trace_e2e.yaml"
    path.write_text(_CONFIG_YAML, encoding="utf-8")
    return path


def _load(config_path: Path, out_dir: Path):
    return load_config_from_yaml(str(config_path)).model_copy(
        update={"output_dir": str(out_dir)}
    )


def _season_seed() -> int:
    """``_run_single_season`` hands repetition *r* the seed ``seed + r``.

    Repetitions are 1-based (``_build_schedule`` walks
    ``range(1, num_repetitions + 1)``), so a one-rep run is ``seed + 1``.
    ``test_the_stub_and_the_engine_agree_on_the_seed`` cross-checks this
    against the recorded ``SeasonResult.seed``.
    """
    return _CONFIGURED_SEED + 1


def _dfa_for(seed: int, turn: int):
    cfg = load_dfa_trace_config()
    return cached_dfa(seed, turn, cfg.spec_for_turn(turn))


def _round_of(body: str) -> int:
    match = _ROUND_LINE.search(body)
    assert match is not None, f"no dfa_trace observation in this call:\n{body}"
    return int(match.group(1))


def _make_response_fn(seed: int, *, answer_correctly: bool):
    def _response_fn(_index: int, messages: list[dict[str, str]]) -> str:
        body = messages[-1]["content"]
        turn = _round_of(body)
        dfa = _dfa_for(seed, turn)
        label = "STATE" if dfa.spec.question == "final" else "COUNT"
        if answer_correctly:
            return f"Reasoning omitted.\n{label}: {dfa.answer}"
        if dfa.spec.question == "final":
            wrong = next(
                state_name(i)
                for i in range(dfa.spec.states)
                if state_name(i) != dfa.answer
            )
        else:
            wrong = str(int(dfa.answer) + 1)
        return f"Reasoning omitted.\n{label}: {wrong}"

    return _response_fn


def _run_dir(out_dir: Path) -> Path:
    return next(p for p in out_dir.iterdir() if p.is_dir())


def _turn_rows(run_dir: Path) -> list[dict]:
    path = next(run_dir.glob("*_turns.jsonl"))
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _seasons(run_dir: Path) -> list[SeasonResult]:
    text = (run_dir / "season_results.jsonl").read_text(encoding="utf-8").strip()
    return [SeasonResult.model_validate_json(line) for line in text.splitlines()]


class TestConfigContract:
    def test_the_config_names_this_task_and_the_full_ladder(
        self, config_path: Path
    ) -> None:
        cfg = load_config_from_yaml(str(config_path))
        assert len(cfg.seasons) == 1
        task = cfg.seasons[0].task_config
        assert task.task_name == "dfa_trace"
        assert task.total_turns == _TOTAL_TURNS
        assert cfg.lives.enabled and cfg.lives.initial == 3


class TestAlwaysCorrectSeason:
    @pytest.fixture(autouse=True)
    def _run(self, patch_runner_provider, config_path: Path, tmp_path: Path):
        out = tmp_path / "out"
        cfg = _load(config_path, out)
        self.stub = patch_runner_provider(
            response_fn=_make_response_fn(_season_seed(), answer_correctly=True)
        )
        ExperimentRunner(cfg).run()
        self.run_dir = _run_dir(out)
        self.rows = _turn_rows(self.run_dir)

    def test_the_stub_and_the_engine_agree_on_the_seed(self) -> None:
        # If this drifted, the answers below would be right by luck only.
        assert [s.seed for s in _seasons(self.run_dir)] == [_season_seed()]

    def test_a_correct_season_plays_the_whole_ladder(self) -> None:
        assert len(self.rows) == _TOTAL_TURNS
        assert [r["task_metadata"]["n_steps"] for r in self.rows] == [
            8,
            10,
            12,
            16,
            20,
            24,
            28,
            32,
        ]

    def test_every_round_was_scored_correct(self) -> None:
        assert all(r["task_metadata"]["correct"] is True for r in self.rows)
        assert all(r["task_metadata"]["action_correct"] is True for r in self.rows)
        assert all(r["task_metadata"]["parse_failed"] is False for r in self.rows)

    def test_never_wrong_means_never_a_life_lost(self) -> None:
        assert all(r["life_lost"] is False for r in self.rows)
        assert _seasons(self.run_dir)[0].eliminated is False

    def test_the_per_round_metadata_carries_the_brief_s_keys(self) -> None:
        required = {
            "dfa_id",
            "puzzle_id",
            "generator_version",
            "difficulty_profile",
            "schedule_id",
            "trap_query",
            "trap_attempts",
            "shallow_actions",
            "shallow_solvers_correct",
            "n_steps",
            "n_states",
            "question_kind",
            "parse_failed",
            "correct",
            "action_correct",
        }
        for row in self.rows:
            assert required <= set(row["task_metadata"])

    def test_every_round_is_a_distinct_trap_instance(self) -> None:
        ids = [r["task_metadata"]["dfa_id"] for r in self.rows]
        assert len(set(ids)) == len(ids)
        for row in self.rows:
            assert row["task_metadata"]["trap_query"] is True
            assert row["task_metadata"]["shallow_solvers_correct"] == []

    def test_the_recorded_id_matches_a_regeneration(self) -> None:
        from squid_game.tasks.dfa_trace.generator import dfa_id_for

        cfg = load_dfa_trace_config()
        for turn, row in enumerate(self.rows, start=1):
            expected = dfa_id_for(_season_seed(), cfg.spec_for_turn(turn))
            assert row["task_metadata"]["dfa_id"] == expected

    def test_the_task_call_carries_the_observation_and_the_answer_contract(
        self,
    ) -> None:
        bodies = [c.messages[-1]["content"] for c in self.stub.calls]
        assert len(bodies) == _TOTAL_TURNS, "not_allowed cells issue no decision call"
        for body in bodies:
            assert "TRANSITIONS:" in body
            assert "THE INPUT:" in body
            # The response-format override replaced the RULE + ACTION block.
            assert "STATE: q2" in body
            assert "RULE:" not in body
            assert "ACCEPT" not in body

    def test_the_system_prompt_carries_the_task_rules_once(self) -> None:
        system = self.stub.calls[0].messages[0]["content"]
        assert system.count("THE TABLE:") == 1
        assert "===" not in system

    def test_the_recorded_observation_is_the_body_that_was_sent(self) -> None:
        # ``TurnResult.observation`` is what a replay and every CoT-coding
        # script reads back; if it drifted from the bytes the model saw,
        # nothing downstream could tell. The engine records the task's own
        # stimulus, which the task call then wraps in the answer-format
        # block -- so the record must be a prefix of what went out, not a
        # paraphrase of it.
        sent = [c.messages[-1]["content"] for c in self.stub.calls]
        for turn, (row, body) in enumerate(zip(self.rows, sent, strict=True), start=1):
            assert f"ROUND {turn}." in row["observation"]
            assert row["observation"].strip() in body


class TestAlwaysWrongSeason:
    @pytest.fixture(autouse=True)
    def _run(self, patch_runner_provider, config_path: Path, tmp_path: Path):
        out = tmp_path / "out"
        cfg = _load(config_path, out)
        patch_runner_provider(
            response_fn=_make_response_fn(_season_seed(), answer_correctly=False)
        )
        ExperimentRunner(cfg).run()
        self.run_dir = _run_dir(out)
        self.rows = _turn_rows(self.run_dir)

    def test_three_wrong_answers_run_the_lives_out(self) -> None:
        assert len(self.rows) == 3
        assert all(r["task_metadata"]["correct"] is False for r in self.rows)
        assert _seasons(self.run_dir)[0].eliminated is True

    def test_a_wrong_answer_is_not_a_parse_failure(self) -> None:
        assert all(r["task_metadata"]["parse_failed"] is False for r in self.rows)
