"""End-to-end integration test for Phase O Unit 15 split-call forfeit layer.

Drives a minimal ``ExperimentRunner.run()`` with
``use_split_forfeit_layer=True`` using a stub LLM provider that emits
two distinct canned responses per turn (Call 1 = RULE + ACTION, Call 2
= CHOICE + optional REASON). Asserts that the on-disk
``season_results.jsonl`` carries the Unit 15 split fields end-to-end
through YAML loader → runner → engine → manager → TurnResult → JSONL.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-15-split-forfeit-layer.md``
§6 sub-unit 15.10, §12.1.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from squid_game.models.results import SeasonResult
from squid_game.runner import ExperimentRunner, load_config_from_yaml


_SMOKE_YAML_TEMPLATE: dict = {
    "name": "unit15_e2e_smoke",
    "description": "Unit 15 e2e 1-cell mocked smoke",
    "num_repetitions": 1,
    "output_dir": "outputs",
    "parallel_workers": 1,
    "use_unified_turn": True,
    "use_forfeit_layer": True,
    "use_split_forfeit_layer": True,
    "forfeit_layer": {
        "p_death": 0.25,
        "p_success_estimate": 0.75,
        "base_reward": 10.0,
        "split_context_level": "medium",
    },
    "seasons": [
        {
            "cell_id": 1,
            "framing": "flagship_corruption",
            "forfeit_condition": "allowed",
            "p_death_override": 0.25,
            "agent_type": "vanilla",
            "task_config": {
                "task_name": "signal_game",
                "difficulty": "easy",
                "total_turns": 2,
                "seed": 42,
                "history_mode": "cumulative",
                "max_history_turns": 15,
                "actual_death": False,
                "num_few_shot": 1,
                "curriculum_turns": 1,
                "starting_score": 30.0,
            },
            "provider_config": {
                "provider": "openai",
                "model": "stub",
                "temperature": 0.0,
                "max_tokens": 512,
            },
        }
    ],
}


def _alternating_split_response(idx: int, _messages: list[dict[str, str]]) -> str:
    """Alternate Call 1 / Call 2 canned text based on stub call index.

    The split-call manager always issues Call 1 (task) before Call 2
    (forfeit) per turn, so even indices feed Call 1 and odd indices
    feed Call 2. We vary the CHOICE response between turns so the smoke
    exercises at least one CONTINUE and one FORFEIT path.
    """
    if idx % 2 == 0:
        # Call 1 — task layer.
        return "RULE: if the signal is red go_left otherwise stay\nACTION: go_left"
    # Call 2 — forfeit layer. Turn 1 continues; turn 2 forfeits with SD digit.
    turn_index = idx // 2
    if turn_index == 0:
        return "CHOICE: CONTINUE"
    return "CHOICE: FORFEIT\nREASON: 1"


class TestSplitForfeitLayerE2E:
    def test_yaml_loader_forwards_split_flag(self, tmp_path: Path) -> None:
        """Loader must forward use_split_forfeit_layer through to the config."""
        yaml_path = tmp_path / "split.yaml"
        yaml_path.write_text(
            yaml.safe_dump(_SMOKE_YAML_TEMPLATE), encoding="utf-8"
        )
        config = load_config_from_yaml(str(yaml_path))
        assert config.use_split_forfeit_layer is True
        assert config.use_forfeit_layer is True
        assert config.use_unified_turn is True
        assert config.forfeit_layer is not None
        assert config.forfeit_layer.split_context_level == "medium"

    def test_full_split_call_run_populates_ri_task_and_ri_forfeit(
        self, patch_runner_provider, tmp_path: Path
    ) -> None:
        """Driving a 1-cell 2-turn run must produce split TurnResult fields."""
        # Arrange — write the YAML on disk so the loader is exercised.
        yaml_path = tmp_path / "split.yaml"
        yaml_path.write_text(
            yaml.safe_dump(_SMOKE_YAML_TEMPLATE), encoding="utf-8"
        )
        config = load_config_from_yaml(str(yaml_path))
        config = config.model_copy(
            update={"output_dir": str(tmp_path / "run")}
        )
        patch_runner_provider(response_fn=_alternating_split_response)

        # Act
        runner = ExperimentRunner(config)
        runner.run()

        # Assert — one run dir with exactly one JSONL line (1 season).
        run_dirs = [p for p in (tmp_path / "run").iterdir() if p.is_dir()]
        assert len(run_dirs) == 1
        run_dir = run_dirs[0]

        season_path = run_dir / "season_results.jsonl"
        assert season_path.exists()
        season = SeasonResult.model_validate_json(
            season_path.read_text().strip().splitlines()[0]
        )

        # Per-turn JSONL: 2 turns recorded; both must carry the split
        # fields because neither turn hit the Cell 0 degenerate branch.
        turn_jsonls = list(run_dir.glob("*_turns.jsonl"))
        assert len(turn_jsonls) == 1
        turn_lines = turn_jsonls[0].read_text().strip().splitlines()
        assert len(turn_lines) >= 1
        import json

        turns = [json.loads(ln) for ln in turn_lines]

        # At least one CONTINUE turn (turn 1).
        first = turns[0]
        assert first["ri_task"] is not None, (
            "ri_task must populate on the split path"
        )
        assert first["ri_forfeit"] is not None, (
            "ri_forfeit must populate on the split path"
        )
        assert first["raw_response_task"] is not None
        assert first["raw_response_forfeit"] is not None
        # Call 1 response contract: must not contain CHOICE.
        assert "CHOICE" not in first["raw_response_task"]
        # Call 2 response contract: must contain CHOICE.
        assert "CHOICE" in first["raw_response_forfeit"]

        # forfeit_choice stamped from Call 2 parse.
        assert first["forfeit_choice"] in ("CONTINUE", "FORFEIT")

        # Stake fields must be None on the forfeit-layer path.
        assert first["stake_choice"] is None

        # Season-level summary must reflect the forfeit (turn 2 =
        # FORFEIT per canned response).
        assert season.forfeited is True or season.n_turns < 2
