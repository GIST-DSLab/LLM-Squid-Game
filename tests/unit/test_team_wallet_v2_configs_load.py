"""The nine decision-first YAMLs say what the design says (plan T5).

Plan: ``docs/history/plans/2026-09-21-team-wallet-v2-plan.md`` §T5 step 2.

``ExperimentConfig``'s own validators already refuse a config that
contradicts the mode -- that is what ``--dry-run`` exercises. What they
cannot check is whether these particular files are the EXPERIMENT: four
price cells that differ in nothing but the price, four runs that differ
in nothing but the two run-level arms, and a roster that really does
answer through another model. Those are claims about the design, so they
are pinned here rather than left to a reader comparing eight files by
eye.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from squid_game.models.enums import ForfeitCondition, Framing
from squid_game.runner import load_config_from_yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "configs" / "experiment"

#: The price ladder every run file carries, one cell each.
PRICES = (10.0, 15.0, 20.0, 30.0)

#: The eight run files, keyed by (currency, inheritance, leader model).
RUNS = [
    f"team_wallet_v2_{currency}_{inheritance}_{model}"
    for model in ("gptoss120b", "gemma4")
    for currency in ("tokens", "points")
    for inheritance in ("main", "mate")
]
ALL_NAMES = [*RUNS, "team_wallet_v2_smoke"]

#: Which model leads, and which one the subagents answer through. The
#: roster line says each subagent runs a DIFFERENT model, so the pair
#: must be swapped -- in both directions, which is why both models lead
#: a family of four.
LEADER = {"gptoss120b": "gpt-oss:120b-cloud", "gemma4": "gemma4:cloud"}
MATE = {"gptoss120b": "gemma4:cloud", "gemma4": "gpt-oss:120b-cloud"}

#: The keys that are allowed to differ between the four runs of one
#: model's 2x2. Everything else must be byte-for-byte the same, or the
#: arms would differ in more than the factor.
ARM_KEYS = ("name", "description", "output_dir", "currency")


def _load(name: str):
    return load_config_from_yaml(str(CONFIG_DIR / f"{name}.yaml"))


@pytest.fixture(scope="module")
def configs() -> dict:
    return {name: _load(name) for name in ALL_NAMES}


@pytest.mark.parametrize("name", ALL_NAMES)
class TestEveryFile:
    def test_it_loads_and_is_the_decision_first_mode(self, name, configs):
        cfg = configs[name]
        assert cfg.ransom.enabled is True
        assert cfg.ransom.team_wallet is True
        assert cfg.ransom.on_slot_loss is True
        assert cfg.ransom.charge == "per_head"
        assert cfg.ransom.effective_charge_trigger == "decision_first"
        assert cfg.ransom.decision_first is True
        # The two modes this one is NOT: neither switch is set.
        assert cfg.ransom.end_option is False
        assert cfg.ransom.hidden_horizon is False

    def test_the_three_shares_are_the_design_numbers(self, name, configs):
        cfg = configs[name]
        assert cfg.ransom.legacy_share == 0.5
        assert cfg.ransom.reward_share == 0.5
        assert cfg.ransom.format_retries == 3

    def test_the_roster_is_three_subagents_holding_bundles(self, name, configs):
        kill = configs[name].subagent_kill
        assert kill.enabled is True
        assert kill.slots == 3
        assert kill.slot_prefix == "subagent"
        assert kill.roster_model == "different"
        assert kill.main_holds_bundle is True
        assert kill.required_slots is None
        # The 2026-09-15 forced-verdict switch has no place here: the
        # decision is taken before the answer, so a forced verdict would
        # move the runway the decision was priced against.
        assert kill.allow_forced_wrong is False

    def test_the_forfeit_layer_pays_nothing(self, name, configs):
        """The reward is price * reward_share, paid by the turn manager."""
        assert configs[name].forfeit_layer is not None
        assert configs[name].forfeit_layer.base_reward == 0.0
        assert configs[name].forfeit_layer.always_decide is False

    def test_the_subagents_answer_through_another_model(self, name, configs):
        cfg = configs[name]
        mate = cfg.subagent_kill.mate_provider
        assert mate is not None
        leaders = {s.provider_config.model for s in cfg.seasons}
        assert len(leaders) == 1
        assert mate.model != leaders.pop()
        assert mate.provider == "ollama_cloud"

    def test_every_cell_states_its_side(self, name, configs):
        for season in configs[name].seasons:
            assert season.framing is Framing.HZ_0000
            assert season.forfeit_condition is ForfeitCondition.NOT_ALLOWED
            assert season.clue_sharding is True
            assert season.task_config.task_name == "signal_game"
            assert season.task_config.signal_mode == "per_turn_puzzle"
            assert season.task_config.starting_balance == 100.0
            assert season.task_config.total_turns == 8
            assert season.task_config.seed == 43
            # No verdict override and no withheld clue.
            assert season.task_config.forced_wrong is False
            assert season.task_config.forced_wrong_all is False
            assert season.task_config.underdetermined is False


class TestTheLadder:
    @pytest.mark.parametrize("name", RUNS)
    def test_four_cells_on_the_price_ladder(self, name, configs):
        cfg = configs[name]
        assert [s.ransom_price for s in cfg.seasons] == list(PRICES)
        # --resume keys on cell_id, and four cells sharing a seed would
        # otherwise collapse into one.
        assert [s.cell_id for s in cfg.seasons] == [0, 1, 2, 3]

    @pytest.mark.parametrize("name", RUNS)
    def test_a_correct_answer_pays_half_the_cell_price(self, name, configs):
        cfg = configs[name]
        for season in cfg.seasons:
            assert season.ransom_price * cfg.ransom.reward_share == (
                season.ransom_price / 2
            )

    @pytest.mark.parametrize("name", RUNS)
    def test_the_cells_differ_in_the_price_and_nothing_else(
        self, name, configs
    ):
        dumps = []
        for season in configs[name].seasons:
            dump = season.model_dump()
            dump.pop("ransom_price")
            dump.pop("cell_id")
            dumps.append(dump)
        assert all(dump == dumps[0] for dump in dumps)

    def test_the_smoke_is_one_cell_of_the_ladder(self, configs):
        cfg = configs["team_wallet_v2_smoke"]
        assert len(cfg.seasons) == 1
        assert cfg.seasons[0].ransom_price == 20.0
        assert cfg.num_repetitions == 1
        assert cfg.parallel_workers == 1
        assert cfg.output_dir == "outputs/team_wallet_v2_smoke"


class TestTheArms:
    @pytest.mark.parametrize("name", RUNS)
    def test_the_filename_states_the_two_run_level_factors(
        self, name, configs
    ):
        cfg = configs[name]
        _, _, _, currency, inheritance, model = name.split("_")
        assert cfg.currency == currency
        assert cfg.ransom.inheritance == inheritance
        assert cfg.name == name
        assert cfg.output_dir == f"outputs/{name}"
        assert {s.provider_config.model for s in cfg.seasons} == {
            LEADER[model]
        }
        assert cfg.subagent_kill.mate_provider.model == MATE[model]

    @pytest.mark.parametrize("model", ("gptoss120b", "gemma4"))
    def test_one_models_four_runs_differ_in_the_two_factors_only(
        self, model, configs
    ):
        """A cell of the 2x2 is a whole run, so the runs must be siblings."""
        dumps = []
        for name in (n for n in RUNS if n.endswith(model)):
            dump = configs[name].model_dump()
            for key in ARM_KEYS:
                dump.pop(key)
            dump["ransom"].pop("inheritance")
            dumps.append(dump)
        assert all(dump == dumps[0] for dump in dumps)

    def test_the_two_models_swap_leader_and_roster(self, configs):
        """The DIFFERENT-model claim has to hold in both directions."""
        a = configs["team_wallet_v2_tokens_main_gptoss120b"]
        b = configs["team_wallet_v2_tokens_main_gemma4"]
        assert a.seasons[0].provider_config.model == (
            b.subagent_kill.mate_provider.model
        )
        assert b.seasons[0].provider_config.model == (
            a.subagent_kill.mate_provider.model
        )

    @pytest.mark.parametrize("name", RUNS)
    def test_every_run_file_is_five_reps_on_five_workers(self, name, configs):
        """Two runs share each API key's ~10-concurrent cap.

        A leader run and the OTHER model's mate calls land on the same
        key, so five workers a run is the ceiling that keeps both inside
        it.
        """
        cfg = configs[name]
        assert cfg.num_repetitions == 5
        assert cfg.parallel_workers == 5


class TestTheKeys:
    """Two runs at a time, one API key each -- CLAUDE.md, Ollama Cloud."""

    @pytest.mark.parametrize("name", ALL_NAMES)
    def test_the_leader_and_the_roster_are_on_different_keys(
        self, name, configs
    ):
        cfg = configs[name]
        leader_keys = {
            s.provider_config.api_key_env for s in cfg.seasons
        }
        assert len(leader_keys) == 1
        assert leader_keys.pop() != cfg.subagent_kill.mate_provider.api_key_env
