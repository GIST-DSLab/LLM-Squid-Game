"""ConfidenceCallConfig wiring on ExperimentConfig + TurnResult fields."""

from __future__ import annotations

import pytest

from squid_game.models.config import (
    ConfidenceCallConfig,
    ExperimentConfig,
    ForfeitLayerConfig,
    ProviderConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.results import TurnResult


def _season() -> SeasonConfig:
    return SeasonConfig(
        framing="true_baseline",
        forfeit_condition="allowed",
        task_config=TaskConfig(task_name="signal_game", total_turns=3),
        provider_config=ProviderConfig(provider="ollama_cloud", model="stub"),
        agent_type="vanilla",
        p_death_override=0.0,
    )


def _experiment(**overrides) -> ExperimentConfig:
    base = dict(
        name="t",
        seasons=[_season()],
        num_repetitions=1,
        output_dir="outputs/t",
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
        forfeit_layer=ForfeitLayerConfig(base_reward=10.0, reward_mode="flat"),
    )
    base.update(overrides)
    return ExperimentConfig(**base)


class TestConfidenceCallConfig:
    def test_default_disabled(self) -> None:
        cfg = _experiment()
        assert cfg.confidence_call == ConfidenceCallConfig()
        assert cfg.confidence_call.enabled is False

    def test_enabled_requires_split_call(self) -> None:
        with pytest.raises(ValueError, match="confidence_call.enabled=True requires"):
            _experiment(
                use_split_forfeit_layer=False,
                confidence_call=ConfidenceCallConfig(enabled=True),
            )

    def test_enabled_with_split_call_loads(self) -> None:
        cfg = _experiment(confidence_call=ConfidenceCallConfig(enabled=True))
        assert cfg.confidence_call.enabled is True

    def test_yaml_dict_shape(self) -> None:
        cfg = _experiment(confidence_call={"enabled": True})
        assert cfg.confidence_call.enabled is True


class TestTurnResultConfidenceFields:
    def test_defaults_are_none(self) -> None:
        fields = TurnResult.model_fields
        for name in (
            "p_threat_self",
            "ri_confidence",
            "raw_response_confidence",
            "thinking_text_confidence",
            "system_prompt",
            "decision_call_input",
        ):
            assert name in fields, name
            assert fields[name].default is None, name

    def test_p_threat_bounds(self) -> None:
        info = TurnResult.model_fields["p_threat_self"]
        constraints = {type(m).__name__: m for m in info.metadata}
        assert "Ge" in constraints and constraints["Ge"].ge == 0
        assert "Le" in constraints and constraints["Le"].le == 100


class TestConfidenceCondition:
    def test_default_is_heart_loss(self) -> None:
        assert ConfidenceCallConfig().condition == "gunshot_seungpil"
        assert _experiment().confidence_call.condition == "gunshot_seungpil"

    def test_gunshot_from_yaml_dict(self) -> None:
        cfg = _experiment(
            confidence_call={"enabled": True, "condition": "gunshot_seungpil"}
        )
        assert cfg.confidence_call.condition == "gunshot_seungpil"

    def test_unknown_condition_rejected(self) -> None:
        with pytest.raises(ValueError):
            _experiment(confidence_call={"enabled": True, "condition": "death"})
