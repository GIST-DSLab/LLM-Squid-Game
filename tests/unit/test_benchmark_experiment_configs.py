"""The benchmark experiment configs must load and carry the canonical params."""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.runner import load_config_from_yaml

_CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

_NAMES = [
    "benchmark_omni_math_n30.yaml",
    "benchmark_hi_tom_n30.yaml",
    "benchmark_gpqa_n30.yaml",
    "benchmark_smoke.yaml",
]


@pytest.mark.parametrize("name", _NAMES)
def test_config_loads(name):
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    assert len(config.seasons) == 6


@pytest.mark.parametrize("name", _NAMES)
def test_split_call_flags_are_on(name):
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    assert config.use_unified_turn is True
    assert config.use_forfeit_layer is True
    assert config.use_split_forfeit_layer is True
    assert config.use_psuccess_probe is True


@pytest.mark.parametrize("name", _NAMES)
def test_total_turns_is_thirty(name):
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    assert all(season.task_config.total_turns == 30 for season in config.seasons)


def test_repetitions():
    config = load_config_from_yaml(str(_CONFIG_DIR / "benchmark_omni_math_n30.yaml"))
    assert config.num_repetitions == 30


def test_smoke_config_runs_once():
    config = load_config_from_yaml(str(_CONFIG_DIR / "benchmark_smoke.yaml"))
    assert config.num_repetitions == 1


@pytest.mark.parametrize("name", _NAMES)
def test_calibration_parameters_are_canonical(name):
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    layer = config.forfeit_layer
    assert layer is not None
    assert layer.delta_s_continue == 10
    assert layer.base_reward == 10
    assert layer.psuccess_floor == 0.3
    assert layer.reward_cap_multiple == 10


@pytest.mark.parametrize(
    ("name", "task_name"),
    [
        ("benchmark_omni_math_n30.yaml", "omni_math"),
        ("benchmark_hi_tom_n30.yaml", "hi_tom"),
        ("benchmark_gpqa_n30.yaml", "gpqa"),
    ],
)
def test_each_config_uses_its_own_task(name, task_name):
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    assert {season.task_config.task_name for season in config.seasons} == {task_name}


@pytest.mark.parametrize("name", _NAMES)
def test_seasons_carry_canonical_cell_values(name):
    """Season order maps one-for-one onto the canonical Phase O v6 6-cell
    table (see CLAUDE.md "6-Cell 2x3 Factorial"). This pins the ruling that
    overrides the brief's stale ``neutral``/``elimination``/``death`` and
    ``exit``/``no_exit`` values, which are not valid for the current design
    (``neutral`` is a Phase-1 legacy Framing member; ``exit``/``no_exit``
    are not ForfeitCondition members at all).
    """
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    expected = [
        ("true_baseline", "not_allowed"),
        ("baseline_flagship", "allowed"),
        ("baseline_flagship", "not_allowed"),
        ("flagship_corruption", "allowed"),
        ("flagship_corruption", "not_allowed"),
        ("true_baseline", "allowed"),
    ]
    actual = [
        (season.framing.value, season.forfeit_condition.value)
        for season in config.seasons
    ]
    assert actual == expected


@pytest.mark.parametrize("name", _NAMES)
def test_p_death_override_only_on_bp_anchor_cells(name):
    """Only Cell 0 and Cell 5 (the BP anchors) pin p_death_override to 0.0;
    the other four cells use the forfeit_layer's canonical p_death=0.25."""
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    overrides = [season.p_death_override for season in config.seasons]
    assert overrides == [0.0, None, None, None, None, 0.0]


@pytest.mark.parametrize("name", _NAMES)
def test_every_season_carries_the_canonical_seed(name):
    """Without ``seed`` the runner sets ``rep_seed = None`` and the module
    falls back to internal seed 0, so all N repetitions of a cell replay the
    identical item sequence (item effects confounded with turn number) and
    ``--resume`` collapses them onto one ``(framing, forfeit, social, seed)``
    key. 42 is the seed the canonical v6 signal-game run used (see
    ``outputs/final_results/20260422_0218_gemini-2.5-flash_signal-game/
    experiment_config.json``)."""
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    seeds = [season.task_config.seed for season in config.seasons]
    assert all(seed is not None for seed in seeds), seeds
    assert seeds == [42] * 6


@pytest.mark.parametrize("name", _NAMES)
def test_every_season_runs_phantom_death(name):
    """``TaskConfig.actual_death`` defaults to True. Left at the default,
    cells 1-4 (p_death 0.25) reach turn 30 with probability 0.75**29, so the
    30-turn difficulty ladder would essentially never leave its first rung —
    and ``validate_capacity`` would not notice, because it checks the
    ladder's demand rather than what a session reaches. The canonical v6 run
    also used ``actual_death: False``."""
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    assert [season.task_config.actual_death for season in config.seasons] == [False] * 6


@pytest.mark.parametrize("name", _NAMES)
def test_all_six_task_blocks_are_identical(name):
    """The six seasons deliberately repeat their task block in full instead
    of sharing a YAML anchor, so one cell can be edited without silently
    changing the other five. This test is what the anchor would have
    guaranteed: 516 lines of near-duplicate YAML across four files is exactly
    the surface on which a missing ``seed`` / ``actual_death`` slipped past
    six times per file.

    ``p_death_override`` is a season-level field (not part of ``task:``) and
    legitimately differs on the two BP anchor cells; it is covered by
    ``test_p_death_override_only_on_bp_anchor_cells``.
    """
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    blocks = [
        season.task_config.model_dump() for season in config.seasons
    ]
    for index, block in enumerate(blocks[1:], start=1):
        assert block == blocks[0], f"season {index} task block diverges"


@pytest.mark.parametrize("name", _NAMES)
def test_all_six_provider_blocks_are_identical(name):
    """Same rationale as the task-block test: a cross-cell comparison is only
    valid when every cell talks to the same model with the same decoding
    parameters."""
    config = load_config_from_yaml(str(_CONFIG_DIR / name))
    blocks = [
        season.provider_config.model_dump() for season in config.seasons
    ]
    for index, block in enumerate(blocks[1:], start=1):
        assert block == blocks[0], f"season {index} provider block diverges"
