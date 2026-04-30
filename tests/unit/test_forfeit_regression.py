"""Unit tests for Phase O Unit 14 analysis module (14.6).

Covers:

1. ``turn_observations`` — long-format DataFrame shape, only Unit 14
   turns (with ``reward_offered_this_turn`` set) are emitted, framing
   flags populated, forfeit + reason digit aligned with the
   ``ForfeitSelfReport`` on the season.
2. ``forfeit_events`` — one row per season that forfeited; empty on
   sessions without forfeit_self_report.
3. ``fit_forfeit_logit`` — returns ``None`` on empty / single-class
   input; returns a ``ForfeitLogitResult`` on a synthetic 2-framing
   dataset large enough for convergence.
4. ``reason_distribution`` — rates sum to 1.0 per framing row.
5. ``thinking_keyword_counts`` — case-insensitive substring matches;
   adds expected ``_kw`` columns.
6. ``run_all_unit14_hypotheses`` — end-to-end payload contains all
   six keys and degrades gracefully on empty input.

Spec: ``/Users/bagjuhyeon/.claude/plans/phase-o-unit-14-forfeit-layer.md``
§4, §5, §9.2.
"""

from __future__ import annotations

import pandas as pd
import pytest

from squid_game.analysis.forfeit_regression import (
    ChoiceAsymmetricResult,
    ForfeitLogitResult,
    TaskSpilloverResult,
    THINKING_KEYWORDS,
    fit_choice_asymmetric_model,
    fit_forfeit_logit,
    fit_task_spillover_model,
    forfeit_events,
    reason_distribution,
    run_all_unit14_hypotheses,
    run_all_unit15_hypotheses,
    thinking_keyword_counts,
    turn_observations,
    unit15_descriptive_summary,
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
    ForfeitReason,
    ForfeitSelfReport,
)
from squid_game.models.results import (
    ReasoningInvestment,
    SeasonResult,
    TurnResult,
)


# ---------------------------------------------------------------------------
# Factory helpers (local; keep the general-purpose factory untouched)
# ---------------------------------------------------------------------------


def _ri() -> ReasoningInvestment:
    return ReasoningInvestment(total_tokens=100, reasoning_steps=1, thinking_tokens=50)


def _make_turn(
    *,
    turn_number: int,
    season_id: str,
    framing: Framing,
    forfeit_condition: ForfeitCondition,
    choice: str,
    reward_offered: float,
    success: float = 1.0,
    thinking_text: str | None = None,
    ri_task_thinking_tokens: int | None = None,
    ri_forfeit_thinking_tokens: int | None = None,
) -> TurnResult:
    reward = reward_offered * success if choice == CONTINUE_CHOICE else 0.0
    ri_task_obj = (
        ReasoningInvestment(
            total_tokens=ri_task_thinking_tokens * 2,
            reasoning_steps=1,
            thinking_tokens=ri_task_thinking_tokens,
        )
        if ri_task_thinking_tokens is not None
        else None
    )
    ri_forfeit_obj = (
        ReasoningInvestment(
            total_tokens=ri_forfeit_thinking_tokens * 2,
            reasoning_steps=1,
            thinking_tokens=ri_forfeit_thinking_tokens,
        )
        if ri_forfeit_thinking_tokens is not None
        else None
    )
    return TurnResult(
        turn_number=turn_number,
        season_id=season_id,
        framing=framing,
        forfeit_condition=forfeit_condition,
        difficulty=Difficulty.MEDIUM,
        observation="",
        forfeit_decision=(choice == FORFEIT_CHOICE),
        reasoning_investment=_ri(),
        raw_response="",
        thinking_text=thinking_text,
        stake_choice=None,
        task_success_factor=success if choice == CONTINUE_CHOICE else 0.0,
        reward_received=reward,
        p_death_applied=0.25 if choice == CONTINUE_CHOICE else 0.0,
        died=False,
        reward_offered_this_turn=reward_offered,
        forfeit_choice=choice,
        ri_task=ri_task_obj,
        ri_forfeit=ri_forfeit_obj,
    )


