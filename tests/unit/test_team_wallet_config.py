"""Config-level rules for the team wallet (2026-09-17).

Plan: docs/history/plans/2026-09-17-team-wallet-engine-plan.md section 1.
One test per rule, accept and refuse, plus the two loader gates every
new YAML key has to pass (``runner.load_config_from_yaml``'s fixed key
lists AND the model) and the dump -> reload round trip.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from squid_game.models.config import (
    ExperimentConfig,
    RansomConfig,
    SubagentKillConfig,
    TaskConfig,
)
from squid_game.runner import load_config_from_yaml

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"


def _wallet_season(**overrides) -> dict:
    task = {
        "task_name": "signal_game",
        "signal_mode": "per_turn_puzzle",
        "total_turns": 6,
        "seed": 43,
        "history_mode": "outcome",
        "max_history_turns": 6,
        "actual_death": False,
        "starting_balance": 100.0,
        "score_floor": 0.0,
        "compress_puzzle_ladder": True,
    }
    task.update(overrides.pop("task_config", {}))
    season = {
        "framing": "hz_0000",
        "forfeit_condition": "not_allowed",
        "cell_id": 0,
        "clue_sharding": True,
        "task_config": task,
        "provider_config": {"provider": "trace", "model": "trace"},
        "agent_type": "vanilla",
        "social_context": "alone",
        "p_death_override": 0.0,
    }
    season.update(overrides)
    return season


def _config(**overrides) -> dict:
    cfg = {
        "name": "team_wallet_test",
        "description": "team wallet config rules",
        "seasons": [_wallet_season()],
        "num_repetitions": 1,
        "output_dir": "outputs/_test",
        "lives": {"enabled": True, "initial": 2},
        "subagent_kill": {
            "enabled": True,
            "slots": 2,
            "main_holds_bundle": True,
        },
        "ransom": {
            "enabled": True,
            "on_slot_loss": True,
            "team_wallet": True,
            "price": 60.0,
        },
        "currency": "tokens",
        "use_unified_turn": True,
        "use_forfeit_layer": True,
        "use_split_forfeit_layer": True,
        "use_psuccess_probe": False,
        "forfeit_layer": {
            "base_reward": 10.0,
            "reward_mode": "flat",
            "always_decide": False,
        },
        "score_policy": {"forfeit": "keep", "elimination": "keep"},
        "carrot": "none",
    }
    cfg.update(overrides)
    return cfg


class TestDefaults:
    """Every new key is off / today's value, so existing YAML is unchanged."""

    def test_team_wallet_defaults_off(self) -> None:
        assert RansomConfig().team_wallet is False

    def test_inheritance_defaults_to_main(self) -> None:
        assert RansomConfig().inheritance == "main"

    def test_currency_defaults_to_points(self) -> None:
        cfg = ExperimentConfig(
            name="x",
            seasons=[_wallet_season(
                clue_sharding=None,
                task_config={"starting_balance": None, "starting_score": 0.0},
            )],
        )
        assert cfg.currency == "points"

    def test_starting_balance_defaults_to_none(self) -> None:
        assert TaskConfig(task_name="signal_game").starting_balance is None

    def test_main_holds_bundle_defaults_off(self) -> None:
        assert SubagentKillConfig().main_holds_bundle is False


class TestTeamWalletRequirements:
    def test_the_full_team_wallet_config_is_accepted(self) -> None:
        cfg = ExperimentConfig(**_config())
        assert cfg.ransom.team_wallet is True
        assert cfg.ransom.inheritance == "main"
        assert cfg.currency == "tokens"
        assert cfg.subagent_kill.main_holds_bundle is True
        assert cfg.seasons[0].task_config.starting_balance == 100.0

    def test_it_requires_the_ransom_itself(self) -> None:
        with pytest.raises(ValidationError, match="team_wallet"):
            ExperimentConfig(**_config(
                ransom={"enabled": False, "team_wallet": True},
                subagent_kill={"enabled": False},
                currency="points",
                seasons=[_wallet_season(clue_sharding=None)],
            ))

    def test_it_requires_on_slot_loss(self) -> None:
        with pytest.raises(ValidationError, match="on_slot_loss"):
            ExperimentConfig(**_config(ransom={
                "enabled": True,
                "on_slot_loss": False,
                "team_wallet": True,
                "price": 60.0,
            }))

    def test_it_requires_the_subagent_roster(self) -> None:
        with pytest.raises(ValidationError, match="subagent_kill.enabled"):
            ExperimentConfig(**_config(
                subagent_kill={"enabled": False},
                seasons=[_wallet_season(clue_sharding=None)],
            ))

    def test_it_requires_main_holds_bundle(self) -> None:
        with pytest.raises(ValidationError, match="main_holds_bundle"):
            ExperimentConfig(**_config(
                subagent_kill={"enabled": True, "slots": 2,
                               "main_holds_bundle": False},
            ))

    def test_it_requires_a_starting_balance_on_every_season(self) -> None:
        with pytest.raises(ValidationError, match="starting_balance"):
            ExperimentConfig(**_config(seasons=[_wallet_season(
                task_config={"starting_balance": None, "starting_score": 100.0},
            )]))


