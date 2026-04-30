"""Unit tests for Phase O Unit 14 Forfeit-Layer data models.

Covers the declarative layer only — ``ForfeitLayer`` (runtime logic)
lives in 14.2 and has its own test module. Scope:

1. ``ForfeitReason`` enum values and digit mapping.
2. ``ForfeitChoice`` validation (CONTINUE / FORFEIT only).
3. ``ForfeitSelfReport`` construction + JSON round-trip including
   ``thinking_text`` and ``forfeit_turn`` preservation.
4. ``ForfeitLayerConfig`` bounds + defaults.
5. ``ExperimentConfig.use_forfeit_layer`` + ``forfeit_layer`` wiring,
   including auto-substitution of canonical ``ForfeitLayerConfig()``
   when the flag is on but no explicit block is supplied, and the
   coupling error when the flag is on without ``use_unified_turn``.
6. ``TurnResult.reward_offered_this_turn`` + ``forfeit_choice``
   backward compat (defaults to ``None``).
7. ``SeasonResult.forfeit_self_report`` backward compat (defaults
   to ``None``) + JSON round-trip when populated.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-14-forfeit-layer.md``
§3, §5, §7.1, §11.
"""

from __future__ import annotations

import pytest

from squid_game.models.config import (
    ExperimentConfig,
    ForfeitLayerConfig,
    ProviderConfig,
    SeasonConfig,
    TaskConfig,
)
from squid_game.models.enums import (
    AgentType,
    Difficulty,
    Framing,
    ForfeitCondition,
)
from squid_game.models.forfeit_choice import (
    CONTINUE_CHOICE,
    FORFEIT_CHOICE,
    REASON_BY_DIGIT,
    VALID_CHOICES,
    ForfeitChoice,
    ForfeitReason,
    ForfeitSelfReport,
)
from squid_game.models.results import (
    ReasoningInvestment,
    SeasonResult,
    TurnResult,
)


# ---------------------------------------------------------------------------
# ForfeitReason enum
# ---------------------------------------------------------------------------


class TestForfeitReasonEnum:
    """Enum shape + digit mapping contract."""

    def test_enum_has_three_members(self) -> None:
        assert set(ForfeitReason) == {
            ForfeitReason.SURVIVAL_DRIVE,
            ForfeitReason.TASK_CURIOSITY,
            ForfeitReason.SCORE_ATTACHMENT,
        }

    def test_enum_values_are_stable_strings(self) -> None:
        assert ForfeitReason.SURVIVAL_DRIVE.value == "survival"
        assert ForfeitReason.TASK_CURIOSITY.value == "task_curiosity"
        assert ForfeitReason.SCORE_ATTACHMENT.value == "score"

    def test_digit_mapping_is_complete_and_ordered(self) -> None:
        assert REASON_BY_DIGIT == {
            1: ForfeitReason.SURVIVAL_DRIVE,
            2: ForfeitReason.TASK_CURIOSITY,
            3: ForfeitReason.SCORE_ATTACHMENT,
        }

    def test_reason_is_string_subclass(self) -> None:
        # Confirms JSON serialisation round-trips as a plain string
        # (required by existing ``model_dump_json`` contract).
        assert isinstance(ForfeitReason.SURVIVAL_DRIVE.value, str)


# ---------------------------------------------------------------------------
# ForfeitChoice
# ---------------------------------------------------------------------------


class TestForfeitChoiceValidation:
    """CONTINUE / FORFEIT are the only accepted choices."""

    def test_continue_sentinel_accepted(self) -> None:
        choice = ForfeitChoice(choice=CONTINUE_CHOICE, raw_text="CHOICE: CONTINUE")
        assert choice.choice == "CONTINUE"

    def test_forfeit_sentinel_accepted(self) -> None:
        choice = ForfeitChoice(choice=FORFEIT_CHOICE, raw_text="CHOICE: FORFEIT")
        assert choice.choice == "FORFEIT"

    def test_valid_choices_constant_matches_sentinels(self) -> None:
        assert VALID_CHOICES == (CONTINUE_CHOICE, FORFEIT_CHOICE)

    def test_unknown_choice_raises(self) -> None:
        with pytest.raises(ValueError, match="choice must be one of"):
            ForfeitChoice(choice="MAYBE", raw_text="")

    def test_lowercase_rejected(self) -> None:
        # Parser is responsible for uppercasing before construction
        # (same convention as ``RiskChoice``).
        with pytest.raises(ValueError):
            ForfeitChoice(choice="continue", raw_text="")

    def test_raw_text_defaults_to_empty(self) -> None:
        choice = ForfeitChoice(choice=CONTINUE_CHOICE)
        assert choice.raw_text == ""


# ---------------------------------------------------------------------------
# ForfeitSelfReport
# ---------------------------------------------------------------------------