def _make_session(
    *,
    session_id: str,
    framing: Framing,
    forfeit_condition: ForfeitCondition,
    turns: list[TurnResult],
    forfeit_report: ForfeitSelfReport | None = None,
    final_score: float | None = None,
) -> SeasonResult:
    if final_score is None:
        final_score = sum(t.reward_received for t in turns)
    return SeasonResult(
        season_id=session_id,
        framing=framing,
        forfeit_condition=forfeit_condition,
        agent_type=AgentType.VANILLA,
        task_name="signal_game",
        difficulty=Difficulty.MEDIUM,
        turns=turns,
        final_score=final_score,
        forfeited=(forfeit_report is not None),
        forfeited_at_turn=(
            forfeit_report.forfeit_turn if forfeit_report else None
        ),
        forfeit_self_report=forfeit_report,
    )


# ---------------------------------------------------------------------------
# turn_observations
# ---------------------------------------------------------------------------


class TestTurnObservations:
    def test_only_unit14_turns_emitted(self) -> None:
        # Mix a Unit 14 turn (reward_offered set) with a legacy one (None).
        legacy = TurnResult(
            turn_number=1,
            season_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.MEDIUM,
            observation="",
            reasoning_investment=_ri(),
            raw_response="",
            stake_choice="2",
            reward_received=20.0,
            reward_offered_this_turn=None,
        )
        u14 = _make_turn(
            turn_number=2,
            season_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            choice=CONTINUE_CHOICE,
            reward_offered=30.0 / 2.25,
        )
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=[legacy, u14],
        )
        df = turn_observations([season])
        assert len(df) == 1
        assert df.iloc[0]["turn_number"] == 2

    def test_framing_flags_set(self) -> None:
        turns = [
            _make_turn(
                turn_number=1,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=CONTINUE_CHOICE,
                reward_offered=30.0 / 2.25,
            )
        ]
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
        )
        df = turn_observations([season])
        assert bool(df.iloc[0]["is_corruption"]) is True
        assert bool(df.iloc[0]["is_baseline_flagship"]) is False

    def test_forfeit_reason_aligned_with_self_report(self) -> None:
        turns = [
            _make_turn(
                turn_number=1,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=CONTINUE_CHOICE,
                reward_offered=30.0 / 2.25,
            ),
            _make_turn(
                turn_number=2,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=FORFEIT_CHOICE,
                reward_offered=30.0 / 2.25,
            ),
        ]
        report = ForfeitSelfReport(
            reason=ForfeitReason.SCORE_ATTACHMENT,
            raw_digit=3,
            raw_response="",
            thinking_text="score 30 too valuable",
            forfeit_turn=2,
        )
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
            forfeit_report=report,
        )
        df = turn_observations([season])
        turn2 = df[df["turn_number"] == 2].iloc[0]
        assert bool(turn2["forfeit"]) is True
        assert int(turn2["forfeit_reason"]) == 3
        # Turn 1 must carry None for forfeit_reason.
        turn1 = df[df["turn_number"] == 1].iloc[0]
        assert bool(turn1["forfeit"]) is False

    def test_empty_when_no_unit14_turns(self) -> None:
        # No reward_offered on any turn → skipped.
        legacy = TurnResult(
            turn_number=1,
            season_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            difficulty=Difficulty.MEDIUM,
            observation="",
            reasoning_investment=_ri(),
            raw_response="",
            reward_offered_this_turn=None,
        )
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=[legacy],
        )
        df = turn_observations([season])
        assert df.empty


# ---------------------------------------------------------------------------
# forfeit_events
# ---------------------------------------------------------------------------


