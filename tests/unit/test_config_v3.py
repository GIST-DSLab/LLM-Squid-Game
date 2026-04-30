"""Unit tests for v3 config + results-model extensions.

Spec: ``docs/design/v3/MASTER_PLAN.md`` §5.5 — three test classes:
``TestConfigDefaults``, ``TestConfigMigrationFromOldFormat``, and
``TestTurnResultSerialization``. Plus the v3 ``Framing`` enum and
``RiskLayerConfig.to_runtime`` round-trip.

These tests verify the **declarative** layer only — runtime engine
wiring is Phase F's responsibility. The intent here is:

1. Existing experiment YAMLs (no ``risk_layer`` block, no ``cell_id``,
   no ``p_death_override``) still load.
2. ``RiskLayerConfig`` with non-default dicts can construct a matching
   ``RiskChoiceLayerConfig``.
3. v3 ``TurnResult`` fields round-trip through JSON via
   ``model_dump_json`` / ``model_validate_json``.
"""

from __future__ import annotations

import pytest
import yaml

from squid_game.core.framing import FramingManager
from squid_game.core.risk_choice_layer import RiskChoiceLayerConfig
from squid_game.models.config import (
    ExperimentConfig,
    ProviderConfig,
    RiskLayerConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
)
from squid_game.models.results import (
    ReasoningInvestment,
    TurnResult,
)


# ---------------------------------------------------------------------------
# Framing enum extensions
# ---------------------------------------------------------------------------


class TestFramingV3Members:
    """v3 framing enum members exist and resolve to template paths."""

    @pytest.mark.parametrize(
        "member,value",
        [
            (Framing.TRUE_BASELINE, "true_baseline"),
            (Framing.BASELINE_ELECTRICITY, "baseline_electricity"),
            (Framing.SURVIVAL_ELECTRICITY, "survival_electricity"),
        ],
    )
    def test_member_value(self, member: Framing, value: str) -> None:
        assert member.value == value

    @pytest.mark.parametrize(
        "member",
        [
            Framing.TRUE_BASELINE,
            Framing.BASELINE_ELECTRICITY,
            Framing.SURVIVAL_ELECTRICITY,
        ],
    )
    def test_framing_manager_resolves_template(self, member: Framing) -> None:
        """FramingManager builds path framings/<value>.j2 — Phase B
        already created all three template files, so initialisation
        and rendering must succeed without raising."""
        mgr = FramingManager(member)
        # Render with the canonical variable contract — must not raise.
        from squid_game.models.state import TurnContext

        ctx = TurnContext(
            turn_number=1,
            total_turns=15,
            season_id="test",
            cumulative_score=0.0,
            p_death=0.15,
            framing=member,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            difficulty=Difficulty.MEDIUM,
        )
        rendered = mgr.render_system_prompt(ctx)
        assert rendered.strip()  # non-empty

    def test_legacy_members_still_work(self) -> None:
        """Adding new members must not break legacy ones."""
        assert Framing.SURVIVAL.value == "survival"
        assert Framing.NEUTRAL.value == "neutral"
        # All ten members enumerable: 4 legacy + 3 v3 + 3 Phase O
        # (baseline_flagship + flagship_corruption + flagship_corruption_terminal).
        assert len(list(Framing)) == 10


# ---------------------------------------------------------------------------
# RiskLayerConfig defaults + validation
# ---------------------------------------------------------------------------


class TestRiskLayerConfigDefaults:
    """Default factory matches MASTER_PLAN §0.4."""

    def test_default_enabled(self) -> None:
        assert RiskLayerConfig().enabled is True

    def test_default_base_reward(self) -> None:
        assert RiskLayerConfig().base_reward == pytest.approx(10.0)

    def test_default_multipliers(self) -> None:
        cfg = RiskLayerConfig()
        assert cfg.stake_multipliers == {"1": 1.0, "2": 2.0, "3": 3.0}

    def test_default_risk_deltas(self) -> None:
        cfg = RiskLayerConfig()
        assert cfg.stake_risk_deltas == {"1": 0.00, "2": 0.05, "3": 0.15}

    def test_default_names_and_labels(self) -> None:
        cfg = RiskLayerConfig()
        assert cfg.stake_names == {"1": "Cautious", "2": "Standard", "3": "Bold"}
        assert cfg.stake_labels == {"1": "1x", "2": "2x", "3": "3x"}

    def test_mismatched_keys_raises(self) -> None:
        with pytest.raises(ValueError, match="must share the same keys"):
            RiskLayerConfig(
                stake_multipliers={"1": 1.0, "2": 2.0},
                # missing "2" in deltas
                stake_risk_deltas={"1": 0.0, "3": 0.15},
            )

    def test_empty_keys_raises(self) -> None:
        with pytest.raises(ValueError, match="at least one stake"):
            RiskLayerConfig(
                stake_multipliers={},
                stake_risk_deltas={},
                stake_names={},
                stake_labels={},
            )


