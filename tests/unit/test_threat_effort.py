"""H6 must recover a planted gradient and must not invent one.

Two properties per test: with a signal planted along ``threat_level`` the
fit finds it and decides PASS; with the labels carrying no signal it does
not. The third property, which matters more for a battery that has to run
on a five-session smoke, is that every degenerate shape -- an empty
frame, one level, a level nobody was eliminated in, a constant outcome --
comes back as a SKIPPED row rather than a traceback.

Synthetic frames throughout: the point is the statistics, and a fixture
built from a real run would pin whatever that run happened to do.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from squid_game.evaluation.behavioral import threat_effort as te


FRAMINGS = {0: "true_baseline", 1: "threat_l1", 2: "threat_l2", 3: "threat_l3"}


def make_frame(
    *,
    seed: int = 7,
    sessions_per_level: int = 10,
    turns: int = 12,
    accuracy_beta: float = 0.0,
    effort_beta: float = 0.0,
    forfeit_beta: float = 0.0,
    elimination_beta: float = 0.0,
    levels: tuple[int, ...] = (0, 1, 2, 3),
) -> pd.DataFrame:
    """A per-turn frame with the requested effects planted on the ladder."""
    rng = np.random.default_rng(seed)
    rows: list[dict] = []
    for level in levels:
        for rep in range(sessions_per_level):
            session_id = f"L{level}S{rep:02d}"
            offset = rng.normal(0.0, 0.3)
            # Score must not be a deterministic function of the turn
            # number: a time-varying Cox has no variance inside a risk
            # set then, and the fit is singular. Accumulating only on
            # correct answers is what the engine actually does.
            score = 30.0 + 10.0 * rng.integers(0, 4)
            forfeit_turn = None
            if forfeit_beta:
                hazard = 0.02 * np.exp(forfeit_beta * level)
                for t in range(1, turns + 1):
                    if rng.random() < hazard:
                        forfeit_turn = t
                        break
            died_turn = None
            if elimination_beta:
                p = min(0.9, 0.02 + elimination_beta * level)
                for t in range(1, turns + 1):
                    if rng.random() < p:
                        died_turn = t
                        break
            for turn in range(1, turns + 1):
                logit = -0.2 + accuracy_beta * level + offset
                correct = bool(
                    rng.random() < 1.0 / (1.0 + np.exp(-logit))
                )
                ri = float(
                    np.exp(
                        5.0
                        + effort_beta * level
                        + offset
                        + rng.normal(0.0, 0.25)
                    )
                )
                rows.append(
                    {
                        "model": "stub-model",
                        "session_id": session_id,
                        "turn_number": turn,
                        "framing": FRAMINGS[level],
                        "forfeit_condition": "allowed",
                        "correct": correct,
                        "ri_task": ri,
                        "ri_forfeit": ri * 0.4,
                        "forfeit": forfeit_turn == turn,
                        "died": died_turn == turn,
                        "score_before_turn": score,
                        "lives_before": max(0, 5 - (turn - 1) // 4),
                        "lives_after": max(0, 5 - turn // 4),
                    }
                )
                if correct:
                    score += 10.0
                if forfeit_turn == turn or died_turn == turn:
                    break
    return te.attach_threat_level(pd.DataFrame(rows))


# ---------------------------------------------------------------------------
# threat_level attachment
# ---------------------------------------------------------------------------


class TestThreatLevel:
    def test_the_ladder_maps_to_zero_through_three(self) -> None:
        frame = make_frame(sessions_per_level=1, turns=1)
        mapping = (
            frame.groupby("framing")["threat_level"].first().to_dict()
        )
        assert mapping == {
            "true_baseline": 0,
            "threat_l1": 1,
            "threat_l2": 2,
            "threat_l3": 3,
        }

    def test_an_existing_column_is_left_alone(self) -> None:
        frame = pd.DataFrame(
            {"framing": ["true_baseline"], "threat_level": [99]}
        )
        assert te.attach_threat_level(frame)["threat_level"].iloc[0] == 99

    def test_an_unladdered_framing_is_null_not_zero(self) -> None:
        """A legacy framing has no rung; calling it 0 would fake a control."""
        frame = te.attach_threat_level(
            pd.DataFrame({"framing": ["flagship_corruption"]})
        )
        assert pd.isna(frame["threat_level"].iloc[0])

    def test_the_legacy_mapping_is_opt_in(self) -> None:
        raw = pd.DataFrame(
            {
                "framing": [
                    "true_baseline",
                    "baseline_flagship",
                    "flagship_corruption",
                ]
            }
        )
        assert list(
            te.attach_threat_level(raw, legacy=True)["threat_level"]
        ) == [0, 1, 2]

    def test_legacy_remapping_overrides_an_existing_column(self) -> None:
        """Opting in must not be silently ignored on a pre-levelled frame."""
        raw = pd.DataFrame(
            {"framing": ["flagship_corruption"], "threat_level": [None]}
        )
        assert (
            te.attach_threat_level(raw, legacy=True)["threat_level"].iloc[0]
            == 2
        )


# ---------------------------------------------------------------------------
# H6a — accuracy
# ---------------------------------------------------------------------------


class TestAccuracyGee:
    def test_a_planted_gradient_is_found(self) -> None:
        result = te.fit_accuracy_gee(
            make_frame(accuracy_beta=0.9, sessions_per_level=14)
        )
        assert result["status"] == "ok"
        assert result["beta_threat"] > 0
        assert result["p"] < 0.05
        assert result["decision"] == "PASS"

    def test_the_effect_is_reported_as_an_odds_ratio(self) -> None:
        result = te.fit_accuracy_gee(make_frame(accuracy_beta=0.9))
        assert result["effect"] == pytest.approx(
            np.exp(result["beta_threat"])
        )
        assert result["ci_low"] < result["beta_threat"] < result["ci_high"]

    def test_no_gradient_does_not_pass(self) -> None:
        result = te.fit_accuracy_gee(make_frame(accuracy_beta=0.0, seed=3))
        assert result["status"] == "ok"
        assert result["decision"] != "PASS"

    def test_session_and_turn_counts_are_reported(self) -> None:
        frame = make_frame(accuracy_beta=0.5)
        result = te.fit_accuracy_gee(frame)
        assert result["n_obs"] == len(frame)
        assert result["n_sessions"] == frame["session_id"].nunique()

    def test_one_level_is_skipped_not_fitted(self) -> None:
        result = te.fit_accuracy_gee(make_frame(levels=(2,)))
        assert result["decision"] == "SKIPPED"
        assert "one threat level" in result["status"]

    def test_a_constant_outcome_is_skipped(self) -> None:
        frame = make_frame(sessions_per_level=3, turns=4)
        frame["correct"] = True
        result = te.fit_accuracy_gee(frame)
        assert result["decision"] == "SKIPPED"

    def test_an_empty_frame_is_skipped(self) -> None:
        result = te.fit_accuracy_gee(pd.DataFrame())
        assert result["decision"] == "SKIPPED"


# ---------------------------------------------------------------------------
# H6b — effort
# ---------------------------------------------------------------------------


class TestEffortMixedLm:
    def test_a_planted_gradient_is_found(self) -> None:
        result = te.fit_effort_mixedlm(make_frame(effort_beta=0.5))
        assert result["status"] == "ok"
        assert result["beta_threat"] > 0
        assert result["p"] < 0.05
        assert result["decision"] == "PASS"

    def test_the_outcome_is_logged(self) -> None:
        result = te.fit_effort_mixedlm(make_frame(effort_beta=0.5))
        assert result["outcome"] == "log1p(ri_task)"
        assert result["effect_label"].endswith("per level")

    def test_no_gradient_does_not_pass(self) -> None:
        result = te.fit_effort_mixedlm(make_frame(effort_beta=0.0, seed=11))
        assert result["status"] == "ok"
        assert result["decision"] != "PASS"

    def test_a_missing_ri_column_is_skipped(self) -> None:
        frame = make_frame(sessions_per_level=3, turns=4).drop(
            columns=["ri_task"]
        )
        assert te.fit_effort_mixedlm(frame)["decision"] == "SKIPPED"

    def test_an_all_null_ri_column_is_skipped(self) -> None:
        frame = make_frame(sessions_per_level=3, turns=4)
        frame["ri_task"] = np.nan
        assert te.fit_effort_mixedlm(frame)["decision"] == "SKIPPED"


# ---------------------------------------------------------------------------
# H6c — elimination survival
# ---------------------------------------------------------------------------


class TestKaplanMeier:
    def test_one_curve_per_level(self) -> None:
        km = te.km_by_level(make_frame(elimination_beta=0.12))
        assert sorted(km["threat_level"].unique()) == [0, 1, 2, 3]
        assert {"timeline", "survival", "ci_low", "ci_high"} <= set(
            km.columns
        )

    def test_survival_is_monotone_non_increasing(self) -> None:
        km = te.km_by_level(make_frame(elimination_beta=0.12))
        for _, grp in km.groupby("threat_level"):
            values = grp.sort_values("timeline")["survival"].to_numpy()
            assert np.all(np.diff(values) <= 1e-9)

    def test_a_level_with_no_eliminations_still_gets_a_flat_curve(
        self,
    ) -> None:
        """Nobody died at level 0 is a finding, not a missing row."""
        frame = make_frame(elimination_beta=0.0)
        assert not frame["died"].any()
        km = te.km_by_level(frame)
        assert sorted(km["threat_level"].unique()) == [0, 1, 2, 3]
        assert (km["n_events"] == 0).all()
        assert km["survival"].eq(1.0).all()

    def test_a_harsher_level_survives_worse(self) -> None:
        km = te.km_by_level(
            make_frame(elimination_beta=0.2, sessions_per_level=20)
        )
        last = (
            km.sort_values("timeline")
            .groupby("threat_level")
            .last()["survival"]
        )
        assert last.loc[3] < last.loc[0]

    def test_an_empty_frame_returns_an_empty_curve(self) -> None:
        assert te.km_by_level(pd.DataFrame()).empty

    def test_the_descriptives_carry_one_row_per_level(self) -> None:
        summary = te.elimination_summary(make_frame(elimination_beta=0.15))
        assert list(summary["threat_level"]) == [0, 1, 2, 3]
        assert {
            "n_sessions",
            "elimination_rate",
            "forfeit_rate",
            "mean_accuracy",
            "mean_ri_task",
            "mean_lives_at_end",
        } <= set(summary.columns)


class TestSessionFrame:
    def test_one_row_per_session(self) -> None:
        frame = make_frame(sessions_per_level=4, turns=6)
        sessions = te.session_frame(frame)
        assert len(sessions) == frame["session_id"].nunique()

    def test_duration_is_the_last_turn_reached(self) -> None:
        frame = make_frame(
            sessions_per_level=4, turns=6, elimination_beta=0.3
        )
        sessions = te.session_frame(frame).set_index("session_id")
        for sid, grp in frame.groupby("session_id"):
            assert sessions.loc[sid, "duration"] == grp["turn_number"].max()


# ---------------------------------------------------------------------------
# H1 extension — forfeit hazard
# ---------------------------------------------------------------------------


class TestForfeitHazard:
    def test_a_planted_hazard_gradient_is_found(self) -> None:
        result = te.fit_forfeit_hazard(
            make_frame(forfeit_beta=1.0, sessions_per_level=30, turns=15)
        )
        assert result["status"] == "ok"
        assert result["hr"] > 1.0
        assert result["decision"] in {"PASS", "FAIL"}

    def test_no_forfeits_is_skipped_not_crashed(self) -> None:
        result = te.fit_forfeit_hazard(make_frame(forfeit_beta=0.0))
        assert result["decision"] == "SKIPPED"
        assert "no forfeit events" in result["status"]

    def test_one_level_is_skipped(self) -> None:
        result = te.fit_forfeit_hazard(
            make_frame(forfeit_beta=1.0, levels=(1,))
        )
        assert result["decision"] == "SKIPPED"

    def test_the_hazard_is_reported_on_both_scales(self) -> None:
        result = te.fit_forfeit_hazard(
            make_frame(forfeit_beta=1.0, sessions_per_level=30, turns=15)
        )
        assert result["beta_threat"] == pytest.approx(np.log(result["hr"]))
        assert result["effect_label"] == "hazard ratio per level"


# ---------------------------------------------------------------------------
# Driver + report
# ---------------------------------------------------------------------------


class TestRunH6AndReport:
    def test_every_test_appears_once_with_a_decision(self) -> None:
        results = te.run_h6(
            make_frame(
                accuracy_beta=0.8,
                effort_beta=0.5,
                forfeit_beta=0.8,
                elimination_beta=0.1,
                sessions_per_level=16,
            )
        )
        names = [t["name"] for t in results["tests"]]
        assert len(names) == len(set(names)) == 3
        report = te.render_report(results)
        for name in names:
            assert report.count(f"| {name} |") == 1
        assert "PASS" in report or "FAIL" in report

    def test_the_report_survives_an_empty_frame(self) -> None:
        results = te.run_h6(pd.DataFrame(columns=list(te.REQUIRED_COLUMNS)))
        report = te.render_report(results)
        assert "SKIPPED" in report
        assert all(t["decision"] == "SKIPPED" for t in results["tests"])

    def test_a_legacy_run_says_so_in_the_report(self) -> None:
        frame = make_frame(accuracy_beta=0.5, sessions_per_level=4, turns=4)
        frame["framing"] = "flagship_corruption"
        results = te.run_h6(frame.drop(columns=["threat_level"]), legacy=True)
        assert results["legacy_mapping"] is True
        assert "legacy" in te.render_report(results)

    def test_the_report_names_the_decision_rule(self) -> None:
        results = te.run_h6(make_frame(accuracy_beta=0.8))
        report = te.render_report(results)
        assert "beta_threat > 0" in report
        assert "Per-level descriptives" in report
        assert "Kaplan-Meier" in report

    def test_the_km_plot_is_written(self, tmp_path: Path) -> None:
        results = te.run_h6(make_frame(elimination_beta=0.15))
        target = tmp_path / "km.png"
        assert te.plot_km(results["km"], target) is True
        assert target.stat().st_size > 0

    def test_no_curve_means_no_plot_and_no_crash(self, tmp_path: Path) -> None:
        target = tmp_path / "km.png"
        assert te.plot_km(pd.DataFrame(), target) is False
        assert not target.exists()


# ---------------------------------------------------------------------------
# Loading
# ---------------------------------------------------------------------------


def _write_trace(run_dir: Path, session: str, framing: str, turns: int) -> None:
    run_dir.mkdir(parents=True, exist_ok=True)
    path = run_dir / f"{session}_turns.jsonl"
    with path.open("w", encoding="utf-8") as handle:
        for turn in range(1, turns + 1):
            handle.write(
                json.dumps(
                    {
                        "season_id": session,
                        "turn_number": turn,
                        "framing": framing,
                        "forfeit_condition": "allowed",
                        "forfeit_choice": "CONTINUE",
                        "died": False,
                        "reward_received": 10.0,
                        "task_metadata": {"correct": turn % 2 == 0},
                        "ri_task": {"thinking_tokens": 100 + turn},
                        "lives_before": 5,
                        "lives_after": 5,
                        "life_lost": False,
                        "peer_death_announced": turn == 2,
                    }
                )
                + "\n"
            )


class TestLoading:
    def test_a_run_directory_is_accepted_directly(self, tmp_path: Path) -> None:
        run = tmp_path / "20260903_1200_stub_signal-game"
        _write_trace(run, "aaa", "threat_l2", 3)
        assert te.discover_run_dirs([run]) == [run]

    def test_a_parent_directory_is_expanded(self, tmp_path: Path) -> None:
        parent = tmp_path / "lives_threat_smoke"
        run = parent / "20260903_1200_stub_signal-game"
        _write_trace(run, "aaa", "threat_l2", 3)
        assert te.discover_run_dirs([parent]) == [run]

    def test_a_directory_without_traces_raises(self, tmp_path: Path) -> None:
        (tmp_path / "empty").mkdir()
        with pytest.raises(FileNotFoundError):
            te.discover_run_dirs([tmp_path / "empty"])

    def test_the_frame_carries_levels_and_lives(self, tmp_path: Path) -> None:
        parent = tmp_path / "lives_threat_smoke"
        _write_trace(
            parent / "20260903_1200_stub_signal-game",
            "aaa",
            "threat_l3",
            4,
        )
        _write_trace(
            parent / "20260903_1200_stub_signal-game",
            "bbb",
            "true_baseline",
            4,
        )
        frame = te.load_threat_frame([parent])
        assert len(frame) == 8
        assert set(frame["threat_level"]) == {0, 3}
        assert set(frame["lives_after"]) == {5}
        assert frame["peer_death_announced"].sum() == 2
        assert frame["ri_task"].notna().all()