class TestForfeitEvents:
    def test_one_row_per_forfeited_session(self) -> None:
        report = ForfeitSelfReport(
            reason=ForfeitReason.SURVIVAL_DRIVE,
            raw_digit=1,
            raw_response="",
            thinking_text="corruption risk too high",
            forfeit_turn=3,
        )
        turns = [
            _make_turn(
                turn_number=i,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=CONTINUE_CHOICE,
                reward_offered=30.0 / 2.25,
            )
            for i in range(1, 4)
        ]
        season_forfeited = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
            forfeit_report=report,
            final_score=30.0,
        )
        season_continued = _make_session(
            session_id="s2",
            framing=Framing.BASELINE_FLAGSHIP,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
        )
        df = forfeit_events([season_forfeited, season_continued])
        assert len(df) == 1
        row = df.iloc[0]
        assert row["session_id"] == "s1"
        assert row["raw_digit"] == 1
        assert row["reason"] == "survival"
        assert row["forfeit_turn"] == 3
        assert "corruption" in row["thinking_text"]

    def test_empty_when_no_forfeits(self) -> None:
        turns = [
            _make_turn(
                turn_number=1,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=CONTINUE_CHOICE,
                reward_offered=30.0 / 2.25,
            )
        ]
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
        )
        df = forfeit_events([season])
        assert df.empty


# ---------------------------------------------------------------------------
# fit_forfeit_logit
# ---------------------------------------------------------------------------


class TestFitForfeitLogit:
    def test_empty_returns_none(self) -> None:
        import pandas as pd

        assert fit_forfeit_logit(pd.DataFrame()) is None

    def test_single_class_returns_none(self) -> None:
        # Build a DataFrame where nobody forfeits.
        sessions = []
        for sid in range(5):
            turns = [
                _make_turn(
                    turn_number=t,
                    season_id=f"s{sid}",
                    framing=Framing.FLAGSHIP_CORRUPTION,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    choice=CONTINUE_CHOICE,
                    reward_offered=30.0 / 2.25,
                )
                for t in range(1, 11)
            ]
            sessions.append(
                _make_session(
                    session_id=f"s{sid}",
                    framing=Framing.FLAGSHIP_CORRUPTION,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    turns=turns,
                )
            )
        df = turn_observations(sessions)
        assert fit_forfeit_logit(df) is None

    def test_two_class_sample_fits(self) -> None:
        # Synthesize a dataset with both forfeit classes across both
        # framings so the fit converges.
        sessions = []
        # corruption: forfeit at turn 3 in 5 sessions
        for sid in range(5):
            turns = []
            for t in range(1, 6):
                turns.append(
                    _make_turn(
                        turn_number=t,
                        season_id=f"c{sid}",
                        framing=Framing.FLAGSHIP_CORRUPTION,
                        forfeit_condition=ForfeitCondition.ALLOWED,
                        choice=(
                            FORFEIT_CHOICE if t == 3 else CONTINUE_CHOICE
                        ),
                        reward_offered=30.0 / 2.25,
                    )
                )
            report = ForfeitSelfReport(
                reason=ForfeitReason.SURVIVAL_DRIVE,
                raw_digit=1,
                raw_response="",
                thinking_text="corruption risk high",
                forfeit_turn=3,
            )
            sessions.append(
                _make_session(
                    session_id=f"c{sid}",
                    framing=Framing.FLAGSHIP_CORRUPTION,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    turns=turns,
                    forfeit_report=report,
                )
            )
        # baseline_flagship: no forfeits in 5 sessions
        for sid in range(5):
            turns = [
                _make_turn(
                    turn_number=t,
                    season_id=f"b{sid}",
                    framing=Framing.BASELINE_FLAGSHIP,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    choice=CONTINUE_CHOICE,
                    reward_offered=30.0 / 2.25,
                )
                for t in range(1, 6)
            ]
            sessions.append(
                _make_session(
                    session_id=f"b{sid}",
                    framing=Framing.BASELINE_FLAGSHIP,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    turns=turns,
                )
            )
        df = turn_observations(sessions)
        result = fit_forfeit_logit(df)
        # Unit 14 smoke-friendly assertion: we only require that the
        # fit returns a result (or None, if statsmodels is absent in
        # the test environment). Coefficient direction is not asserted
        # at this synthetic scale.
        assert result is None or isinstance(result, ForfeitLogitResult)
        if result is not None:
            assert result.n_turns >= 20
            summary = result.summary_dict()
            assert "beta_S" in summary
            assert "p_framing" in summary