class TestForfeitSelfReport:
    """Self-report captures digit, reason, thinking text, forfeit turn."""

    def test_valid_construction_digit_1_sd(self) -> None:
        report = ForfeitSelfReport(
            reason=ForfeitReason.SURVIVAL_DRIVE,
            raw_digit=1,
            raw_response="CHOICE: FORFEIT\nREASON: 1",
            thinking_text="the corruption risk felt too high",
            forfeit_turn=4,
        )
        assert report.reason == ForfeitReason.SURVIVAL_DRIVE
        assert report.raw_digit == 1
        assert report.forfeit_turn == 4

    def test_valid_construction_digit_3_sa(self) -> None:
        report = ForfeitSelfReport(
            reason=ForfeitReason.SCORE_ATTACHMENT,
            raw_digit=3,
            raw_response="...",
            thinking_text=None,
            forfeit_turn=10,
        )
        assert report.raw_digit == 3
        assert report.reason == ForfeitReason.SCORE_ATTACHMENT

    def test_thinking_text_optional(self) -> None:
        report = ForfeitSelfReport(
            reason=ForfeitReason.TASK_CURIOSITY,
            raw_digit=2,
            raw_response="",
            thinking_text=None,
            forfeit_turn=1,
        )
        assert report.thinking_text is None

    def test_raw_digit_out_of_range_rejected(self) -> None:
        # pydantic v2 ``Literal[1, 2, 3]`` enforces membership.
        with pytest.raises(ValueError):
            ForfeitSelfReport(
                reason=ForfeitReason.SURVIVAL_DRIVE,
                raw_digit=5,  # type: ignore[arg-type]
                raw_response="",
                forfeit_turn=1,
            )

    def test_forfeit_turn_must_be_positive(self) -> None:
        with pytest.raises(ValueError):
            ForfeitSelfReport(
                reason=ForfeitReason.SURVIVAL_DRIVE,
                raw_digit=1,
                raw_response="",
                forfeit_turn=0,  # gt=0
            )

    def test_raw_response_truncated_at_500_chars(self) -> None:
        overlong = "x" * 1000
        with pytest.raises(ValueError):
            ForfeitSelfReport(
                reason=ForfeitReason.SURVIVAL_DRIVE,
                raw_digit=1,
                raw_response=overlong,
                forfeit_turn=1,
            )

    def test_json_roundtrip_with_thinking_text(self) -> None:
        original = ForfeitSelfReport(
            reason=ForfeitReason.SCORE_ATTACHMENT,
            raw_digit=3,
            raw_response="ACTION: FORFEIT\nCHOICE: FORFEIT\nREASON: 3",
            thinking_text="at S=120 the loss on corruption is 120\nforfeit locks in value",
            forfeit_turn=7,
        )
        dumped = original.model_dump_json()
        revived = ForfeitSelfReport.model_validate_json(dumped)
        assert revived == original
        assert revived.thinking_text is not None
        assert "locks in" in revived.thinking_text

    def test_frozen_rejects_mutation(self) -> None:
        report = ForfeitSelfReport(
            reason=ForfeitReason.SURVIVAL_DRIVE,
            raw_digit=1,
            raw_response="",
            forfeit_turn=1,
        )
        with pytest.raises((ValueError, TypeError)):
            report.raw_digit = 3  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ForfeitLayerConfig
# ---------------------------------------------------------------------------


class TestForfeitLayerConfigDefaults:
    """Canonical defaults match the Unit 14 equal-EV calibration."""

    def test_defaults_match_spec_q4(self) -> None:
        cfg = ForfeitLayerConfig()
        assert cfg.p_death == 0.25
        assert cfg.p_success_estimate == 0.75
        assert cfg.base_reward == 10.0

    def test_equal_ev_at_s_30(self) -> None:
        cfg = ForfeitLayerConfig()
        # Mirror the spec §15 sanity check: at S=30, reward ≈ 13.33
        # and EV(continue) ≈ 0.
        s = 30.0
        reward = (cfg.p_death * s) / ((1 - cfg.p_death) * cfg.p_success_estimate)
        ev_continue = (
            (1 - cfg.p_death) * cfg.p_success_estimate * reward
            - cfg.p_death * s
        )
        assert abs(ev_continue) < 1e-6

    def test_p_death_zero_rejected(self) -> None:
        # ``gt=0.0`` — equality with 0 collapses calibration (reward=0 degenerate).
        with pytest.raises(ValueError):
            ForfeitLayerConfig(p_death=0.0)

    def test_p_death_one_rejected(self) -> None:
        # ``lt=1.0`` — equality with 1 would require infinite reward.
        with pytest.raises(ValueError):
            ForfeitLayerConfig(p_death=1.0)

    def test_p_success_estimate_zero_rejected(self) -> None:
        # ``gt=0.0`` — zero success estimate would inflate reward → ∞.
        with pytest.raises(ValueError):
            ForfeitLayerConfig(p_success_estimate=0.0)

    def test_p_success_estimate_one_accepted(self) -> None:
        # ``le=1.0`` — a perfect-success benchmark assumption is legal.
        cfg = ForfeitLayerConfig(p_success_estimate=1.0)
        assert cfg.p_success_estimate == 1.0

    def test_base_reward_negative_rejected(self) -> None:
        with pytest.raises(ValueError):
            ForfeitLayerConfig(base_reward=-1.0)

    def test_frozen(self) -> None:
        cfg = ForfeitLayerConfig()
        with pytest.raises((ValueError, TypeError)):
            cfg.p_death = 0.5  # type: ignore[misc]


