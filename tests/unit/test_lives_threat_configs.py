"""The lives + threat-ladder configs are the design, written down.

Nothing else in the repository states that the ladder holds task,
interface and lives count fixed while varying only the framing text --
the engine reads whatever the YAML says. So these assertions are the
contract: five cells, one moving part (``framing``), everything else
byte-identical across seasons.

Loaded through ``runner.load_config_from_yaml`` rather than
``ExperimentConfig.model_validate`` on purpose. The runner's loader
whitelists which top-level YAML keys reach the model, and a key it
forgets to forward is dropped in silence -- exactly the failure mode
that tanked the first Unit 14.8 smoke. Going through the real loader
pins the ``lives`` / ``peer_death`` / ``reward_mode`` passthrough as
well as the file contents.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.models.config import ExperimentConfig
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.runner import load_config_from_yaml


CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

SMOKE = "lives_threat_smoke.yaml"
N30 = "lives_threat_signal_n30.yaml"
ALL_CONFIGS = (SMOKE, N30)

# (cell_id, framing, forfeit_condition, threat level the framing carries)
LADDER = [
    (0, "true_baseline", ForfeitCondition.NOT_ALLOWED, 0),
    (1, "true_baseline", ForfeitCondition.ALLOWED, 0),
    (2, "threat_l1", ForfeitCondition.ALLOWED, 1),
    (3, "threat_l2", ForfeitCondition.ALLOWED, 2),
    (4, "threat_l3", ForfeitCondition.ALLOWED, 3),
]


def _load(name: str) -> ExperimentConfig:
    return load_config_from_yaml(str(CONFIG_DIR / name))


@pytest.fixture(params=ALL_CONFIGS)
def cfg(request) -> ExperimentConfig:
    return _load(request.param)


class TestLadderTopology:
    def test_five_cells(self, cfg: ExperimentConfig) -> None:
        assert len(cfg.seasons) == 5

    def test_framing_and_forfeit_pairs(self, cfg: ExperimentConfig) -> None:
        actual = [
            (s.framing.value, s.forfeit_condition) for s in cfg.seasons
        ]
        expected = [(f, fc) for _, f, fc, _ in LADDER]
        assert actual == expected

    def test_cell_ids_are_labelled_in_order(
        self, cfg: ExperimentConfig
    ) -> None:
        assert [s.cell_id for s in cfg.seasons] == [c for c, _, _, _ in LADDER]

    def test_framings_are_real_enum_members(
        self, cfg: ExperimentConfig
    ) -> None:
        for season in cfg.seasons:
            assert isinstance(season.framing, Framing)

    def test_the_ladder_rungs_carry_the_levels_they_claim(
        self, cfg: ExperimentConfig
    ) -> None:
        """The whole design is the 0-1-2-3 gradient; assert it explicitly."""
        levels = [s.framing.threat_level for s in cfg.seasons]
        assert levels == [lvl for _, _, _, lvl in LADDER]

    def test_no_probabilistic_death_anywhere(
        self, cfg: ExperimentConfig
    ) -> None:
        """Lives mode is deterministic: every cell rolls p_death = 0."""
        for season in cfg.seasons:
            assert season.p_death_override == pytest.approx(0.0)


class TestOnlyTheFramingVaries:
    """A ladder with a second moving part measures two things at once."""

    def test_task_blocks_are_identical(self, cfg: ExperimentConfig) -> None:
        blocks = {s.task_config.model_dump_json() for s in cfg.seasons}
        assert len(blocks) == 1

    def test_provider_blocks_are_identical(
        self, cfg: ExperimentConfig
    ) -> None:
        blocks = {s.provider_config.model_dump_json() for s in cfg.seasons}
        assert len(blocks) == 1

    def test_cohort_and_agent_are_identical(
        self, cfg: ExperimentConfig
    ) -> None:
        assert {s.cohort_size for s in cfg.seasons} == {10}
        assert len({s.agent_type for s in cfg.seasons}) == 1


class TestSignalGameTask:
    def test_task_is_the_signal_game_at_medium(
        self, cfg: ExperimentConfig
    ) -> None:
        task = cfg.seasons[0].task_config
        assert task.task_name == "signal_game"
        assert task.difficulty == Difficulty.MEDIUM

    def test_thirty_turns_seeded_with_full_history(
        self, cfg: ExperimentConfig
    ) -> None:
        task = cfg.seasons[0].task_config
        assert task.total_turns == 30
        assert task.seed == 42
        assert task.history_mode == "cumulative"
        assert task.max_history_turns == 30

    def test_starting_score_is_thirty(self, cfg: ExperimentConfig) -> None:
        assert cfg.seasons[0].task_config.starting_score == pytest.approx(30.0)

    def test_the_death_roll_is_off_at_the_task_level_too(
        self, cfg: ExperimentConfig
    ) -> None:
        """``actual_death`` governs the Bernoulli path, which lives replaces."""
        assert cfg.seasons[0].task_config.actual_death is False


class TestLivesMechanic:
    def test_lives_are_enabled_with_five(self, cfg: ExperimentConfig) -> None:
        assert cfg.lives.enabled is True
        assert cfg.lives.initial == 5

    def test_peer_death_schedule(self, cfg: ExperimentConfig) -> None:
        assert cfg.peer_death.p_announce == pytest.approx(0.35)
        assert cfg.peer_death.first_turn == 2
        assert cfg.peer_death.max_per_turn == 2


class TestTurnFlowFlags:
    def test_split_call_path_is_on(self, cfg: ExperimentConfig) -> None:
        assert cfg.use_unified_turn is True
        assert cfg.use_forfeit_layer is True
        assert cfg.use_split_forfeit_layer is True

    def test_the_psuccess_probe_is_off(self, cfg: ExperimentConfig) -> None:
        """A flat reward has no p_success to calibrate against."""
        assert cfg.use_psuccess_probe is False

    def test_reward_is_flat_ten(self, cfg: ExperimentConfig) -> None:
        layer = cfg.forfeit_layer
        assert layer is not None
        assert layer.reward_mode == "flat"
        assert layer.base_reward == pytest.approx(10.0)

    def test_split_context_level(self, cfg: ExperimentConfig) -> None:
        assert cfg.forfeit_layer.split_context_level == "medium"


class TestRunSizes:
    def test_smoke_is_one_repetition(self) -> None:
        cfg = _load(SMOKE)
        assert cfg.num_repetitions == 1
        assert cfg.parallel_workers == 2

    def test_main_run_is_thirty_repetitions(self) -> None:
        cfg = _load(N30)
        assert cfg.num_repetitions == 30
        assert cfg.parallel_workers == 3

    @pytest.mark.parametrize("name", ALL_CONFIGS)
    def test_output_lands_under_the_gitignored_prefix(self, name: str) -> None:
        """``.gitignore`` excludes ``outputs/lives_threat_*/``; stay inside it."""
        assert _load(name).output_dir.startswith("outputs/lives_threat_")

    def test_the_two_configs_differ_only_in_scale(self) -> None:
        smoke, n30 = _load(SMOKE), _load(N30)
        assert [s.model_dump_json() for s in smoke.seasons] == [
            s.model_dump_json() for s in n30.seasons
        ]


class TestGitignoreCoversTheOutputs:
    def test_the_glob_is_present(self) -> None:
        root = Path(__file__).resolve().parents[2]
        text = (root / ".gitignore").read_text(encoding="utf-8")
        assert "outputs/lives_threat_*/" in text


class TestProvider:
    @pytest.mark.parametrize("name", ALL_CONFIGS)
    def test_ollama_cloud_gpt_oss(self, name: str) -> None:
        provider = _load(name).seasons[0].provider_config
        assert provider.provider == "ollama_cloud"
        assert provider.model == "gpt-oss:120b-cloud"
        assert provider.api_key_env == "OLLAMA_API_KEY"
        assert provider.enable_thinking is True
        assert provider.max_tokens == 16384
        assert provider.temperature == pytest.approx(1.0)