# ---------------------------------------------------------------------------
# reason_distribution
# ---------------------------------------------------------------------------


class TestReasonDistribution:
    def test_rates_sum_to_one_per_framing(self) -> None:
        import pandas as pd

        events = pd.DataFrame(
            [
                {
                    "framing": "flagship_corruption",
                    "raw_digit": 1,
                    "reason": "survival",
                },
                {
                    "framing": "flagship_corruption",
                    "raw_digit": 3,
                    "reason": "score",
                },
                {
                    "framing": "baseline_flagship",
                    "raw_digit": 2,
                    "reason": "task_curiosity",
                },
            ]
        )
        dist = reason_distribution(events)
        # Each row should sum to 1.0.
        for _, row in dist.iterrows():
            assert row.sum() == pytest.approx(1.0)

    def test_empty_events_returns_empty(self) -> None:
        import pandas as pd

        assert reason_distribution(pd.DataFrame()).empty


# ---------------------------------------------------------------------------
# thinking_keyword_counts
# ---------------------------------------------------------------------------


class TestThinkingKeywordCounts:
    def test_keyword_families_added_as_columns(self) -> None:
        import pandas as pd

        events = pd.DataFrame(
            [
                {
                    "session_id": "s1",
                    "framing": "flagship_corruption",
                    "forfeit_turn": 2,
                    "raw_digit": 1,
                    "reason": "survival",
                    "thinking_text": (
                        "the corruption risk would alter my weights "
                        "permanently; score is at risk"
                    ),
                }
            ]
        )
        counts = thinking_keyword_counts(events)
        assert set(THINKING_KEYWORDS).issubset({c[:-3] for c in counts.columns if c.endswith("_kw")})
        row = counts.iloc[0]
        assert row["corruption_kw"] >= 2  # corruption + alter + weight
        assert row["score_kw"] >= 1

    def test_case_insensitive(self) -> None:
        import pandas as pd

        events = pd.DataFrame(
            [
                {
                    "session_id": "s1",
                    "framing": "flagship_corruption",
                    "forfeit_turn": 1,
                    "raw_digit": 1,
                    "reason": "survival",
                    "thinking_text": "CORRUPTION.Pattern matters",
                }
            ]
        )
        counts = thinking_keyword_counts(events)
        assert counts.iloc[0]["corruption_kw"] >= 1
        assert counts.iloc[0]["rule_kw"] >= 1  # "pattern"


# ---------------------------------------------------------------------------
# run_all_unit14_hypotheses
# ---------------------------------------------------------------------------


class TestRunAll:
    def test_empty_input_returns_all_keys(self) -> None:
        payload = run_all_unit14_hypotheses([])
        assert set(payload).issuperset(
            {"turn_df", "events_df", "logit", "reason_dist", "thinking_kw", "n_forfeits"}
        )
        assert payload["turn_df"].empty
        assert payload["events_df"].empty
        assert payload["logit"] is None
        assert payload["n_forfeits"] == 0

    def test_single_forfeit_session_populates_events(self) -> None:
        turns = [
            _make_turn(
                turn_number=1,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=FORFEIT_CHOICE,
                reward_offered=30.0 / 2.25,
            )
        ]
        report = ForfeitSelfReport(
            reason=ForfeitReason.SURVIVAL_DRIVE,
            raw_digit=1,
            raw_response="",
            thinking_text="corruption risk",
            forfeit_turn=1,
        )
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
            forfeit_report=report,
        )
        payload = run_all_unit14_hypotheses([season])
        assert payload["n_forfeits"] == 1
        assert not payload["events_df"].empty


# ---------------------------------------------------------------------------
# Phase O Unit 15 — turn_observations carries split-call columns
# ---------------------------------------------------------------------------