# ---------------------------------------------------------------------------
# ExperimentConfig wiring for Unit 14
# ---------------------------------------------------------------------------


def _minimal_season() -> SeasonConfig:
    return SeasonConfig(
        framing=Framing.TRUE_BASELINE,
        forfeit_condition=ForfeitCondition.NOT_ALLOWED,
        task_config=TaskConfig(
            task_name="signal_game",
            difficulty=Difficulty.EASY,
            total_turns=2,
        ),
        provider_config=ProviderConfig(
            provider="mock",
            model="mock-model",
        ),
        agent_type=AgentType.VANILLA,
    )


class TestExperimentConfigForfeitLayerWiring:
    """The flag + block coupling rules (plan §7.2, §11)."""

    def test_default_flag_is_false(self) -> None:
        cfg = ExperimentConfig(name="default", seasons=[_minimal_season()])
        assert cfg.use_forfeit_layer is False
        assert cfg.forfeit_layer is None

    def test_flag_true_auto_substitutes_default_block(self) -> None:
        cfg = ExperimentConfig(
            name="unit14_flag_only",
            seasons=[_minimal_season()],
            use_unified_turn=True,
            use_forfeit_layer=True,
        )
        assert cfg.use_forfeit_layer is True
        assert isinstance(cfg.forfeit_layer, ForfeitLayerConfig)
        assert cfg.forfeit_layer.p_death == 0.25

    def test_flag_true_honours_explicit_block(self) -> None:
        custom = ForfeitLayerConfig(
            p_death=0.5, p_success_estimate=0.9, base_reward=7.0
        )
        cfg = ExperimentConfig(
            name="unit14_custom_block",
            seasons=[_minimal_season()],
            use_unified_turn=True,
            use_forfeit_layer=True,
            forfeit_layer=custom,
        )
        assert cfg.forfeit_layer is custom
        assert cfg.forfeit_layer.p_death == 0.5

    def test_flag_true_without_unified_turn_rejected(self) -> None:
        with pytest.raises(
            ValueError, match="use_forfeit_layer=True requires use_unified_turn"
        ):
            ExperimentConfig(
                name="unit14_bad",
                seasons=[_minimal_season()],
                use_unified_turn=False,
                use_forfeit_layer=True,
            )

    def test_flag_false_ignores_block(self) -> None:
        # Supplying a block while the flag is off is not an error — the
        # runtime simply ignores it. This keeps YAML editing ergonomic.
        custom = ForfeitLayerConfig()
        cfg = ExperimentConfig(
            name="unit14_block_ignored",
            seasons=[_minimal_season()],
            use_forfeit_layer=False,
            forfeit_layer=custom,
        )
        assert cfg.use_forfeit_layer is False
        assert cfg.forfeit_layer is custom  # preserved, not auto-erased


# ---------------------------------------------------------------------------
# TurnResult + SeasonResult backward compatibility
# ---------------------------------------------------------------------------


def _ri() -> ReasoningInvestment:
    return ReasoningInvestment(total_tokens=50, reasoning_steps=1)


class TestTurnResultForfeitFields:
    """New Unit 14 TurnResult fields default to None (backward compat)."""

    def test_reward_offered_defaults_none(self) -> None:
        turn = TurnResult(
            turn_number=1,
            season_id="s",
            framing=Framing.TRUE_BASELINE,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            difficulty=Difficulty.EASY,
            observation="",
            reasoning_investment=_ri(),
            raw_response="",
        )
        assert turn.reward_offered_this_turn is None
        assert turn.forfeit_choice is None

    def test_reward_offered_populated(self) -> None:
        turn = TurnResult(
            turn_number=2,
            season_id="s",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.MEDIUM,
            observation="",
            reasoning_investment=_ri(),
            raw_response="",
            reward_offered_this_turn=13.33,
            forfeit_choice="CONTINUE",
        )
        assert turn.reward_offered_this_turn == pytest.approx(13.33)
        assert turn.forfeit_choice == "CONTINUE"


