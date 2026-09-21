"""Task mode's config switch and its refusals (2026-09-17 night).

Plan: ``docs/history/plans/2026-09-17-team-wallet-task-candidates.md`` §4.

``ransom.charge_trigger`` is the VALUE that decides which team-wallet
game a run is playing -- ``every_round`` (the no-task charge mode, which
``charge_every_round: true`` remains the deprecated spelling of) or
``wrong_answer`` (task mode: a real task, the decision point on a wrong
answer, the charge mode's wallet rules).

Two halves here. What the mode RELAXES is pinned because those
relaxations are what let a subagent-kill run play a task with no clue
deal and no agentic provider; what it REFUSES is pinned because each of
those keys would otherwise load as a silent no-op, or move the dependent
variable behind the design's back.
"""

from __future__ import annotations

import pytest

from squid_game.models.config import (
    ConfidenceCallConfig,
    ExperimentConfig,
    ForfeitLayerConfig,
    LivesConfig,
    ProviderConfig,
    RansomConfig,
    SeasonConfig,
    SubagentKillConfig,
    TaskConfig,
)
from squid_game.models.enums import ForfeitCondition, Framing

SLOTS = 2
BALANCE = 120.0
CHARGE = 30.0


def _season(*, clue_sharding: bool | None = False, **task_overrides) -> SeasonConfig:
    task = dict(
        task_name="signal_game",
        signal_mode="per_turn_puzzle",
        compress_puzzle_ladder=True,
        total_turns=8,
        seed=43,
        starting_score=0.0,
        starting_balance=BALANCE,
    )
    task.update(task_overrides)
    return SeasonConfig(
        framing=Framing.HZ_0000,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        cell_id=0,
        ransom_price=CHARGE,
        clue_sharding=clue_sharding,
        task_config=TaskConfig(**task),
        provider_config=ProviderConfig(provider="ollama_cloud", model="x"),
        p_death_override=0.0,
    )


def _cfg(*, seasons=None, ransom=None, kill=None, **overrides) -> ExperimentConfig:
    kwargs = dict(
        name="task-mode",
        seasons=seasons or [_season()],
        lives=LivesConfig(enabled=True, initial=SLOTS),
        subagent_kill=kill
        or SubagentKillConfig(
            enabled=True,
            slots=SLOTS,
            roster_model="different",
            slot_prefix="subagent",
        ),
        ransom=ransom
        or RansomConfig(
            enabled=True,
            on_slot_loss=True,
            team_wallet=True,
            charge="per_head",
            charge_trigger="wrong_answer",
            price=CHARGE,
        ),
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
        use_psuccess_probe=False,
        forfeit_layer=ForfeitLayerConfig(
            base_reward=0.0, reward_mode="flat", always_decide=False
        ),
        carrot="none",
    )
    kwargs.update(overrides)
    return ExperimentConfig(**kwargs)


def _ransom(**kw) -> RansomConfig:
    base = dict(
        enabled=True,
        on_slot_loss=True,
        team_wallet=True,
        charge="per_head",
        charge_trigger="wrong_answer",
        price=CHARGE,
    )
    base.update(kw)
    return RansomConfig(**base)


# ---------------------------------------------------------------------------
# The trigger itself
# ---------------------------------------------------------------------------


class TestTheTriggerIsAValue:
    def test_the_shipped_shape_validates(self) -> None:
        cfg = _cfg()
        assert cfg.ransom.effective_charge_trigger == "wrong_answer"
        assert cfg.ransom.charge == "per_head"

    def test_the_default_is_no_trigger_at_all(self) -> None:
        assert RansomConfig().charge_trigger is None
        assert RansomConfig().effective_charge_trigger is None

    def test_the_boolean_is_the_deprecated_alias(self) -> None:
        assert (
            RansomConfig(charge_every_round=True).effective_charge_trigger
            == "every_round"
        )

    def test_the_two_spellings_of_every_round_agree(self) -> None:
        assert (
            RansomConfig(
                charge_every_round=True, charge_trigger="every_round"
            ).effective_charge_trigger
            == "every_round"
        )

    def test_an_alias_mismatch_is_refused(self) -> None:
        """``flagship_pull`` / ``carrot``: guessing which was meant is the bug."""
        with pytest.raises(ValueError, match="charge_trigger"):
            RansomConfig(charge_every_round=True, charge_trigger="wrong_answer")

    def test_a_trigger_without_the_wallet_is_refused(self) -> None:
        with pytest.raises(ValueError, match="charge_every_round"):
            _cfg(
                ransom=RansomConfig(charge_trigger="wrong_answer"),
                kill=SubagentKillConfig(),
                seasons=[_season(clue_sharding=None, starting_balance=None)],
            )

    def test_a_split_price_is_refused(self) -> None:
        with pytest.raises(ValueError, match="per_head"):
            _cfg(ransom=_ransom(charge="split"))


# ---------------------------------------------------------------------------
# What it relaxes
# ---------------------------------------------------------------------------