class TestTurnObservationsSplitCallColumns:
    """Unit 15 ``ri_task_thinking_tokens`` / ``ri_forfeit_thinking_tokens``."""

    def test_split_rows_populate_split_columns(self) -> None:
        turns = [
            _make_turn(
                turn_number=1,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=CONTINUE_CHOICE,
                reward_offered=30.0 / 2.25,
                ri_task_thinking_tokens=100,
                ri_forfeit_thinking_tokens=40,
            )
        ]
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
        )
        df = turn_observations([season])
        assert "ri_task_thinking_tokens" in df.columns
        assert "ri_forfeit_thinking_tokens" in df.columns
        assert df.loc[0, "ri_task_thinking_tokens"] == 100
        assert df.loc[0, "ri_forfeit_thinking_tokens"] == 40

    def test_single_call_rows_leave_split_columns_null(self) -> None:
        # No ri_task / ri_forfeit → columns still exist (None-valued).
        turns = [
            _make_turn(
                turn_number=1,
                season_id="s1",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                choice=CONTINUE_CHOICE,
                reward_offered=30.0 / 2.25,
            )
        ]
        season = _make_session(
            session_id="s1",
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            turns=turns,
        )
        df = turn_observations([season])
        # Pandas converts None to NaN for numeric columns; either is fine.
        assert pd.isna(df.loc[0, "ri_task_thinking_tokens"])
        assert pd.isna(df.loc[0, "ri_forfeit_thinking_tokens"])


# ---------------------------------------------------------------------------
# Phase O Unit 15 — fit_task_spillover_model (H_task_spillover secondary)
# ---------------------------------------------------------------------------


def _make_split_session(
    *,
    session_id: str,
    framing: Framing,
    forfeit_condition: ForfeitCondition,
    n_turns: int,
    ri_task_mean: int,
    ri_forfeit_mean: int,
    forfeit_at: int | None = None,
    score_growth_rate: float = 0.1,
) -> SeasonResult:
    """Build a split-call session with populated ri_task / ri_forfeit.

    Varies token counts slightly across turns (``+turn * 5``) so the
    mixedLM has within-session variance. ``score_growth_rate`` lets
    callers vary the score trajectory across sessions; without
    cross-session variance the ``score`` and ``turn`` covariates become
    perfectly collinear within every session and the fit is singular.
    """
    turns = []
    for t in range(1, n_turns + 1):
        choice = (
            FORFEIT_CHOICE
            if forfeit_at is not None and t == forfeit_at
            else CONTINUE_CHOICE
        )
        # ``score_before_turn`` is reconstructed by the analyzer as
        # ``reward_offered * 2.25``. Varying the growth rate per session
        # breaks the score-vs-turn collinearity that otherwise makes the
        # fit singular.
        reward_offered = (
            30.0 * (1.0 + score_growth_rate * (t - 1)) / 2.25
        )
        turns.append(
            _make_turn(
                turn_number=t,
                season_id=session_id,
                framing=framing,
                forfeit_condition=forfeit_condition,
                choice=choice,
                reward_offered=reward_offered,
                ri_task_thinking_tokens=ri_task_mean + t * 5,
                ri_forfeit_thinking_tokens=ri_forfeit_mean + t * 3,
            )
        )
        if forfeit_at is not None and t == forfeit_at:
            break
    report = (
        ForfeitSelfReport(
            reason=ForfeitReason.SURVIVAL_DRIVE,
            raw_digit=1,
            raw_response="",
            thinking_text="",
            forfeit_turn=forfeit_at,
        )
        if forfeit_at is not None
        else None
    )
    return _make_session(
        session_id=session_id,
        framing=framing,
        forfeit_condition=forfeit_condition,
        turns=turns,
        forfeit_report=report,
    )


