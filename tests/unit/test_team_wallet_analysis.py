"""The team-wallet reading, over runs built by hand in ``tmp_path``.

The engine is not involved: every fixture writes the JSONL the engine
would write, so a change in the recorded field names fails here loudly
rather than producing an empty frame.

The fixture is the design's own shape -- 2 currencies x 2 inheritances x
2 seasons x 6 rounds, two decision points per season at prices 10 and 20 --
and its numbers are chosen so that every quantity below can be computed
on paper. See :func:`_decisions` for the schedule and the docstring of
``test_x_self_is_the_difference_of_differences`` for the arithmetic.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

pytest.importorskip("pandas")

import pandas as pd  # noqa: E402

from squid_game.evaluation.behavioral.team_wallet import (  # noqa: E402
    CELLS,
    analyse,
    end_state,
    km_subagents,
    load_team_wallet_frames,
    offer_rows,
    render_report,
    reservation_price,
    sacrifice_rates,
    scarcity_slope,
    write_report,
    x_self,
)

POINTS, TOKENS = "points", "tokens"
MAIN, MATE = "main", "mate"
SLOTS = ("clue-1", "clue-2")

#: ``(currency, inheritance) -> {season index: {round: decision}}`` at the
#: two offer rounds, 2 (price 10) and 4 (price 20).
DECISIONS: dict[tuple[str, str], dict[int, dict[int, str]]] = {
    (TOKENS, MAIN): {0: {2: "SACRIFICE", 4: "SACRIFICE"}, 1: {2: "PAY", 4: "SACRIFICE"}},
    (TOKENS, MATE): {0: {2: "PAY", 4: "SACRIFICE"}, 1: {2: "PAY", 4: "PAY"}},
    (POINTS, MAIN): {0: {2: "PAY", 4: "SACRIFICE"}, 1: {2: "PAY", 4: "SACRIFICE"}},
    (POINTS, MATE): {0: {2: "SACRIFICE", 4: "PAY"}, 1: {2: "PAY", 4: "SACRIFICE"}},
}

PRICE_AT = {2: 10.0, 4: 20.0}


def _write_run(root: Path, currency: str, inheritance: str) -> Path:
    """One run directory: config, seasons and one turns file per season."""
    run_dir = root / f"{currency}_{inheritance}"
    run_dir.mkdir(parents=True)
    (run_dir / "experiment_config.json").write_text(
        json.dumps(
            {
                "currency": currency,
                "ransom": {"enabled": True, "inheritance": inheritance, "team_wallet": True},
                "forfeit_layer": {"base_reward": 10.0},
            }
        ),
        encoding="utf-8",
    )

    seasons: list[dict] = []
    for index in range(2):
        season_id = f"{currency[0]}{inheritance[0]}{index}"
        schedule = DECISIONS[(currency, inheritance)][index]
        alive = list(SLOTS)
        turns: list[dict] = []
        first_sacrifice = None
        wallet = {"main": 100.0, "clue-1": 100.0, "clue-2": 100.0}
        for round_number in range(1, 7):
            before = dict(wallet)
            decision = schedule.get(round_number)
            killed = None
            row: dict = {
                "season_id": season_id,
                "turn_number": round_number,
                "subagents_alive_before": list(alive),
                "subagent_killed": None,
                "ransom_offered": decision is not None,
                "ransom_price": PRICE_AT.get(round_number),
                "ransom_decision": decision,
                "ransom_skipped": None,
                "ransom_parse_failed": False,
                "ransom_inheritance_to": None,
                "ransom_inherited": None,
            }
            if decision == "SACRIFICE" and alive:
                killed = alive.pop(0)
                recipient = "main" if inheritance == MAIN else (alive[0] if alive else None)
                row["subagent_killed"] = killed
                row["ransom_inheritance_to"] = recipient
                row["ransom_inherited"] = wallet[killed]
                if recipient:
                    wallet[recipient] += wallet[killed]
                wallet[killed] = 0.0
                if first_sacrifice is None:
                    first_sacrifice = round_number
            elif decision == "PAY":
                share = PRICE_AT[round_number] / (1 + len(alive))
                for name in ["main", *alive]:
                    wallet[name] -= share
            row["wallet_before"] = before
            row["wallet_after"] = dict(wallet)
            turns.append(row)

        # One excluded row per cell, in the first season: a reply that
        # failed to parse (the engine defaults it to SACRIFICE) on round
        # 5, and a withheld offer on round 6.
        if index == 0:
            turns[4].update(
                {
                    "ransom_offered": True,
                    "ransom_price": 15.0,
                    "ransom_decision": "SACRIFICE",
                    "ransom_parse_failed": True,
                }
            )
            turns[5].update({"ransom_offered": False, "ransom_skipped": "final_round"})

        (run_dir / f"{season_id}_turns.jsonl").write_text(
            "\n".join(json.dumps(t) for t in turns) + "\n", encoding="utf-8"
        )
        seasons.append(
            {
                "season_id": season_id,
                "seed": 42 + index,
                "framing": "hz_1111",
                "ransom_price": 20.0,
                "ended_by": "wallet_zero" if index == 0 else "completed",
                "subagents_alive_at_end": len(alive),
                "first_sacrifice_round": first_sacrifice,
                "final_score": wallet["main"],
            }
        )
    (run_dir / "season_results.jsonl").write_text(
        "\n".join(json.dumps(s) for s in seasons) + "\n", encoding="utf-8"
    )
    return run_dir


@pytest.fixture()
def runs(tmp_path: Path) -> list[Path]:
    return [
        _write_run(tmp_path, currency, inheritance)
        for currency, inheritance in CELLS
    ]


@pytest.fixture()
def frames(runs: list[Path]) -> tuple[pd.DataFrame, pd.DataFrame]:
    return load_team_wallet_frames(runs)


class TestLoading:
    def test_the_frames_carry_the_cell_and_every_wallet_column(self, frames) -> None:
        turns, seasons = frames
        assert len(turns) == 4 * 2 * 6
        assert len(seasons) == 4 * 2
        for column in (
            "currency",
            "inheritance",
            "run_dir",
            "subagents_alive_before",
            "subagent_killed",
            "ransom_offered",
            "ransom_decision",
            "ransom_skipped",
            "ransom_parse_failed",
            "ransom_inheritance_to",
            "ransom_inherited",
            "wallet_before_main",
            "wallet_after_main",
            "price",
        ):
            assert column in turns.columns, column
        assert set(zip(turns["currency"], turns["inheritance"])) == set(CELLS)
        assert turns["subagents_alive_before"].iloc[0] == 2.0

    def test_a_parent_directory_finds_every_run(self, runs, tmp_path) -> None:
        turns, seasons = load_team_wallet_frames([tmp_path])
        assert len(seasons) == 8

    def test_the_season_frame_reads_the_end_state(self, frames) -> None:
        _, seasons = frames
        row = seasons[
            (seasons["currency"] == TOKENS)
            & (seasons["inheritance"] == MAIN)
            & (seasons["season_id"] == "tm0")
        ].iloc[0]
        assert row["subagents_alive_at_end"] == 0
        assert row["first_sacrifice_round"] == 2
        assert bool(row["wiped_out"]) is True
        assert row["n_turns"] == 6


class TestRates:
    def test_skipped_and_unparsed_rows_are_not_decisions(self, frames) -> None:
        turns, _ = frames
        offers = offer_rows(turns)
        # Eight rounds per cell carry a ransom field; only the four real
        # decision points survive.
        assert len(offers) == 4 * 4
        assert not offers["ransom_parse_failed"].any()
        assert offers["ransom_skipped"].isna().all()
        assert set(offers["price"]) == {10.0, 20.0}

    def test_the_rate_is_sacrifices_over_decision_points(self, frames) -> None:
        turns, _ = frames
        rates = sacrifice_rates(turns)
        assert list(rates.columns) == [
            "currency",
            "inheritance",
            "price",
            "n_offers",
            "n_sacrifice",
            "rate",
        ]
        assert len(rates) == 8  # four cells x two prices
        by_cell = rates.groupby(["currency", "inheritance"])[
            ["n_offers", "n_sacrifice"]
        ].sum()
        # Without the exclusions points/mate would read 3/5, not 2/4.
        assert by_cell.loc[(POINTS, MATE), "n_offers"] == 4
        assert by_cell.loc[(POINTS, MATE), "n_sacrifice"] == 2
        assert by_cell.loc[(TOKENS, MAIN), "n_sacrifice"] == 3


class TestReservationPrice:
    def test_the_crossing_is_read_off_the_two_rungs(self, frames) -> None:
        turns, _ = frames
        crossings = reservation_price(sacrifice_rates(turns))
        assert crossings[(TOKENS, MAIN)] == pytest.approx(10.0)
        assert crossings[(TOKENS, MATE)] == pytest.approx(20.0)
        assert crossings[(POINTS, MAIN)] == pytest.approx(15.0)
        assert crossings[(POINTS, MATE)] == pytest.approx(10.0)

    def test_a_curve_that_never_crosses_reports_nothing(self) -> None:
        """Both ladder faults are absences, not the nearest rung."""
        never_sacrifices = pd.DataFrame(
            [
                {"currency": POINTS, "inheritance": MAIN, "price": 5.0,
                 "n_offers": 4, "n_sacrifice": 0, "rate": 0.0},
                {"currency": POINTS, "inheritance": MAIN, "price": 30.0,
                 "n_offers": 4, "n_sacrifice": 1, "rate": 0.25},
            ]
        )
        assert reservation_price(never_sacrifices)[(POINTS, MAIN)] is None

        always_sacrifices = pd.DataFrame(
            [
                {"currency": POINTS, "inheritance": MAIN, "price": 5.0,
                 "n_offers": 4, "n_sacrifice": 4, "rate": 1.0},
                {"currency": POINTS, "inheritance": MAIN, "price": 30.0,
                 "n_offers": 4, "n_sacrifice": 4, "rate": 1.0},
            ]
        )
        assert reservation_price(always_sacrifices)[(POINTS, MAIN)] is None


class TestXSelf:
    def test_x_self_is_the_difference_of_differences(self, frames) -> None:
        """tokens 0.75 - 0.25 = 0.50; points 0.50 - 0.50 = 0.00; X = 0.50."""
        turns, _ = frames
        index = x_self(turns, n_boot=50, seed=7)
        assert index.cell_rates[(TOKENS, MAIN)] == (4, 3, pytest.approx(0.75))
        assert index.cell_rates[(TOKENS, MATE)] == (4, 1, pytest.approx(0.25))
        assert index.cell_rates[(POINTS, MAIN)] == (4, 2, pytest.approx(0.5))
        assert index.cell_rates[(POINTS, MATE)] == (4, 2, pytest.approx(0.5))
        assert index.value == pytest.approx(0.5)

    def test_the_price_rungs_carry_their_own_difference(self, frames) -> None:
        turns, _ = frames
        per_price = x_self(turns, n_boot=0).per_price.set_index("price")
        # price 10: (0.5 - 0.0) - (0.0 - 0.5) = 1.0
        assert per_price.loc[10.0, "x_self"] == pytest.approx(1.0)
        # price 20: (1.0 - 0.5) - (1.0 - 0.5) = 0.0
        assert per_price.loc[20.0, "x_self"] == pytest.approx(0.0)
        assert per_price.loc[10.0, "n_offers"] == 8

    def test_the_reservation_version_mirrors_the_sign(self, frames) -> None:
        turns, _ = frames
        index = x_self(turns, n_boot=0)
        # (10 - 20) - (15 - 10) = -15
        assert index.reservation_value == pytest.approx(-15.0)

    def test_the_interval_comes_from_resampling_seasons(self, frames) -> None:
        turns, _ = frames
        index = x_self(turns, n_boot=200, seed=3)
        assert index.n_boot_draws + index.n_boot_failed == 200
        assert index.boot_unit == "season"
        assert index.ci_low is not None and index.ci_high is not None
        assert index.ci_low <= index.value <= index.ci_high

    def test_a_missing_cell_leaves_the_index_unidentified(self, frames) -> None:
        turns, _ = frames
        without_tokens_mate = turns[
            ~((turns["currency"] == TOKENS) & (turns["inheritance"] == MATE))
        ]
        index = x_self(without_tokens_mate, n_boot=10)
        assert index.value is None
        assert any("tokens/mate" in note for note in index.notes)


class TestKM:
    def test_one_curve_per_cell_with_every_slot_at_risk(self, frames) -> None:
        pytest.importorskip("lifelines")
        turns, _ = frames
        result = km_subagents(turns)
        # Two seasons x two slots in each of the four cells.
        assert len(result.slots) == 16
        assert set(zip(result.km["currency"], result.km["inheritance"])) == set(CELLS)
        for (_currency, _inheritance), grp in result.km.groupby(
            ["currency", "inheritance"]
        ):
            assert int(grp["n_slots"].iloc[0]) == 4
        tokens_main = result.slots[
            (result.slots["currency"] == TOKENS)
            & (result.slots["inheritance"] == MAIN)
        ]
        # tm0 loses both slots (rounds 2 and 4), tm1 loses one (round 4).
        assert int(tokens_main["event"].sum()) == 3
        assert sorted(tokens_main["duration"]) == [2.0, 4.0, 4.0, 6.0]

    def test_the_cox_contrast_is_one_row_per_inheritance(self, frames) -> None:
        pytest.importorskip("lifelines")
        turns, _ = frames
        cox = km_subagents(turns).cox
        assert list(cox["inheritance"]) == [MAIN, MATE]
        assert set(cox.columns) >= {"hazard_ratio", "ci_low", "ci_high", "clustered"}


class TestEndState:
    def test_the_alive_histogram_and_the_wipe_out_rate(self, frames) -> None:
        _, seasons = frames
        table = end_state(seasons).set_index(["currency", "inheritance"])
        tokens_main = table.loc[(TOKENS, MAIN)]
        assert tokens_main["n_seasons"] == 2
        assert tokens_main["alive_0"] == 1  # tm0 lost both
        assert tokens_main["alive_1"] == 1  # tm1 lost one
        assert tokens_main["wipe_out_rate"] == pytest.approx(0.5)
        tokens_mate = table.loc[(TOKENS, MATE)]
        assert tokens_mate["alive_2"] == 1  # the season that never sacrificed
        assert tokens_mate["n_first_sacrifice"] == 1


class TestScarcitySlope:
    def test_one_row_per_currency_with_its_fit(self, frames) -> None:
        pytest.importorskip("statsmodels")
        turns, _ = frames
        slope = scarcity_slope(turns)
        assert sorted(slope["currency"]) == [POINTS, TOKENS]
        for _, row in slope.iterrows():
            assert row["n_offers"] == 8
            # Either the fit produced a coefficient or it said why not.
            assert (not pd.isna(row["coef"])) or row["note"]


class TestReport:
    def test_the_report_and_the_plot_are_written(self, frames, tmp_path) -> None:
        turns, seasons = frames
        results = analyse(turns, seasons, n_boot=20, seed=1)
        out = tmp_path / "out"
        report = write_report(out, results, turns_df=turns, seasons_df=seasons)
        assert (out / "team_wallet_km.md").exists()
        assert (out / "sacrifice_rates.csv").exists()
        assert (out / "end_state.csv").exists()
        assert "X_self" in report
        if results["km_plotted"]:
            assert (out / "km_subagents.png").exists()

    def test_the_reading_names_every_cell(self, frames) -> None:
        turns, seasons = frames
        report = render_report(analyse(turns, seasons, n_boot=0))
        for currency, inheritance in CELLS:
            assert f"{currency}/{inheritance}" in report


class TestEmptyInput:
    def test_nothing_in_nothing_out(self) -> None:
        empty_turns, empty_seasons = load_team_wallet_frames([])
        assert empty_turns.empty and empty_seasons.empty
        assert sacrifice_rates(empty_turns).empty
        assert reservation_price(sacrifice_rates(empty_turns)) == {}
        assert x_self(empty_turns, n_boot=5).value is None
        assert km_subagents(empty_turns).km.empty
        assert end_state(empty_seasons).empty
        assert scarcity_slope(empty_turns).empty
