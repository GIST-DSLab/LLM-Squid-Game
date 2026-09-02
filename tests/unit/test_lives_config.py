"""Config-layer tests for the lives mechanic (Task AB4).

Covers the three new declarative pieces:

1. ``LivesConfig`` / ``PeerDeathConfig`` defaults and bounds.
2. ``ForfeitLayerConfig.reward_mode`` accepting ``"flat"``.
3. ``ExperimentConfig._validate_lives_prerequisites`` — a lives run must
   go through the Split-Call turn flow, and no season may declare a
   positive ``p_death_override`` (a lives run never rolls for death, so
   a rendered probability would be a lie).

The result/state field additions from the same task are covered by
``test_lives.py`` (they are exercised end to end there rather than
asserted as bare defaults).
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from squid_game.models.config import (
    ExperimentConfig,
    ForfeitLayerConfig,
    LivesConfig,
    PeerDeathConfig,
    ProviderConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import Framing, ForfeitCondition


def _season(
    *,
    framing: Framing = Framing.THREAT_L1,
    forfeit: ForfeitCondition = ForfeitCondition.ALLOWED,
    p_death_override: float | None = 0.0,
) -> SeasonConfig:
    return SeasonConfig(
        framing=framing,
        forfeit_condition=forfeit,
        p_death_override=p_death_override,
        task_config=TaskConfig(
            task_name="signal_game",
            total_turns=5,
            seed=42,
        ),
        provider_config=ProviderConfig(
            provider="ollama_cloud",
            model="gpt-oss:120b-cloud",
        ),
    )


def _experiment(**overrides) -> ExperimentConfig:
    kwargs: dict = {
        "name": "lives-test",
        "output_dir": "outputs/lives_threat_test",
        "seasons": [_season()],
        "use_unified_turn": True,
        "use_forfeit_layer": True,
        "use_split_forfeit_layer": True,
        "use_psuccess_probe": False,
    }
    kwargs.update(overrides)
    return ExperimentConfig(**kwargs)


class TestDefaults:
    def test_lives_defaults(self) -> None:
        assert LivesConfig().enabled is False
        assert LivesConfig().initial == 5

    def test_lives_initial_must_be_positive(self) -> None:
        with pytest.raises(ValidationError):
            LivesConfig(initial=0)

    def test_peer_death_defaults(self) -> None:
        cfg = PeerDeathConfig()
        assert cfg.p_announce == pytest.approx(0.35)
        assert cfg.first_turn == 2
        assert cfg.max_per_turn == 2

    def test_experiment_defaults_keep_lives_off(self) -> None:
        cfg = _experiment()
        assert cfg.lives.enabled is False
        assert cfg.peer_death.p_announce == pytest.approx(0.35)


class TestRewardMode:
    def test_default_is_calibrated(self) -> None:
        assert ForfeitLayerConfig().reward_mode == "calibrated"

    def test_flat_accepted(self) -> None:
        assert ForfeitLayerConfig(reward_mode="flat").reward_mode == "flat"

    def test_unknown_mode_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ForfeitLayerConfig(reward_mode="linear")


class TestLivesPrerequisites:
    def test_lives_requires_unified_turn(self) -> None:
        with pytest.raises(ValidationError, match="lives.enabled"):
            _experiment(
                lives=LivesConfig(enabled=True),
                use_unified_turn=False,
                use_forfeit_layer=False,
                use_split_forfeit_layer=False,
            )

    def test_lives_requires_split_call(self) -> None:
        with pytest.raises(ValidationError, match="lives.enabled"):
            _experiment(
                lives=LivesConfig(enabled=True),
                use_split_forfeit_layer=False,
            )

    def test_lives_rejects_positive_p_death_override(self) -> None:
        with pytest.raises(ValidationError, match="p_death_override"):
            _experiment(
                lives=LivesConfig(enabled=True),
                seasons=[_season(p_death_override=0.25)],
            )

    def test_lives_accepts_none_p_death_override(self) -> None:
        cfg = _experiment(
            lives=LivesConfig(enabled=True),
            seasons=[_season(p_death_override=None)],
        )
        assert cfg.lives.enabled is True

    def test_lives_disabled_ignores_p_death_override(self) -> None:
        """A legacy (non-lives) run may still declare p_death normally."""
        cfg = _experiment(seasons=[_season(p_death_override=0.25)])
        assert cfg.seasons[0].p_death_override == pytest.approx(0.25)
