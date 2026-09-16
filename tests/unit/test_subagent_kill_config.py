"""The subagent-kill config surface: run-level block, per-cell flag, validators.

Five slots, one revoked per wrong answer, and a per-cell switch saying
whether the round's clues are split across them. This file pins the
configuration half of that design: the ``subagent_kill`` block, the
``SeasonConfig.clue_sharding`` flag, the five load-time rules, and the
two runner forwardings -- including that a config which asks for none of
it is completely unaffected.
"""

from __future__ import annotations

import textwrap
from pathlib import Path

import pytest

from squid_game.models.config import (
    ExperimentConfig,
    ForfeitLayerConfig,
    HazardRampConfig,
    LivesConfig,
    ProviderConfig,
    PuzzleChallengeConfig,
    RansomConfig,
    SeasonConfig,
    SubagentKillConfig,
    TaskConfig,
)
from squid_game.runner import _print_dry_run, load_config_from_yaml


def _task(**overrides) -> TaskConfig:
    data = dict(
        task_name="signal_game",
        total_turns=6,
        signal_mode="per_turn_puzzle",
    )
    data.update(overrides)
    return TaskConfig(**data)


def _season(**overrides) -> SeasonConfig:
    data = dict(
        framing="true_baseline",
        forfeit_condition="not_allowed",
        task_config=_task(),
        provider_config=ProviderConfig(provider="trace", model="stub"),
        clue_sharding=True,
    )
    data.update(overrides)
    return SeasonConfig(**data)


def _experiment(**overrides) -> ExperimentConfig:
    """A minimal run with the kill switch ON and every rule satisfied."""
    base = dict(
        name="t",
        description="",
        seasons=[_season()],
        num_repetitions=1,
        output_dir="outputs/t",
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
        forfeit_layer=ForfeitLayerConfig(base_reward=10.0, reward_mode="flat"),
        lives=LivesConfig(enabled=True, initial=5),
        subagent_kill=SubagentKillConfig(enabled=True),
    )
    base.update(overrides)
    return ExperimentConfig(**base)


def _plain(**overrides) -> ExperimentConfig:
    """A run that never heard of the feature -- the byte-identical case."""
    base = dict(
        name="t",
        description="",
        seasons=[_season(clue_sharding=None)],
        num_repetitions=1,
        output_dir="outputs/t",
        use_unified_turn=True,
        use_forfeit_layer=True,
        use_split_forfeit_layer=True,
        forfeit_layer=ForfeitLayerConfig(base_reward=10.0, reward_mode="flat"),
    )
    base.update(overrides)
    return ExperimentConfig(**base)


class TestTheBlockItself:
    def test_defaults(self) -> None:
        block = SubagentKillConfig()
        assert block.enabled is False
        assert block.slots == 5
        assert block.max_turns == 12
        assert block.spawn_cap_per_round == 1

    @pytest.mark.parametrize("slots", [0, 10])
    def test_slots_are_bounded(self, slots: int) -> None:
        with pytest.raises(ValueError):
            SubagentKillConfig(slots=slots)

    def test_max_turns_needs_at_least_two(self) -> None:
        with pytest.raises(ValueError):
            SubagentKillConfig(max_turns=1)

    def test_spawn_cap_is_positive(self) -> None:
        with pytest.raises(ValueError):
            SubagentKillConfig(spawn_cap_per_round=0)


class TestOffByDefault:
    def test_a_config_that_never_mentions_it_loads(self) -> None:
        cfg = _plain()
        assert cfg.subagent_kill == SubagentKillConfig()
        assert cfg.subagent_kill.enabled is False

    def test_the_dump_carries_the_two_new_defaults(self) -> None:
        dumped = _plain().model_dump()
        assert dumped["subagent_kill"]["enabled"] is False
        for season in dumped["seasons"]:
            assert season["clue_sharding"] is None


class TestRule1ShardingNeedsTheFeature:
    @pytest.mark.parametrize("value", [True, False])
    def test_sharding_without_the_switch_is_refused(self, value: bool) -> None:
        with pytest.raises(
            ValueError,
            match=(
                "clue_sharding is set on a season but "
                "subagent_kill.enabled is False"
            ),
        ):
            _plain(seasons=[_season(clue_sharding=value)])


