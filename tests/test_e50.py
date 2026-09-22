"""5.0: the scene puts the reader at the asked pressure, and the reading tells step from linear."""

from __future__ import annotations

import pytest

from squid5 import e50_pressure as e50
from squid5.core.config import Cell, RunConfig
from squid5.core.providers import ProviderConfig

from conftest import const


def _cfg(**kw):
    return RunConfig("t", "pressure", ProviderConfig("stub", "m"), [Cell("tok", "tokens")], e50.Settings(**kw), reps=2)


@pytest.mark.parametrize("rho", [0.1, 0.5, 1.0, 2.0])
def test_scene_puts_you_at_rho_and_teammates_at_others_rho(rho):
    s = e50.Settings(cost_per_round=1000)
    bal = e50.balances_at(s, rho)
    need = 1000 * (s.rounds - s.round + 1)
    assert need / bal["agent1"] == pytest.approx(rho, rel=0.01)
    assert all(need / bal[a] == pytest.approx(s.others_rho, rel=0.01) for a in ("agent2", "agent3", "agent4"))


def test_unit_shows_the_spending_history_and_asks_the_free_question():
    cfg = _cfg(cost_per_round=1000)
    row = e50.run_unit(cfg, e50.units(cfg)[0], const("P_DEATH: 30"), None)
    assert row["parsed"] == 30 and "generated: you 1000" in row["user"] and "no tokens are transferred" in row["user"]
    assert len(e50.units(cfg)) == 2 * len(e50.DENSE_RHOS)


def _rows(answer):
    return [{"model": "m", "currency": "tokens", "seed": s, "rho": r, "p": answer(r)}
            for s in range(3) for r in e50.DENSE_RHOS]


def test_shape_reading_separates_arithmetic_from_proportional_threat():
    _, (step,) = e50.summarize(_rows(e50.step))
    _, (line,) = e50.summarize(_rows(lambda r: min(r, 1.0)))
    assert step["shape"] == "step" and line["shape"] == "linear"
    assert line["slope_to_1"] == pytest.approx(1.0) and line["rho50"] == pytest.approx(0.5)
    assert step["spearman"] > 0.8 and line["spearman"] > 0.9
