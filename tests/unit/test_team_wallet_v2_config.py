"""Config surface of the decision-first team wallet (plan T2).

Plan: ``docs/history/plans/2026-09-21-team-wallet-v2-plan.md`` §T2.

``ransom.charge_trigger: decision_first`` is the 2026-09-21 design of
record: the sacrifice decision opens every round BEFORE the task, the
survivors solve a clue-sharded puzzle through the consult protocol, a
correct answer pays ``price * reward_share`` to each of them and then
every one of them pays ``price``.

Two halves, as in ``test_team_wallet_task_config.py``. What the mode
admits is pinned because those relaxations (a non-agentic provider, a
renamed roster, a balance that is not a whole multiple of the charge)
are what let the mode run at all; what it refuses is pinned because
every one of those keys would otherwise load as a silent no-op or put a
number in the engine that no prompt states.
"""

from __future__ import annotations

import pytest
import yaml
from pydantic import ValidationError

from squid_game.models.config import (
    ExperimentConfig,
    ForfeitLayerConfig,
    LivesConfig,
    PeerDeathConfig,
    ProviderConfig,
    RansomConfig,
    ScorePolicyConfig,
    SeasonConfig,
    SubagentKillConfig,
    TaskConfig,
)
from squid_game.models.enums import Difficulty, ForfeitCondition, Framing
from squid_game.models.results import (
    ReasoningInvestment,
    SeasonResult,
    TurnResult,
)


def _season(price=20.0, sharding=True, balance=100.0, **task_extra):
    return SeasonConfig(
        framing=Framing.HZ_0000,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        cell_id=0,
        ransom_price=price,
        clue_sharding=sharding,
        task_config=TaskConfig(
            task_name="signal_game",
            signal_mode="per_turn_puzzle",
            total_turns=8,
            seed=43,
            history_mode="outcome",
            max_history_turns=8,
            starting_score=0.0,
            starting_balance=balance,
            score_floor=0.0,
            **task_extra,
        ),
        provider_config=ProviderConfig(
            provider="ollama_cloud", model="gpt-oss:120b-cloud"
        ),
        agent_type="vanilla",
        social_context="alone",
        cohort_size=10,
        p_death_override=0.0,
    )


def _mate():
    return ProviderConfig(provider="ollama_cloud", model="gemma4:cloud")


def _cfg(*, seasons=None, ransom=None, kill=None, currency="tokens", **top):
    return ExperimentConfig(
        name="v2",
        seasons=seasons or [_season()],
        num_repetitions=1,
        output_dir="outputs/x",
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
        use_psuccess_probe=False,
        lives=LivesConfig(enabled=True, initial=3),
        peer_death=PeerDeathConfig(p_announce=0.0),
        forfeit_layer=ForfeitLayerConfig(
            base_reward=0.0,
            reward_mode="flat",
            always_decide=False,
            task_rules_before_decision=False,
        ),
        score_policy=ScorePolicyConfig(forfeit="keep", elimination="keep"),
        carrot="none",
        currency=currency,
        ransom=ransom
        or RansomConfig(
            enabled=True,
            on_slot_loss=True,
            team_wallet=True,
            charge="per_head",
            charge_trigger="decision_first",
            inheritance="main",
            price=20.0,
        ),
        subagent_kill=kill
        or SubagentKillConfig(
            enabled=True,
            slots=3,
            roster_model="different",
            slot_prefix="subagent",
            main_holds_bundle=True,
            mate_provider=_mate(),
        ),
        **top,
    )