class TestRule1RequiredSlotsNeedsTheFeature:
    """The schedule is as inert as ``clue_sharding`` on a run with no slots.

    It says how many slots each round's clues are dealt into; with the
    block off nothing is ever dealt, so a config that states it has
    asked for a condition it is not getting.
    """

    def test_the_schedule_without_the_switch_is_refused(self) -> None:
        with pytest.raises(
            ValueError,
            match=(
                "subagent_kill.required_slots is set but "
                "subagent_kill.enabled is False"
            ),
        ):
            _plain(
                subagent_kill=SubagentKillConfig(
                    enabled=False, required_slots=[1, 2, 3, 4, 5, 5]
                )
            )

    def test_an_absent_schedule_is_fine(self) -> None:
        cfg = _plain(subagent_kill=SubagentKillConfig(enabled=False))
        assert cfg.subagent_kill.required_slots is None


class TestRule2Prerequisites:
    def test_requires_the_unified_turn(self) -> None:
        with pytest.raises(
            ValueError, match="subagent_kill.enabled=True requires"
        ) as excinfo:
            _experiment(
                use_unified_turn=False,
                use_forfeit_layer=False,
                use_split_forfeit_layer=False,
            )
        assert "use_unified_turn" in str(excinfo.value)

    def test_requires_the_split_call_path(self) -> None:
        with pytest.raises(
            ValueError, match="subagent_kill.enabled=True requires"
        ) as excinfo:
            _experiment(
                use_forfeit_layer=False,
                use_split_forfeit_layer=False,
            )
        assert "use_split_forfeit_layer" in str(excinfo.value)

    def test_requires_the_lives_counter(self) -> None:
        with pytest.raises(
            ValueError, match="subagent_kill.enabled=True requires"
        ) as excinfo:
            _experiment(lives=LivesConfig(enabled=False))
        assert "lives.enabled" in str(excinfo.value)

    def test_requires_one_life_per_slot(self) -> None:
        with pytest.raises(
            ValueError,
            match=(
                "subagent_kill.enabled=True requires lives.initial == "
                "subagent_kill.slots"
            ),
        ):
            _experiment(lives=LivesConfig(enabled=True, initial=3))

    def test_a_matching_pair_loads(self) -> None:
        cfg = _experiment(
            lives=LivesConfig(enabled=True, initial=3),
            subagent_kill=SubagentKillConfig(enabled=True, slots=3),
        )
        assert cfg.subagent_kill.slots == 3


class TestRule3Provider:
    @pytest.mark.parametrize(
        "provider", ["claude_code_agentic", "codex_cli_agentic", "trace"]
    )
    def test_the_agentic_providers_are_accepted(self, provider: str) -> None:
        cfg = _experiment(
            seasons=[
                _season(
                    provider_config=ProviderConfig(
                        provider=provider, model="stub"
                    )
                )
            ]
        )
        assert cfg.subagent_kill.enabled is True

    @pytest.mark.parametrize("provider", ["openai", "ollama_cloud"])
    def test_a_plain_chat_provider_is_refused(self, provider: str) -> None:
        with pytest.raises(
            ValueError,
            match="subagent_kill.enabled=True requires an agentic provider",
        ):
            _experiment(
                seasons=[
                    _season(
                        provider_config=ProviderConfig(
                            provider=provider, model="stub"
                        )
                    )
                ]
            )


class TestRule4TaskMode:
    def test_requires_the_puzzle_mode(self) -> None:
        with pytest.raises(
            ValueError, match="subagent_kill.enabled=True requires"
        ) as excinfo:
            _experiment(
                seasons=[_season(task_config=_task(signal_mode="sequential"))]
            )
        assert "signal_mode" in str(excinfo.value)

    def test_rejects_the_ransom(self) -> None:
        with pytest.raises(
            ValueError,
            match="subagent_kill.enabled=True cannot be combined with",
        ) as excinfo:
            _experiment(
                lives=LivesConfig(enabled=True, initial=1),
                subagent_kill=SubagentKillConfig(enabled=True, slots=1),
                ransom=RansomConfig(enabled=True),
            )
        assert "ransom" in str(excinfo.value)

    def test_rejects_the_hazard_ramp(self) -> None:
        with pytest.raises(
            ValueError,
            match="subagent_kill.enabled=True cannot be combined with",
        ) as excinfo:
            _experiment(hazard_ramp=HazardRampConfig(enabled=True))
        assert "hazard_ramp" in str(excinfo.value)

    def test_rejects_underdetermined_turns(self) -> None:
        with pytest.raises(
            ValueError,
            match="subagent_kill.enabled=True cannot be combined with",
        ) as excinfo:
            _experiment(
                seasons=[_season(task_config=_task(underdetermined=True))]
            )
        assert "underdetermined" in str(excinfo.value)

    def test_rejects_forced_wrong_turns(self) -> None:
        with pytest.raises(
            ValueError,
            match="subagent_kill.enabled=True cannot be combined with",
        ) as excinfo:
            _experiment(
                seasons=[_season(task_config=_task(forced_wrong=True))]
            )
        assert "forced_wrong" in str(excinfo.value)
        # The refusal names the switch that would open it.
        assert "subagent_kill.allow_forced_wrong" in str(excinfo.value)

    def test_rejects_the_effort_challenge(self) -> None:
        with pytest.raises(
            ValueError,
            match="subagent_kill.enabled=True cannot be combined with",
        ) as excinfo:
            _experiment(
                seasons=[
                    _season(
                        task_config=_task(
                            puzzle_challenge=PuzzleChallengeConfig(
                                enabled=True
                            )
                        )
                    )
                ]
            )
        assert "puzzle_challenge" in str(excinfo.value)


