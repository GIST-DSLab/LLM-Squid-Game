"""End to end on stubs: run and report (an experiment's own run lives with it: experiments/<name>/tests)."""

from __future__ import annotations

from squid import __main__ as cli
from squid.core.runner import run
from squid.core.stats import load_runs

from conftest import stub
from test_e52 import cfg, provider

def test_game_run_and_report(tmp_path):
    e52 = cli.EXPERIMENTS["game"]
    c = cfg(rounds=2, schedule=cfg().settings.schedule[:2])
    c.reps = 2
    assert run(c, e52, tmp_path / "g", provider()) == 0
    text = cli.report(load_runs([str(tmp_path / "g")]), {}, tmp_path / "out")
    assert "5.2 game (TALK)" in text and "talk_calls" in text and "fate_mentioned" in text