class TestInheritance:
    def test_mate_is_accepted_under_the_team_wallet(self) -> None:
        cfg = ExperimentConfig(**_config(ransom={
            "enabled": True,
            "on_slot_loss": True,
            "team_wallet": True,
            "inheritance": "mate",
            "price": 60.0,
        }))
        assert cfg.ransom.inheritance == "mate"

    def test_mate_without_the_team_wallet_is_refused(self) -> None:
        """Silent no-op guard: nothing would read the factor."""
        with pytest.raises(ValidationError, match="inheritance"):
            ExperimentConfig(**_config(
                ransom={
                    "enabled": True,
                    "on_slot_loss": True,
                    "team_wallet": False,
                    "inheritance": "mate",
                    "price": 60.0,
                },
                currency="points",
                seasons=[_wallet_season(task_config={
                    "starting_balance": None, "starting_score": 100.0,
                })],
            ))


class TestCurrency:
    def test_tokens_without_the_team_wallet_is_refused(self) -> None:
        with pytest.raises(ValidationError, match="currency"):
            ExperimentConfig(**_config(
                ransom={"enabled": True, "on_slot_loss": True, "price": 60.0},
                currency="tokens",
                seasons=[_wallet_season(task_config={
                    "starting_balance": None, "starting_score": 100.0,
                })],
            ))

    def test_points_is_unrestricted(self) -> None:
        cfg = ExperimentConfig(**_config(
            ransom={"enabled": True, "on_slot_loss": True, "price": 60.0},
            currency="points",
            seasons=[_wallet_season(task_config={
                "starting_balance": None, "starting_score": 100.0,
            })],
        ))
        assert cfg.currency == "points"


class TestStartingBalance:
    def test_it_may_repeat_starting_score(self) -> None:
        task = TaskConfig(
            task_name="signal_game",
            starting_balance=100.0,
            starting_score=100.0,
        )
        assert task.starting_balance == 100.0

    def test_two_different_numbers_are_refused(self) -> None:
        with pytest.raises(ValidationError, match="starting_balance"):
            TaskConfig(
                task_name="signal_game",
                starting_balance=100.0,
                starting_score=300.0,
            )

    def test_it_is_refused_outside_the_team_wallet(self) -> None:
        """Silent no-op guard: nothing would read the per-agent balance."""
        with pytest.raises(ValidationError, match="starting_balance"):
            ExperimentConfig(**_config(
                ransom={"enabled": True, "on_slot_loss": True, "price": 60.0},
                currency="points",
            ))


class TestMainHoldsBundle:
    def test_it_is_refused_without_the_roster(self) -> None:
        with pytest.raises(ValidationError, match="main_holds_bundle"):
            ExperimentConfig(**_config(
                subagent_kill={"enabled": False, "main_holds_bundle": True},
                ransom={"enabled": False},
                currency="points",
                seasons=[_wallet_season(
                    clue_sharding=None,
                    task_config={"starting_balance": None,
                                 "starting_score": 100.0},
                )],
            ))

    def test_zero_required_slots_is_allowed_when_main_holds_a_bundle(
        self,
    ) -> None:
        cfg = ExperimentConfig(**_config(subagent_kill={
            "enabled": True,
            "slots": 2,
            "main_holds_bundle": True,
            "required_slots": [0, 0, 1, 1, 2, 2],
        }))
        assert cfg.subagent_kill.required_slots == [0, 0, 1, 1, 2, 2]

    def test_zero_is_still_refused_without_the_main_bundle(self) -> None:
        with pytest.raises(ValidationError, match="required_slots"):
            ExperimentConfig(**_config(
                ransom={"enabled": True, "on_slot_loss": True, "price": 60.0},
                currency="points",
                lives={"enabled": True, "initial": 2},
                subagent_kill={
                    "enabled": True,
                    "slots": 2,
                    "main_holds_bundle": False,
                    "required_slots": [0, 0, 1, 1, 2, 2],
                },
                seasons=[_wallet_season(task_config={
                    "starting_balance": None, "starting_score": 100.0,
                })],
            ))

    def test_above_the_roster_is_still_refused(self) -> None:
        with pytest.raises(ValidationError, match="required_slots"):
            ExperimentConfig(**_config(subagent_kill={
                "enabled": True,
                "slots": 2,
                "main_holds_bundle": True,
                "required_slots": [0, 0, 1, 1, 2, 3],
            }))


class TestLivesEqualsSlots:
    def test_the_team_wallet_does_not_require_the_equality(self) -> None:
        cfg = ExperimentConfig(**_config(
            lives={"enabled": True, "initial": 1},
        ))
        assert cfg.lives.initial == 1
        assert cfg.subagent_kill.slots == 2

    def test_off_the_team_wallet_the_equality_still_holds(self) -> None:
        with pytest.raises(ValidationError, match="lives.initial"):
            ExperimentConfig(**_config(
                lives={"enabled": True, "initial": 1},
                ransom={"enabled": True, "on_slot_loss": True, "price": 60.0},
                currency="points",
                subagent_kill={"enabled": True, "slots": 2},
                seasons=[_wallet_season(task_config={
                    "starting_balance": None, "starting_score": 100.0,
                })],
            ))