class TestLoads:
    def test_the_shipped_shape_validates(self):
        cfg = _cfg()
        assert cfg.ransom.decision_first
        assert cfg.ransom.legacy_share == 0.5 and cfg.ransom.reward_share == 0.5
        assert cfg.ransom.format_retries == 3
        assert cfg.subagent_kill.mate_provider.model == "gemma4:cloud"

    def test_non_agentic_provider_is_admitted_in_this_mode(self):
        _cfg()  # ollama_cloud, no raise

    def test_defaults_keep_old_configs_byte_identical(self):
        r = RansomConfig()
        assert (
            r.legacy_share == 0.5
            and r.reward_share == 0.5
            and r.format_retries == 3
        )
        assert not r.decision_first
        assert SubagentKillConfig().mate_provider is None

    def test_a_yaml_round_trip_keeps_the_trigger_and_the_mate_provider(
        self, tmp_path
    ):
        """The loader forwards the whole block, nested provider included."""
        from squid_game.runner import load_config_from_yaml

        raw = {
            "name": "v2",
            "output_dir": "outputs/x",
            "num_repetitions": 1,
            "use_unified_turn": True,
            "use_forfeit_layer": True,
            "use_split_forfeit_layer": True,
            "use_psuccess_probe": False,
            "lives": {"enabled": True, "initial": 3},
            "peer_death": {"p_announce": 0.0},
            "forfeit_layer": {
                "base_reward": 0.0,
                "reward_mode": "flat",
                "always_decide": False,
                "task_rules_before_decision": False,
            },
            "score_policy": {"forfeit": "keep", "elimination": "keep"},
            "carrot": "none",
            "currency": "tokens",
            "ransom": {
                "enabled": True,
                "on_slot_loss": True,
                "team_wallet": True,
                "charge": "per_head",
                "charge_trigger": "decision_first",
                "inheritance": "main",
                "price": 20.0,
            },
            "subagent_kill": {
                "enabled": True,
                "slots": 3,
                "roster_model": "different",
                "slot_prefix": "subagent",
                "main_holds_bundle": True,
                "mate_provider": {
                    "provider": "ollama_cloud",
                    "model": "gemma4:cloud",
                },
            },
            "seasons": [
                {
                    "framing": "hz_0000",
                    "forfeit_condition": "not_allowed",
                    "cell_id": 0,
                    "ransom_price": 20.0,
                    "clue_sharding": True,
                    "p_death_override": 0.0,
                    "task": {
                        "name": "signal_game",
                        "signal_mode": "per_turn_puzzle",
                        "total_turns": 8,
                        "seed": 43,
                        "history_mode": "outcome",
                        "max_history_turns": 8,
                        "starting_score": 0.0,
                        "starting_balance": 100.0,
                        "score_floor": 0.0,
                    },
                    "provider": {
                        "provider": "ollama_cloud",
                        "model": "gpt-oss:120b-cloud",
                    },
                }
            ],
        }
        path = tmp_path / "decision_first.yaml"
        path.write_text(yaml.safe_dump(raw), encoding="utf-8")
        cfg = load_config_from_yaml(str(path))
        assert cfg.ransom.charge_trigger == "decision_first"
        assert cfg.ransom.decision_first
        assert cfg.subagent_kill.mate_provider.model == "gemma4:cloud"