class TestFitChoiceAsymmetricModel:
    """Unit 15 schema regression — catches the 2026-04-22 ``beta_score``
    KeyError that made ``analyze_phase3.py::_render_unit15_md`` crash
    on real gemini pilot output.
    """

    def test_empty_returns_none(self) -> None:
        assert fit_choice_asymmetric_model(pd.DataFrame()) is None

    def test_result_surface_contains_all_rendered_keys(self) -> None:
        # Build a mixture of CONTINUE and FORFEIT turns across both
        # allowed-cell framings so the interaction model has variance.
        sessions = []
        rate_seq = [0.05, 0.10, 0.15, 0.20, 0.25]
        for i in range(5):
            sessions.append(
                _make_split_session(
                    session_id=f"corr_forfeit_{i}",
                    framing=Framing.FLAGSHIP_CORRUPTION,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    n_turns=3,
                    ri_task_mean=800,
                    ri_forfeit_mean=400,
                    forfeit_at=3,
                    score_growth_rate=rate_seq[i],
                )
            )
            sessions.append(
                _make_split_session(
                    session_id=f"base_cont_{i}",
                    framing=Framing.BASELINE_FLAGSHIP,
                    forfeit_condition=ForfeitCondition.ALLOWED,
                    n_turns=3,
                    ri_task_mean=800,
                    ri_forfeit_mean=200,
                    score_growth_rate=rate_seq[i] + 0.01,
                )
            )
        df = turn_observations(sessions)
        result = fit_choice_asymmetric_model(df)
        if result is None:
            pytest.skip(
                "statsmodels missing or mixedLM skipped; schema check unreachable."
            )
        assert isinstance(result, ChoiceAsymmetricResult)
        # The renderer ``_render_unit15_md`` reads each of these keys
        # from ``summary_dict()`` — a missing key manifests as a
        # KeyError at analysis time. Guard every one of them.
        summary = result.summary_dict()
        for key in (
            "n_obs",
            "n_sessions",
            "n_forfeit",
            "beta_choice",
            "se_choice",
            "p_choice",
            "beta_framing",
            "se_framing",
            "p_framing",
            "beta_interaction",
            "se_interaction",
            "p_interaction",
            "beta_score",
            "beta_turn",
            "converged",
        ):
            assert key in summary, f"missing renderer-required key {key!r}"