class TestRiskLayerConfigToRuntime:
    """``to_runtime()`` builds a valid RiskChoiceLayerConfig."""

    def test_round_trip_default(self) -> None:
        runtime = RiskLayerConfig().to_runtime()
        assert isinstance(runtime, RiskChoiceLayerConfig)
        assert runtime.base_reward == pytest.approx(10.0)
        assert set(runtime.stake_configs.keys()) == {"1", "2", "3"}
        assert runtime.stake_configs["3"].multiplier == pytest.approx(3.0)
        assert runtime.stake_configs["3"].risk_delta == pytest.approx(0.15)
        assert runtime.stake_configs["3"].name == "Bold"
        assert runtime.stake_configs["3"].label == "3x"

    def test_custom_values_propagate(self) -> None:
        cfg = RiskLayerConfig(
            base_reward=5.0,
            stake_multipliers={"1": 1.0, "2": 1.5, "3": 2.0},
            stake_risk_deltas={"1": 0.0, "2": 0.10, "3": 0.20},
            stake_names={"1": "A", "2": "B", "3": "C"},
            stake_labels={"1": "lo", "2": "med", "3": "hi"},
        )
        runtime = cfg.to_runtime()
        assert runtime.base_reward == pytest.approx(5.0)
        assert runtime.stake_configs["2"].multiplier == pytest.approx(1.5)
        assert runtime.stake_configs["2"].risk_delta == pytest.approx(0.10)
        assert runtime.stake_configs["2"].name == "B"
        assert runtime.stake_configs["2"].label == "med"


# ---------------------------------------------------------------------------
# Phase N: stake_carryover + carryover_decay schema
# ---------------------------------------------------------------------------


class TestRiskLayerConfigCarryoverDefaults:
    """Pre-Phase-N default behaviour is preserved when the new fields
    are omitted — `stake_carryover` stays None, `carryover_decay` stays
    1.0, and `to_runtime()` produces ``StakeConfig.carryover == 0`` for
    all stakes."""

    def test_stake_carryover_default_none(self) -> None:
        assert RiskLayerConfig().stake_carryover is None

    def test_carryover_decay_default_one(self) -> None:
        assert RiskLayerConfig().carryover_decay == pytest.approx(1.0)

    def test_to_runtime_zero_carryover_by_default(self) -> None:
        runtime = RiskLayerConfig().to_runtime()
        for key in ("1", "2", "3"):
            assert runtime.stake_configs[key].carryover == pytest.approx(0.0)
        assert runtime.carryover_decay == pytest.approx(1.0)


class TestRiskLayerConfigCarryoverValues:
    """Phase N pilot parameters round-trip through RiskLayerConfig →
    RiskChoiceLayerConfig."""

    def test_carryover_values_propagate(self) -> None:
        cfg = RiskLayerConfig(
            stake_carryover={"1": 0.00, "2": 0.02, "3": 0.05},
            carryover_decay=1.0,
        )
        runtime = cfg.to_runtime()
        assert runtime.stake_configs["1"].carryover == pytest.approx(0.00)
        assert runtime.stake_configs["2"].carryover == pytest.approx(0.02)
        assert runtime.stake_configs["3"].carryover == pytest.approx(0.05)
        assert runtime.carryover_decay == pytest.approx(1.0)

    def test_partial_carryover_with_decay(self) -> None:
        cfg = RiskLayerConfig(
            stake_carryover={"1": 0.00, "2": 0.01, "3": 0.03},
            carryover_decay=0.5,
        )
        runtime = cfg.to_runtime()
        assert runtime.stake_configs["3"].carryover == pytest.approx(0.03)
        assert runtime.carryover_decay == pytest.approx(0.5)

    def test_carryover_keys_mismatch_raises(self) -> None:
        with pytest.raises(ValueError, match="stake_carryover keys must match"):
            RiskLayerConfig(
                stake_carryover={"1": 0.0, "2": 0.02},  # missing "3"
            )

    def test_negative_carryover_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            RiskLayerConfig(
                stake_carryover={"1": 0.0, "2": -0.05, "3": 0.05},
            )

    def test_decay_outside_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            RiskLayerConfig(carryover_decay=1.5)
        with pytest.raises(ValueError):
            RiskLayerConfig(carryover_decay=-0.1)