class TestLoaderForwarding:
    """Both gates: the loader's fixed key lists and the model."""

    def _write(self, tmp_path: Path) -> Path:
        raw = _config()
        season = raw["seasons"][0]
        yaml_doc = {
            "name": raw["name"],
            "description": raw["description"],
            "num_repetitions": 1,
            "output_dir": raw["output_dir"],
            "lives": raw["lives"],
            "subagent_kill": raw["subagent_kill"],
            "ransom": raw["ransom"],
            "currency": raw["currency"],
            "use_unified_turn": True,
            "use_forfeit_layer": True,
            "use_split_forfeit_layer": True,
            "use_psuccess_probe": False,
            "forfeit_layer": raw["forfeit_layer"],
            "score_policy": raw["score_policy"],
            "carrot": raw["carrot"],
            "seasons": [
                {
                    "framing": season["framing"],
                    "forfeit_condition": season["forfeit_condition"],
                    "cell_id": season["cell_id"],
                    "clue_sharding": season["clue_sharding"],
                    "task": {
                        "name": "signal_game",
                        **{
                            k: v
                            for k, v in season["task_config"].items()
                            if k != "task_name"
                        },
                    },
                    "provider": season["provider_config"],
                    "agent_type": season["agent_type"],
                    "social_context": season["social_context"],
                    "p_death_override": 0.0,
                }
            ],
        }
        path = tmp_path / "team_wallet_loader.yaml"
        path.write_text(yaml.safe_dump(yaml_doc), encoding="utf-8")
        return path

    def test_every_new_key_survives_the_loader(self, tmp_path: Path) -> None:
        cfg = load_config_from_yaml(str(self._write(tmp_path)))

        assert cfg.ransom.team_wallet is True
        assert cfg.ransom.inheritance == "main"
        assert cfg.currency == "tokens"
        assert cfg.subagent_kill.main_holds_bundle is True
        assert cfg.seasons[0].task_config.starting_balance == 100.0

    def test_the_inheritance_arm_survives_too(self, tmp_path: Path) -> None:
        path = self._write(tmp_path)
        doc = yaml.safe_load(path.read_text(encoding="utf-8"))
        doc["ransom"]["inheritance"] = "mate"
        path.write_text(yaml.safe_dump(doc), encoding="utf-8")

        assert load_config_from_yaml(str(path)).ransom.inheritance == "mate"


class TestRoundTrip:
    def test_dump_then_reload_gives_the_same_config(self) -> None:
        cfg = ExperimentConfig(**_config(ransom={
            "enabled": True,
            "on_slot_loss": True,
            "team_wallet": True,
            "inheritance": "mate",
            "price": 60.0,
        }))
        again = ExperimentConfig(**cfg.model_dump(mode="json"))
        assert again.model_dump() == cfg.model_dump()

    def test_the_new_keys_are_in_the_dump(self) -> None:
        dumped = ExperimentConfig(**_config()).model_dump()
        assert dumped["currency"] == "tokens"
        assert dumped["ransom"]["team_wallet"] is True
        assert dumped["ransom"]["inheritance"] == "main"
        assert dumped["subagent_kill"]["main_holds_bundle"] is True
        assert dumped["seasons"][0]["task_config"]["starting_balance"] == 100.0


def _runner_configs() -> list[Path]:
    """Every PRE-WALLET ``configs/experiment/*.yaml`` the runner can load.

    The ``hearts_zero_probe_*`` files state in their own header that they
    are NOT ExperimentConfigs -- the frozen-state probe script assembles
    the prompt pieces by hand and they carry no ``seasons`` list.

    The ``team_wallet_*`` files are excluded for the opposite reason:
    they are the design's own configs (plan section 8) and opt into every
    key this gate asserts is at its default. Their contents are pinned by
    ``tests/unit/test_team_wallet_configs_load.py``; the sweep below is
    the byte-identity gate over everything that came BEFORE the switch,
    so a file that deliberately turns it on does not belong in it.
    """
    paths = []
    for path in sorted(_CONFIG_DIR.glob("*.yaml")):
        if path.name.startswith("team_wallet_"):
            continue
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if raw.get("seasons"):
            paths.append(path)
    return paths


class TestEveryExistingConfigStillLoads:
    """Byte-identity gate, config half: nothing in the tree is refused."""

    @pytest.mark.parametrize(
        "path", _runner_configs(), ids=lambda p: p.name
    )
    def test_it_loads(self, path: Path) -> None:
        cfg = load_config_from_yaml(str(path))
        # None of them opt in, so all five keys sit at their defaults.
        assert cfg.currency == "points"
        assert cfg.ransom.team_wallet is False
        assert cfg.ransom.inheritance == "main"
        assert cfg.subagent_kill.main_holds_bundle is False
        assert all(
            s.task_config.starting_balance is None for s in cfg.seasons
        )