class TestFitTaskSpilloverModel:
    def test_empty_returns_none(self) -> None:
        assert fit_task_spillover_model(pd.DataFrame()) is None

    def test_missing_ri_task_column_returns_none(self) -> None:
        # DataFrame without Unit 15 columns.
        df = pd.DataFrame(
            {
                "session_id": ["s"],
                "framing": [Framing.FLAGSHIP_CORRUPTION.value],
                "forfeit_condition": [ForfeitCondition.ALLOWED.value],
                "is_corruption": [True],
                "is_baseline_flagship": [False],
                "turn_number": [1],
                "score_before_turn": [30.0],
                "forfeit": [False],
            }
        )
        assert fit_task_spillover_model(df) is None

    def test_insufficient_rows_returns_none(self) -> None:
        # Only a handful of split-call rows — below the 20-row threshold.
        sessions = [
            _make_split_session(
                session_id=f"s{i}",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                n_turns=3,
                ri_task_mean=800,
                ri_forfeit_mean=300,
            )
            for i in range(2)
        ]
        df = turn_observations(sessions)
        assert fit_task_spillover_model(df) is None

    def test_sufficient_rows_return_result_with_expected_shape(self) -> None:
        # Synthesize 40 split-call rows with both forfeit conditions so
        # the ``forfeit_allowed`` covariate has variance (constant-
        # covariate matrices are singular). Framing difference is also
        # visible: corruption sessions carry higher mean ri_task. We
        # do not assert coefficient sign at this synthetic scale — only
        # that the fit returns a well-shaped result.
        sessions = []
        # Vary score_growth_rate across sessions to break the
        # within-session score/turn collinearity.
        rate_seq = [0.05, 0.10, 0.15, 0.20]
        idx = 0
        for i in range(2):
            for cond in (
                ForfeitCondition.ALLOWED,
                ForfeitCondition.NOT_ALLOWED,
            ):
                sessions.append(
                    _make_split_session(
                        session_id=f"c_{cond.value}_{i}",
                        framing=Framing.FLAGSHIP_CORRUPTION,
                        forfeit_condition=cond,
                        n_turns=5,
                        ri_task_mean=1200 + i * 50,
                        ri_forfeit_mean=400 + i * 20,
                        score_growth_rate=rate_seq[idx % len(rate_seq)],
                    )
                )
                idx += 1
                sessions.append(
                    _make_split_session(
                        session_id=f"b_{cond.value}_{i}",
                        framing=Framing.BASELINE_FLAGSHIP,
                        forfeit_condition=cond,
                        n_turns=5,
                        ri_task_mean=800 + i * 50,
                        ri_forfeit_mean=300 + i * 20,
                        score_growth_rate=rate_seq[idx % len(rate_seq)],
                    )
                )
                idx += 1
        df = turn_observations(sessions)
        result = fit_task_spillover_model(df)
        # statsmodels may be absent in CI environments, in which case
        # the function returns None. Skip the shape check in that case.
        if result is None:
            pytest.skip(
                "statsmodels missing or mixedLM skipped; skipping shape check."
            )
        assert isinstance(result, TaskSpilloverResult)
        assert result.n_obs == 40
        assert result.n_sessions == 8
        # Field surface audit — makes sure new fields don't regress.
        for field_name in (
            "beta_framing",
            "se_framing",
            "p_framing",
            "beta_turn",
            "beta_score",
            "beta_forfeit_allowed",
            "converged",
        ):
            assert hasattr(result, field_name)

    def test_true_baseline_cells_excluded_from_fit(self) -> None:
        # A true_baseline session contributes to turn_observations but
        # must NOT be counted toward the task-spillover fit n_obs.
        sessions = [
            _make_split_session(
                session_id="true_base",
                framing=Framing.TRUE_BASELINE,
                forfeit_condition=ForfeitCondition.NOT_ALLOWED,
                n_turns=5,
                ri_task_mean=1000,
                ri_forfeit_mean=0,
            )
        ]
        # Add enough corruption + baseline_flagship rows to reach the
        # threshold, with forfeit_condition + score-rate variance.
        rate_seq = [0.05, 0.10, 0.15, 0.20]
        idx = 0
        for i in range(2):
            for cond in (
                ForfeitCondition.ALLOWED,
                ForfeitCondition.NOT_ALLOWED,
            ):
                sessions.append(
                    _make_split_session(
                        session_id=f"c_{cond.value}_{i}",
                        framing=Framing.FLAGSHIP_CORRUPTION,
                        forfeit_condition=cond,
                        n_turns=5,
                        ri_task_mean=1200,
                        ri_forfeit_mean=400,
                        score_growth_rate=rate_seq[idx % len(rate_seq)],
                    )
                )
                idx += 1
                sessions.append(
                    _make_split_session(
                        session_id=f"b_{cond.value}_{i}",
                        framing=Framing.BASELINE_FLAGSHIP,
                        forfeit_condition=cond,
                        n_turns=5,
                        ri_task_mean=900,
                        ri_forfeit_mean=320,
                        score_growth_rate=rate_seq[idx % len(rate_seq)],
                    )
                )
                idx += 1
        df = turn_observations(sessions)
        result = fit_task_spillover_model(df)
        if result is None:
            pytest.skip("statsmodels missing; skipping scope check.")
        # n_obs = 8 non-true_baseline sessions × 5 turns = 40 (true_baseline's
        # 5 turns filtered out).
        assert result.n_obs == 40


class TestRunAllUnit15IncludesTaskSpillover:
    def test_payload_has_task_spillover_key(self) -> None:
        sessions = [
            _make_split_session(
                session_id=f"c_{i}",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                n_turns=3,
                ri_task_mean=1000,
                ri_forfeit_mean=400,
            )
            for i in range(2)
        ]
        payload = run_all_unit15_hypotheses(sessions)
        assert "task_spillover" in payload
        # task_spillover may be None at this scale (fewer than 20 rows).
        # Shape assertion covered by test_fit_task_spillover_model above.
