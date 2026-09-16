"""Config-level rules for the slot ransom (2026-09-16).

Plan: docs/history/plans/2026-09-16-slot-ransom-merge.md Task 1.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from squid_game.models.config import ExperimentConfig, RansomConfig


def _kill_season(**overrides) -> dict:
    season = {
        "framing": "hz_0000",
        "forfeit_condition": "not_allowed",
        "cell_id": 0,
        "clue_sharding": True,
        "task_config": {
            "task_name": "signal_game",
            "signal_mode": "per_turn_puzzle",
            "total_turns": 6,
            "seed": 43,
            "history_mode": "outcome",
            "max_history_turns": 6,
            "actual_death": False,
            "starting_score": 300.0,
            "score_floor": 0.0,
            "compress_puzzle_ladder": True,
        },
        "provider_config": {"provider": "trace", "model": "trace"},
        "agent_type": "vanilla",
        "social_context": "alone",
        "p_death_override": 0.0,
    }
    season.update(overrides)
    return season


def _config(**overrides) -> dict:
    cfg = {
        "name": "slot_ransom_test",
        "description": "slot ransom config rules",
        "seasons": [_kill_season()],
        "num_repetitions": 1,
        "output_dir": "outputs/_test",
        "lives": {"enabled": True, "initial": 5},
        "subagent_kill": {"enabled": True, "slots": 5},
        "ransom": {"enabled": True, "on_slot_loss": True, "price": 20.0},
        "use_unified_turn": True,
        "use_forfeit_layer": True,
        "use_split_forfeit_layer": True,
        "use_psuccess_probe": False,
        "forfeit_layer": {"base_reward": 10.0, "reward_mode": "flat",
                          "always_decide": False},
        "score_policy": {"forfeit": "keep", "elimination": "keep"},
        "carrot": "none",
    }
    cfg.update(overrides)
    return cfg


def test_the_switch_defaults_off():
    assert RansomConfig().on_slot_loss is False


def test_slot_mode_admits_the_kill_and_five_lives():
    config = ExperimentConfig(**_config())
    assert config.ransom.on_slot_loss is True
    assert config.subagent_kill.enabled is True
    assert config.lives.initial == 5


def test_slot_mode_requires_the_kill():
    with pytest.raises(ValidationError, match="on_slot_loss"):
        ExperimentConfig(**_config(subagent_kill={"enabled": False},
                                   seasons=[_kill_season(clue_sharding=None)]))


def test_without_the_switch_the_kill_still_rejects_the_ransom():
    with pytest.raises(ValidationError, match="second exit"):
        ExperimentConfig(**_config(ransom={"enabled": True, "price": 20.0}))


def test_the_single_life_rule_still_holds_off_slot_mode():
    with pytest.raises(ValidationError, match="exactly one life"):
        ExperimentConfig(**_config(
            subagent_kill={"enabled": False},
            seasons=[_kill_season(clue_sharding=None)],
            ransom={"enabled": True, "price": 20.0},
        ))


def test_on_slot_loss_without_the_ransom_is_rejected():
    with pytest.raises(ValidationError, match="ransom.enabled"):
        ExperimentConfig(**_config(
            subagent_kill={"enabled": False},
            seasons=[_kill_season(clue_sharding=None)],
            ransom={"enabled": False, "on_slot_loss": True},
        ))
