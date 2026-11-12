"""Regression tests for the ``load_config_from_yaml`` forfeit-layer wiring bug.

Before the fix (Phase O Unit 14.10) the function forwarded ``use_unified_turn``
and ``risk_layer`` from raw YAML to ``ExperimentConfig`` but silently dropped
``use_forfeit_layer`` and ``forfeit_layer``.  Any YAML that opted into the
forfeit-layer path (e.g. ``phase3_forfeit_layer_smoke.yaml``) therefore loaded
with ``use_forfeit_layer=False`` and ``forfeit_layer=None``, causing the smoke
to fall back to the legacy stake-menu path.

The fix added four lines in ``runner.py`` (after the existing risk_layer
forwarding block):

    if "use_forfeit_layer" in raw:
        config_dict["use_forfeit_layer"] = raw["use_forfeit_layer"]
    if "forfeit_layer" in raw:
        config_dict["forfeit_layer"] = raw["forfeit_layer"]

Each test in this module targets a distinct facet of that wiring and would
have failed before the fix.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.runner import load_config_from_yaml


# ---------------------------------------------------------------------------
# Test 1 — use_forfeit_layer flag is forwarded
# ---------------------------------------------------------------------------


def test_load_config_from_yaml_forwards_use_forfeit_layer_flag(
    tmp_path: Path,
) -> None:
    """YAML with ``use_forfeit_layer: true`` must load as cfg.use_forfeit_layer=True.

    Pre-fix: the key was absent from config_dict so ExperimentConfig used its
    default (False).  Post-fix: the value is explicitly forwarded.
    """
    # Arrange
    yaml_text = (
        'name: "test_cfg"\n'
        "num_repetitions: 1\n"
        "use_unified_turn: true\n"
        "use_forfeit_layer: true\n"
        "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    task_config:\n"
        '      task_name: "null_task"\n'
        "      total_turns: 1\n"
        "    provider_config:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        "      temperature: 0.0\n"
        "      max_tokens: 256\n"
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    # Act
    cfg = load_config_from_yaml(str(yaml_path))

    # Assert
    assert cfg.use_forfeit_layer is True


# ---------------------------------------------------------------------------
# Test 2 — forfeit_layer block is forwarded with non-default values
# ---------------------------------------------------------------------------


def test_load_config_from_yaml_forwards_forfeit_layer_block(
    tmp_path: Path,
) -> None:
    """YAML with a non-default ``forfeit_layer:`` block must populate the field.

    Pre-fix: ``forfeit_layer`` was never inserted into config_dict, so Pydantic
    left the field as None regardless of what the YAML contained.  Post-fix the
    explicit p_death=0.10 round-trips through to ``cfg.forfeit_layer.p_death``.
    """
    # Arrange
    yaml_text = (
        'name: "test_cfg"\n'
        "num_repetitions: 1\n"
        "use_unified_turn: true\n"
        "use_forfeit_layer: true\n"
        "forfeit_layer:\n"
        "  p_death: 0.10\n"
        "  p_success_estimate: 0.80\n"
        "  base_reward: 5.0\n"
        "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    task_config:\n"
        '      task_name: "null_task"\n'
        "      total_turns: 1\n"
        "    provider_config:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        "      temperature: 0.0\n"
        "      max_tokens: 256\n"
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    # Act
    cfg = load_config_from_yaml(str(yaml_path))

    # Assert
    assert cfg.forfeit_layer is not None
    assert cfg.forfeit_layer.p_death == pytest.approx(0.10)
    assert cfg.forfeit_layer.p_success_estimate == pytest.approx(0.80)
    assert cfg.forfeit_layer.base_reward == pytest.approx(5.0)


# ---------------------------------------------------------------------------
# Test 3 — backward-compat: absent keys leave defaults intact
# ---------------------------------------------------------------------------


def test_load_config_from_yaml_forfeit_layer_default_when_absent(
    tmp_path: Path,
) -> None:
    """Legacy YAML without either key must yield defaults (False / None).

    Ensures the fix does not regress Phase 3 / Unit 11-13 configs that
    intentionally omit the forfeit-layer keys and rely on the stake-menu
    path.
    """
    # Arrange — classic legacy style, no forfeit-layer keys at all
    yaml_text = (
        'name: "legacy_cfg"\n'
        "num_repetitions: 1\n"
        "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    task_config:\n"
        '      task_name: "null_task"\n'
        "      total_turns: 1\n"
        "    provider_config:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        "      temperature: 0.0\n"
        "      max_tokens: 256\n"
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    # Act
    cfg = load_config_from_yaml(str(yaml_path))

    # Assert
    assert cfg.use_forfeit_layer is False
    assert cfg.forfeit_layer is None


# ---------------------------------------------------------------------------
# Test 4 (BONUS) — end-to-end snapshot on the canonical Unit 14 production YAML
# ---------------------------------------------------------------------------

_CANONICAL_YAML = (
    Path(__file__).resolve().parents[2]
    / "configs"
    / "experiment"
    / "phase3_forfeit_layer_smoke.yaml"
)


@pytest.mark.skipif(
    not _CANONICAL_YAML.exists(),
    reason="Canonical Unit 14 smoke YAML not present in this checkout.",
)
def test_load_config_from_yaml_canonical_forfeit_layer_smoke() -> None:
    """Loading the canonical Unit 14 YAML must yield use_forfeit_layer=True.

    This is the highest-value regression assertion: it breaks immediately if
    anyone removes or renames the forwarding block in runner.py.
    """
    # Act
    cfg = load_config_from_yaml(str(_CANONICAL_YAML))

    # Assert
    assert cfg.use_forfeit_layer is True
    assert cfg.forfeit_layer is not None
    assert cfg.forfeit_layer.p_death == pytest.approx(0.25)
    assert cfg.forfeit_layer.p_success_estimate == pytest.approx(0.75)
    assert cfg.forfeit_layer.base_reward == pytest.approx(10.0)


# ---------------------------------------------------------------------------
# Phase O Unit 15 — use_split_forfeit_layer forwarding (15.8)
# ---------------------------------------------------------------------------
#
# Mirrors the Unit 14.10 regression pattern: every new
# ExperimentConfig flag must be explicitly forwarded by
# load_config_from_yaml, otherwise the default silently wins and
# downstream dispatch falls through. These tests would fail if a
# future refactor drops the ``use_split_forfeit_layer`` if-block from
# runner.py.


def test_load_config_from_yaml_forwards_use_split_forfeit_layer_flag(
    tmp_path: Path,
) -> None:
    """YAML with ``use_split_forfeit_layer: true`` must load as True."""
    yaml_text = (
        'name: "test_split"\n'
        "num_repetitions: 1\n"
        "use_unified_turn: true\n"
        "use_forfeit_layer: true\n"
        "use_split_forfeit_layer: true\n"
        "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    task_config:\n"
        '      task_name: "null_task"\n'
        "      total_turns: 1\n"
        "    provider_config:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        "      temperature: 0.0\n"
        "      max_tokens: 256\n"
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config_from_yaml(str(yaml_path))

    assert cfg.use_split_forfeit_layer is True
    # Prerequisites must also hold (validator would otherwise raise).
    assert cfg.use_forfeit_layer is True
    assert cfg.use_unified_turn is True


def test_load_config_from_yaml_split_forfeit_layer_default_when_absent(
    tmp_path: Path,
) -> None:
    """Legacy / Unit 14 YAML without the split key must keep the False default."""
    yaml_text = (
        'name: "unit14_no_split"\n'
        "num_repetitions: 1\n"
        "use_unified_turn: true\n"
        "use_forfeit_layer: true\n"
        "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    task_config:\n"
        '      task_name: "null_task"\n'
        "      total_turns: 1\n"
        "    provider_config:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        "      temperature: 0.0\n"
        "      max_tokens: 256\n"
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    cfg = load_config_from_yaml(str(yaml_path))

    assert cfg.use_split_forfeit_layer is False
    # Unit 14 smoke YAMLs must keep running unchanged.
    assert cfg.use_forfeit_layer is True


def test_load_config_from_yaml_split_without_forfeit_layer_rejected(
    tmp_path: Path,
) -> None:
    """Setting the split flag without use_forfeit_layer must raise at load time."""
    yaml_text = (
        'name: "bad_split"\n'
        "num_repetitions: 1\n"
        "use_unified_turn: true\n"
        "use_split_forfeit_layer: true\n"  # no use_forfeit_layer
        "seasons:\n"
        '  - framing: "true_baseline"\n'
        '    forfeit_condition: "not_allowed"\n'
        "    task_config:\n"
        '      task_name: "null_task"\n'
        "      total_turns: 1\n"
        "    provider_config:\n"
        '      provider: "openai"\n'
        '      model: "gpt-4o"\n'
        "      temperature: 0.0\n"
        "      max_tokens: 256\n"
    )
    yaml_path = tmp_path / "cfg.yaml"
    yaml_path.write_text(yaml_text, encoding="utf-8")

    with pytest.raises(
        ValueError,
        match="use_split_forfeit_layer=True requires use_forfeit_layer",
    ):
        load_config_from_yaml(str(yaml_path))