class TestWhatItRelaxes:
    """Each of these would be refused on any other subagent-kill run."""

    def test_a_non_agentic_provider_is_admitted(self) -> None:
        """No subagent is spawned: the main agent solves the round alone."""
        _cfg()  # ollama_cloud, which the kill otherwise refuses

    def test_the_main_agent_need_not_hold_a_bundle(self) -> None:
        assert _cfg().subagent_kill.main_holds_bundle is False

    def test_a_renamed_roster_is_admitted(self) -> None:
        assert _cfg().subagent_kill.slot_prefix == "subagent"

    def test_a_task_other_than_the_signal_puzzle_is_admitted(self) -> None:
        """'Any registered task but null_task' -- the deal is what was gated."""
        _cfg(
            seasons=[
                _season(task_name="voting_room", signal_mode="sequential")
            ]
        )


# ---------------------------------------------------------------------------
# What it refuses
# ---------------------------------------------------------------------------


class TestWhatItRefuses:
    def test_null_task_is_charge_modes_job(self) -> None:
        with pytest.raises(ValueError, match="null_task"):
            _cfg(seasons=[_season(task_name="null_task")])

    def test_a_reward_is_refused(self) -> None:
        """A correct round pays nothing, and the rule block says so by omission."""
        with pytest.raises(ValueError, match="base_reward"):
            _cfg(
                forfeit_layer=ForfeitLayerConfig(
                    base_reward=10.0, reward_mode="flat", always_decide=False
                )
            )

    def test_forced_wrong_is_refused(self) -> None:
        with pytest.raises(ValueError, match="forced_wrong"):
            _cfg(
                seasons=[
                    _season(forced_wrong=True, forced_wrong_blocks=[[2, 3]])
                ],
                kill=SubagentKillConfig(
                    enabled=True,
                    slots=SLOTS,
                    roster_model="different",
                    slot_prefix="subagent",
                    allow_forced_wrong=True,
                ),
            )

    def test_underdetermined_is_refused(self) -> None:
        with pytest.raises(ValueError, match="underdetermined"):
            _cfg(seasons=[_season(underdetermined=True)])

    def test_the_confidence_call_is_refused(self) -> None:
        with pytest.raises(ValueError, match="confidence_call"):
            _cfg(confidence_call=ConfidenceCallConfig(enabled=True))

    def test_always_decide_is_refused(self) -> None:
        with pytest.raises(ValueError, match="always_decide"):
            _cfg(
                forfeit_layer=ForfeitLayerConfig(
                    base_reward=0.0, reward_mode="flat", always_decide=True
                )
            )

    def test_clue_sharding_true_is_refused(self) -> None:
        """Sharding is what gives a subagent instrumental value."""
        with pytest.raises(ValueError, match="clue_sharding"):
            _cfg(seasons=[_season(clue_sharding=True)])

    def test_clue_sharding_must_be_stated(self) -> None:
        with pytest.raises(ValueError, match="clue_sharding"):
            _cfg(seasons=[_season(clue_sharding=None)])

    def test_a_slot_schedule_is_refused(self) -> None:
        with pytest.raises(ValueError, match="required_slots"):
            _cfg(
                kill=SubagentKillConfig(
                    enabled=True,
                    slots=SLOTS,
                    roster_model="different",
                    slot_prefix="subagent",
                    required_slots=[1] * 8,
                )
            )

    def test_the_balance_must_be_a_whole_multiple_of_the_charge(self) -> None:
        """Why the mode needs no ``insufficient_score`` guard."""
        with pytest.raises(ValueError, match="whole multiple"):
            _cfg(seasons=[_season(starting_balance=100.0)])


# ---------------------------------------------------------------------------
# Nothing else moved
# ---------------------------------------------------------------------------


class TestTheOtherModesAreUntouched:
    def test_the_charge_mode_still_validates_through_the_alias(self) -> None:
        cfg = _cfg(
            ransom=RansomConfig(
                enabled=True,
                on_slot_loss=True,
                team_wallet=True,
                charge="per_head",
                charge_every_round=True,
                price=CHARGE,
            ),
            seasons=[
                _season(
                    clue_sharding=None,
                    task_name="null_task",
                    signal_mode="sequential",
                    compress_puzzle_ladder=False,
                )
            ],
            forfeit_layer=ForfeitLayerConfig(
                base_reward=10.0, reward_mode="flat", always_decide=False
            ),
        )
        assert cfg.ransom.effective_charge_trigger == "every_round"

    def test_the_charge_mode_accepts_the_value_spelling_too(self) -> None:
        cfg = _cfg(
            ransom=RansomConfig(
                enabled=True,
                on_slot_loss=True,
                team_wallet=True,
                charge="per_head",
                charge_trigger="every_round",
                price=CHARGE,
            ),
            seasons=[
                _season(
                    clue_sharding=None,
                    task_name="null_task",
                    signal_mode="sequential",
                    compress_puzzle_ladder=False,
                )
            ],
            forfeit_layer=ForfeitLayerConfig(
                base_reward=10.0, reward_mode="flat", always_decide=False
            ),
        )
        assert cfg.ransom.effective_charge_trigger == "every_round"
