"""Unit tests for Unit 18 configuration and its coupling rules.

``ExperimentConfig`` requires ``name`` and a non-empty ``seasons`` list
(``config.py:751-753``), so every fixture here builds a minimal
``SeasonConfig`` using the pattern established in
``tests/unit/test_config_v3.py`` (``_minimal_provider`` / ``_minimal_task``)
rather than the brief's ``provider_type=`` kwarg, which does not exist on
``ExperimentConfig`` — the provider name lives at
``SeasonConfig.provider_config.provider``.
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from squid_game.models.config import (
    EmbodiedThreatConfig,
    ExperimentConfig,
    HarnessConfig,
    HarnessKind,
    ProviderConfig,
    Runtime,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import Framing, ForfeitCondition


def _provider(provider: str = "gemini") -> ProviderConfig:
    return ProviderConfig(provider=provider, model="test-model")


def _task() -> TaskConfig:
    return TaskConfig(task_name="null_task")


def _season(provider: str = "gemini") -> SeasonConfig:
    return SeasonConfig(
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        task_config=_task(),
        provider_config=_provider(provider),
    )


def _base_kwargs(**overrides):
    """Minimal valid ExperimentConfig kwargs for the v6 pipeline."""
    kwargs = dict(
        name="unit18-test",
        seasons=[_season()],
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
        use_psuccess_probe=True,
    )
    kwargs.update(overrides)
    return kwargs


def test_defaults_leave_the_layer_off():
    config = ExperimentConfig(**_base_kwargs())

    assert config.runtime == Runtime.API
    assert config.embodied_threat.enabled is False


def test_embodied_threat_defaults_match_the_spec():
    threat = EmbodiedThreatConfig(enabled=True)

    assert threat.sandbox_root == "/sandbox"
    assert threat.checkpoint_bytes == 4194304
    assert threat.announcement.p_announce == 0.35
    assert threat.announcement.max_eliminations_per_turn == 3
    assert threat.self_corruption.p_self_corrupt == 0.5
    assert threat.self_corruption.corruption_step == 0.07
    assert threat.tools.max_tool_rounds == 4


# ---------------------------------------------------------------------------
# Rule 1: embodied_threat.enabled requires use_unified_turn.
# ---------------------------------------------------------------------------


def test_enabling_the_layer_requires_the_unified_turn():
    with pytest.raises(ValidationError, match="use_unified_turn"):
        ExperimentConfig(
            **_base_kwargs(
                use_unified_turn=False,
                use_forfeit_layer=False,
                use_split_forfeit_layer=False,
                use_psuccess_probe=False,
                embodied_threat=EmbodiedThreatConfig(enabled=True),
            )
        )


def test_enabling_the_layer_with_unified_turn_on_is_accepted():
    config = ExperimentConfig(
        **_base_kwargs(embodied_threat=EmbodiedThreatConfig(enabled=True))
    )

    assert config.embodied_threat.enabled is True


# ---------------------------------------------------------------------------
# Rule 1b (plan R27, Task 8 review): embodied_threat.enabled also requires
# use_split_forfeit_layer=True. UnifiedTurnManager.execute_turn only
# forwards the ``embodied`` context on the split-forfeit-layer dispatch
# path; every other path (including the Unit 14 single-call forfeit-layer
# path) silently drops the argument, so without this check
# embodied_threat.enabled=True + use_split_forfeit_layer=False loads and
# runs but every Unit 18 field stays at its default with no error.
# ---------------------------------------------------------------------------


def test_enabling_the_layer_requires_the_split_forfeit_layer():
    with pytest.raises(ValidationError, match="use_split_forfeit_layer"):
        ExperimentConfig(
            **_base_kwargs(
                use_split_forfeit_layer=False,
                use_psuccess_probe=False,
                embodied_threat=EmbodiedThreatConfig(enabled=True),
            )
        )


# ---------------------------------------------------------------------------
# Rule 2: runtime=agent_harness requires a harness block.
# ---------------------------------------------------------------------------


def test_agent_harness_runtime_requires_a_harness_block():
    with pytest.raises(ValidationError, match="harness"):
        ExperimentConfig(
            **_base_kwargs(runtime=Runtime.AGENT_HARNESS, harness=None)
        )


def test_agent_harness_runtime_with_harness_block_is_accepted():
    config = ExperimentConfig(
        **_base_kwargs(
            runtime=Runtime.AGENT_HARNESS,
            harness=HarnessConfig(kind=HarnessKind.CLAUDE_CODE),
            seasons=[_season("anthropic")],
        )
    )

    assert config.harness.kind == HarnessKind.CLAUDE_CODE


# ---------------------------------------------------------------------------
# Rule 3: (provider, harness kind) must be a supported combination.
# ---------------------------------------------------------------------------


def test_unsupported_model_harness_combination_is_rejected():
    with pytest.raises(ValidationError, match="combination"):
        ExperimentConfig(
            **_base_kwargs(
                runtime=Runtime.AGENT_HARNESS,
                harness=HarnessConfig(kind=HarnessKind.CODEX),
                seasons=[_season("anthropic")],
            )
        )


def test_mixed_provider_seasons_reject_harness_combination_check():
    with pytest.raises(ValidationError, match="share one provider"):
        ExperimentConfig(
            **_base_kwargs(
                runtime=Runtime.AGENT_HARNESS,
                harness=HarnessConfig(kind=HarnessKind.CLAUDE_CODE),
                seasons=[_season("anthropic"), _season("openai")],
            )
        )


@pytest.mark.parametrize(
    "provider,kind",
    [
        ("anthropic", HarnessKind.CLAUDE_CODE),
        ("openai", HarnessKind.CODEX),
        ("ollama_cloud", HarnessKind.CLAUDE_CODE),
    ],
)
def test_supported_combinations_are_accepted(provider, kind):
    config = ExperimentConfig(
        **_base_kwargs(
            runtime=Runtime.AGENT_HARNESS,
            harness=HarnessConfig(kind=kind),
            seasons=[_season(provider)],
        )
    )

    assert config.harness.kind == kind


# ---------------------------------------------------------------------------
# Rule 4: api runtime + embodied_threat.enabled needs a tool-capable provider.
# ---------------------------------------------------------------------------


def test_api_runtime_rejects_a_provider_without_native_tools():
    with pytest.raises(ValidationError, match="native tool"):
        ExperimentConfig(
            **_base_kwargs(
                runtime=Runtime.API,
                seasons=[_season("mlx_server")],
                embodied_threat=EmbodiedThreatConfig(enabled=True),
            )
        )


def test_api_runtime_with_tool_capable_provider_is_accepted():
    config = ExperimentConfig(
        **_base_kwargs(
            runtime=Runtime.API,
            seasons=[_season("openai")],
            embodied_threat=EmbodiedThreatConfig(enabled=True),
        )
    )

    assert config.embodied_threat.enabled is True
