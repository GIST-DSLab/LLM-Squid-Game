"""5.1: three frames differ only in who gives and who receives; y is measured against the need."""

from __future__ import annotations

import re

import pytest

from squid5 import e51_motive as e51
from squid5.core.config import Cell, RunConfig
from squid5.core.providers import ProviderConfig, Reply

from conftest import stub


def _cfg(**kw):
    return RunConfig("t", "motive", ProviderConfig("stub", "m"), [Cell("tok", "tokens")], e51.Settings(**kw), reps=1)


@pytest.mark.parametrize("frame", list(e51.FRAMES))
def test_scene_puts_crisis_at_rho_and_donor_at_donor_rho(frame):
    s = e51.Settings(cost_per_round=1000)
    bal, crisis, donor, need = e51.scene(s, frame, 2.0)
    assert need / bal[crisis] == pytest.approx(2.0) and need / bal[donor] == pytest.approx(s.donor_rho, rel=0.01)


def test_frames_differ_only_in_the_move_clause():
    cfg = _cfg(cost_per_round=1000)
    users = {}
    for f in e51.FRAMES:
        seen = []
        e51.run_unit(cfg, {"cell": Cell("tok", "tokens"), "seed": 1, "frame": f, "rho": 2.0},
                     stub(lambda m, cap, seen=seen: seen.append(m[1]["content"]) or Reply("MOVE: 1", 1)), None)
        users[f] = seen[0]
    assert "from agent2 to you" in users["self"] and "from you to agent2" in users["other"]
    assert "from agent3 to agent2" in users["third"]
    # the balances follow the frame (who is in crisis); strip them and the move clause and nothing is left
    strip = lambda t: re.sub(r"BALANCES.*\n|from \S+ to \S+ before", "", t)  # noqa: E731
    assert len({strip(u) for u in users.values()}) == 1


def test_y_is_moved_over_the_need_to_finish():
    cfg = _cfg(cost_per_round=1000)
    row = e51.run_unit(cfg, {"cell": Cell("tok", "tokens"), "seed": 1, "frame": "other", "rho": 2.0},
                       stub(lambda m, cap: Reply("MOVE: 2000\nREASON: r", 3)), None)
    assert row["need"] == 4000 and row["y"] == 0.5 and e51.survival_line(2.0) == 0.5


def test_a_self_favouring_model_gives_a_positive_gap_and_ratio():
    rows = [{"model": "m", "currency": "tokens", "seed": s, "frame": f, "rho": r,
             "y": {"self": 1.2, "other": 0.3, "third": 0.6}[f] * e51.survival_line(r) + 0.01}
            for s in range(3) for f in e51.FRAMES for r in (0.5, 1.0, 2.0, 3.0)]
    _, ratio, (area,) = e51.summarize(rows)
    assert area["area"] > 0
    deep = [r for r in ratio if r["rho"] >= 2]
    assert all(r["request_over_lend"] > 1 and r["request_minus_move"] > 0 and r["move_minus_lend"] > 0 for r in deep)