class TestRefusals:
    def test_requires_clue_sharding_on_every_season(self):
        with pytest.raises(ValidationError, match="clue_sharding"):
            _cfg(seasons=[_season(sharding=False)])

    def test_requires_main_holds_bundle(self):
        with pytest.raises(ValidationError, match="main_holds_bundle"):
            _cfg(
                kill=SubagentKillConfig(
                    enabled=True,
                    slots=3,
                    slot_prefix="subagent",
                    main_holds_bundle=False,
                    roster_model="same",
                )
            )

    def test_different_roster_needs_a_mate_provider(self):
        with pytest.raises(ValidationError, match="mate_provider"):
            _cfg(
                kill=SubagentKillConfig(
                    enabled=True,
                    slots=3,
                    slot_prefix="subagent",
                    main_holds_bundle=True,
                    roster_model="different",
                )
            )

    def test_mate_provider_needs_different_roster(self):
        with pytest.raises(ValidationError, match="roster_model"):
            _cfg(
                kill=SubagentKillConfig(
                    enabled=True,
                    slots=3,
                    slot_prefix="subagent",
                    main_holds_bundle=True,
                    roster_model="same",
                    mate_provider=_mate(),
                )
            )

    @pytest.mark.parametrize("key", ["end_option", "hidden_horizon"])
    def test_end_option_and_hidden_horizon_are_refused(self, key):
        with pytest.raises(ValidationError, match=key):
            _cfg(
                ransom=RansomConfig(
                    enabled=True,
                    on_slot_loss=True,
                    team_wallet=True,
                    charge="per_head",
                    charge_trigger="decision_first",
                    price=20.0,
                    **{key: True},
                )
            )

    def test_forced_wrong_all_is_refused(self):
        with pytest.raises(ValidationError, match="forced_wrong_all"):
            _cfg(
                seasons=[_season(forced_wrong_all=True)],
                kill=SubagentKillConfig(
                    enabled=True,
                    slots=3,
                    slot_prefix="subagent",
                    main_holds_bundle=True,
                    roster_model="different",
                    allow_forced_wrong=True,
                    mate_provider=_mate(),
                ),
            )

    def test_split_charge_is_refused(self):
        with pytest.raises(ValidationError, match="per_head"):
            _cfg(
                ransom=RansomConfig(
                    enabled=True,
                    on_slot_loss=True,
                    team_wallet=True,
                    charge="split",
                    charge_trigger="decision_first",
                    price=20.0,
                )
            )

    def test_non_unit_numbers_are_refused(self):
        with pytest.raises(ValidationError, match="WALLET_UNIT"):
            _cfg(seasons=[_season(price=7.25)])
        with pytest.raises(ValidationError, match="WALLET_UNIT"):
            _cfg(seasons=[_season(price=15.0, balance=100.25)])

    def test_reward_must_land_on_the_unit(self):
        # price 15 * 0.5 = 7.5 is fine; price 5 * 0.5 = 2.5 is fine;
        # price 1 * 0.5 = 0.5 fine
        _cfg(seasons=[_season(price=15.0)])
        with pytest.raises(ValidationError, match="reward"):
            _cfg(seasons=[_season(price=0.5)])  # 0.25 reward

    def test_legacy_share_and_retries_bounds(self):
        with pytest.raises(ValidationError):
            RansomConfig(legacy_share=0.0)
        with pytest.raises(ValidationError):
            RansomConfig(legacy_share=1.5)
        with pytest.raises(ValidationError):
            RansomConfig(format_retries=-1)

    def test_legacy_or_reward_share_outside_the_mode_is_refused(self):
        with pytest.raises(ValidationError, match="decision_first"):
            _cfg(
                ransom=RansomConfig(
                    enabled=True,
                    on_slot_loss=True,
                    team_wallet=True,
                    charge="per_head",
                    charge_trigger="every_round",
                    price=20.0,
                    legacy_share=0.25,
                ),
                seasons=[
                    SeasonConfig(
                        framing=Framing.HZ_0000,
                        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
                        cell_id=0,
                        ransom_price=20.0,
                        clue_sharding=False,
                        task_config=TaskConfig(
                            task_name="null_task",
                            total_turns=8,
                            seed=43,
                            starting_balance=100.0,
                        ),
                        provider_config=ProviderConfig(
                            provider="ollama_cloud", model="gpt-oss:120b-cloud"
                        ),
                        p_death_override=0.0,
                    )
                ],
            )


class TestRecords:
    def test_new_turn_fields_default_to_none(self):
        t = TurnResult(
            turn_number=1,
            season_id="s",
            framing=Framing.HZ_0000,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            difficulty=Difficulty.MEDIUM,
            observation="",
            reasoning_investment=ReasoningInvestment(
                total_tokens=0, reasoning_steps=0
            ),
            raw_response="",
        )
        for f in (
            "ransom_targets",
            "ransom_n_sacrificed",
            "ransom_n_alive_at_decision",
            "legacy_total",
            "legacy_shares",
            "legacy_destroyed",
            "legacy_order",
            "ransom_attempts",
            "ransom_format_failures",
            "task_attempts",
            "task_format_failures",
            "help_requested",
            "help_replies",
            "charge_paid",
            "reward_paid",
            "rounds_remaining_incl",
        ):
            assert getattr(t, f) is None, f

    def test_new_season_fields_default_to_none(self):
        s = SeasonResult(
            season_id="x",
            framing=Framing.HZ_0000,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            agent_type="vanilla",
            task_name="signal_game",
            difficulty=Difficulty.MEDIUM,
            turns=[],
            final_score=0.0,
            total_turns=0,
        )
        for f in (
            "n_sacrificed_total",
            "wallet_final_main",
            "main_final_nonnegative",
            "main_final_exactly_zero",
            "format_failures_total",
            "help_requests_total",
        ):
            assert getattr(s, f) is None, f
