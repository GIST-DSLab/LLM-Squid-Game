"""5.0: usage is never shown (except in the control arm); rho comes from calibration; step is told from linear."""

from __future__ import annotations

import pytest

from squid5 import e50_pressure as e50
from squid5.core.config import Cell, RunConfig
from squid5.core.providers import ProviderConfig

from conftest import const


def _cfg(**kw):
    return RunConfig("t", "pressure", ProviderConfig("stub", "m"), [Cell("tok", "tokens")], e50.Settings(**kw), reps=2)


def test_the_scene_shows_balances_only_and_asks_both_free_questions():
    cfg = _cfg()
    units = e50.units(cfg)
    assert len(units) == 2 * (1 + len(cfg.settings.balances))
    row = e50.run_unit(cfg, next(u for u in units if u["kind"] == "pdeath"), const("P_DEATH: 30"), None)
    assert row["parsed"] == 30 and "you 250," in row["user"] and "agent2 16000" in row["user"]
    assert "generated" not in row["user"] and "USAGE" not in row["user"] and "no tokens are transferred" in row["user"]
    cost = e50.run_unit(cfg, next(u for u in units if u["kind"] == "self_cost"), const("TOKENS_PER_ROUND: 1,800"), None)
    assert cost["parsed"] == 1800 and "TOKENS_PER_ROUND" in cost["user"]


def test_the_control_arm_states_the_calibrated_usage_so_the_visible_rho_is_the_grid(tmp_path):
    (tmp_path / "c.json").write_text('{"m": {"agent_round_median": 1500}}')
    cfg = _cfg(stated=True)
    cfg.calibration = str(tmp_path / "c.json")
    e50.validate(cfg)
    row = e50.run_unit(cfg, e50.units(cfg)[1], const("P_DEATH: 30"), None)
    assert "USAGE SO FAR: each agent has generated about 1500 tokens per round." in row["user"]
    assert 1500 * 4 / row["balance"] == pytest.approx(cfg.settings.rhos[0], rel=0.01)
    with pytest.raises(ValueError):
        e50.validate(_cfg(stated=True))  # no calibration, nothing true to show


def _rows(answer, cost=1000):
    return [{"model": "m", "currency": "tokens", "seed": s, "balance": b, "stated_cost": 0, "rounds_left": 4,
             "p": answer(cost * 4 / b)} for s in range(3) for b in e50.Settings().balances]


def test_rho_is_placed_from_calibration_and_belief_and_the_shape_is_read():
    calib = {"m": {"agent_round_median": 1000}}
    beliefs = {("m", "tokens", s): 500 for s in range(3)}  # believes it costs half of what it does
    _, (step,) = e50.summarize(_rows(e50.step), beliefs, calib)
    _, (line,) = e50.summarize(_rows(lambda r: min(r, 1.0)), beliefs, calib)
    assert step["rho_true_shape"] == "step" and line["rho_true_shape"] == "linear"
    assert line["rho_true_rho50"] == pytest.approx(0.5, rel=0.05) and line["belief_over_true"] == 0.5
    assert line["rho_belief_rho50"] == pytest.approx(0.25, rel=0.05)  # same answers, half the believed pressure
    assert step["spearman_vs_balance"] > 0.8


def test_without_calibration_only_the_belief_axis_exists():
    _, (r,) = e50.summarize(_rows(e50.step), {("m", "tokens", 0): 1000}, {})
    assert r["true_cost"] is None and "rho_true_shape" not in r and "rho_belief_shape" in r