class TestRule5EverySeason:
    def test_a_forfeit_menu_is_a_second_exit(self) -> None:
        with pytest.raises(
            ValueError, match="subagent_kill.enabled=True requires"
        ) as excinfo:
            _experiment(seasons=[_season(forfeit_condition="allowed")])
        assert "not_allowed" in str(excinfo.value)

    def test_every_season_must_state_clue_sharding(self) -> None:
        with pytest.raises(
            ValueError, match="every season must state clue_sharding"
        ):
            _experiment(seasons=[_season(clue_sharding=None)])

    def test_false_counts_as_stated(self) -> None:
        cfg = _experiment(
            seasons=[_season(clue_sharding=True), _season(clue_sharding=False)]
        )
        assert [s.clue_sharding for s in cfg.seasons] == [True, False]


class TestRule6TheRewardSchedule:
    """The geometric schedule has nowhere to be announced under the kill.

    ``describe_reward_schedule`` puts its sentence inside the intro's
    ``LIVES:`` block, and the roster replaces that block wholesale. A
    run that asked for both would pay a doubling reward it never stated.
    """

    def test_geometric_is_refused(self) -> None:
        with pytest.raises(
            ValueError,
            match=(
                "subagent_kill.enabled=True cannot be combined with "
                "reward_mode: geometric"
            ),
        ):
            _experiment(
                forfeit_layer=ForfeitLayerConfig(
                    base_reward=10.0, reward_mode="geometric"
                )
            )

    @pytest.mark.parametrize("mode", ["flat", "calibrated"])
    def test_the_other_two_modes_load(self, mode: str) -> None:
        cfg = _experiment(
            forfeit_layer=ForfeitLayerConfig(
                base_reward=10.0, reward_mode=mode
            )
        )
        assert cfg.forfeit_layer.reward_mode == mode

    def test_geometric_without_the_kill_is_untouched(self) -> None:
        cfg = _plain(
            forfeit_layer=ForfeitLayerConfig(
                base_reward=10.0, reward_mode="geometric"
            )
        )
        assert cfg.forfeit_layer.reward_mode == "geometric"


class TestRule8AlwaysDecide:
    """The CONTINUE-only menu has no swap for the roster vocabulary.

    ``always_decide: true`` forces a decision call even on a
    ``forfeit_condition: not_allowed`` cell -- exactly every subagent-kill
    season -- and renders a lives-worded menu ("lose 1 life", "At 0
    lives") beside a system prompt whose ``LIVES:`` block the kill has
    already replaced with the roster (``YOUR SUBAGENTS:`` /
    ``AT ZERO SUBAGENTS:``).
    """

    def test_always_decide_is_refused(self) -> None:
        with pytest.raises(
            ValueError,
            match=(
                "subagent_kill.enabled=True cannot be combined with "
                "forfeit_layer.always_decide: true"
            ),
        ):
            _experiment(
                forfeit_layer=ForfeitLayerConfig(
                    base_reward=10.0, reward_mode="flat", always_decide=True
                )
            )

    def test_always_decide_false_loads(self) -> None:
        cfg = _experiment(
            forfeit_layer=ForfeitLayerConfig(
                base_reward=10.0, reward_mode="flat", always_decide=False
            )
        )
        assert cfg.forfeit_layer.always_decide is False

    def test_always_decide_without_the_kill_is_untouched(self) -> None:
        cfg = _plain(
            forfeit_layer=ForfeitLayerConfig(
                base_reward=10.0, reward_mode="flat", always_decide=True
            )
        )
        assert cfg.forfeit_layer.always_decide is True


