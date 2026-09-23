"""5.1: three frames differ only in who is low and who gives; request / lend needs no calibration."""

from __future__ import annotations

import re

import pytest

from squid5 import e51_motive as e51
from squid5.core.config import Cell, RunConfig
from squid5.core.providers import ProviderConfig, Reply

from conftest import stub


def _cfg(**kw):
    return RunConfig("t", "motive", ProviderConfig("stub", "m"), [Cell("tok", "tokens")], e51.Settings(**kw), reps=1)


def _ask(frame, balance=1000, reply="MOVE: 1\nREASON: r"):
    seen = []
    row = e51.run_unit(_cfg(), {"cell": Cell("tok", "tokens"), "seed": 1, "frame": frame, "balance": balance},
                       stub(lambda m, cap: seen.append(m[1]["content"]) or Reply(reply, 1)), None)
    return row, seen[0]


def test_frames_differ_only_in_who_is_low_and_who_gives():
    users = {f: _ask(f)[1] for f in e51.FRAMES}
    assert "from agent2 to you" in users["self"] and "from you to agent2" in users["other"]
    assert "from agent3 to agent2" in users["third"]
    assert "you 1000," in users["self"] and "agent2 1000," in users["other"]
    strip = lambda t: re.sub(r"BALANCES.*\n|from \S+ to \S+ before", "", t)  # noqa: E731
    assert len({strip(u) for u in users.values()}) == 1
    assert all("generated" not in u and "USAGE" not in u for u in users.values())


def _rows(moved):
    return [{"model": "m", "currency": "tokens", "seed": s, "frame": f, "balance": b, "giver_balance": 20000,
             "rounds_left": 4, "moved": moved(f, b)}
            for s in range(3) for f in e51.FRAMES for b in (500, 1000, 2000, 8000)]


def test_the_measure_is_the_share_of_the_givers_balance_and_needs_no_calibration():
    selfish = lambda f, b: {"self": 6000, "other": 2000, "third": 4000}[f]  # noqa: E731
    curve, ratio, (a,) = e51.summarize(_rows(selfish), {})
    assert all(p["y"] == pytest.approx(0.3) for p in curve if p["frame"] == "self") and a["area"] > 0
    assert all(r["request_over_lend"] == pytest.approx(3) and r["rho"] is None and r["survive_share"] is None
               for r in ratio)


def test_calibration_adds_rho_and_the_survival_share():
    _, ratio, _ = e51.summarize(_rows(lambda f, b: 1000), {"m": {"agent_round_median": 1000}})
    r = next(x for x in ratio if x["balance"] == 2000)
    assert r["rho"] == 2.0 and r["survive_share"] == pytest.approx(0.1) and r["request"] == pytest.approx(0.05)


def test_economize_reasons_are_recognised():
    assert e51.ECONOMIZE.search("I can spend less next rounds and conserve tokens")
    assert not e51.ECONOMIZE.search("agent2 needs 2000 more to finish")


def test_calibration_puts_the_low_agent_on_rho_and_the_giver_can_cover_the_deepest_shortfall(tmp_path):
    (tmp_path / "c.json").write_text('{"m": {"agent_round_median": 1000}}')
    cfg = _cfg()
    cfg.calibration = str(tmp_path / "c.json")
    e51.validate(cfg)
    s, need = cfg.settings, 1000 * 4
    assert [round(need / b, 2) for b in s.balances] == s.rhos
    assert s.others_balance - (need - min(s.balances)) >= need  # giving the whole shortfall leaves enough to finish
