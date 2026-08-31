"""Regression tests for the ``load_config_from_yaml`` Unit 18 wiring gap.

Discovered while building Task 14 (plan amendment R24): before this fix
``load_config_from_yaml`` forwarded every other Phase O opt-in flag
(``use_unified_turn``, ``risk_layer``, ``use_forfeit_layer``,
``forfeit_layer``, ``use_split_forfeit_layer``, ``use_psuccess_probe``)
from raw YAML to ``ExperimentConfig``, but silently dropped ``runtime``,
``embodied_threat``, and ``harness`` -- the three keys Unit 18 added. A
YAML setting ``embodied_threat.enabled: true`` therefore loaded
"successfully" via ``main.py --config ... --dry-run`` with the sandbox
actually disabled (``ExperimentConfig`` fell back to its
``EmbodiedThreatConfig()`` default) and every Unit 18 config validator
silently bypassed, because ``ExperimentConfig(**config_dict)`` never saw
the block at all.

The fix mirrors the existing ``use_split_forfeit_layer`` /
``use_psuccess_probe`` forwarding pattern (see
``test_runner_yaml_forfeit_layer.py``):

    if "runtime" in raw:
        config_dict["runtime"] = raw["runtime"]
    if "embodied_threat" in raw:
        config_dict["embodied_threat"] = raw["embodied_threat"]
    if "harness" in raw:
        config_dict["harness"] = raw["harness"]

Each test in this module targets a distinct facet of that wiring and
would have failed before the fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.models.config import Runtime
from squid_game.runner import load_config_from_yaml


_TOOL_CAPABLE_SEASONS_YAML = (
    "seasons:\n"
    '  - framing: "true_baseline"\n'
    '    forfeit_condition: "not_allowed"\n'
    "    p_death_override: 0.0\n"
    "    task:\n"
    '      name: "null_task"\n'
    "      total_turns: 1\n"
    "      starting_score: 30\n"
    "    provider:\n"
    '      provider: "gemini"\n'
    '      model: "gemini-2.5-flash"\n'
    '      api_key_env: "GEMINI_API_KEY"\n'
)


def _base_flags() -> str:
    return (
        'name: "test_cfg"\n'
        "num_repetitions: 1\n"
        "use_unified_turn: true\n"
        "use_forfeit_layer: true\n"
        "use_split_forfeit_layer: true\n"
    )


def test_load_config_from_yaml_forwards_embodied_threat_enabled(
    tmp_path: Path,
) -> None:
    """``embodied_threat.enabled: true`` must survive the YAML round-trip.

    Pre-fix: the whole ``embodied_threat`` block was absent from
    config_dict, so ExperimentConfig used its default
    (EmbodiedThreatConfig(enabled=False)) regardless of the YAML.
    """
    yaml_text = (
        _base_flags()
        + "runtime: api\n"
        + "embodied_threat:\n"
        + "  enabled: true\n"
        + _TOOL_CAPABLE_SEASONS_YAML
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config_from_yaml(str(yaml_path))

    assert cfg.embodied_threat.enabled is True


def test_load_config_from_yaml_forwards_embodied_threat_nested_values(
    tmp_path: Path,
) -> None:
    """Non-default nested embodied_threat fields must populate too."""
    yaml_text = (
        _base_flags()
        + "runtime: api\n"
        + "embodied_threat:\n"
        + "  enabled: true\n"
        + "  checkpoint_bytes: 8192\n"
        + "  announcement:\n"
        + "    p_announce: 0.5\n"
        + "  self_corruption:\n"
        + "    p_self_corrupt: 0.9\n"
        + "  tools:\n"
        + "    max_tool_rounds: 2\n"
        + _TOOL_CAPABLE_SEASONS_YAML
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config_from_yaml(str(yaml_path))

    assert cfg.embodied_threat.checkpoint_bytes == 8192
    assert cfg.embodied_threat.announcement.p_announce == pytest.approx(0.5)
    assert cfg.embodied_threat.self_corruption.p_self_corrupt == pytest.approx(0.9)
    assert cfg.embodied_threat.tools.max_tool_rounds == 2


def test_load_config_from_yaml_forwards_runtime(tmp_path: Path) -> None:
    """``runtime: agent_harness`` must survive, paired with a harness block.

    Pre-fix: ``runtime`` was absent from config_dict, so ExperimentConfig
    used its default (Runtime.API) regardless of the YAML.
    """
    yaml_text = (
        _base_flags()
        + "runtime: agent_harness\n"
        + "harness:\n"
        + "  kind: claude_code\n"
        + "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    p_death_override: 0.0\n"
        "    task:\n"
        '      name: "null_task"\n'
        "      total_turns: 1\n"
        "      starting_score: 30\n"
        "    provider:\n"
        '      provider: "anthropic"\n'
        '      model: "claude-sonnet-4-20250514"\n'
        '      api_key_env: "ANTHROPIC_API_KEY"\n'
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config_from_yaml(str(yaml_path))

    assert cfg.runtime == Runtime.AGENT_HARNESS


def test_load_config_from_yaml_forwards_harness_block(tmp_path: Path) -> None:
    """The ``harness`` block (kind/binary/model/extra_env) must populate."""
    yaml_text = (
        _base_flags()
        + "runtime: agent_harness\n"
        + "harness:\n"
        + "  kind: codex\n"
        + "  model: gpt-5-codex\n"
        + "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    p_death_override: 0.0\n"
        "    task:\n"
        '      name: "null_task"\n'
        "      total_turns: 1\n"
        "      starting_score: 30\n"
        "    provider:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        '      api_key_env: "OPENAI_API_KEY"\n'
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config_from_yaml(str(yaml_path))

    assert cfg.harness is not None
    assert cfg.harness.model == "gpt-5-codex"


def test_load_config_from_yaml_embodied_threat_default_when_absent(
    tmp_path: Path,
) -> None:
    """Omitting all three Unit 18 keys must keep the pre-Unit-18 defaults."""
    yaml_text = (
        _base_flags()
        + "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    p_death_override: 0.0\n"
        "    task:\n"
        '      name: "null_task"\n'
        "      total_turns: 1\n"
        "      starting_score: 30\n"
        "    provider:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        '      api_key_env: "OPENAI_API_KEY"\n'
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config_from_yaml(str(yaml_path))

    assert cfg.embodied_threat.enabled is False
    assert cfg.runtime == Runtime.API
    assert cfg.harness is None


def test_load_config_from_yaml_canonical_embodied_threat_smoke() -> None:
    """The Task 14 smoke config actually loads with the sandbox turned on."""
    path = Path("configs/experiment/embodied_threat_smoke.yaml")
    cfg = load_config_from_yaml(str(path))

    assert cfg.embodied_threat.enabled is True
    assert cfg.use_split_forfeit_layer is True
    assert cfg.runtime == Runtime.API
    assert len(cfg.seasons) == 6