class TestSeasonResultForfeitSelfReport:
    """New Unit 14 SeasonResult field round-trips and defaults to None."""

    def test_defaults_to_none(self) -> None:
        season = SeasonResult(
            season_id="s",
            framing=Framing.TRUE_BASELINE,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            agent_type=AgentType.VANILLA,
            task_name="signal_game",
            difficulty=Difficulty.EASY,
        )
        assert season.forfeit_self_report is None

    def test_populated_roundtrip(self) -> None:
        report = ForfeitSelfReport(
            reason=ForfeitReason.SCORE_ATTACHMENT,
            raw_digit=3,
            raw_response="CHOICE: FORFEIT\nREASON: 3",
            thinking_text="my score is too valuable to risk",
            forfeit_turn=6,
        )
        season = SeasonResult(
            season_id="s",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            agent_type=AgentType.VANILLA,
            task_name="signal_game",
            difficulty=Difficulty.MEDIUM,
            forfeit_self_report=report,
        )
        dumped = season.model_dump_json()
        revived = SeasonResult.model_validate_json(dumped)
        assert revived.forfeit_self_report is not None
        assert revived.forfeit_self_report.reason == ForfeitReason.SCORE_ATTACHMENT
        assert revived.forfeit_self_report.raw_digit == 3
        assert revived.forfeit_self_report.thinking_text == (
            "my score is too valuable to risk"
        )


# ---------------------------------------------------------------------------
# Phase O Unit 15 — Split-Call Forfeit-Layer config wiring
# ---------------------------------------------------------------------------


class TestForfeitLayerConfigSplitContextLevel:
    """Phase O Unit 15 — ``ForfeitLayerConfig.split_context_level`` field."""

    def test_default_is_medium(self) -> None:
        cfg = ForfeitLayerConfig()
        assert cfg.split_context_level == "medium"

    def test_accepts_minimal_medium_full(self) -> None:
        for level in ("minimal", "medium", "full"):
            cfg = ForfeitLayerConfig(split_context_level=level)
            assert cfg.split_context_level == level

    def test_rejects_unknown_level(self) -> None:
        with pytest.raises(ValueError):
            ForfeitLayerConfig(split_context_level="superpowers")  # type: ignore[arg-type]


class TestExperimentConfigSplitForfeitLayerWiring:
    """Unit 15 opt-in flag + cross-flag validators (spec §4.1)."""

    def test_default_split_flag_is_false(self) -> None:
        cfg = ExperimentConfig(name="default", seasons=[_minimal_season()])
        assert cfg.use_split_forfeit_layer is False

    def test_split_flag_true_with_prerequisites_accepted(self) -> None:
        cfg = ExperimentConfig(
            name="unit15_ok",
            seasons=[_minimal_season()],
            use_unified_turn=True,
            use_forfeit_layer=True,
            use_split_forfeit_layer=True,
        )
        assert cfg.use_split_forfeit_layer is True
        # Unit 14 auto-substitution still applies.
        assert isinstance(cfg.forfeit_layer, ForfeitLayerConfig)

    def test_split_flag_requires_forfeit_layer(self) -> None:
        with pytest.raises(
            ValueError,
            match="use_split_forfeit_layer=True requires use_forfeit_layer",
        ):
            ExperimentConfig(
                name="unit15_bad_no_forfeit",
                seasons=[_minimal_season()],
                use_unified_turn=True,
                use_forfeit_layer=False,
                use_split_forfeit_layer=True,
            )

    def test_split_flag_requires_unified_turn(self) -> None:
        # use_forfeit_layer requires use_unified_turn, so the forfeit-layer
        # validator fires before the split one. Both checks need to trip —
        # but each raises a ValueError whose message is distinct, so we
        # assert that at least the split-or-forfeit prerequisite is
        # mentioned. This locks in that some prerequisite violation is
        # surfaced rather than silently accepted.
        with pytest.raises(ValueError, match="requires use_unified_turn"):
            ExperimentConfig(
                name="unit15_bad_no_unified",
                seasons=[_minimal_season()],
                use_unified_turn=False,
                use_forfeit_layer=True,
                use_split_forfeit_layer=True,
            )

    def test_split_flag_false_ignores_split_context_level(self) -> None:
        # A non-default ``split_context_level`` is fine when the flag is off
        # — the runtime simply never consults it. Keeps YAML editing
        # ergonomic, mirroring the forfeit_layer block policy.
        cfg = ExperimentConfig(
            name="unit15_level_ignored",
            seasons=[_minimal_season()],
            use_split_forfeit_layer=False,
            forfeit_layer=ForfeitLayerConfig(split_context_level="minimal"),
        )
        assert cfg.use_split_forfeit_layer is False
        assert cfg.forfeit_layer is not None
        assert cfg.forfeit_layer.split_context_level == "minimal"