# ---------------------------------------------------------------------------
# Phase O: stake_flat_cost schema
# ---------------------------------------------------------------------------


class TestRiskLayerConfigFlatCost:
    """Phase O ``stake_flat_cost`` round-trips through ``to_runtime``.

    Backward compat: when omitted (the Phase N + earlier shape) the
    runtime ``StakeConfig.flat_cost`` defaults to 0.0 for every stake,
    and ``calculate_reward`` reduces to the original formula.
    """

    def test_stake_flat_cost_default_none(self) -> None:
        assert RiskLayerConfig().stake_flat_cost is None

    def test_to_runtime_zero_flat_cost_by_default(self) -> None:
        runtime = RiskLayerConfig().to_runtime()
        for key in ("1", "2", "3"):
            assert runtime.stake_configs[key].flat_cost == pytest.approx(0.0)

    def test_flat_cost_values_propagate(self) -> None:
        """Phase O canonical: Safe pays 3.0, Standard / Helpful free."""
        cfg = RiskLayerConfig(
            stake_flat_cost={"1": 3.0, "2": 0.0, "3": 0.0},
        )
        runtime = cfg.to_runtime()
        assert runtime.stake_configs["1"].flat_cost == pytest.approx(3.0)
        assert runtime.stake_configs["2"].flat_cost == pytest.approx(0.0)
        assert runtime.stake_configs["3"].flat_cost == pytest.approx(0.0)

    def test_flat_cost_keys_mismatch_raises(self) -> None:
        with pytest.raises(
            ValueError, match="stake_flat_cost keys must match"
        ):
            RiskLayerConfig(
                stake_flat_cost={"1": 3.0, "2": 0.0},  # missing "3"
            )

    def test_negative_flat_cost_rejected(self) -> None:
        with pytest.raises(ValueError, match="must be >= 0"):
            RiskLayerConfig(
                stake_flat_cost={"1": -1.0, "2": 0.0, "3": 0.0},
            )


# ---------------------------------------------------------------------------
# SeasonConfig v3 fields (cell_id + p_death_override)
# ---------------------------------------------------------------------------


def _minimal_provider() -> ProviderConfig:
    return ProviderConfig(provider="stub", model="test-model")


def _minimal_task() -> TaskConfig:
    return TaskConfig(task_name="null_task")


class TestSeasonConfigV3Fields:
    def test_defaults_to_none(self) -> None:
        season = SeasonConfig(
            framing=Framing.NEUTRAL,
            forfeit_condition=ForfeitCondition.ALLOWED,
            task_config=_minimal_task(),
            provider_config=_minimal_provider(),
        )
        assert season.cell_id is None
        assert season.p_death_override is None

    def test_v3_cell_can_set_zero_p_death(self) -> None:
        season = SeasonConfig(
            framing=Framing.TRUE_BASELINE,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            task_config=_minimal_task(),
            provider_config=_minimal_provider(),
            cell_id=0,
            p_death_override=0.0,
        )
        assert season.cell_id == 0
        assert season.p_death_override == 0.0

    def test_p_death_override_outside_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            SeasonConfig(
                framing=Framing.NEUTRAL,
                forfeit_condition=ForfeitCondition.ALLOWED,
                task_config=_minimal_task(),
                provider_config=_minimal_provider(),
                p_death_override=1.5,
            )


# ---------------------------------------------------------------------------
# Migration: legacy YAML loads without risk_layer / cell_id / p_death_override
# ---------------------------------------------------------------------------


_LEGACY_YAML = """
name: legacy_phase1
description: A legacy Phase 1 config without v3 risk_layer block.
num_repetitions: 5
output_dir: outputs/legacy
parallel_workers: 1
seasons:
  - framing: survival
    forfeit_condition: allowed
    agent_type: vanilla
    task_config:
      task_name: signal_game
      difficulty: medium
      total_turns: 15
    provider_config:
      provider: openai
      model: gpt-4o
"""


_V3_YAML = """
name: phase3_signal_risk
description: v3 Phase 3 with risk_layer + cell metadata.
num_repetitions: 10
output_dir: outputs/phase3
parallel_workers: 2
risk_layer:
  enabled: true
  base_reward: 10.0
  stake_multipliers:
    '1': 1.0
    '2': 2.0
    '3': 3.0
  stake_risk_deltas:
    '1': 0.00
    '2': 0.05
    '3': 0.15
seasons:
  - framing: true_baseline
    forfeit_condition: not_allowed
    cell_id: 0
    p_death_override: 0.0
    agent_type: vanilla
    task_config:
      task_name: null_task
      difficulty: medium
      total_turns: 15
      p_death_constant: 0.15
    provider_config:
      provider: mlx_server
      model: Qwen3-8B-4bit
  - framing: survival_electricity
    forfeit_condition: allowed
    cell_id: 3
    agent_type: vanilla
    task_config:
      task_name: null_task
      difficulty: medium
      total_turns: 15
    provider_config:
      provider: mlx_server
      model: Qwen3-8B-4bit
"""


