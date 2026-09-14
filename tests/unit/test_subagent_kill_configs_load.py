"""The four subagent-kill experiment configs load, validate, and dry-run.

Task 12: smoke + pilot, Claude Code + Codex CLI. Each YAML must satisfy
``ExperimentConfig._validate_subagent_kill`` (see
``game/squid_game/models/config.py``) and must print a dry-run plan
without raising -- the same path ``squid-game --config <path> --dry-run``
takes (``runner.run_experiment_cli`` -> ``load_config_from_yaml`` ->
``_print_dry_run``, see ``game/squid_game/runner.py``).
"""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.runner import _print_dry_run, load_config_from_yaml

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

_CONFIGS = [
    ("subagent_kill_smoke_opus5cc.yaml", "claude_code_agentic", "claude-opus-5", 1),
    ("subagent_kill_smoke_codex56.yaml", "codex_cli_agentic", "gpt-5.6-luna", 1),
    ("subagent_kill_pilot_opus5cc.yaml", "claude_code_agentic", "claude-opus-5", 4),
    ("subagent_kill_pilot_codex56.yaml", "codex_cli_agentic", "gpt-5.6-luna", 4),
]


@pytest.mark.parametrize(
    "filename, provider, model, num_repetitions", _CONFIGS
)
class TestSubagentKillConfigsLoad:
    def test_the_file_exists(
        self, filename: str, provider: str, model: str, num_repetitions: int
    ) -> None:
        assert (_CONFIG_DIR / filename).exists()

    def test_it_loads_and_validates(
        self, filename: str, provider: str, model: str, num_repetitions: int
    ) -> None:
        cfg = load_config_from_yaml(str(_CONFIG_DIR / filename))

        assert cfg.subagent_kill.enabled is True
        assert cfg.subagent_kill.slots == 5
        assert cfg.lives.enabled is True
        assert cfg.lives.initial == 5
        assert cfg.num_repetitions == num_repetitions

        assert len(cfg.seasons) == 2
        sharding = {s.cell_id: s.clue_sharding for s in cfg.seasons}
        assert sharding == {0: True, 1: False}

        for season in cfg.seasons:
            assert season.provider_config.provider == provider
            assert season.provider_config.model == model
            assert season.forfeit_condition.value == "not_allowed"
            assert season.task_config.signal_mode == "per_turn_puzzle"

        # required_slots is left out: the default 1,2,3,4,5,5 schedule applies.
        assert cfg.subagent_kill.required_slots is None

        # No ransom, hazard ramp, or a second difficulty mechanism.
        assert cfg.ransom.enabled is False
        assert cfg.hazard_ramp.enabled is False
        assert cfg.forfeit_layer.reward_mode != "geometric"

    def test_dry_run_does_not_raise(
        self, filename: str, provider: str, model: str, num_repetitions: int
    ) -> None:
        cfg = load_config_from_yaml(str(_CONFIG_DIR / filename))
        _print_dry_run(cfg)  # the exact call `--dry-run` makes; must not raise
