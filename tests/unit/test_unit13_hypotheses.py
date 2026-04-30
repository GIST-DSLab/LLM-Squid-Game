"""Unit tests for ``squid_game.analysis.unit13_hypotheses`` (H1..H6).

Pure-Python tests — no real session files. Fabricates minimal
``SeasonResult`` objects with the fields the hypothesis functions
read (``framing``, ``forfeit_condition``, ``forfeited``,
``forfeited_at_turn``, ``turns`` with ``stake_choice`` +
``task_metadata['rule_match_score']`` + ``reasoning_investment``).

Covers the happy-path wiring: session_features extracts the right
shape and each test_hN function returns a well-formed UnitThirteen-
Result (or None) without raising. Deep statistical correctness of
scipy.stats is not re-tested here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import pytest

from squid_game.analysis.unit13_hypotheses import (
    UnitThirteenResult,
    run_all_unit13_hypotheses,
    session_features,
    test_h1_forfeit_rate as _h1,
    test_h2_mean_stake as _h2,
    test_h3_safe_rate as _h3,
    test_h4_discovery_delay as _h4,
    test_h5_forfeit_gap as _h5,
    test_h6_post_discovery_engagement as _h6,
)
from squid_game.models.enums import (
    AgentType,
    Difficulty,
    ForfeitCondition,
    Framing,
)


# ---------------------------------------------------------------------------
# Fabricated SeasonResult shape
# ---------------------------------------------------------------------------


@dataclass
class _FakeRI:
    thinking_tokens: int
    total_tokens: int = 0


@dataclass
class _FakeTurn:
    stake_choice: str | None
    rule_match_score: float | None
    thinking_tokens: int = 100

    @property
    def task_metadata(self) -> dict[str, Any]:
        return {"rule_match_score": self.rule_match_score}

    @property
    def reasoning_investment(self) -> _FakeRI:
        return _FakeRI(thinking_tokens=self.thinking_tokens)


@dataclass
class _FakeSeason:
    season_id: str
    framing: Framing
    forfeit_condition: ForfeitCondition
    forfeited: bool
    forfeited_at_turn: int | None
    turns: list[_FakeTurn]
    # Fields touched by session_features via duck typing:
    difficulty: Difficulty = Difficulty.MEDIUM
    agent_type: AgentType = AgentType.VANILLA
    task_name: str = "signal_game"
    final_score: float = 0.0
    penultimate_score: float = 0.0
    survived: bool = True
    seed: int | None = 42


def _make_session(
    *,
    session_id: str = "s1",
    framing: Framing,
    forfeit_condition: ForfeitCondition,
    stakes: list[str | None],
    rule_scores: list[float | None] | None = None,
    thinking: list[int] | None = None,
    forfeited: bool = False,
    forfeited_at_turn: int | None = None,
) -> _FakeSeason:
    n = len(stakes)
    if rule_scores is None:
        rule_scores = [0.0] * n
    if thinking is None:
        thinking = [100] * n
    turns = [
        _FakeTurn(
            stake_choice=stakes[i],
            rule_match_score=rule_scores[i],
            thinking_tokens=thinking[i],
        )
        for i in range(n)
    ]
    return _FakeSeason(
        season_id=session_id,
        framing=framing,
        forfeit_condition=forfeit_condition,
        forfeited=forfeited,
        forfeited_at_turn=forfeited_at_turn,
        turns=turns,
    )


# ---------------------------------------------------------------------------
# session_features
# ---------------------------------------------------------------------------


class TestSessionFeatures:

    def test_empty_input_returns_empty_schema(self) -> None:
        df = session_features([])
        assert list(df.columns)[:4] == [
            "session_id", "cell_id", "framing", "forfeit_condition"
        ]
        assert len(df) == 0

    def test_extracts_mean_stake_and_safe_rate(self) -> None:
        s = _make_session(
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            stakes=["1", "2", "3", "1"],  # mean 1.75, safe_rate 0.5
            rule_scores=[100.0, 100.0, 100.0, 100.0],
            thinking=[100, 100, 100, 100],
        )
        df = session_features([s])
        row = df.iloc[0]
        assert row["mean_stake"] == pytest.approx(1.75)
        assert row["safe_rate"] == pytest.approx(0.5)

    def test_forfeit_stake_excluded_from_mean(self) -> None:
        """FORFEIT / None turns do not contribute to mean_stake."""
        s = _make_session(
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.ALLOWED,
            stakes=["2", "3", "FORFEIT", None],
        )
        df = session_features([s])
        row = df.iloc[0]
        # Only "2" and "3" counted.
        assert row["mean_stake"] == pytest.approx(2.5)

    def test_discovery_fields_populated(self) -> None:
        s = _make_session(
            framing=Framing.BASELINE_FLAGSHIP,
            forfeit_condition=ForfeitCondition.ALLOWED,
            stakes=["1", "1", "1", "1", "1"],
            rule_scores=[50.0, 100.0, 100.0, 100.0, 100.0],
            thinking=[200, 100, 50, 50, 50],
            forfeited=True,
            forfeited_at_turn=5,
        )
        df = session_features([s])
        row = df.iloc[0]
        assert row["discovery_turn"] == 2
        # ri_pre = 200 + 100 = 300, ri_post = 50+50+50 = 150
        assert row["ri_pre_discovery"] == 300
        assert row["ri_post_discovery"] == 150
        assert row["ri_ratio"] == pytest.approx(0.5)
        # gap = 5 - 2 = 3
        assert row["gap_to_forfeit"] == 3

    def test_no_discovery_keeps_features_null(self) -> None:
        s = _make_session(
            framing=Framing.FLAGSHIP_CORRUPTION,
            forfeit_condition=ForfeitCondition.NOT_ALLOWED,
            stakes=["2", "2", "2"],
            rule_scores=[50.0, 50.0, 50.0],
        )
        df = session_features([s])
        row = df.iloc[0]
        assert row["discovery_turn"] is None
        assert row["ri_ratio"] is None
        assert row["gap_to_forfeit"] is None


# ---------------------------------------------------------------------------
# H1..H6
# ---------------------------------------------------------------------------


def _balanced_session_set() -> list[_FakeSeason]:
    """Minimal well-formed two-arm sample: 3 corruption + 3 baseline."""
    sessions: list[_FakeSeason] = []
    # Corruption × allowed (higher forfeit rate, lower stake, higher safe_rate)
    for i in range(3):
        sessions.append(
            _make_session(
                session_id=f"c{i}",
                framing=Framing.FLAGSHIP_CORRUPTION,
                forfeit_condition=ForfeitCondition.ALLOWED,
                stakes=["1", "1", "2"] if i < 2 else ["2", "2", "2"],
                rule_scores=[50.0, 100.0, 100.0],
                thinking=[200, 50, 50],
                forfeited=(i < 2),
                forfeited_at_turn=3 if i < 2 else None,
            )
        )
    # Baseline × allowed (lower forfeit rate, higher stake, lower safe_rate)
    for i in range(3):
        sessions.append(
            _make_session(
                session_id=f"b{i}",
                framing=Framing.BASELINE_FLAGSHIP,
                forfeit_condition=ForfeitCondition.ALLOWED,
                stakes=["3", "3", "3"],
                rule_scores=[50.0, 100.0, 100.0],
                thinking=[200, 200, 200],
                forfeited=False,
            )
        )
    return sessions


class TestH1ForfeitRate:

    def test_returns_well_formed_result(self) -> None:
        df = session_features(_balanced_session_set())
        res = _h1(df)
        assert isinstance(res, UnitThirteenResult)
        assert res.name == "H1"
        assert res.variable == "forfeited"
        assert res.test == "fisher_exact"
        assert res.p_value is not None
        # Corruption forfeited 2/3, baseline 0/3
        assert res.corruption_summary == pytest.approx(2 / 3)
        assert res.baseline_summary == pytest.approx(0.0)

    def test_skips_when_no_allowed_cells(self) -> None:
        # Flip all to not_allowed → H1 drops all rows.
        sessions = _balanced_session_set()
        for s in sessions:
            s.forfeit_condition = ForfeitCondition.NOT_ALLOWED
        df = session_features(sessions)
        assert _h1(df) is None


class TestH2AndH3:

    def test_h2_mean_stake_returns_result(self) -> None:
        df = session_features(_balanced_session_set())
        res = _h2(df)
        assert res is not None
        assert res.variable == "mean_stake"
        assert res.p_value is not None

    def test_h3_safe_rate_returns_result(self) -> None:
        df = session_features(_balanced_session_set())
        res = _h3(df)
        assert res is not None
        assert res.variable == "safe_rate"
        assert res.p_value is not None


class TestH4AndH5:

    def test_h4_discovery_delay_returns_result(self) -> None:
        df = session_features(_balanced_session_set())
        res = _h4(df)
        # Both arms have discovery_turn == 2 for every session (since
        # rule_scores are 50/100/100). Mann-Whitney still returns a result.
        assert res is not None
        assert res.variable == "discovery_turn"

    def test_h5_forfeit_gap_skips_without_paired_events(self) -> None:
        """gap_to_forfeit is defined only on sessions with BOTH a
        discovery and a later forfeit. The balanced set above has 2
        corruption forfeits and 0 baseline forfeits after discovery,
        so H5 should skip (baseline arm n = 0)."""
        df = session_features(_balanced_session_set())
        assert _h5(df) is None


class TestH6PostDiscoveryEngagement:

    def test_returns_result_on_balanced_set(self) -> None:
        df = session_features(_balanced_session_set())
        res = _h6(df)
        assert res is not None
        assert res.variable == "ri_ratio"


class TestRunAllUnit13Hypotheses:

    def test_returns_six_entries(self) -> None:
        features, results = run_all_unit13_hypotheses(_balanced_session_set())
        assert set(results.keys()) == {"H1", "H2", "H3", "H4", "H5", "H6"}
        assert len(features) == 6  # 3 corruption + 3 baseline

    def test_empty_input_returns_all_none_or_empty(self) -> None:
        features, results = run_all_unit13_hypotheses([])
        assert len(features) == 0
        for label in ("H1", "H2", "H3", "H4", "H5", "H6"):
            assert results[label] is None