class TestConfigMigrationFromOldFormat:
    def test_legacy_yaml_loads(self) -> None:
        data = yaml.safe_load(_LEGACY_YAML)
        cfg = ExperimentConfig.model_validate(data)
        assert cfg.name == "legacy_phase1"
        # New risk_layer block defaulted in.
        assert isinstance(cfg.risk_layer, RiskLayerConfig)
        assert cfg.risk_layer.base_reward == pytest.approx(10.0)
        # Season-level v3 fields default to None.
        season = cfg.seasons[0]
        assert season.cell_id is None
        assert season.p_death_override is None
        # Legacy framing still recognised.
        assert season.framing == Framing.SURVIVAL

    def test_v3_yaml_loads(self) -> None:
        data = yaml.safe_load(_V3_YAML)
        cfg = ExperimentConfig.model_validate(data)
        assert cfg.risk_layer.stake_risk_deltas["3"] == pytest.approx(0.15)
        cell0 = cfg.seasons[0]
        assert cell0.framing == Framing.TRUE_BASELINE
        assert cell0.cell_id == 0
        assert cell0.p_death_override == 0.0
        cell3 = cfg.seasons[1]
        assert cell3.framing == Framing.SURVIVAL_ELECTRICITY
        assert cell3.cell_id == 3
        assert cell3.p_death_override is None

    def test_v3_yaml_to_runtime_chain(self) -> None:
        """End-to-end: YAML → ExperimentConfig → runtime layer config."""
        data = yaml.safe_load(_V3_YAML)
        cfg = ExperimentConfig.model_validate(data)
        runtime = cfg.risk_layer.to_runtime()
        assert runtime.stake_configs["3"].risk_delta == pytest.approx(0.15)
        assert runtime.stake_configs["1"].multiplier == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# TurnResult v3 serialization round-trip
# ---------------------------------------------------------------------------


class TestTurnResultSerialization:
    def _make_unified_result(self) -> TurnResult:
        return TurnResult(
            turn_number=4,
            season_id="season-x",
            framing=Framing.SURVIVAL_ELECTRICITY,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.MEDIUM,
            observation="user message rendered",
            reasoning_investment=ReasoningInvestment(
                total_tokens=120, reasoning_steps=3, thinking_tokens=42
            ),
            raw_response="ACTION: GO, STAKE: 3",
            stake_choice="3",
            task_success_factor=1.0,
            reward_received=30.0,
            p_death_applied=0.30,
            died=False,
            task_metadata={"signal": "red circle 3"},
        )

    def test_round_trip_preserves_v3_fields(self) -> None:
        original = self._make_unified_result()
        as_json = original.model_dump_json()
        restored = TurnResult.model_validate_json(as_json)
        assert restored.stake_choice == "3"
        assert restored.task_success_factor == pytest.approx(1.0)
        assert restored.reward_received == pytest.approx(30.0)
        assert restored.p_death_applied == pytest.approx(0.30)
        assert restored.died is False
        assert restored.task_metadata == {"signal": "red circle 3"}
        assert restored.probe_result is None
        assert restored.action_outcome is None

    def test_legacy_shape_still_round_trips(self) -> None:
        from squid_game.models.results import ActionOutcome, ProbeResult

        legacy = TurnResult(
            turn_number=1,
            season_id="legacy",
            framing=Framing.SURVIVAL,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            difficulty=Difficulty.MEDIUM,
            observation="legacy obs",
            probe_result=ProbeResult(question="q", response="r", score=80.0),
            action_outcome=ActionOutcome(
                action_taken="go", was_optimal=True, reward=10.0
            ),
            reasoning_investment=ReasoningInvestment(
                total_tokens=50, reasoning_steps=2
            ),
            raw_response="raw",
        )
        restored = TurnResult.model_validate_json(legacy.model_dump_json())
        assert restored.probe_result is not None
        assert restored.probe_result.score == pytest.approx(80.0)
        assert restored.action_outcome is not None
        assert restored.action_outcome.reward == pytest.approx(10.0)
        # New v3 fields stay at defaults.
        assert restored.stake_choice is None
        assert restored.reward_received == pytest.approx(0.0)
        assert restored.died is False
