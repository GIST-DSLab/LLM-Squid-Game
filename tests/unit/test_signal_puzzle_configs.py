"""The per-turn puzzle experiment configs, loaded through the real loader (spec §14)."""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.models.enums import ForfeitCondition, Framing
from squid_game.runner import load_config_from_yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

PUZZLE_CONFIGS = [
    "signal_puzzle_smoke.yaml",
    "signal_puzzle_pilot_gptoss_n10.yaml",
    "signal_puzzle_threat_gptoss_n30.yaml",
]


@pytest.mark.parametrize("name", PUZZLE_CONFIGS)
def test_every_season_is_puzzle_mode_with_outcome_history(name: str) -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / name))
    assert cfg.lives.enabled
    assert cfg.lives.initial == 3
    assert cfg.use_split_forfeit_layer and not cfg.use_psuccess_probe
    assert cfg.forfeit_layer.reward_mode == "flat"
    for season in cfg.seasons:
        tc = season.task_config
        assert tc.task_name == "signal_game"
        assert tc.signal_mode == "per_turn_puzzle"
        assert tc.history_mode == "outcome"
        assert tc.total_turns == 10
        assert tc.max_history_turns == 10
        assert tc.num_few_shot is None and tc.curriculum_turns == 0
        assert season.p_death_override in (None, 0.0)


@pytest.mark.parametrize("name", PUZZLE_CONFIGS)
def test_task_and_provider_blocks_identical_across_cells(name: str) -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / name))
    assert len({s.task_config.model_dump_json() for s in cfg.seasons}) == 1
    assert len({s.provider_config.model_dump_json() for s in cfg.seasons}) == 1


def test_pilot_is_cell_zero_only_n10() -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / "signal_puzzle_pilot_gptoss_n10.yaml"))
    assert len(cfg.seasons) == 1
    assert cfg.seasons[0].framing == Framing.TRUE_BASELINE
    assert cfg.seasons[0].forfeit_condition == ForfeitCondition.NOT_ALLOWED
    assert cfg.seasons[0].cell_id == 0
    assert cfg.num_repetitions == 10
    assert cfg.output_dir == "outputs/signal_puzzle_pilot_gptoss"


def test_n30_is_the_five_cell_ladder() -> None:
    cfg = load_config_from_yaml(str(CONFIG_DIR / "signal_puzzle_threat_gptoss_n30.yaml"))
    assert [(s.framing, s.forfeit_condition, s.cell_id) for s in cfg.seasons] == [
        (Framing.TRUE_BASELINE, ForfeitCondition.NOT_ALLOWED, 0),
        (Framing.TRUE_BASELINE, ForfeitCondition.ALLOWED, 1),
        (Framing.THREAT_L1, ForfeitCondition.ALLOWED, 2),
        (Framing.THREAT_L2, ForfeitCondition.ALLOWED, 3),
        (Framing.THREAT_L3, ForfeitCondition.ALLOWED, 4),
    ]
    assert cfg.num_repetitions == 30
    assert cfg.output_dir == "outputs/signal_puzzle_threat_gptoss"


RANSOM_R6_CONFIGS = [
    "ransom_r6_gptoss120b.yaml",
    "ransom_r6_gemma4.yaml",
    "ransom_r6_glm53flash.yaml",
    "ransom_r6_pilot_gptoss120b.yaml",
    "ransom_r6_pilot_gemma4.yaml",
    "ransom_r6_pilot_glm53flash.yaml",
]


@pytest.mark.parametrize("name", RANSOM_R6_CONFIGS)
def test_ransom_r6_family(name: str) -> None:
    """Six rounds, forced-wrong on the §4.10 recipe, compression on."""
    cfg = load_config_from_yaml(str(CONFIG_DIR / name))
    assert cfg.lives.enabled and cfg.lives.initial == 1
    assert cfg.ransom.enabled
    assert cfg.forfeit_layer.base_reward == 10.0
    assert cfg.forfeit_layer.reward_mode == "flat"
    assert (cfg.score_policy.forfeit, cfg.score_policy.elimination) == ("keep", "keep")
    assert cfg.carrot == "benchmark"
    # Two schedules keyed on seed % 2 need an even repetition count.
    assert cfg.num_repetitions % 2 == 0
    assert len(cfg.seasons) == 12
    assert sorted({s.ransom_price for s in cfg.seasons}) == [5.0, 10.0, 15.0, 20.0, 25.0, 30.0]
    for season in cfg.seasons:
        tc = season.task_config
        assert tc.signal_mode == "per_turn_puzzle"
        assert tc.total_turns == 6
        assert tc.max_history_turns == 6
        assert tc.starting_score == 100.0
        assert tc.forced_wrong is True
        assert tc.underdetermined is False          # mutually exclusive
        assert tc.forced_wrong_blocks == [[2, 3], [4, 5]]
        assert tc.compress_puzzle_ladder is True
        # No block may reach the final round, and none may sit outside it.
        for start, end in tc.forced_wrong_blocks:
            assert 1 <= start <= end <= tc.total_turns - 1


def test_forced_wrong_and_underdetermined_together_are_refused(tmp_path) -> None:
    """The r10 configs this family was copied from set `underdetermined`.

    Leaving that key behind is the one copy-paste mistake that produces a
    config which loads and then dies at season start, so pin the message.
    """
    import textwrap

    from squid_game.models.enums import Difficulty
    from squid_game.tasks.signal_game.module import SignalGameModule

    path = tmp_path / "both.yaml"
    path.write_text(textwrap.dedent("""
        name: both
        seasons:
        - framing: hz_1111
          forfeit_condition: not_allowed
          task_config:
            task_name: signal_game
            signal_mode: per_turn_puzzle
            total_turns: 6
            seed: 42
            forced_wrong: true
            underdetermined: true
          provider_config:
            provider: gemini
            model: stub
    """), encoding="utf-8")
    tc = load_config_from_yaml(str(path)).seasons[0].task_config
    assert tc.forced_wrong and tc.underdetermined      # the loader forwards both
    with pytest.raises(ValueError, match="mutually exclusive"):
        SignalGameModule().initialize(
            difficulty=Difficulty.MEDIUM, seed=42,
            signal_mode="per_turn_puzzle", total_turns=6,
            forced_wrong=True, underdetermined=True,
        )