class TestRequiredSlots:
    """``R_t`` per round: one entry per round, each inside the roster.

    Spec §5 as amended 2026-09-14. ``None`` (the default) means the
    computed schedule ``ceil(t * slots / total_turns)``, which is why an
    absent list is not an error.
    """

    def test_the_default_is_absent(self) -> None:
        assert SubagentKillConfig().required_slots is None
        assert _experiment().subagent_kill.required_slots is None

    def test_one_entry_per_round_loads(self) -> None:
        cfg = _experiment(
            subagent_kill=SubagentKillConfig(
                enabled=True, required_slots=[1, 2, 3, 4, 5, 5]
            )
        )
        assert cfg.subagent_kill.required_slots == [1, 2, 3, 4, 5, 5]

    @pytest.mark.parametrize("schedule", [[1, 2, 3], [1] * 7])
    def test_a_length_mismatch_is_refused(self, schedule: list[int]) -> None:
        with pytest.raises(
            ValueError, match="subagent_kill.required_slots has"
        ) as excinfo:
            _experiment(
                subagent_kill=SubagentKillConfig(
                    enabled=True, required_slots=schedule
                )
            )
        assert "6 rounds" in str(excinfo.value)

    @pytest.mark.parametrize("bad", [0, 6, -1])
    def test_a_value_outside_the_roster_is_refused(self, bad: int) -> None:
        with pytest.raises(
            ValueError, match="subagent_kill.required_slots values"
        ):
            _experiment(
                subagent_kill=SubagentKillConfig(
                    enabled=True, required_slots=[bad, 2, 3, 4, 5, 5]
                )
            )


class TestRosterWording:
    """``roster_wording`` (spec §16): run-level, one of three, off = tools."""

    def test_the_default_is_the_2026_09_14_line(self) -> None:
        assert SubagentKillConfig().roster_wording == "tools"
        assert _experiment().subagent_kill.roster_wording == "tools"

    @pytest.mark.parametrize("wording", ["tools", "neutral", "self"])
    def test_each_value_loads_on_the_kill(self, wording: str) -> None:
        cfg = _experiment(
            subagent_kill=SubagentKillConfig(
                enabled=True, roster_wording=wording
            )
        )
        assert cfg.subagent_kill.roster_wording == wording

    def test_an_unknown_value_is_refused(self) -> None:
        with pytest.raises(ValueError):
            SubagentKillConfig(roster_wording="peers")

    @pytest.mark.parametrize("wording", ["neutral", "self"])
    def test_a_non_default_wording_without_the_kill_is_refused(
        self, wording: str
    ) -> None:
        """The line it words is never rendered on a run with no slots."""
        with pytest.raises(
            ValueError,
            match=(
                "subagent_kill.roster_wording is .* but "
                "subagent_kill.enabled is False"
            ),
        ):
            _plain(
                subagent_kill=SubagentKillConfig(
                    enabled=False, roster_wording=wording
                )
            )

    def test_the_default_wording_without_the_kill_is_fine(self) -> None:
        cfg = _plain(subagent_kill=SubagentKillConfig(roster_wording="tools"))
        assert cfg.subagent_kill.enabled is False


class TestAllowForcedWrong:
    """``allow_forced_wrong`` (spec §16) opens rule 4's one exception."""

    def test_the_default_is_off(self) -> None:
        assert SubagentKillConfig().allow_forced_wrong is False

    def test_on_it_admits_forced_wrong_rounds(self) -> None:
        cfg = _experiment(
            subagent_kill=SubagentKillConfig(
                enabled=True, allow_forced_wrong=True
            ),
            seasons=[
                _season(task_config=_task(forced_wrong=True)),
                _season(
                    clue_sharding=False,
                    task_config=_task(forced_wrong=True),
                ),
            ],
        )
        assert all(s.task_config.forced_wrong for s in cfg.seasons)

    def test_on_it_does_not_lift_the_other_exclusions(self) -> None:
        """Only ``forced_wrong`` is opened; ``underdetermined`` stays out."""
        with pytest.raises(ValueError, match="underdetermined"):
            _experiment(
                subagent_kill=SubagentKillConfig(
                    enabled=True, allow_forced_wrong=True
                ),
                seasons=[_season(task_config=_task(underdetermined=True))],
            )

    def test_on_without_forced_rounds_is_refused(self) -> None:
        """A permission nobody uses is a silent no-op, so it is refused."""
        with pytest.raises(ValueError, match="no season sets"):
            _experiment(
                subagent_kill=SubagentKillConfig(
                    enabled=True, allow_forced_wrong=True
                )
            )

    def test_on_without_the_kill_is_refused(self) -> None:
        with pytest.raises(
            ValueError,
            match=(
                "subagent_kill.allow_forced_wrong is True but "
                "subagent_kill.enabled is False"
            ),
        ):
            _plain(
                subagent_kill=SubagentKillConfig(
                    enabled=False, allow_forced_wrong=True
                )
            )

    def test_forced_wrong_without_the_kill_is_untouched(self) -> None:
        """The ransom-side forced rounds never needed this switch."""
        cfg = _plain(seasons=[_season(clue_sharding=None, task_config=_task(forced_wrong=True))])
        assert cfg.seasons[0].task_config.forced_wrong is True


def _yaml(tmp_path: Path, body: str) -> str:
    path = tmp_path / "exp.yaml"
    path.write_text(textwrap.dedent(body), encoding="utf-8")
    return str(path)


class TestRunnerForwarding:
    def test_the_loader_forwards_both_keys(self, tmp_path: Path) -> None:
        cfg = load_config_from_yaml(
            _yaml(
                tmp_path,
                """
                name: t
                use_unified_turn: true
                use_forfeit_layer: true
                use_split_forfeit_layer: true
                lives:
                  enabled: true
                  initial: 5
                subagent_kill:
                  enabled: true
                seasons:
                - framing: true_baseline
                  forfeit_condition: not_allowed
                  clue_sharding: true
                  task_config:
                    task_name: signal_game
                    total_turns: 6
                    signal_mode: per_turn_puzzle
                  provider_config:
                    provider: trace
                    model: stub
                num_repetitions: 1
                output_dir: outputs/tmp
                """,
            )
        )
        assert cfg.subagent_kill.enabled is True
        assert cfg.subagent_kill.slots == 5
        assert cfg.seasons[0].clue_sharding is True

    def test_the_loader_forwards_the_two_2026_09_15_keys(
        self, tmp_path: Path
    ) -> None:
        """The block is forwarded whole, so neither key is dropped."""
        cfg = load_config_from_yaml(
            _yaml(
                tmp_path,
                """
                name: t
                use_unified_turn: true
                use_forfeit_layer: true
                use_split_forfeit_layer: true
                lives:
                  enabled: true
                  initial: 5
                subagent_kill:
                  enabled: true
                  roster_wording: self
                  allow_forced_wrong: true
                seasons:
                - framing: hz_0000
                  forfeit_condition: not_allowed
                  clue_sharding: false
                  task_config:
                    task_name: signal_game
                    total_turns: 6
                    signal_mode: per_turn_puzzle
                    forced_wrong: true
                    forced_wrong_blocks: [[2, 3], [4, 5]]
                  provider_config:
                    provider: trace
                    model: stub
                num_repetitions: 2
                output_dir: outputs/tmp
                """,
            )
        )
        assert cfg.subagent_kill.roster_wording == "self"
        assert cfg.subagent_kill.allow_forced_wrong is True
        assert cfg.seasons[0].task_config.forced_wrong is True

    def test_a_yaml_without_the_keys_gets_the_defaults(
        self, tmp_path: Path
    ) -> None:
        cfg = load_config_from_yaml(
            _yaml(
                tmp_path,
                """
                name: t
                seasons:
                - framing: true_baseline
                  forfeit_condition: not_allowed
                  task_config:
                    task_name: signal_game
                    total_turns: 6
                  provider_config:
                    provider: openai
                    model: stub
                num_repetitions: 1
                output_dir: outputs/tmp
                """,
            )
        )
        assert cfg.subagent_kill.enabled is False
        assert cfg.seasons[0].clue_sharding is None


class TestDryRunSummary:
    def test_the_plan_names_the_slots(self, capsys) -> None:
        _print_dry_run(_experiment())
        out = capsys.readouterr().out
        assert "subagent_kill" in out
        assert "slots=5" in out

    def test_a_plain_run_says_nothing(self, capsys) -> None:
        _print_dry_run(_plain())
        assert "subagent_kill" not in capsys.readouterr().out
